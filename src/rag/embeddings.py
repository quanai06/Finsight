"""Dense text embeddings via FastEmbed (ONNX, CPU — no PyTorch, no GPU).

Default model: ``intfloat/multilingual-e5-large`` (1024-dim, strong multilingual
including Vietnamese). E5 models are trained with instruction prefixes and expect
``"query: …"`` for queries and ``"passage: …"`` for indexed text — applying them
is what makes asymmetric retrieval work, so the embedder owns that detail and
exposes two explicit methods.
"""

from __future__ import annotations

from collections.abc import Iterable

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

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        prepared = self._prefix(texts, "passage")
        return [vec.tolist() for vec in self._model.embed(prepared)]

    def embed_query(self, text: str) -> list[float]:
        prepared = self._prefix([text], "query")
        return next(iter(self._model.embed(prepared))).tolist()
