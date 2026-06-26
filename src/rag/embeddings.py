"""Dense + sparse text embeddings for hybrid retrieval.

Two complementary signals power hybrid retrieval:

  * **Dense** captures *meaning*, so an English question retrieves a Vietnamese
    passage without sharing words. Two backends are available behind one
    interface (pick via ``FINSIGHT_EMBED_BACKEND``):

      - :class:`Embedder` — ``intfloat/multilingual-e5-large`` (1024-dim) run
        locally on CPU via FastEmbed/ONNX (no PyTorch, no GPU). E5 expects
        instruction prefixes — ``"query: …"`` / ``"passage: …"`` — which is what
        makes asymmetric retrieval work, so the embedder owns that detail.
        Correct but slow: dense embedding is ~99% of index time on CPU.
      - :class:`ApiEmbedder` — calls a hosted embedding model over HTTP (the
        Hugging Face Inference API by default, model
        ``AITeamVN/Vietnamese_Embedding`` — a BGE-M3 fine-tune that tops the
        Vietnamese MTEB and needs no word segmentation). Moves the heavy dense
        stage off the CPU, so indexing a report drops from ~11 min to seconds.

  * **Sparse** (``Qdrant/bm25``) captures *exact lexical* matches — figures
    ("5.538.327"), codes, years — which dense vectors blur. BM25 is statistical
    (no neural weights, ~0 RAM) and language-agnostic, so it works on Vietnamese.
    It is cheap (~1s for hundreds of chunks) and so **always runs locally**, for
    both dense backends. Qdrant applies the IDF term at query time.

The two are fused with Reciprocal Rank Fusion in the vector store.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass


class EmbeddingError(RuntimeError):
    """Raised when a remote embedding backend fails after exhausting retries."""


@dataclass(slots=True)
class SparseVec:
    """A sparse embedding as plain Python lists, ready for Qdrant."""

    indices: list[int]
    values: list[float]


class _BM25Sparse:
    """BM25 sparse embeddings via FastEmbed (local, ~0 RAM, language-agnostic).

    Shared by both dense backends: sparse is the lexical half of hybrid retrieval
    that pins exact figures/codes/years, it is cheap, and there is no benefit to
    moving it off the box — so it always runs locally.
    """

    def __init__(
        self, model_name: str, *, threads: int | None = None, batch_size: int = 16
    ) -> None:
        from fastembed import SparseTextEmbedding

        kw = {"threads": threads} if threads else {}
        self.batch_size = batch_size
        self._model = SparseTextEmbedding(model_name=model_name, **kw)

    def passages_iter(self, texts: list[str]) -> Iterator[SparseVec]:
        """Yield one BM25 sparse vector per passage, aligned with ``texts``."""
        if not texts:
            return
        for emb in self._model.embed(texts, batch_size=self.batch_size):
            yield SparseVec(emb.indices.tolist(), emb.values.tolist())

    def query(self, text: str) -> SparseVec:
        """BM25 query weights (term-presence; IDF is applied by Qdrant)."""
        emb = next(iter(self._model.query_embed(text)))
        return SparseVec(emb.indices.tolist(), emb.values.tolist())


class Embedder:
    """Local dense (FastEmbed/ONNX, CPU) + optional BM25 sparse."""

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
        self._sparse = (
            _BM25Sparse(sparse_model_name, threads=threads, batch_size=batch_size)
            if enable_sparse
            else None
        )

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
        if not texts or self._sparse is None:
            return
        yield from self._sparse.passages_iter(texts)

    def embed_sparse_query(self, text: str) -> SparseVec | None:
        return self._sparse.query(text) if self._sparse is not None else None


class ApiEmbedder:
    """Dense embeddings via a hosted HTTP model; BM25 sparse stays local.

    Drop-in replacement for :class:`Embedder` — same public interface, so the
    vector store and pipeline don't change. The default endpoint is the Hugging
    Face Inference API ``feature-extraction`` pipeline; point ``endpoint`` at a
    dedicated Inference Endpoint or a self-hosted TEI server with the same shape
    to scale up. The model is symmetric (no ``query:``/``passage:`` prefixes).
    """

    _HF_ROUTER = "https://router.huggingface.co/hf-inference/models/{model}/pipeline/feature-extraction"

    def __init__(
        self,
        model_name: str = "AITeamVN/Vietnamese_Embedding",
        *,
        api_key: str,
        sparse_model_name: str = "Qdrant/bm25",
        enable_sparse: bool = True,
        batch_size: int = 32,
        timeout: float = 60.0,
        max_retries: int = 5,
        backoff: float = 1.0,
        threads: int | None = None,
        endpoint: str | None = None,
    ) -> None:
        import httpx

        if not api_key:
            raise EmbeddingError("ApiEmbedder requires an API key (set HF_API_TOKEN).")
        self.model_name = model_name
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.backoff = backoff
        self._url = endpoint or self._HF_ROUTER.format(model=model_name)
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = httpx.Client(timeout=timeout)
        # Sparse always runs locally (cheap, ~0 RAM); only dense goes remote.
        self._sparse = (
            _BM25Sparse(sparse_model_name, threads=threads, batch_size=batch_size)
            if enable_sparse
            else None
        )

    @property
    def has_sparse(self) -> bool:
        return self._sparse is not None

    # ----------------------------------------------------------------- dense
    @staticmethod
    def _as_vector(v: list) -> list[float]:
        # feature-extraction returns a pooled [dim] vector for sentence models;
        # if a model returns token-level [tokens][dim], mean-pool it to [dim].
        if v and isinstance(v[0], list):
            n = len(v)
            return [sum(col) / n for col in zip(*v)]
        return [float(x) for x in v]

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """POST a batch of texts, returning one vector each. Retries transient
        failures (rate-limit 429, cold-start 503, 5xx, network) with exponential
        backoff; ``wait_for_model`` lets the first call wait out a cold start."""
        payload = {"inputs": texts, "options": {"wait_for_model": True}}
        last_err: object = None
        for attempt in range(self.max_retries):
            try:
                resp = self._client.post(self._url, headers=self._headers, json=payload)
            except Exception as exc:  # noqa: BLE001 - network/timeout: retry
                last_err = exc
            else:
                if resp.status_code == 200:
                    data = resp.json()
                    return [self._as_vector(v) for v in data]
                body = resp.text[:200]
                if resp.status_code in (429, 503) or resp.status_code >= 500:
                    last_err = EmbeddingError(f"HF API {resp.status_code}: {body}")
                else:  # 4xx (bad token, unsupported model): not retryable
                    raise EmbeddingError(f"HF API {resp.status_code}: {body}")
            if attempt < self.max_retries - 1:
                time.sleep(self.backoff * (2**attempt))
        raise EmbeddingError(
            f"HF embedding failed after {self.max_retries} attempts: {last_err}"
        )

    def embed_passages_iter(self, texts: list[str]) -> Iterator[list[float]]:
        """Embed in batches and yield one vector at a time (aligned with
        ``texts``), so the vector store keeps its bounded-memory / progress /
        cancel-between-batches behaviour unchanged."""
        if not texts:
            return
        for i in range(0, len(texts), self.batch_size):
            for vec in self._embed_batch(texts[i : i + self.batch_size]):
                yield vec

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return list(self.embed_passages_iter(texts))

    def embed_query(self, text: str) -> list[float]:
        return self._embed_batch([text])[0]

    # ---------------------------------------------------------------- sparse
    def embed_sparse_passages_iter(self, texts: list[str]) -> Iterator[SparseVec]:
        if not texts or self._sparse is None:
            return
        yield from self._sparse.passages_iter(texts)

    def embed_sparse_query(self, text: str) -> SparseVec | None:
        return self._sparse.query(text) if self._sparse is not None else None
