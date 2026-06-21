# Finsight

Upload financial documents into a **session**, then ask questions answered with
citations grounded in those documents (RAG). The flow mirrors the OCR → RAG
pipeline, but runs **CPU-only** so no GPU is required:

- Upload **PDF**, **Markdown (.md)** or **JSON** documents.
  - `.md` / `.json` are indexed directly (the fast path while there's no GPU).
  - `.pdf` uses its embedded text layer; scanned PDFs fall back to OCR if available.
- Retrieval is **TF-IDF** (scikit-learn — no model weights to download).
- Generation is **Groq** (`llama-3.3-70b-versatile`).
- Everything is persisted to disk per session: uploads, the index, and chat
  history all survive a restart (`data/sessions/<id>/`).

## Architecture

```
frontend (React + Vite)  ──HTTP──>  backend (FastAPI)
                                       ├─ src/serving   sessions, uploads, chat API
                                       └─ src/rag       chunking, TF-IDF index, Groq LLM
```

## 1. Configure

The Groq API key lives in `.env` (git-ignored). Copy the example and fill it in:

```bash
cp .env.example .env       # then set GROQ_API_KEY
```

## 2. Backend

```bash
pip install -r requirements.txt
uvicorn src.serving.app:app --reload --port 8000
```

API docs: http://localhost:8000/docs · health: http://localhost:8000/api/health

## 3. Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 (proxies /api to :8000)
```

Open http://localhost:5173 — create a session on the home page, click it to open
the session page, upload documents, and chat.

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
