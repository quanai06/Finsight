"""Shared singletons wired once and injected into routes."""

from __future__ import annotations

from functools import lru_cache

from src.rag import GroqClient, RAGPipeline

from .config import get_settings
from .storage import SessionStore


@lru_cache(maxsize=1)
def get_store() -> SessionStore:
    return SessionStore(get_settings().sessions_dir)


@lru_cache(maxsize=1)
def get_pipeline() -> RAGPipeline:
    settings = get_settings()
    llm = GroqClient(settings.groq_api_key, model=settings.groq_model)
    return RAGPipeline(llm, top_k=settings.top_k)
