"""Retrieval-Augmented Generation layer for Finsight.

A multilingual, CPU-only RAG stack (no GPU required):

    documents ─chunk→ embed dense+sparse (FastEmbed/ONNX) ─→ Qdrant vector store
                                                                    │
        question ─embed→ hybrid search (dense+BM25, RRF) ─→ dedup+MMR ─→ Groq LLM

Retrieval is hybrid: dense vectors for meaning + BM25 sparse for exact figures/
codes, fused with Reciprocal Rank Fusion. A cross-encoder reranker is optional
(off by default — MMR recovers most of its benefit far more cheaply on CPU).
Components are swappable behind small classes: ``Embedder``, ``VectorStore``,
``Reranker``, ``GroqClient``, composed by ``RAGPipeline``.
"""

from .chunking import Chunk, chunk_markdown
from .embeddings import Embedder
from .llm import GroqClient, LLMError
from .pipeline import RAGPipeline, RetrievedChunk
from .reranker import Reranker
from .vectorstore import Hit, VectorStore

__all__ = [
    "Chunk",
    "chunk_markdown",
    "Embedder",
    "VectorStore",
    "Hit",
    "Reranker",
    "GroqClient",
    "LLMError",
    "RAGPipeline",
    "RetrievedChunk",
]
