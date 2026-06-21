"""Retrieval-Augmented Generation layer for Finsight.

A deliberately lightweight, CPU-only RAG stack so the app runs without a GPU:

    documents (md / json / pdf-ocr)  ->  chunking  ->  TF-IDF index  ->  retriever
                                                                            |
                              question  ->  retrieve top-k chunks  ->  Groq LLM  ->  answer

The retriever is swappable: ``SessionIndex`` only needs ``add`` / ``search`` /
``save`` / ``load``. Today it is TF-IDF (scikit-learn, no model download); drop
in sentence-transformers later without touching the serving layer.
"""

from .chunking import Chunk, chunk_markdown
from .index import SessionIndex
from .llm import GroqClient, LLMError
from .pipeline import RAGPipeline, RetrievedChunk

__all__ = [
    "Chunk",
    "chunk_markdown",
    "SessionIndex",
    "GroqClient",
    "LLMError",
    "RAGPipeline",
    "RetrievedChunk",
]
