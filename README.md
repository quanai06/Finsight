# Finsight

Upload financial documents into a **session**, then ask questions answered with
citations grounded in those documents (RAG). Runs **CPU-only** — no GPU required.

- Upload **PDF**, **Markdown (.md)** or **JSON** documents.
  - `.md` / `.json` are indexed directly; `.json` table exports render to clean Markdown tables.
  - `.pdf` uses its embedded text layer; scanned PDFs fall back to OCR if available.
- **Retrieval:** multilingual dense embeddings (FastEmbed / ONNX, CPU) in **Qdrant**,
  with an optional **cross-encoder reranker** — so an English question retrieves over
  Vietnamese reports.
- **Generation:** **Groq** (`llama-3.3-70b-versatile`), called over plain `httpx`.
- **State:** **Postgres** (sessions, documents, durable chat history), **Qdrant**
  (vectors), **Redis** (short-term conversational memory), disk (original uploads +
  normalized Markdown).

> A full Vietnamese architecture/stack write-up lives in [`log_structure.md`](log_structure.md).

## Architecture

```
frontend (React + Vite)
        │  HTTP /api
        ▼
backend (FastAPI)  ──  src/serving  (sessions, uploads, chat API)
        │              src/rag       (chunking, embeddings, Qdrant, rerank, Groq)
        ▼
   Postgres        Qdrant        Redis        disk
 (metadata/chat)  (vectors)   (short-term)  (uploads/processed)
```

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | React + Vite |
| Backend | FastAPI + Uvicorn |
| Embeddings | FastEmbed (ONNX, CPU) — multilingual |
| Vector DB | Qdrant |
| Reranker | FastEmbed cross-encoder (optional) |
| Generation | Groq (`llama-3.3-70b-versatile`) |
| Relational store | Postgres + SQLAlchemy 2.0 |
| Short-term memory | Redis |
| Infra | Docker Compose |

## 1. Infrastructure

```bash
docker compose up -d   # Postgres + Qdrant + Redis
```

## 2. Configure

```bash
cp .env.example .env        # then set GROQ_API_KEY
```

## 3. Backend

```bash
pip install -r requirements.txt
uvicorn src.serving.app:app --reload --port 8000
```

The first request downloads the embedding model (and the reranker, if enabled) —
one time. Health (incl. service status): http://localhost:8000/api/health · Docs: `/docs`

## 4. Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 (proxies /api to :8000)
```

Open http://localhost:5173 — create a session, open it, upload documents, and chat.

## Model & memory tuning

Because everything runs CPU-only, the models live in RAM. The defaults favor
quality; you can trade quality for a smaller footprint in `.env`:

| Setting | Quality default | Lighter (low-RAM) |
| --- | --- | --- |
| `FINSIGHT_EMBED_MODEL` | `intfloat/multilingual-e5-large` | `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` |
| `FINSIGHT_EMBED_DIM` | `1024` | `768` |
| `FINSIGHT_USE_RERANKER` | `true` | `false` |

The quality config uses ~3 GB; the lighter one (mpnet 768-dim, reranker off) uses
~1.5 GB. An even smaller embedder is `paraphrase-multilingual-MiniLM-L12-v2` (384-dim).

> Changing the embedding model changes the **vector dimension** — drop and recreate
> the Qdrant collection, then re-index your documents (`scripts/migrate_to_postgres.py`).

## Migrating older file-based sessions

If you used the earlier prototype (JSON files + TF-IDF), re-create those sessions
in Postgres + Qdrant from their original uploads:

```bash
python scripts/migrate_to_postgres.py
```

## API surface

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/sessions` | Create a session |
| `GET` | `/api/sessions` | List sessions |
| `GET` | `/api/sessions/{id}` | Session detail (+ documents) |
| `DELETE` | `/api/sessions/{id}` | Delete a session |
| `POST` | `/api/sessions/{id}/documents` | Upload a PDF/MD/JSON document |
| `GET` | `/api/sessions/{id}/documents` | List documents |
| `DELETE` | `/api/sessions/{id}/documents/{doc_id}` | Remove a document |
| `POST` | `/api/sessions/{id}/chat` | Ask a question (RAG) |
| `GET` | `/api/sessions/{id}/chat` | Chat history |
| `GET` | `/api/health` | Health + service status |
```
