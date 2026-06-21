# Finsight — RAG Phase: How It Was Built

This document records what was built in the **session → upload → RAG chat** phase
of Finsight, the design decisions behind it, and how to run and extend it.

The stack is **CPU-only** — the embedding and reranking models run as ONNX via
FastEmbed (no PyTorch, no GPU), and generation is offloaded to a hosted LLM
(Groq). State is split across three services run with Docker: **Postgres**
(metadata + durable chat), **Qdrant** (vectors), and **Redis** (short-term memory).

---

## 1. What the phase delivers

A working end-to-end product on top of the existing OCR pipeline:

- **Home page** — create a session, see all sessions.
- **Session page** — upload documents (**PDF / Markdown / JSON**) and chat with
  them. Answers are **grounded** in the uploaded documents and show **citations**.
- **Persistence** — sessions, documents, and the full chat history live in
  Postgres; chunk vectors in Qdrant; original uploads + normalized Markdown on
  disk. Nothing is lost on restart.

```
                ┌────────────────────────┐         ┌──────────────────────────────┐
                │  Frontend (React/Vite)  │  HTTP   │       Backend (FastAPI)       │
   browser ───▶ │  Home → Session page    │ ──────▶ │  src/serving  (REST API)      │
                │  /api/* via Vite proxy  │         │  src/rag      (RAG engine)    │
                └────────────────────────┘         └───────────────┬──────────────┘
                                                                     │
                       ┌──────────────┬──────────────┬──────────────┼──────────────┐
                       ▼              ▼              ▼              ▼              ▼
                   Postgres        Qdrant         Redis      disk (uploads/    Groq LLM
                (sessions, docs,  (chunk         (recent      processed md)   llama-3.3-70b
                 chat history)    vectors)        turns)                       -versatile)
```

---

## 2. The flow, step by step

### Create a session
`POST /api/sessions` → a `SessionRow` is inserted in Postgres. Disk folders and
Qdrant points are created lazily as documents arrive.

### Upload a document
`POST /api/sessions/{id}/documents` (multipart). On upload the backend:

1. Saves the original file under `data/sessions/<id>/uploads/` (`src/serving/files.py`).
2. **Ingests** it to normalized Markdown (`src/serving/ingest.py`):
   - `.md` → used as-is (fast path).
   - `.json` → rendered to readable Markdown (nested keys + flat lists become tables).
   - `.pdf` → embedded text layer via PyMuPDF; a scanned PDF falls back to the
     project's OCR pipeline if available, otherwise the document is flagged.
3. **Chunks** the Markdown into structure-aware pieces (`src/rag/chunking.py`) —
   page/heading aware, tables kept intact with repeated headers.
4. **Embeds** the chunks (`intfloat/multilingual-e5-large`, FastEmbed/ONNX) and
   **upserts** them into the shared Qdrant collection with a `session_id` payload
   (`src/rag/vectorstore.py`).
5. Records the document's status (`ready` / `failed`), chunk count, and char count
   in Postgres.

### Ask a question
`POST /api/sessions/{id}/chat`:

1. **Recent turns** are pulled from Redis (the short-term window); on a cache miss
   the window is primed from the durable Postgres history.
2. **Retrieve** — the question is embedded and Qdrant returns the top-N candidates
   filtered to this `session_id`.
3. **Rerank** — a cross-encoder (`jina-reranker-v2-base-multilingual`) reads each
   (question, chunk) pair together and keeps the best top-K.
4. **Generate** — the chunks become numbered context `[1]…[K]`; the LLM is told to
   answer **only** from that context and cite the brackets it used.
5. The user + assistant turns are written to **both** Postgres (durable) and Redis
   (working window).
6. The response returns the answer + citations (doc name, page, score, snippet).

---

## 3. Key design decisions

| Decision | Why |
| --- | --- |
| **Dense multilingual embeddings** (`multilingual-e5-large`, FastEmbed/ONNX) | Semantic retrieval that works **across languages** — an English question retrieves over Vietnamese reports without keyword overlap. ONNX runtime keeps it CPU-only (no PyTorch, no GPU). E5 instruction prefixes (`query:` / `passage:`) make asymmetric retrieval work. |
| **Cross-encoder reranker** (`jina-reranker-v2-base-multilingual`) | Vector search ranks by embedding similarity alone; the reranker reads the pair together and sharpens the top results. Over-fetch N candidates, rerank, keep K. Toggleable via `FINSIGHT_USE_RERANKER`. |
| **Qdrant, one shared collection** | All sessions share one collection; each point carries a `session_id` payload and queries filter on it (keyword-indexed for speed). Sessions stay isolated while the index is managed in one place. |
| **Groq for generation** | Hosted LLM = no local GPU. Called over plain `httpx` (no extra SDK). Default `llama-3.3-70b-versatile`. |
| **Postgres for metadata + chat** | Durable, queryable source of truth for sessions / documents / chat. SQLAlchemy 2.0 ORM with cascade deletes; the `Database` class exposes task-oriented methods so routes stay thin. |
| **Redis for short-term memory** | A bounded, TTL'd sliding window of recent turns fed back into the prompt so follow-ups ("and for 2024?") stay coherent. Best-effort: if Redis is down, chat falls back to Postgres history. |
| **Disk for blobs** | Binary uploads and extracted Markdown don't belong in Postgres — they live under `data/sessions/<id>/`. |
| **Accept PDF + MD + JSON** | MD/JSON (e.g. OCR exports) are the fast path; PDFs with a text layer work instantly via PyMuPDF. |

---

## 4. Why dense retrieval (the cross-language win)

The earlier prototype used **TF-IDF**, which is purely lexical. After uploading
Vietnamese reports, an **English** question (`"revenue"`) returned *"I couldn't
find anything relevant…"* — the word "revenue" never appears in the documents, so
there was zero term overlap. The workaround was LLM **query expansion** into
document-language keywords.

Dense multilingual embeddings remove the need for that hack entirely: `"revenue"`
and `"doanh thu"` map to nearby vectors, so the English question retrieves the
Vietnamese passage directly. The reranker then orders the survivors by true
relevance. Query expansion is gone from the pipeline.

> Practical tip: mixing many years in one session still makes retrieval harder —
> name the year in the question, or use one session per year/report.

---

## 5. File map

```
src/rag/
  chunking.py     structure-aware Markdown → page/heading-tagged chunks (tables kept intact)
  embeddings.py   Embedder: multilingual-e5-large via FastEmbed (ONNX, CPU); E5 query/passage prefixes
  vectorstore.py  VectorStore: Qdrant collection, per-session filter, add/search/delete
  reranker.py     Reranker: jina cross-encoder via FastEmbed (ONNX, CPU)
  llm.py          GroqClient: minimal chat-completions over httpx
  pipeline.py     RAGPipeline: dense retrieve → rerank → grounded answer + citations

src/serving/
  config.py       settings + .env loader (Groq, DB/Qdrant/Redis URLs, embed/rerank, top_k, limits)
  schemas.py      Pydantic request/response models (the API contract)
  db.py           Database + ORM rows: sessions / documents / chat_messages (Postgres)
  files.py        FileStore: original uploads + normalized Markdown on disk
  memory.py       ShortTermMemory: Redis sliding window of recent turns
  ingest.py       pdf/md/json → normalized Markdown
  deps.py         shared singletons (db, files, embedder, vectorstore, reranker, memory, pipeline)
  app.py          FastAPI app, CORS, router wiring, /api/health
  routes/         sessions.py · documents.py · chat.py

scripts/
  migrate_to_postgres.py   one-off: re-create old file-based sessions in Postgres + Qdrant

docker/
  docker-compose.yml       Postgres + Qdrant + Redis (named volumes)

frontend/
  src/api.js              tiny fetch client for /api
  src/App.jsx             app shell (top bar)
  src/pages/HomePage.jsx        create + list sessions
  src/pages/SessionPage.jsx     upload + chat layout
  src/components/DocumentPanel.jsx   drag/drop upload + document list
  src/components/ChatPanel.jsx       conversation + expandable citations
  src/styles.css          flat neutral theme (no gradients, single accent, English)
```

---

## 6. API surface

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/sessions` | Create a session |
| `GET` | `/api/sessions` | List sessions |
| `GET` | `/api/sessions/{id}` | Session detail (+ documents) |
| `DELETE` | `/api/sessions/{id}` | Delete a session (Postgres + Qdrant + disk + Redis) |
| `POST` | `/api/sessions/{id}/documents` | Upload a PDF/MD/JSON document |
| `GET` | `/api/sessions/{id}/documents` | List documents |
| `DELETE` | `/api/sessions/{id}/documents/{doc_id}` | Remove a document |
| `POST` | `/api/sessions/{id}/chat` | Ask a question (RAG) |
| `GET` | `/api/sessions/{id}/chat` | Chat history |
| `GET` | `/api/health` | Health + LLM/embed/rerank/Qdrant/Redis status |

---

## 7. Run it

```bash
# 1. Infrastructure — Postgres + Qdrant + Redis
docker compose -f docker/docker-compose.yml up -d

# 2. Config — put your Groq key in .env (git-ignored)
cp .env.example .env        # then set GROQ_API_KEY

# 3. Backend
pip install -r requirements.txt
uvicorn src.serving.app:app --reload --port 8000
# first request downloads the embed + rerank models (~3.3 GB, one time)

# 4. Frontend
cd frontend && npm install && npm run dev    # http://localhost:5173
```

The Vite dev server proxies `/api` to `http://localhost:8000`, so the frontend
uses same-origin relative URLs (no CORS friction in development).

Migrating an older file-based prototype? `python scripts/migrate_to_postgres.py`
re-creates those sessions in Postgres and re-embeds their uploads into Qdrant.

---

## 8. Where to take it next

- **Hybrid retrieval** — fuse dense search with BM25 / Qdrant sparse vectors for
  exact-match recall on tickers, codes, and account names.
- **Per-document / per-year filtering** in a session to avoid cross-year mixups
  (the Qdrant payload already carries `doc_id`).
- **Streaming answers** (Server-Sent Events) for a faster-feeling chat.
- **Background ingestion** for large PDFs so uploads return immediately and the UI
  polls for `ready` status.
- **GPU embeddings** — swap the FastEmbed model for a larger one once a GPU is
  available; only `src/rag/embeddings.py` changes, the API and frontend stay the same.
```
