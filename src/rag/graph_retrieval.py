"""Graph-RAG cross-period retrieval: answer questions that span several years.

Plain top-k retrieval has a structural blind spot for financial Q&A: ask
"doanh thu qua các năm 2021–2025" and the top-k chunks are easily dominated by a
single year (the one whose wording best matches), so the LLM only ever sees one
number and can't build the series. The fix mirrors the *local→neighbours* step of
graph RAG, but uses the cheap structured edge we already have — the **period** each
chunk is tagged with (``year`` payload) — instead of an LLM-built entity graph.

When a question targets multiple periods, we **fan the search out per year** (one
filtered hybrid search per target year) and merge, guaranteeing every period is
represented in the context. This is the same "same line item across time is one
node" idea as :mod:`src.rag.financial_facts`, applied at retrieval time. No LLM
calls, no offline index — it reuses the ``year`` filter the vector store already
supports.
"""

from __future__ import annotations

import re

# Phrases that signal "report this for every period", not one specific year.
_ALL_YEARS_RE = re.compile(
    r"\b(qua\s+các\s+năm|các\s+năm|từng\s+năm|hằng\s+năm|hàng\s+năm|mỗi\s+năm|"
    r"giai\s+đoạn|xu\s+hướng|tăng\s+trưởng|over\s+the\s+years|each\s+year|trend)\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_RANGE_RE = re.compile(r"\b(20\d{2})\s*[–\-—đến to]+\s*(20\d{2})\b")


def detect_periods(question: str, known_years: list[int] | None = None) -> list[int]:
    """Years a question targets. Empty list ⇒ not a multi-period question.

    - An explicit range "2021–2025" expands to every year in between.
    - Two or more explicit years are taken as-is.
    - A single year is *not* multi-period (the normal routed search handles it).
    - A "các năm / giai đoạn / tăng trưởng" phrase with no explicit year means
      *all* known years in the corpus.
    """
    years = sorted({int(m.group(0)) for m in _YEAR_RE.finditer(question)})

    rng = _RANGE_RE.search(question)
    if rng:
        lo, hi = int(rng.group(1)), int(rng.group(2))
        if lo <= hi and hi - lo <= 30:
            return list(range(lo, hi + 1))

    if len(years) >= 2:
        return years

    if _ALL_YEARS_RE.search(question) and known_years:
        # "doanh thu các năm" → all years; if one year is also named, span from it
        if years:
            lo = min(years[0], min(known_years))
            return [y for y in known_years if y >= lo] or list(known_years)
        return list(known_years)

    return []


def cross_period_search(vectorstore, session_id: str, question: str, periods: list[int],
                        *, total_limit: int, statement_type: str = "", note_no=None):
    """Run one filtered hybrid search per target year and merge the results.

    Splits the candidate budget across periods so each year is represented, then
    interleaves by rank (year A #1, year B #1, …) so the merged list stays
    balanced before dedup/MMR. Years that return nothing are simply skipped.
    """
    if not periods:
        return vectorstore.search(session_id, question, limit=total_limit,
                                  statement_type=statement_type, note_no=note_no)
    per_year = max(2, total_limit // len(periods) + 1)
    buckets = []
    for y in periods:
        hits = vectorstore.search(session_id, question, limit=per_year,
                                  statement_type=statement_type, note_no=note_no, year=y)
        # Degrade per-year: a statement/note filter can wrongly empty a year when
        # the corpus isn't tagged with statement types, so retry that year on the
        # year filter alone before giving up on it.
        if not hits and (statement_type or note_no is not None):
            hits = vectorstore.search(session_id, question, limit=per_year, year=y)
        if not hits:
            continue
        buckets.append(hits)
    if not buckets:
        return vectorstore.search(session_id, question, limit=total_limit,
                                  statement_type=statement_type, note_no=note_no)
    merged, seen = [], set()
    for rank in range(max(len(b) for b in buckets)):
        for b in buckets:
            if rank < len(b):
                h = b[rank]
                key = (h.doc_id, h.page, h.text[:60])
                if key not in seen:
                    seen.add(key)
                    merged.append(h)
    return merged[:total_limit] if total_limit else merged
