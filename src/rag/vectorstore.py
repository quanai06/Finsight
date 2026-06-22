"""Qdrant-backed hybrid vector store for chunk retrieval.

Each chunk is stored as a point carrying **two** vectors:

  * ``dense`` — multilingual semantic vector (cosine), and
  * ``bm25``  — sparse lexical vector (BM25, IDF applied by Qdrant).

Retrieval runs both branches and fuses them with **Reciprocal Rank Fusion**
(``FusionQuery(RRF)``) via Qdrant's Query API ``prefetch``. Dense alone misses
exact figures/codes; BM25 alone misses cross-lingual paraphrase — together they
cover each other's blind spots.

All sessions share one collection; each point carries a ``session_id`` payload
and queries filter on it, so sessions stay isolated while the index is managed
in one place. Embeddings come from :class:`~src.rag.embeddings.Embedder`.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from qdrant_client import QdrantClient, models

from .chunking import Chunk
from .embeddings import Embedder

logger = logging.getLogger(__name__)

_BATCH = 64
_DENSE = "dense"
_SPARSE = "bm25"


@dataclass(slots=True)
class Hit:
    text: str
    doc_id: str
    doc_name: str
    page: int | None
    heading: str
    score: float
    ordinal: int = 0
    parent_id: str = ""
    parent_text: str = ""
    vector: list[float] = field(default_factory=list)  # dense, for MMR


class VectorStore:
    def __init__(
        self,
        embedder: Embedder,
        *,
        url: str,
        collection: str,
        dim: int = 1024,
    ) -> None:
        self.embedder = embedder
        self.collection = collection
        self.dim = dim
        self.hybrid = embedder.has_sparse
        self.client = QdrantClient(url=url)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        # The dense+sparse schema differs from the old single-vector layout, so a
        # collection missing the sparse vector is from a previous scheme and must
        # be rebuilt (the vectors are unusable anyway). Documents have to be
        # re-indexed after this — expected when the retrieval scheme changes.
        if self.client.collection_exists(self.collection):
            info = self.client.get_collection(self.collection)
            sparse = info.config.params.sparse_vectors or {}
            if self.hybrid and _SPARSE not in sparse:
                logger.warning(
                    "Collection %s predates hybrid retrieval; recreating it. "
                    "Re-index documents (scripts/migrate_to_postgres.py).",
                    self.collection,
                )
                self.client.delete_collection(self.collection)

        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config={
                    _DENSE: models.VectorParams(
                        size=self.dim, distance=models.Distance.COSINE
                    )
                },
                sparse_vectors_config=(
                    {_SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)}
                    if self.hybrid
                    else {}
                ),
            )
        # Payload indexes make the session/doc filters and statement/note/year
        # routing filters fast. Idempotent: ignore "already exists" on re-runs.
        keyword = models.PayloadSchemaType.KEYWORD
        integer = models.PayloadSchemaType.INTEGER
        for fieldname, schema in (
            ("session_id", keyword),
            ("doc_id", keyword),
            ("statement_type", keyword),
            ("note_no", integer),
            ("year", integer),
        ):
            try:
                self.client.create_payload_index(
                    self.collection, field_name=fieldname, field_schema=schema
                )
            except Exception:  # noqa: BLE001 - index may already exist
                pass

    # ------------------------------------------------------------- writes
    def add(
        self,
        session_id: str,
        chunks: list[Chunk],
        progress_cb: Callable[[int, int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> int:
        """Embed (dense + sparse) and upsert chunks in batches.

        Vectors are produced one at a time and flushed every ``_BATCH`` points,
        so memory stays bounded and ``progress_cb(done, total)`` can report how
        far indexing has got (used to drive the per-document % in the UI).

        ``should_cancel`` is polled per chunk; when it returns True the loop stops
        early and returns the count indexed so far (the caller is responsible for
        removing the partial vectors). This is what makes a cancelled upload stop
        burning CPU instead of embedding to the end.
        """
        total = len(chunks)
        if total == 0:
            return 0
        texts = [c.text for c in chunks]
        dense_iter = self.embedder.embed_passages_iter(texts)
        if self.hybrid:
            sparse_iter = self.embedder.embed_sparse_passages_iter(texts)
        else:
            sparse_iter = iter(lambda: None, 0)  # never yields

        buffer: list[models.PointStruct] = []
        done = 0
        for c, dense in zip(chunks, dense_iter):
            if should_cancel is not None and should_cancel():
                return done  # stop early; caller deletes the partial vectors
            vector: dict = {_DENSE: dense}
            if self.hybrid:
                sp = next(sparse_iter)
                vector[_SPARSE] = models.SparseVector(
                    indices=sp.indices, values=sp.values
                )
            buffer.append(
                models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        "session_id": session_id,
                        "doc_id": c.doc_id,
                        "doc_name": c.doc_name,
                        "page": c.page,
                        "heading": c.heading,
                        "text": c.text,
                        "ordinal": c.ordinal,
                        "parent_id": c.parent_id,
                        "parent_text": c.parent_text,
                        "statement_type": c.statement_type,
                        "note_no": c.note_no,
                        "section_id": c.section_id,
                        "parent_section_id": c.parent_section_id,
                        "year": c.year,
                    },
                )
            )
            done += 1
            if len(buffer) >= _BATCH:
                self.client.upsert(self.collection, points=buffer)
                buffer = []
            if progress_cb is not None:
                progress_cb(done, total)
        # Re-check before the trailing flush: without this, a cancel arriving after
        # the last per-chunk check would still upsert the final batch, leaving
        # orphan vectors after the caller deletes the (partial) document.
        if buffer and not (should_cancel is not None and should_cancel()):
            self.client.upsert(self.collection, points=buffer)
        return done

    def delete_doc(self, session_id: str, doc_id: str) -> None:
        self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="session_id", match=models.MatchValue(value=session_id)
                        ),
                        models.FieldCondition(
                            key="doc_id", match=models.MatchValue(value=doc_id)
                        ),
                    ]
                )
            ),
        )

    def delete_session(self, session_id: str) -> None:
        self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="session_id", match=models.MatchValue(value=session_id)
                        )
                    ]
                )
            ),
        )

    # ------------------------------------------------------------ reads
    def search(
        self,
        session_id: str,
        query: str,
        *,
        limit: int,
        statement_type: str = "",
        note_no: int | None = None,
        year: int | None = None,
    ) -> list[Hit]:
        """Hybrid search, optionally soft-filtered to a financial statement /
        note / year (query routing). The caller decides the fallback when a
        filtered search returns nothing."""
        if not query.strip():
            return []
        must = [
            models.FieldCondition(
                key="session_id", match=models.MatchValue(value=session_id)
            )
        ]
        if statement_type:
            must.append(
                models.FieldCondition(
                    key="statement_type", match=models.MatchValue(value=statement_type)
                )
            )
        if note_no is not None:
            must.append(
                models.FieldCondition(key="note_no", match=models.MatchValue(value=note_no))
            )
        if year is not None:
            must.append(
                models.FieldCondition(key="year", match=models.MatchValue(value=year))
            )
        flt = models.Filter(must=must)
        dense_q = self.embedder.embed_query(query)

        if self.hybrid:
            sparse_q = self.embedder.embed_sparse_query(query)
            # Over-fetch on each branch, then fuse with RRF. Branch limits are a
            # bit larger than `limit` so good-but-not-top items can still surface
            # after fusion.
            branch = max(limit * 2, limit + 10)
            response = self.client.query_points(
                self.collection,
                prefetch=[
                    models.Prefetch(
                        query=dense_q, using=_DENSE, filter=flt, limit=branch
                    ),
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=sparse_q.indices, values=sparse_q.values
                        ),
                        using=_SPARSE,
                        filter=flt,
                        limit=branch,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=limit,
                with_payload=True,
                with_vectors=[_DENSE],
            )
        else:
            response = self.client.query_points(
                self.collection,
                query=dense_q,
                using=_DENSE,
                query_filter=flt,
                limit=limit,
                with_payload=True,
                with_vectors=[_DENSE],
            )

        hits: list[Hit] = []
        for p in response.points:
            payload = p.payload or {}
            vec = p.vector or {}
            dense = vec.get(_DENSE, []) if isinstance(vec, dict) else vec
            hits.append(
                Hit(
                    text=payload.get("text", ""),
                    doc_id=payload.get("doc_id", ""),
                    doc_name=payload.get("doc_name", ""),
                    page=payload.get("page"),
                    heading=payload.get("heading", ""),
                    score=float(p.score),
                    ordinal=payload.get("ordinal", 0),
                    parent_id=payload.get("parent_id", ""),
                    parent_text=payload.get("parent_text", ""),
                    vector=list(dense) if dense else [],
                )
            )
        return hits
