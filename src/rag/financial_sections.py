"""Financial-statement structure recognition for Vietnamese reports (BCTC).

Pure heuristics — regex/keyword only, no model, no GPU — so it stays cheap and is
easy to tune against real data. Two jobs:

  * :func:`detect_statement_type` / :func:`detect_note_no` — at *index* time, tag a
    heading with which financial statement it belongs to (Bảng cân đối kế toán,
    Kết quả kinh doanh, Lưu chuyển tiền tệ, Thuyết minh, …) and, for notes, the
    note number. Tags are stored on each chunk's payload.
  * :func:`route_query` — at *query* time, read the question and decide which
    statement / note / year it is about, so retrieval can soft-filter to that
    branch (with a fallback to no filter if it comes back empty).

Statement-type codes are stable strings used in payloads and filters:
``cdkt`` (balance sheet), ``kqkd`` (income statement), ``lctt`` (cash flow),
``thuyet_minh`` (notes), ``kiem_toan`` (auditor's report), ``bgd`` (board report).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- heading -> statement type (checked in order; first hit wins) -------------
_TYPE_PATTERNS: list[tuple[str, list[str]]] = [
    ("lctt", [r"l[uư]u\s*chuy[eể]n\s*ti[eề]n\s*t[eệ]", r"cash\s*flow"]),
    ("cdkt", [r"b[aả]ng\s*c[aâ]n\s*đ[oố]i\s*k[eế]\s*to[aá]n", r"balance\s*sheet"]),
    (
        "kqkd",
        [
            r"k[eế]t\s*qu[aả]\s*(ho[aạ]t\s*đ[oộ]ng\s*)?kinh\s*doanh",
            r"income\s*statement",
            r"profit\s*and\s*loss",
            r"b[aá]o\s*c[aá]o\s*l[aãi]i?\s*l[oỗ]",
        ],
    ),
    ("thuyet_minh", [r"thuy[eế]t\s*minh", r"notes?\s*to\s*(the\s*)?financial"]),
    (
        "kiem_toan",
        [r"b[aá]o\s*c[aá]o\s*ki[eể]m\s*to[aá]n", r"independent\s*auditor",
         r"[yý]\s*ki[eế]n\s*ki[eể]m\s*to[aá]n"],
    ),
    ("bgd", [r"b[aá]o\s*c[aá]o\s*c[uủ]a\s*ban\s*(t[oổ]ng\s*)?gi[aá]m\s*đ[oố]c",
             r"statement\s*of\s*the\s*board"]),
]
_TYPE_COMPILED = [
    (code, [re.compile(p, re.IGNORECASE) for p in pats]) for code, pats in _TYPE_PATTERNS
]

# leading note numbering: "12.", "V.1", "Note 5", "Thuyết minh số 8"
_NOTE_NO_RE = re.compile(
    r"^\s*(?:thuy[eế]t\s*minh\s*)?(?:s[oố]\s*)?(?:note\s*)?(?:[IVXLC]+\.)?(\d{1,3})\b",
    re.IGNORECASE,
)

# --- query -> route hints -----------------------------------------------------
_ROUTE_PATTERNS: dict[str, list[str]] = {
    "cdkt": [r"t[aà]i\s*s[aả]n", r"n[oợ]\s*ph[aả]i\s*tr[aả]", r"v[oố]n\s*ch[uủ]\s*s[oở]\s*h[uữ]u",
             r"c[aâ]n\s*đ[oố]i\s*k[eế]\s*to[aá]n", r"h[aà]ng\s*t[oồ]n\s*kho", r"t[oổ]ng\s*t[aà]i\s*s[aả]n"],
    "kqkd": [r"doanh\s*thu", r"l[oợ]i\s*nhu[aậ]n", r"chi\s*ph[ií]", r"gi[aá]\s*v[oố]n",
             r"\beps\b", r"l[aã]i\s*g[oộ]p", r"bi[eê]n\s*l[oợ]i\s*nhu[aậ]n"],
    "lctt": [r"d[oò]ng\s*ti[eề]n", r"l[uư]u\s*chuy[eể]n\s*ti[eề]n", r"ti[eề]n\s*thu[aầ]n"],
}
_ROUTE_COMPILED = {
    code: [re.compile(p, re.IGNORECASE) for p in pats] for code, pats in _ROUTE_PATTERNS.items()
}
_QUERY_NOTE_RE = re.compile(r"thuy[eế]t\s*minh\s*(?:s[oố]\s*)?(\d{1,3})", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def detect_statement_type(text: str) -> str:
    """Statement-type code for a heading/breadcrumb, or ``""`` if none matches."""
    if not text:
        return ""
    for code, regexes in _TYPE_COMPILED:
        if any(r.search(text) for r in regexes):
            return code
    return ""


def detect_note_no(heading_leaf: str) -> int | None:
    """Note number from the *leaf* heading of a thuyết-minh subsection, if present."""
    m = _NOTE_NO_RE.match(heading_leaf or "")
    return int(m.group(1)) if m else None


@dataclass(slots=True)
class QueryRoute:
    statement_type: str = ""
    note_no: int | None = None
    year: int | None = None

    @property
    def has_filter(self) -> bool:
        return bool(self.statement_type or self.note_no or self.year)


def route_query(question: str) -> QueryRoute:
    """Infer which statement / note / year a question targets.

    Conservative on purpose: if the question matches *several* distinct statement
    types it stays ambiguous (no type filter) rather than routing to the wrong
    one. A note mention ("thuyết minh 12") implies the notes statement.
    """
    q = question or ""
    matched = {code for code, regexes in _ROUTE_COMPILED.items() if any(r.search(q) for r in regexes)}

    note_m = _QUERY_NOTE_RE.search(q)
    note_no = int(note_m.group(1)) if note_m else None

    statement_type = ""
    if note_no is not None:
        statement_type = "thuyet_minh"
    elif len(matched) == 1:
        statement_type = next(iter(matched))

    year_m = _YEAR_RE.search(q)
    year = int(year_m.group(0)) if year_m else None
    return QueryRoute(statement_type=statement_type, note_no=note_no, year=year)
