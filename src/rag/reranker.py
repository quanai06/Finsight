"""Cross-encoder reranking via FastEmbed (ONNX, CPU).

Vector search is fast but approximate — it ranks by embedding similarity alone.
A cross-encoder reads the (query, passage) pair *together* and scores true
relevance, which meaningfully sharpens the top results. We over-fetch candidates
from Qdrant, then rerank and keep the best few.

Default model: ``jinaai/jina-reranker-v2-base-multilingual`` (handles Vietnamese).
"""

from __future__ import annotations

from fastembed.rerank.cross_encoder import TextCrossEncoder


class Reranker:
    def __init__(
        self, model_name: str = "jinaai/jina-reranker-v2-base-multilingual"
    ) -> None:
        self.model_name = model_name
        self._model = TextCrossEncoder(model_name=model_name)

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Return a relevance score per document, aligned with ``documents``."""
        if not documents:
            return []
        return list(self._model.rerank(query, documents))

    def top_indices(self, query: str, documents: list[str], k: int) -> list[int]:
        """Indices of the ``k`` highest-scoring documents, best first."""
        scores = self.rerank(query, documents)
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return order[:k]
