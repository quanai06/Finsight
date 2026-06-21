"""Per-session vector index backed by TF-IDF (CPU-only, no model download).

Why TF-IDF: the project targets machines without a GPU, and a TF-IDF index has
zero model weights to download, is fast to build, and gives solid keyword/term
retrieval over financial reports. The class boundary (``add`` / ``search`` /
``save`` / ``load``) is intentionally generic so a dense embedder can replace it
later without changing the serving layer.

Each session owns one ``SessionIndex`` persisted under ``<session>/index/``.
Adding documents refits the vectorizer over the full corpus (cheap at this
scale) so IDF stays meaningful as the corpus grows.
"""

from __future__ import annotations

import pickle
from dataclasses import asdict
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

from .chunking import Chunk

_INDEX_FILE = "index.pkl"


class SessionIndex:
    """A searchable TF-IDF index over all chunks in one session."""

    def __init__(self, chunks: list[Chunk] | None = None) -> None:
        self._chunks: list[Chunk] = list(chunks or [])
        self._vectorizer: TfidfVectorizer | None = None
        self._matrix = None
        if self._chunks:
            self._fit()

    def _fit(self) -> None:
        corpus = [c.text for c in self._chunks]
        self._vectorizer = TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, 2),
            sublinear_tf=True,
            max_df=1.0,   # keep all terms; corpora here are small per session
            min_df=1,
        )
        self._matrix = self._vectorizer.fit_transform(corpus)

    def add(self, chunks: list[Chunk]) -> None:
        """Add chunks and refit. Caller persists with ``save`` afterwards."""
        if not chunks:
            return
        self._chunks.extend(chunks)
        self._fit()

    def remove_doc(self, doc_id: str) -> None:
        """Drop every chunk belonging to ``doc_id`` and refit."""
        kept = [c for c in self._chunks if c.doc_id != doc_id]
        self._chunks = kept
        if kept:
            self._fit()
        else:
            self._vectorizer = None
            self._matrix = None

    # ---------------------------------------------------------------- search
    def search(self, query: str, *, k: int = 5) -> list[tuple[Chunk, float]]:
        """Return the ``k`` most relevant chunks with cosine scores (0..1)."""
        if not self._chunks or self._vectorizer is None or not query.strip():
            return []
        q = self._vectorizer.transform([query])
        scores = linear_kernel(q, self._matrix).ravel()  # tf-idf rows are l2-normed
        k = min(k, len(self._chunks))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [(self._chunks[i], float(scores[i])) for i in top if scores[i] > 0.0]

    # --------------------------------------------------------------- counts
    @property
    def num_chunks(self) -> int:
        return len(self._chunks)

    def doc_ids(self) -> set[str]:
        return {c.doc_id for c in self._chunks}

    # ------------------------------------------------------------ persistence
    def save(self, index_dir: str | Path) -> None:
        index_dir = Path(index_dir)
        index_dir.mkdir(parents=True, exist_ok=True)
        payload = {"chunks": [asdict(c) for c in self._chunks]}
        with open(index_dir / _INDEX_FILE, "wb") as f:
            pickle.dump(payload, f)

    @classmethod
    def load(cls, index_dir: str | Path) -> "SessionIndex":
        path = Path(index_dir) / _INDEX_FILE
        if not path.exists():
            return cls()
        with open(path, "rb") as f:
            payload = pickle.load(f)
        chunks = [Chunk(**c) for c in payload.get("chunks", [])]
        return cls(chunks)
