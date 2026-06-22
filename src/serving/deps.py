"""Shared singletons wired once and injected into routes.

Heavy objects (ONNX models, DB engine, Qdrant/Redis clients) are built lazily
and cached so the first request pays the cost and the rest are free.
"""

from __future__ import annotations

from functools import lru_cache

from src.rag import Embedder, GroqClient, RAGPipeline, Reranker, VectorStore

from .config import get_settings
from .db import Database
from .files import FileStore
from .memory import ShortTermMemory


@lru_cache(maxsize=1)
def get_db() -> Database:
    db = Database(get_settings().database_url)
    db.create_all()
    return db


@lru_cache(maxsize=1)
def get_files() -> FileStore:
    return FileStore(get_settings().sessions_dir)


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    s = get_settings()
    return Embedder(
        s.embed_model,
        sparse_model_name=s.sparse_model,
        enable_sparse=s.use_hybrid,
        threads=s.embed_threads or None,
        batch_size=s.embed_batch,
    )


@lru_cache(maxsize=1)
def get_vectorstore() -> VectorStore:
    s = get_settings()
    return VectorStore(
        get_embedder(), url=s.qdrant_url, collection=s.qdrant_collection, dim=s.embed_dim
    )


@lru_cache(maxsize=1)
def get_reranker() -> Reranker | None:
    s = get_settings()
    return Reranker(s.rerank_model) if s.use_reranker else None


@lru_cache(maxsize=1)
def get_memory() -> ShortTermMemory:
    s = get_settings()
    return ShortTermMemory(s.redis_url, window=s.memory_window, ttl=s.memory_ttl)


@lru_cache(maxsize=1)
def get_pipeline() -> RAGPipeline:
    s = get_settings()
    return RAGPipeline(
        GroqClient(s.groq_api_key, model=s.groq_model),
        get_vectorstore(),
        reranker=get_reranker(),
        top_k=s.top_k,
        candidates=s.retrieve_candidates,
        mmr_lambda=s.mmr_lambda,
        score_threshold=s.score_threshold,
        use_routing=s.use_routing,
        use_graph=s.use_graph,
    )
