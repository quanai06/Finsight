#!/usr/bin/env python3
"""Generate the Finsight multi-year financial QA benchmark (v2, ~500 questions).

Every numeric question is grounded in a value extracted *deterministically* from
the Vingroup statement tables (`src/rag/financial_facts.py`) — so the ground truth
is exact, never hallucinated. Facts are kept only if they pass the cross-report
consistency check (report Y "current" == report Y+1 "prior"), giving an
automatically-verified gold set.

Question variety (mixing số + chữ, deliberately a bit harder than v1):
  * single-year lookup            (numeric_single)
  * year-over-year change         (numeric_compare)
  * multi-year trend, cross-file  (multi_year)      ← the Graph-RAG questions
  * growth / which-year-extreme   (reasoning)
  * derived ratios (margins)      (reasoning)
  * carried-over verified text Q  (factual / policy / unanswerable, from v1)

Run:  python -m benchmark.rag.build_dataset
Out:  data/rag/finsight_finqa_eval_v2.jsonl
"""

from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.rag.financial_facts import (  # noqa: E402
    FinancialFactGraph,
    extract_facts_from_tables,
    extract_prior,
    verify_consistency,
)

_TABLES = str(_REPO_ROOT / "data" / "processed" / "ocr_clean" / "2*_tables.json")
_V1 = _REPO_ROOT / "data" / "rag" / "finsight_finqa_eval_v1.jsonl"
_OUT = _REPO_ROOT / "data" / "rag" / "finsight_finqa_eval_v2.jsonl"

# Headline items used for trend / ratio / extreme questions (the meaningful ones).
_HEADLINE = [
    ("kqkd", "01"), ("kqkd", "10"), ("kqkd", "11"), ("kqkd", "20"),
    ("kqkd", "21"), ("kqkd", "22"), ("kqkd", "25"), ("kqkd", "26"),
    ("kqkd", "50"), ("kqkd", "60"), ("kqkd", "61"),
    ("cdkt_ts", "100"), ("cdkt_ts", "110"), ("cdkt_ts", "140"),
    ("cdkt_nv", "300"), ("cdkt_nv", "400"), ("cdkt_nv", "440"),
]


def _fmt(fact) -> str:
    """Signed, human-readable value with unit."""
    if fact.value < 0:
        return f"âm {fact.value_raw.strip('()')} {fact.unit}"
    return f"{fact.value_raw} {fact.unit}"


def _period_phrase(stmt: str, year: int) -> str:
    return f"tại ngày 31/12/{year}" if stmt.startswith("cdkt") else f"năm {year}"


def _direction(curr: float, prev: float) -> str:
    if curr > prev:
        return "tăng"
    if curr < prev:
        return "giảm"
    return "không đổi"


def build() -> list[dict]:
    files = {int(os.path.basename(f)[:4]): f for f in sorted(glob.glob(_TABLES))}
    facts_by_year, prior_by_year = {}, {}
    g = FinancialFactGraph()
    for y, f in files.items():
        tabs = json.load(open(f, encoding="utf-8"))["tables"]
        fc = extract_facts_from_tables(tabs, y)
        facts_by_year[y] = fc
        prior_by_year[y] = extract_prior(tabs)
        g.add(fc)

    # keep only line items whose extraction is cross-report consistent
    v = verify_consistency(facts_by_year, prior_by_year)
    bad = {k for k, ok in v["agree"].items() if not ok}

    items: list[dict] = []
    n = [0]

    def add(qid_kind, q, gt, atype, stmt, years, golds, diff, lang="vi"):
        n[0] += 1
        q = q[0].upper() + q[1:] if q else q  # sentence-case the question
        items.append({
            "id": f"fin2-{n[0]:03d}",
            "question": q,
            "ground_truth": gt,
            "answer_type": atype,
            "statement_type": stmt,
            "relevant_years": years,
            "gold_numbers": golds,
            "difficulty": diff,
            "lang": lang,
        })

    # ---- 1. single-year lookups (varied phrasings) -------------------------
    lookup_templates = [
        "{label} của Vingroup {period} là bao nhiêu?",
        "Cho biết {label} của Tập đoàn Vingroup {period}.",
        "Giá trị {label} {period} trên báo cáo hợp nhất của Vingroup là bao nhiêu?",
    ]
    for i, (stmt, code) in enumerate(sorted(g._by_item)):
        if (stmt, code) in bad:
            continue
        for fact in g.series(stmt, code):
            tmpl = lookup_templates[(i + fact.year) % len(lookup_templates)]
            period = _period_phrase(stmt, fact.year)
            label = fact.label
            q = tmpl.format(label=label[0].lower() + label[1:], period=period)
            gt = f"{label} {period} là {_fmt(fact)}."
            add("lookup", q, gt, "numeric_single", stmt, [fact.year],
                [fact.value_raw.strip("()")], "easy" if code in {"01", "10", "440"} else "medium")

    # ---- 2. year-over-year change (all consistent items) -------------------
    for stmt, code in sorted(g._by_item):
        if (stmt, code) in bad or stmt.startswith("cdkt"):
            continue  # balance-sheet items handled as đầu-năm/cuối-năm below
        s = g.series(stmt, code)
        for a, b in zip(s, s[1:]):
            d = _direction(b.value, a.value)
            label = b.label
            q = (f"{label[0].upper() + label[1:]} của Vingroup năm {b.year} thay đổi "
                 f"thế nào so với năm {a.year}?")
            gt = (f"{label} năm {b.year} là {_fmt(b)}, {d} so với {_fmt(a)} năm {a.year}.")
            add("yoy", q, gt, "numeric_compare", stmt, [a.year, b.year],
                [b.value_raw.strip("()"), a.value_raw.strip("()")], "medium")

    # ---- 3. multi-year trend (cross-file, Graph-RAG) — all items -----------
    for stmt, code in sorted(g._by_item):
        if (stmt, code) in bad:
            continue
        s = g.series(stmt, code)
        if len(s) < 4:
            continue
        label = s[0].label
        yrs = [f.year for f in s]
        q = (f"{label[0].upper() + label[1:]} của Vingroup các năm "
             f"{yrs[0]}–{yrs[-1]} lần lượt là bao nhiêu?")
        parts = ", ".join(f"năm {f.year}: {f.value_raw.strip('()')}" for f in s)
        gt = f"{label} qua các năm ({s[0].unit}) — {parts}."
        add("trend", q, gt, "multi_year", stmt, yrs,
            [f.value_raw.strip("()") for f in s], "hard")

    # ---- 4. growth multiple + which-year extreme (reasoning) ---------------
    for stmt, code in _HEADLINE:
        if (stmt, code) in bad:
            continue
        s = g.series(stmt, code)
        if len(s) < 4:
            continue
        first, last = s[0], s[-1]
        label = first.label
        if first.value > 0 and last.value > 0:
            mult = last.value / first.value
            q = (f"{label[0].upper() + label[1:]} của Vingroup năm {last.year} gấp "
                 f"khoảng bao nhiêu lần năm {first.year}?")
            gt = (f"{label} tăng từ {first.value_raw} ({first.year}) lên {last.value_raw} "
                  f"({last.year}), tức khoảng {mult:.1f} lần.")
            add("growth", q, gt, "reasoning", stmt, [first.year, last.year],
                [first.value_raw.strip("()"), last.value_raw.strip("()")], "hard")
        # which year is the maximum
        mx = max(s, key=lambda f: f.value)
        q = (f"Trong giai đoạn {s[0].year}–{s[-1].year}, năm nào Vingroup có "
             f"{label[0].lower() + label[1:]} cao nhất?")
        gt = f"Cao nhất vào năm {mx.year} với {_fmt(mx)}."
        add("argmax", q, gt, "reasoning", stmt, [f.year for f in s],
            [mx.value_raw.strip("()")], "hard")

    # ---- 5. derived ratios: gross & net margin (reasoning) -----------------
    for stmt_pair, name in [(("20", "10"), "Biên lợi nhuận gộp"),
                            (("60", "10"), "Biên lợi nhuận ròng")]:
        num_c, den_c = stmt_pair
        for fy in g.series("kqkd", num_c):
            den = {f.year: f for f in g.series("kqkd", den_c)}.get(fy.year)
            if not den or den.value == 0:
                continue
            margin = fy.value / den.value * 100
            q = f"{name} của Vingroup năm {fy.year} xấp xỉ bao nhiêu phần trăm?"
            gt = (f"{name} năm {fy.year} ≈ {margin:.1f}% "
                  f"({fy.label.lower()} {fy.value_raw} / {den.label.lower()} {den.value_raw}).")
            add("ratio", q, gt, "reasoning", "kqkd", [fy.year],
                [fy.value_raw.strip("()"), den.value_raw.strip("()")], "hard")

    # ---- 5b. balance-sheet đầu-năm vs cuối-năm change ----------------------
    for stmt in ("cdkt_ts", "cdkt_nv"):
        for code in sorted({c for (st, c) in g._by_item if st == stmt}):
            if (stmt, code) in bad:
                continue
            for fact in g.series(stmt, code):
                # report's prior column is the same year's opening balance
                prior_raw = prior_by_year.get(fact.year, {}).get((stmt, code))
                if not prior_raw:
                    continue
                label = fact.label
                q = (f"{label[0].upper() + label[1:]} của Vingroup cuối năm {fact.year} so với "
                     f"đầu năm {fact.year} thay đổi thế nào?")
                gt = (f"{label} cuối năm {fact.year} là {_fmt(fact)}, so với {prior_raw} "
                      f"triệu VND đầu năm.")
                add("bs_change", q, gt, "numeric_compare", stmt, [fact.year],
                    [fact.value_raw.strip("()"), prior_raw.strip("()")], "medium")

    # ---- 5c. English cross-lingual lookups for headline items --------------
    _EN = {
        "10": "net revenue from sales of goods and services",
        "20": "gross profit", "50": "profit before tax",
        "60": "profit after tax", "440": "total resources (equals total assets)",
        "100": "current assets", "400": "owners' equity",
    }
    for (stmt, code), en in (((s, c), _EN[c]) for (s, c) in _HEADLINE if c in _EN):
        if (stmt, code) in bad:
            continue
        for fact in g.series(stmt, code):
            q = f"What was Vingroup's {en} in {fact.year}?"
            gt = f"{en.capitalize()} in {fact.year} was {fact.value_raw} {fact.unit}."
            add("en_lookup", q, gt, "numeric_single", stmt, [fact.year],
                [fact.value_raw.strip("()")], "medium", lang="en")

    # ---- 5d. absolute YoY delta (computed, reasoning) ----------------------
    for stmt, code in _HEADLINE:
        if (stmt, code) in bad or stmt.startswith("cdkt"):
            continue
        s = g.series(stmt, code)
        for a, b in zip(s, s[1:]):
            delta = b.value - a.value
            label = b.label
            d = "tăng" if delta > 0 else "giảm"
            q = (f"{label[0].upper() + label[1:]} của Vingroup năm {b.year} {d} bao nhiêu "
                 f"triệu VND so với năm {a.year}?")
            gt = (f"{label} {d} khoảng {abs(int(delta)):,}".replace(",", ".")
                  + f" triệu VND ({b.value_raw} năm {b.year} so với {a.value_raw} năm {a.year}).")
            add("delta", q, gt, "reasoning", stmt, [a.year, b.year],
                [b.value_raw.strip("()"), a.value_raw.strip("()")], "hard")

    # ---- 6. carry over verified TEXT questions from v1 ----------------------
    carried = 0
    for line in _V1.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["answer_type"] in ("factual", "policy", "reasoning", "unanswerable"):
            n[0] += 1
            r2 = {
                "id": f"fin2-{n[0]:03d}",
                "question": r["question"],
                "ground_truth": r["ground_truth"],
                "answer_type": r["answer_type"],
                "statement_type": r["statement_type"],
                "relevant_years": [r["year"]] if r["year"] else [],
                "gold_numbers": r["gold_numbers"],
                "difficulty": r["difficulty"],
                "lang": r["lang"],
            }
            items.append(r2)
            carried += 1
    print(f"[build] carried {carried} verified text questions from v1")
    return items


def main() -> int:
    items = build()
    # dedup by question text (keep first), then re-id for a clean sequence
    seen, deduped = set(), []
    for it in items:
        key = it["question"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        it["id"] = f"fin2-{len(deduped) + 1:03d}"
        deduped.append(it)
    items = deduped
    with open(_OUT, "w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    import collections
    print(f"[build] wrote {len(items)} questions -> {_OUT}")
    print("[build] by type:", dict(collections.Counter(i["answer_type"] for i in items)))
    print("[build] by difficulty:", dict(collections.Counter(i["difficulty"] for i in items)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
