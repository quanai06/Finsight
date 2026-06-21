"""Dense text embeddings via FastEmbed (ONNX, CPU — no PyTorch, no GPU).

Default model: ``intfloat/multilingual-e5-large`` (1024-dim, strong multilingual
including Vietnamese). E5 models are trained with instruction prefixes and expect
``"query: …"`` for queries and ``"passage: …"`` for indexed text — applying them
is what makes asymmetric retrieval work, so the embedder owns that detail and
exposes two explicit methods.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from fastembed import TextEmbedding


class Embedder:
    def __init__(self, model_name: str = "intfloat/multilingual-e5-large") -> None:
        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name)
        self._is_e5 = "e5" in model_name.lower()

    def _prefix(self, texts: Iterable[str], kind: str) -> list[str]:
        if not self._is_e5:
            return list(texts)
        return [f"{kind}: {t}" for t in texts]

    def embed_passages_iter(self, texts: list[str]) -> Iterator[list[float]]:
        """Yield one passage vector at a time so callers can report progress and
        keep only a small batch in memory instead of all vectors at once."""
        if not texts:
            return
        prepared = self._prefix(texts, "passage")
        # Small batch -> FastEmbed yields more often, so progress updates are
        # granular (not one big jump) and peak RAM stays low.
        for vec in self._model.embed(prepared, batch_size=16):
            yield vec.tolist()

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return list(self.embed_passages_iter(texts))

    def embed_query(self, text: str) -> list[float]:
        prepared = self._prefix([text], "query")
        return next(iter(self._model.embed(prepared))).tolist()
