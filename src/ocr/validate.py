"""Validate OCR'd financial tables — flag suspicious numeric cells for review.

Runs three tiers of checks over the ``*_tables.json`` files produced by
``postprocess`` and writes a report listing each flagged cell with its location
and reason. It never edits data — a human reviews the flagged cells against the
source PDF.

Tier 1 (structural):   adjacent duplicate numbers · large number in the
                       "Thuyết minh" reference column · ragged rows.
Tier 2 (arithmetic):   income-statement identities by Mã số
                       (10 = 01 + 02,  20 = 10 + 11,  60 = 50 + 51 + 52).
Tier 3 (cross-year):   a line item's prior-year column in year N must equal its
                       current-year column in year N-1 (independent redundancy).

CLI:
    python -m src.ocr.validate --input data/processed/ocr_clean \
        --out benchmark/validation_report.md
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path

# ------------------------------------------------------------------ parsing

_NUM_BODY = re.compile(r"-?\d[\d.]*(?:,\d+)?")


def parse_number(cell: str) -> float | None:
    """Parse a Vietnamese-formatted financial cell -> float, else None.

    '125.780.761' -> 125780761.0 ; '(92.891)' -> -92891.0 ; '30.1' -> 30.1? no:
    dotted groups are thousands, so '30.1' is treated as a ref, not a number here
    -> we only accept it as a number; ambiguity handled by callers via magnitude.
    """
    s = (cell or "").strip()
    if not s:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").strip()
    if not _NUM_BODY.fullmatch(s):
        return None
    s = s.replace(".", "").replace(",", ".")  # thousands '.' out, decimal ',' -> '.'
    try:
        val = float(s)
    except ValueError:
        return None
    return -val if neg else val


def is_ma_so(cell: str) -> bool:
    return bool(re.fullmatch(r"\d{1,3}", (cell or "").strip()))


def norm_label(s: str) -> str:
    s = unicodedata.normalize("NFC", (s or "").lower())
    s = re.sub(r"^\s*\d+[.)]\s*", "", s)       # drop leading "1." / "2)" numbering
    return re.sub(r"\s+", " ", s).strip()


def _find_col(header: list[str], *keywords: str) -> int | None:
    for i, h in enumerate(header):
        hl = norm_label(h)
        if any(k in hl for k in keywords):
            return i
    return None


# ------------------------------------------------------------------ findings

@dataclass(slots=True)
class Finding:
    file: str
    table: int
    row: int
    ma_so: str
    label: str
    column: str
    value: str
    rule: str
    severity: str
    detail: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _fmt(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".") if v == int(v) else str(v)


# ------------------------------------------------------------------ Tier 1

def tier1_structural(file: str, tidx: int, table: dict) -> list[Finding]:
    out: list[Finding] = []
    header = table.get("header", [])
    ncols = table.get("n_cols", len(header))
    tm_idx = _find_col(header, "thuyết minh", "thuyet minh")
    rows = table.get("rows", [])

    for r, row in enumerate(rows):
        ma = row[0] if row and is_ma_so(row[0]) else ""
        label = max((c for c in row), key=len, default="")[:60]

        nums = [(i, parse_number(c)) for i, c in enumerate(row)]
        n_numeric = sum(1 for _, v in nums if v is not None)

        # ragged row — only data rows (>=2 numbers), section headers are ignored
        if len(row) != ncols and n_numeric >= 2:
            out.append(Finding(file, tidx, r, ma, label, f"{len(row)}/{ncols} cols",
                               "", "ragged_row", "low",
                               "số cột khác header → bảng có thể bị vỡ"))

        # large number in the "Thuyết minh" reference column
        if tm_idx is not None and tm_idx < len(row):
            v = parse_number(row[tm_idx])
            if v is not None and abs(v) >= 1000:
                out.append(Finding(file, tidx, r, ma, label, "Thuyết minh",
                                   row[tm_idx], "big_num_in_ref_col", "high",
                                   "cột Thuyết minh chứa số lớn → OCR điền nhầm ô"))

        # adjacent duplicate large numbers
        for (i1, v1), (i2, v2) in zip(nums, nums[1:]):
            if v1 is not None and v2 is not None and v1 == v2 and abs(v1) >= 1000:
                out.append(Finding(file, tidx, r, ma, label,
                                   f"cols {i1},{i2}", _fmt(v1),
                                   "adjacent_duplicate", "high",
                                   "hai ô số kề nhau trùng giá trị"))
                break
    return out


# ------------------------------------------------------------------ Tier 2

# income-statement identities: result = sum(operands), operands already signed
_IS_IDENTITIES = [("10", ["01", "02"]), ("20", ["10", "11"]),
                  ("60", ["50", "51", "52"])]


def tier2_income_statement(file: str, tidx: int, table: dict) -> list[Finding]:
    header = table.get("header", [])
    cur = _find_col(header, "năm nay", "nam nay")
    if cur is None:
        return []
    rows = table.get("rows", [])
    by_ma: dict[str, float] = {}
    label_of: dict[str, str] = {}
    for row in rows:
        if row and is_ma_so(row[0]) and cur < len(row):
            v = parse_number(row[cur])
            if v is not None:
                by_ma[row[0].strip()] = v
                label_of[row[0].strip()] = max((c for c in row), key=len, default="")[:50]

    # only treat as an income statement if the key codes are present AND
    # code 01's label is revenue ("doanh thu") — this excludes the cash-flow
    # statement, which reuses codes 01/10/20 with a different meaning
    if not {"01", "10", "20"} <= by_ma.keys():
        return []
    if "doanh thu" not in norm_label(label_of.get("01", "")):
        return []

    out: list[Finding] = []
    for result, operands in _IS_IDENTITIES:
        if result in by_ma and all(o in by_ma for o in operands):
            expect = sum(by_ma[o] for o in operands)
            got = by_ma[result]
            if abs(expect - got) > 1:  # tolerance 1 (rounding to triệu)
                out.append(Finding(file, tidx, -1, result, label_of.get(result, ""),
                                   "Năm nay", _fmt(got), "arithmetic_mismatch", "medium",
                                   f"kỳ vọng {'+'.join(operands)}={_fmt(expect)}, OCR={_fmt(got)}"))
    return out


# ------------------------------------------------------------------ Tier 3

def _collect_comparatives(file_tables: list[dict]) -> dict[str, tuple[float, float]]:
    """label -> (current, prior).

    Only keeps labels that are **globally unique** within the year: the same
    label text appearing in more than one place (e.g. once in the balance sheet
    and once in a cash-flow note, with different numbers) is dropped, since we
    can't tell which one to compare across years.
    """
    pairs: dict[str, set[tuple[float, float]]] = {}
    for table in file_tables:
        header = table.get("header", [])
        cur = _find_col(header, "năm nay", "nam nay", "số cuối", "so cuoi")
        pri = _find_col(header, "năm trước", "nam truoc", "số đầu", "so dau")
        if cur is None or pri is None:
            continue
        for row in table.get("rows", []):
            if max(cur, pri) >= len(row):
                continue
            cv, pv = parse_number(row[cur]), parse_number(row[pri])
            if cv is None or pv is None or abs(cv) < 1000:
                continue
            others = [c for i, c in enumerate(row) if i not in (cur, pri)]
            label = norm_label(max(others, key=len, default=""))
            if len(label) < 12:          # require a descriptive, distinctive label
                continue
            pairs.setdefault(label, set()).add((cv, pv))
    # keep only labels with a single, unambiguous value pair
    return {lbl: next(iter(vs)) for lbl, vs in pairs.items() if len(vs) == 1}


def tier3_cross_year(by_year: dict[str, list[dict]]) -> list[Finding]:
    years = sorted(by_year)
    out: list[Finding] = []
    comps = {y: _collect_comparatives(by_year[y]) for y in years}
    for prev, cur in zip(years, years[1:]):
        cprev, ccur = comps[prev], comps[cur]
        for label, (cur_now, cur_prior) in ccur.items():
            if label in cprev:
                prev_current = cprev[label][0]      # year prev "current"
                if cur_prior != prev_current:
                    out.append(Finding(
                        cur, -1, -1, "", label[:50], f"Năm trước (vs {prev})",
                        _fmt(cur_prior), "cross_year_mismatch", "high",
                        f"{cur} 'năm trước'={_fmt(cur_prior)} ≠ {prev} 'năm nay'="
                        f"{_fmt(prev_current)} (có thể do trình bày lại)"))
    return out


# ------------------------------------------------------------------ runner

def run(input_dir: str, pattern: str = "*_tables.json") -> dict:
    files = sorted(Path(input_dir).glob(pattern))
    by_year: dict[str, list[dict]] = {}
    findings: list[Finding] = []

    for fp in files:
        year = re.match(r"(\d{4})", fp.name)
        key = year.group(1) if year else fp.stem
        tables = json.loads(fp.read_text(encoding="utf-8")).get("tables", [])
        by_year[key] = tables
        for tidx, table in enumerate(tables):
            findings += tier1_structural(key, tidx, table)
            findings += tier2_income_statement(key, tidx, table)

    findings += tier3_cross_year(by_year)

    sev_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (sev_order.get(f.severity, 9), f.file, f.table, f.row))
    return {"files": [f.name for f in files], "by_year_tables":
            {y: len(t) for y, t in by_year.items()}, "findings": findings}


def _report_md(result: dict) -> str:
    f = result["findings"]
    by_rule: dict[str, int] = {}
    by_sev: dict[str, int] = {}
    for x in f:
        by_rule[x.rule] = by_rule.get(x.rule, 0) + 1
        by_sev[x.severity] = by_sev.get(x.severity, 0) + 1
    lines = [
        "# OCR Number Validation Report",
        f"Tables scanned: {sum(result['by_year_tables'].values())} "
        f"across {len(result['files'])} file(s) — {result['by_year_tables']}",
        f"**Flagged cells: {len(f)}**  "
        f"(high {by_sev.get('high',0)}, medium {by_sev.get('medium',0)}, "
        f"low {by_sev.get('low',0)})",
        "",
        "## By rule",
        "| Rule | Count |", "|---|---|",
        *[f"| {k} | {v} |" for k, v in sorted(by_rule.items(), key=lambda i: -i[1])],
        "",
        "## Flagged cells (review these against the PDF)",
        "| sev | file | table | row(Mã) | column | value | rule | detail |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for x in f:
        row = x.ma_so or (x.label[:28] if x.row == -1 else str(x.row))
        lines.append(
            f"| {x.severity} | {x.file} | {x.table if x.table>=0 else '-'} | {row} "
            f"| {x.column} | {x.value} | {x.rule} | {x.detail} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m src.ocr.validate")
    ap.add_argument("--input", default="data/processed/ocr_clean")
    ap.add_argument("--pattern", default="*_tables.json")
    ap.add_argument("--out", default="benchmark/validation_report.md")
    args = ap.parse_args(argv)

    result = run(args.input, args.pattern)
    out_md = Path(args.out)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(_report_md(result), encoding="utf-8")
    out_csv = out_md.with_suffix(".csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["severity", "file", "table", "row", "ma_so", "label",
                    "column", "value", "rule", "detail"])
        for x in result["findings"]:
            w.writerow([x.severity, x.file, x.table, x.row, x.ma_so, x.label,
                        x.column, x.value, x.rule, x.detail])

    f = result["findings"]
    hi = sum(1 for x in f if x.severity == "high")
    print(f"Flagged {len(f)} cell(s) — {hi} high. Report: {out_md} (+ .csv)")
    print("\nTop high-severity:")
    for x in [x for x in f if x.severity == "high"][:12]:
        print(f"  [{x.file} t{x.table} {x.ma_so or x.label[:20]}] {x.rule}: "
              f"{x.value}  — {x.detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
