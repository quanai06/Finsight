"""Dense + sparse text embeddings via FastEmbed (ONNX, CPU — no PyTorch, no GPU).

Two complementary signals power hybrid retrieval:

  * **Dense** (``intfloat/multilingual-e5-large``, 1024-dim) captures *meaning*,
    so an English question retrieves a Vietnamese passage without sharing words.
    E5 expects instruction prefixes — ``"query: …"`` / ``"passage: …"`` — which is
    what makes asymmetric retrieval work, so the embedder owns that detail.
  * **Sparse** (``Qdrant/bm25``) captures *exact lexical* matches — figures
    ("5.538.327"), codes, years — which dense vectors blur. BM25 is statistical
    (no neural weights, ~0 RAM) and language-agnostic, so it works on Vietnamese.
    Qdrant applies the IDF term at query time (see ``VectorStore``).

The two are fused with Reciprocal Rank Fusion in the vector store.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass


@dataclass(slots=True)
class SparseVec:
    """A sparse embedding as plain Python lists, ready for Qdrant."""

    indices: list[int]
    values: list[float]


class Embedder:
    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-large",
        *,
        sparse_model_name: str = "Qdrant/bm25",
        enable_sparse: bool = True,
        threads: int | None = None,
        batch_size: int = 16,
    ) -> None:
        from fastembed import TextEmbedding

        self.model_name = model_name
        self.sparse_model_name = sparse_model_name if enable_sparse else None
        self.batch_size = batch_size
        # threads=None lets onnxruntime pick (measured fastest here; forcing the
        # logical-core count oversubscribed and was slower). Exposed for tuning.
        kw = {"threads": threads} if threads else {}
        self._model = TextEmbedding(model_name=model_name, **kw)
        self._is_e5 = "e5" in model_name.lower()
        self._sparse = None
        if enable_sparse:
            from fastembed import SparseTextEmbedding

            self._sparse = SparseTextEmbedding(model_name=sparse_model_name, **kw)

    @property
    def has_sparse(self) -> bool:
        return self._sparse is not None

    # ----------------------------------------------------------------- dense
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
        # Smaller batch -> FastEmbed yields more often (granular progress, lower
        # peak RAM); larger -> marginally more throughput. Configurable.
        for vec in self._model.embed(prepared, batch_size=self.batch_size):
            yield vec.tolist()

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return list(self.embed_passages_iter(texts))

    def embed_query(self, text: str) -> list[float]:
        prepared = self._prefix([text], "query")
        return next(iter(self._model.embed(prepared))).tolist()

    # ---------------------------------------------------------------- sparse
    def embed_sparse_passages_iter(self, texts: list[str]) -> Iterator[SparseVec]:
        """Yield one BM25 sparse vector per passage, aligned with ``texts``."""
        if not texts or self._sparse is None:
            return
        for emb in self._sparse.embed(texts, batch_size=self.batch_size):
            yield SparseVec(emb.indices.tolist(), emb.values.tolist())

    def embed_sparse_query(self, text: str) -> SparseVec | None:
        """BM25 query weights (term-presence; IDF is applied by Qdrant)."""
        if self._sparse is None:
            return None
        emb = next(iter(self._sparse.query_embed(text)))
        return SparseVec(emb.indices.tolist(), emb.values.tolist())
