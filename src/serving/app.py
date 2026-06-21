"""FastAPI application factory and entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .deps import get_db, get_memory, get_vectorstore
from .routes import chat, documents, sessions

logger = logging.getLogger("finsight")
settings = get_settings()

app = FastAPI(
    title="Finsight API",
    version="0.2.0",
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
def _startup() -> None:
    # create Postgres tables + the Qdrant collection up front so the first
    # request doesn't pay for schema setup (models still load lazily on first use)
    get_db().create_all()
    try:
        get_vectorstore()
    except Exception as exc:  # noqa: BLE001 - surfaced via /api/health
        logger.warning("Qdrant not ready at startup: %s", exc)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    qdrant_ok = True
    try:
        get_vectorstore().client.get_collections()
    except Exception:  # noqa: BLE001
        qdrant_ok = False
    return {
        "status": "ok",
        "llm_configured": bool(settings.groq_api_key),
        "model": settings.groq_model,
        "embed_model": settings.embed_model,
        "rerank_model": settings.rerank_model if settings.use_reranker else None,
        "qdrant": qdrant_ok,
        "redis": get_memory().ping(),
    }
