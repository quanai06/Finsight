"""Retrieval-Augmented Generation layer for Finsight.

A multilingual, CPU-only RAG stack (no GPU required):

    documents ─chunk→ embed (bge-class, FastEmbed/ONNX) ─→ Qdrant vector store
                                                                  │
        question ─embed→ search top-N ─→ cross-encoder rerank ─→ top-K ─→ Groq LLM

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
