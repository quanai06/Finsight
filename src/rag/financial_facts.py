"""Structured financial-facts extraction + a cross-period fact graph.

This is the deterministic, **zero-LLM** core of Finsight's Graph-RAG layer. Vietnamese
consolidated financial statements (BCTC) are highly structured: every line has a
fixed VAS *line code* (``Mã số``) in column 0 — ``01`` = revenue, ``20`` = gross
profit, ``50`` = profit before tax, ``270``/``440`` = total assets/resources, …
The line code is numeric, so OCR preserves it even when the Vietnamese label is
mangled by diacritic noise. We therefore key facts on the line code, attach a clean
canonical label ourselves, and read the value straight from the statement table.

A full LightRAG/GraphRAG build (an LLM extracting entities per chunk) is infeasible
here — CPU-only + a 12k-token/min Groq free tier would need tens of thousands of LLM
calls just to index. We don't need it: the "entity" *is* the line code, and the
cross-year/quarter edge is implicit — the **same canonical key in two periods is the
same node across time**. That link is what answers "doanh thu qua các năm 2021–2025".

Two consumers share this module:
  * the offline benchmark/dataset generator (`benchmark/rag/build_dataset.py`), and
  * the retrieval pipeline's optional cross-period fan-out (`graph_retrieval`).

The graph is backed by ``networkx`` (pure-Python, CPU, no GPU) when available, with a
plain-dict fallback so the extractor works even if networkx isn't installed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
#  Canonical VAS line-code maps  (code -> clean Vietnamese label)
# --------------------------------------------------------------------------- #
# Codes are read *within* an already-identified statement table, so the same code
# (e.g. "20") can mean different things in KQKD vs LCTT without colliding.

KQKD_CODES: dict[str, str] = {
    "01": "Doanh thu bán hàng và cung cấp dịch vụ",
    "02": "Các khoản giảm trừ doanh thu",
    "10": "Doanh thu thuần về bán hàng và cung cấp dịch vụ",
    "11": "Giá vốn hàng bán và dịch vụ cung cấp",
    "20": "Lợi nhuận gộp về bán hàng và cung cấp dịch vụ",
    "21": "Doanh thu hoạt động tài chính",
    "22": "Chi phí tài chính",
    "23": "Chi phí lãi vay",
    "24": "Phần lãi/lỗ trong công ty liên doanh, liên kết",
    "25": "Chi phí bán hàng",
    "26": "Chi phí quản lý doanh nghiệp",
    "30": "Lợi nhuận thuần từ hoạt động kinh doanh",
    "31": "Thu nhập khác",
    "32": "Chi phí khác",
    "40": "Lợi nhuận khác",
    "50": "Tổng lợi nhuận kế toán trước thuế",
    "51": "Chi phí thuế TNDN hiện hành",
    "52": "Chi phí thuế TNDN hoãn lại",
    "60": "Lợi nhuận sau thuế thu nhập doanh nghiệp",
    "61": "Lợi nhuận sau thuế của cổ đông công ty mẹ",
    "62": "Lợi nhuận sau thuế của cổ đông không kiểm soát",
    "70": "Lãi cơ bản trên cổ phiếu",
    "71": "Lãi suy giảm trên cổ phiếu",
}

CDKT_ASSET_CODES: dict[str, str] = {
    "100": "Tài sản ngắn hạn",
    "110": "Tiền và các khoản tương đương tiền",
    "120": "Đầu tư tài chính ngắn hạn",
    "130": "Các khoản phải thu ngắn hạn",
    "140": "Hàng tồn kho",
    "150": "Tài sản ngắn hạn khác",
    "200": "Tài sản dài hạn",
    "270": "Tổng cộng tài sản",
}

CDKT_RESOURCE_CODES: dict[str, str] = {
    "300": "Nợ phải trả",
    "310": "Nợ ngắn hạn",
    "330": "Nợ dài hạn",
    "400": "Vốn chủ sở hữu",
    "410": "Vốn chủ sở hữu (mục I)",
    "411": "Vốn cổ phần đã phát hành",
    "412": "Thặng dư vốn cổ phần",
    "421": "Lợi nhuận sau thuế chưa phân phối",
    "429": "Lợi ích cổ đông không kiểm soát",
    "440": "Tổng cộng nguồn vốn",
}

LCTT_CODES: dict[str, str] = {
    "20": "Lưu chuyển tiền thuần từ hoạt động kinh doanh",
    "30": "Lưu chuyển tiền thuần từ hoạt động đầu tư",
    "40": "Lưu chuyển tiền thuần từ hoạt động tài chính",
    "50": "Lưu chuyển tiền thuần trong kỳ",
    "60": "Tiền và tương đương tiền đầu kỳ",
    "70": "Tiền và tương đương tiền cuối kỳ",
}

# statement_type -> (code map, unit, column semantics)
#   "year" column = the report's own year; "prior" column = report year - 1.
STATEMENTS = {
    "kqkd": {"codes": KQKD_CODES, "unit": "triệu VND", "name": "Báo cáo kết quả hoạt động kinh doanh"},
    "cdkt_ts": {"codes": CDKT_ASSET_CODES, "unit": "triệu VND", "name": "Bảng cân đối kế toán (Tài sản)"},
    "cdkt_nv": {"codes": CDKT_RESOURCE_CODES, "unit": "triệu VND", "name": "Bảng cân đối kế toán (Nguồn vốn)"},
    "lctt": {"codes": LCTT_CODES, "unit": "triệu VND", "name": "Báo cáo lưu chuyển tiền tệ"},
}
# EPS lines are in đồng/cổ phiếu, not millions.
_VND_PER_SHARE_CODES = {"70", "71"}

_NUM = re.compile(r"^\(?-?[\d.]+\)?$")
_CODE = re.compile(r"\d{2,3}[a-z]?$")


# --------------------------------------------------------------------------- #
#  Facts
# --------------------------------------------------------------------------- #


@dataclass(slots=True, frozen=True)
class Fact:
    """One value of one line item in one period (the graph's leaf node)."""

    statement: str          # kqkd | cdkt_ts | cdkt_nv | lctt
    code: str               # VAS line code
    label: str              # canonical Vietnamese label
    year: int               # period the value belongs to
    value_raw: str          # as printed, e.g. "(91.623.165)" or "125.780.761"
    value: float            # signed numeric (parentheses -> negative)
    unit: str               # "triệu VND" | "VND/cổ phiếu"

    @property
    def key(self) -> tuple[str, str]:
        """Canonical line-item identity, shared across periods."""
        return (self.statement, self.code)


def _is_num(s: str) -> bool:
    s = str(s).strip()
    return bool(_NUM.match(s)) and any(c.isdigit() for c in s)


def _parse_value(raw: str) -> float:
    s = str(raw).strip()
    neg = s.startswith("(") and s.endswith(")")
    digits = re.sub(r"[^\d]", "", s)
    if not digits:
        return 0.0
    v = float(digits)
    return -v if neg else v


def _code_of(cell: str) -> str | None:
    s = str(cell).strip()
    return s if _CODE.fullmatch(s) else None


def _detect_statement(codes: set[str]) -> str | None:
    """Identify which statement a table is, by which canonical code set it best
    matches (codes are read in-table so KQKD-20 ≠ LCTT-20)."""
    scores = {
        "kqkd": len(codes & set(KQKD_CODES)) if {"10", "20"} <= codes else 0,
        "cdkt_ts": len(codes & set(CDKT_ASSET_CODES)) if "100" in codes else 0,
        "cdkt_nv": len(codes & set(CDKT_RESOURCE_CODES)) if "400" in codes else 0,
    }
    best = max(scores, key=scores.get)
    return best if scores[best] >= 3 else None


def extract_facts_from_tables(tables: list[dict], year: int) -> list[Fact]:
    """Pull line-item facts from a year's statement tables (tables.json shape:
    ``{header, rows}``). Only the report-year ("current") column is emitted here
    — the prior column is used by :func:`verify_consistency` for cross-checking.

    ``year`` is the report's own year (the "Năm nay" / "Số cuối năm" column).
    """
    facts: list[Fact] = []
    seen: set[tuple[str, str]] = set()
    for t in tables:
        rows = t.get("rows") or []
        codes = {
            c for r in rows
            if r and len(r) >= 5 and _is_num(r[-1]) and _is_num(r[-2]) and (c := _code_of(r[0]))
        }
        stmt = _detect_statement(codes)
        if not stmt:
            continue
        codemap = STATEMENTS[stmt]["codes"]
        for r in rows:
            if not r or len(r) < 5 or not (_is_num(r[-1]) and _is_num(r[-2])):
                continue
            code = _code_of(r[0])
            if code not in codemap or (stmt, code) in seen:
                continue
            unit = "VND/cổ phiếu" if (stmt == "kqkd" and code in _VND_PER_SHARE_CODES) else "triệu VND"
            raw = str(r[-2]).strip()
            facts.append(Fact(stmt, code, codemap[code], year, raw, _parse_value(raw), unit))
            seen.add((stmt, code))
    return facts


def extract_prior(tables: list[dict]) -> dict[tuple[str, str], str]:
    """Prior-year ("Năm trước"/"Số đầu năm") raw value per line item, for the
    cross-report consistency check."""
    out: dict[tuple[str, str], str] = {}
    for t in tables:
        rows = t.get("rows") or []
        codes = {
            c for r in rows
            if r and len(r) >= 5 and _is_num(r[-1]) and _is_num(r[-2]) and (c := _code_of(r[0]))
        }
        stmt = _detect_statement(codes)
        if not stmt:
            continue
        codemap = STATEMENTS[stmt]["codes"]
        for r in rows:
            if not r or len(r) < 5 or not (_is_num(r[-1]) and _is_num(r[-2])):
                continue
            code = _code_of(r[0])
            if code in codemap and (stmt, code) not in out:
                out[(stmt, code)] = str(r[-1]).strip()
    return out


# --------------------------------------------------------------------------- #
#  Cross-period fact graph
# --------------------------------------------------------------------------- #


@dataclass
class FinancialFactGraph:
    """A directed graph linking line items across periods.

    Nodes: ``item:{statement}:{code}`` (LineItem), ``period:{year}`` (Period),
    ``fact:{statement}:{code}:{year}`` (Fact value). Edges: Fact→LineItem
    (``OF_ITEM``), Fact→Period (``IN_PERIOD``). The LineItem node is the cross-time
    hub — every period's value hangs off it, so a series query is one node lookup.

    Uses networkx when present (so it's a real graph you can traverse/serialize),
    else a dict index with identical query semantics.
    """

    facts: list[Fact] = field(default_factory=list)
    _by_item: dict[tuple[str, str], dict[int, Fact]] = field(default_factory=dict)
    g: object = None  # networkx.DiGraph | None

    def add(self, facts: list[Fact]) -> None:
        try:
            import networkx as nx  # noqa: PLC0415
            if self.g is None:
                self.g = nx.DiGraph()
        except Exception:  # noqa: BLE001 - graph store is optional
            pass
        for f in facts:
            self.facts.append(f)
            self._by_item.setdefault(f.key, {})[f.year] = f
            if self.g is not None:
                item = f"item:{f.statement}:{f.code}"
                period = f"period:{f.year}"
                node = f"fact:{f.statement}:{f.code}:{f.year}"
                self.g.add_node(item, kind="line_item", label=f.label, statement=f.statement)
                self.g.add_node(period, kind="period", year=f.year)
                self.g.add_node(node, kind="fact", value=f.value, raw=f.value_raw, unit=f.unit)
                self.g.add_edge(node, item, rel="OF_ITEM")
                self.g.add_edge(node, period, rel="IN_PERIOD")

    def series(self, statement: str, code: str) -> list[Fact]:
        """All values of one line item across periods, oldest → newest."""
        return [self._by_item[(statement, code)][y]
                for y in sorted(self._by_item.get((statement, code), {}))]

    def years(self) -> list[int]:
        return sorted({f.year for f in self.facts})

    def find_items(self, statement: str | None = None) -> list[tuple[str, str, str]]:
        """(statement, code, label) for every line item the graph knows."""
        out = []
        for (stmt, code), per in self._by_item.items():
            if statement and stmt != statement:
                continue
            any_fact = next(iter(per.values()))
            out.append((stmt, code, any_fact.label))
        return out


def verify_consistency(facts_by_year: dict[int, list[Fact]],
                       prior_by_year: dict[int, dict[tuple[str, str], str]]) -> dict:
    """Auto-validate extraction: report year Y's current value must equal report
    Y+1's prior value for the same line item. Returns per-item agreement so the
    dataset generator can keep only consistently-extracted facts.
    """
    agree: dict[tuple[str, str], bool] = {}
    checks = 0
    for y, facts in facts_by_year.items():
        nxt = prior_by_year.get(y + 1)
        if not nxt:
            continue
        for f in facts:
            if f.key in nxt:
                checks += 1
                ok = re.sub(r"[^\d]", "", f.value_raw) == re.sub(r"[^\d]", "", nxt[f.key])
                agree[f.key] = agree.get(f.key, True) and ok
    return {"agree": agree, "checks": checks}
