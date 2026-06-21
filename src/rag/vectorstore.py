"""Qdrant-backed vector store for chunk retrieval.

All sessions share one collection; each point carries a ``session_id`` payload
and queries filter on it, so sessions stay isolated while the index is managed
in one place. Embeddings are produced by :class:`~src.rag.embeddings.Embedder`.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from qdrant_client import QdrantClient, models

from .chunking import Chunk
from .embeddings import Embedder

_BATCH = 64


@dataclass(slots=True)
class Hit:
    text: str
    doc_id: str
    doc_name: str
    page: int | None
    heading: str
    score: float


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
        self.client = QdrantClient(url=url)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(
                    size=self.dim, distance=models.Distance.COSINE
                ),
            )
            # keyword index makes the per-session filter fast
            self.client.create_payload_index(
                self.collection,
                field_name="session_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                self.collection,
                field_name="doc_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

    # ------------------------------------------------------------- writes
    def add(
        self,
        session_id: str,
        chunks: list[Chunk],
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> int:
        """Embed + upsert chunks in batches.

        Vectors are produced one at a time and flushed every ``_BATCH`` points,
        so memory stays bounded and ``progress_cb(done, total)`` can report how
        far indexing has got (used to drive the per-document % in the UI).
        """
        total = len(chunks)
        if total == 0:
            return 0
        buffer: list[models.PointStruct] = []
        done = 0
        texts = [c.text for c in chunks]
        for c, vector in zip(chunks, self.embedder.embed_passages_iter(texts)):
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
                    },
                )
            )
            done += 1
            if len(buffer) >= _BATCH:
                self.client.upsert(self.collection, points=buffer)
                buffer = []
            if progress_cb is not None:
                progress_cb(done, total)
        if buffer:
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
    def search(self, session_id: str, query: str, *, limit: int) -> list[Hit]:
        if not query.strip():
            return []
        vector = self.embedder.embed_query(query)
        response = self.client.query_points(
            self.collection,
            query=vector,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="session_id", match=models.MatchValue(value=session_id)
                    )
                ]
            ),
            limit=limit,
            with_payload=True,
        )
        hits: list[Hit] = []
        for p in response.points:
            payload = p.payload or {}
            hits.append(
                Hit(
                    text=payload.get("text", ""),
                    doc_id=payload.get("doc_id", ""),
                    doc_name=payload.get("doc_name", ""),
                    page=payload.get("page"),
                    heading=payload.get("heading", ""),
                    score=float(p.score),
                )
            )
        return hits
