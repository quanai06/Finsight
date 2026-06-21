"""FastAPI application factory and entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .deps import get_store
from .routes import chat, documents, sessions

settings = get_settings()

app = FastAPI(
    title="Finsight API",
    version="0.1.0",
    description="Sessions, document ingestion, and RAG chat over financial documents.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(documents.router)
app.include_router(chat.router)


@app.on_event("startup")
def _ensure_store() -> None:
    # touch the store so the sessions directory exists before the first request
    get_store()


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {
        "status": "ok",
        "llm_configured": bool(settings.groq_api_key),
        "model": settings.groq_model,
    }
