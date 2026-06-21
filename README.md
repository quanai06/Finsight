# Finsight

Upload financial documents into a **session**, then ask questions answered with
citations grounded in those documents (RAG). Runs **CPU-only** — no GPU required.

- Upload **PDF**, **Markdown (.md)** or **JSON** documents.
  - `.md` / `.json` are indexed directly; `.json` table exports render to clean Markdown tables.
  - `.pdf` uses its embedded text layer; scanned PDFs fall back to OCR if available.
- **Retrieval:** multilingual dense embeddings (`multilingual-e5-large`, FastEmbed/ONNX,
  CPU) in **Qdrant**, then a **cross-encoder reranker** (`jina-reranker-v2-multilingual`).
- **Generation:** **Groq** (`llama-3.3-70b-versatile`).
- **State:** **Postgres** (sessions, documents, durable chat history), **Qdrant**
  (vectors), **Redis** (short-term conversational memory).

## Architecture

```
frontend (React + Vite)
        │  HTTP /api
        ▼
backend (FastAPI)  ──  src/serving  (sessions, uploads, chat API)
        │              src/rag       (chunking, embeddings, Qdrant, rerank, Groq)
        ▼
   Postgres        Qdrant        Redis
 (metadata/chat)  (vectors)   (short-term memory)
```

## 1. Infrastructure

```bash
docker compose -f docker/docker-compose.yml up -d   # Postgres + Qdrant + Redis
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

The first request downloads the embedding + reranker models (~3.3 GB, one time).
Health (incl. service status): http://localhost:8000/api/health · Docs: `/docs`

## 4. Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 (proxies /api to :8000)
```

Open http://localhost:5173 — create a session, open it, upload documents, and chat.

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
