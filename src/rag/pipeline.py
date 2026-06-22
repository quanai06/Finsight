"""RAG pipeline: hybrid retrieve → dedup + MMR (or rerank) → grounded generation.

    question ─hybrid(dense+BM25, RRF)→ candidates ─dedup→ MMR ─→ top-K ─→ Groq LLM
                                                                            │
                         short-term memory (recent turns) ─────────────────┘

Reranking is intentionally *not* required: on CPU it is the heaviest stage, and
hybrid retrieval + Maximal Marginal Relevance recover most of its benefit far
more cheaply. A cross-encoder reranker can still be plugged in (it then replaces
the MMR step). Two post-retrieval steps do the diversity/precision work:

  * **parent-table collapse** — multiple row-groups of one table are merged into
    a single source carrying the *whole* table (small-to-big), so one table can't
    swallow every top-K slot and the LLM sees totals/sibling rows.
  * **MMR** — picks a relevant *and* non-redundant top-K, which matters for long,
    repetitive reports where near-identical chunks would otherwise crowd out the
    one chunk that actually answers the question.

Stateless: the serving layer owns the vector store, reranker, LLM, and memory,
and passes the session id + recent history in.
"""

from __future__ import annotations

from dataclasses import dataclass

from .financial_sections import route_query
from .llm import GroqClient
from .reranker import Reranker
from .vectorstore import Hit, VectorStore

_SYSTEM_PROMPT = (
    "You are Finsight, an assistant that answers questions about the user's "
    "uploaded financial documents. Use ONLY the provided context to answer. "
    "If the context does not contain the answer, say you could not find it in "
    "the documents — do not invent figures.\n"
    "When you state a number, always include its unit of measure (e.g. 'triệu "
    "đồng' / 'million VND') and the period/year it belongs to, exactly as shown "
    "in the context. If the context spans several periods, report only the "
    "period the question asks about; if the unit or period is missing, say so "
    "rather than guessing.\n"
    "Cite the sources you used with their bracket numbers, e.g. [1]. Keep answers "
    "concise and factual, report numbers exactly as they appear, and answer in "
    "the language of the question."
)

_MAX_PARENT_CHARS = 4000  # cap an expanded table so it can't dominate the context


@dataclass(slots=True)
class RetrievedChunk:
    rank: int
    text: str
    doc_id: str
    doc_name: str
    page: int | None
    heading: str
    score: float


@dataclass(slots=True)
class RAGAnswer:
    answer: str
    sources: list[RetrievedChunk]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _mmr_numpy(hits: list[Hit], k: int, lam: float):
    """Vectorized MMR: one normalized matrix + matmul instead of O(n²) Python
    cosine loops. Returns the selected hit list, or None if numpy/vectors are
    unavailable so the caller can fall back to the pure-Python path."""
    try:
        import numpy as np
    except Exception:  # noqa: BLE001 - numpy is a declared dep; guard anyway
        return None
    if any(not h.vector for h in hits):
        return None
    V = np.asarray([h.vector for h in hits], dtype=np.float32)
    norms = np.linalg.norm(V, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    Vn = V / norms
    sim = Vn @ Vn.T  # pairwise cosine, all at once
    scores = np.asarray([h.score for h in hits], dtype=np.float32)
    lo, hi = float(scores.min()), float(scores.max())
    rel = (scores - lo) / ((hi - lo) or 1.0)

    selected: list[int] = []
    remaining = list(range(len(hits)))
    while remaining and len(selected) < k:
        if not selected:
            best = max(remaining, key=lambda i: rel[i])
        else:
            red = sim[remaining][:, selected].max(axis=1)
            vals = lam * rel[remaining] - (1 - lam) * red
            best = remaining[int(vals.argmax())]
        selected.append(best)
        remaining.remove(best)
    return [hits[i] for i in selected]


def _collapse_parents(hits: list[Hit]) -> list[Hit]:
    """Merge a table's row-group hits into one, carrying the full table text.

    Keeps the best-scoring hit per ``parent_id`` and swaps its text for the whole
    table (capped), so retrieval precision is preserved but generation sees the
    complete table. Non-table hits pass through untouched.
    """
    out: list[Hit] = []
    seen: dict[str, Hit] = {}
    for h in hits:
        if not h.parent_id:
            out.append(h)
            continue
        if h.parent_id not in seen:
            kept = Hit(
                text=(h.parent_text or h.text)[:_MAX_PARENT_CHARS],
                doc_id=h.doc_id,
                doc_name=h.doc_name,
                page=h.page,
                heading=h.heading,
                score=h.score,
                ordinal=h.ordinal,
                parent_id=h.parent_id,
                vector=h.vector,
            )
            seen[h.parent_id] = kept
            out.append(kept)
    return out


def _mmr(hits: list[Hit], k: int, lam: float) -> list[Hit]:
    """Maximal Marginal Relevance: relevant (retrieval score) but diverse (dense)."""
    if len(hits) <= k:
        return hits
    fast = _mmr_numpy(hits, k, lam)
    if fast is not None:
        return fast
    scores = [h.score for h in hits]
    lo, hi = min(scores), max(scores)
    span = (hi - lo) or 1.0
    rel = [(s - lo) / span for s in scores]

    selected: list[int] = []
    remaining = list(range(len(hits)))
    while remaining and len(selected) < k:
        best_i, best_val = remaining[0], float("-inf")
        for i in remaining:
            redundancy = max(
                (_cosine(hits[i].vector, hits[j].vector) for j in selected),
                default=0.0,
            )
            val = lam * rel[i] - (1 - lam) * redundancy
            if val > best_val:
                best_i, best_val = i, val
        selected.append(best_i)
        remaining.remove(best_i)
    return [hits[i] for i in selected]


class RAGPipeline:
    def __init__(
        self,
        llm: GroqClient,
        vectorstore: VectorStore,
        *,
        reranker: Reranker | None = None,
        top_k: int = 8,
        candidates: int = 50,
        mmr_lambda: float = 0.6,
        score_threshold: float = 0.0,
        use_routing: bool = True,
        use_graph: bool = False,
        known_years: list[int] | None = None,
    ) -> None:
        self.llm = llm
        self.vectorstore = vectorstore
        self.reranker = reranker
        self.top_k = top_k
        self.candidates = candidates
        self.mmr_lambda = mmr_lambda
        self.score_threshold = score_threshold
        self.use_routing = use_routing
        # Graph-RAG cross-period fan-out: when a question spans several years,
        # search each year and merge so the context covers every period.
        self.use_graph = use_graph
        self.known_years = known_years or []

    def _routed_search(self, session_id: str, question: str) -> list[Hit]:
        """Hybrid search, soft-filtered to the statement/note/year the question
        targets. Degrades gracefully: drop the year filter first, then all
        filters, so routing never blocks an answer that exists off-route."""
        n = self.candidates

        # Graph-RAG: multi-period questions fan out across years (see
        # src/rag/graph_retrieval.py) so one year can't crowd out the others.
        if self.use_graph:
            from .graph_retrieval import cross_period_search, detect_periods

            periods = detect_periods(question, self.known_years)
            if periods:
                r = route_query(question) if self.use_routing else None
                return cross_period_search(
                    self.vectorstore, session_id, question, periods, total_limit=n,
                    statement_type=(r.statement_type if r else ""),
                    note_no=(r.note_no if r else None),
                )

        if not self.use_routing:
            return self.vectorstore.search(session_id, question, limit=n)
        r = route_query(question)
        if not r.has_filter:
            return self.vectorstore.search(session_id, question, limit=n)
        hits = self.vectorstore.search(
            session_id, question, limit=n,
            statement_type=r.statement_type, note_no=r.note_no, year=r.year,
        )
        if not hits and r.year is not None and (r.statement_type or r.note_no is not None):
            hits = self.vectorstore.search(
                session_id, question, limit=n,
                statement_type=r.statement_type, note_no=r.note_no,
            )
        if not hits:
            hits = self.vectorstore.search(session_id, question, limit=n)
        return hits

    def _periods(self, question: str) -> list[int]:
        if not self.use_graph:
            return []
        from .graph_retrieval import detect_periods

        return detect_periods(question, self.known_years)

    def retrieve(self, session_id: str, question: str) -> list[RetrievedChunk]:
        hits = self._routed_search(session_id, question)
        if not hits:
            return []

        # Optional strict grounding: reject when nothing is semantically close.
        # Off by default (0.0) — a non-zero threshold can drop BM25-only exact
        # matches whose dense similarity is modest, so tune it per corpus.
        if self.score_threshold > 0.0:
            if max(h.score for h in hits) < self.score_threshold:
                return []

        hits = _collapse_parents(hits)
        periods = self._periods(question)
        multi = len(periods) > 1

        if multi:
            # Cross-period question: the same line item in each year is exactly what
            # we want, but MMR would penalise those as near-duplicates and starve
            # the later years. Keep the year-balanced fan-out order instead, and
            # widen top_k to ~2 chunks per period so every year survives.
            k = min(max(self.top_k, 2 * len(periods)), self.candidates)
            ranked = hits[:k]
        elif self.reranker is not None:
            scores = self.reranker.rerank(question, [h.text for h in hits])
            ranked = [h for h, _ in sorted(zip(hits, scores), key=lambda x: x[1], reverse=True)]
            ranked = ranked[: self.top_k]
        else:
            ranked = _mmr(hits, self.top_k, self.mmr_lambda)

        return [
            RetrievedChunk(
                rank=i + 1,
                text=h.text,
                doc_id=h.doc_id,
                doc_name=h.doc_name,
                page=h.page,
                heading=h.heading,
                score=round(float(h.score), 4),
            )
            for i, h in enumerate(ranked)
        ]

    def answer(
        self,
        session_id: str,
        question: str,
        *,
        history: list[dict] | None = None,
    ) -> RAGAnswer:
        sources = self.retrieve(session_id, question)
        if not sources:
            return RAGAnswer(
                answer=(
                    "I couldn't find anything relevant in this session's "
                    "documents. Try uploading a document or rephrasing the "
                    "question."
                ),
                sources=[],
            )

        # The heading breadcrumb already lives inside each chunk's text, so the
        # source label only needs doc + page (avoids repeating it for the LLM).
        context = "\n\n".join(
            f"[{s.rank}] (source: {s.doc_name}"
            + (f", page {s.page}" if s.page is not None else "")
            + f")\n{s.text}"
            for s in sources
        )
        messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]
        for turn in history or []:
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append(
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}
        )

        answer = self.llm.chat(messages)
        return RAGAnswer(answer=answer, sources=sources)
