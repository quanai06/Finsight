"""Run OCR evaluation for given pages and save a benchmark.

Pairs each predicted page (OCR output) with its golden reference, computes the
metrics in ``ocr_metrics``, prints a table, and writes JSON + Markdown reports
into ``benchmark/``.

Usage:
    python -m tests.ocr.evaluate                      # default: pages 13,14
    python -m tests.ocr.evaluate --pages 13 14 15 16
    python -m tests.ocr.evaluate --doc 2021_bctc_hop_nhat --pages 13 14
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ocr_metrics import OCRScore, evaluate_pair

PRED_DIR = "data/processed/ocr/{doc}_pages"
GOLD_DIR = "data/golden/{doc}"
BENCH_DIR = Path("benchmark")


def _load(doc: str, page: int) -> tuple[str | None, str | None]:
    pred = Path(PRED_DIR.format(doc=doc)) / f"page_{page:03d}.md"
    gold = Path(GOLD_DIR.format(doc=doc)) / f"page_{page:03d}.md"
    p = pred.read_text(encoding="utf-8") if pred.exists() else None
    g = gold.read_text(encoding="utf-8") if gold.exists() else None
    return p, g


def _mean(scores: list[OCRScore], attr: str) -> float:
    vals = [getattr(s, attr) for s in scores]
    return round(sum(vals) / len(vals), 4) if vals else 0.0


def _micro_number_f1(scores: list[OCRScore]) -> dict:
    matched = sum(s.numbers_matched for s in scores)
    pred = sum(s.pred_numbers for s in scores)
    gold = sum(s.gold_numbers for s in scores)
    p = matched / pred if pred else 0.0
    r = matched / gold if gold else 0.0
    f1 = (2 * p * r / (p + r)) if (p + r) else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4),
            "f1": round(f1, 4), "matched": matched, "pred": pred, "gold": gold}


def run(doc: str, pages: list[int]) -> dict:
    per_page: dict[str, dict] = {}
    scores: list[OCRScore] = []
    skipped: list[int] = []

    for pg in pages:
        pred, gold = _load(doc, pg)
        if pred is None or gold is None:
            skipped.append(pg)
            continue
        score = evaluate_pair(pred, gold)
        per_page[f"page_{pg:03d}"] = score.as_dict()
        scores.append(score)

    aggregate = {
        "pages_scored": len(scores),
        "pages_skipped": skipped,
        "macro_cer": _mean(scores, "cer"),
        "macro_char_accuracy": _mean(scores, "char_accuracy"),
        "macro_wer": _mean(scores, "wer"),
        "macro_word_f1": _mean(scores, "word_f1"),
        "macro_similarity": _mean(scores, "similarity"),
        "macro_number_f1": _mean(scores, "number_f1"),
        "micro_number": _micro_number_f1(scores),
    }
    return {"doc": doc, "pages": pages, "aggregate": aggregate, "per_page": per_page}


def _markdown_report(result: dict) -> str:
    agg = result["aggregate"]
    lines = [
        f"# OCR Benchmark — {result['doc']}",
        f"Pages: {result['pages']}  |  scored: {agg['pages_scored']}  "
        f"|  skipped: {agg['pages_skipped']}",
        "",
        "## Aggregate",
        "| Metric | Value |",
        "|---|---|",
        f"| Char accuracy (1-CER) | {agg['macro_char_accuracy']:.2%} |",
        f"| CER | {agg['macro_cer']:.2%} |",
        f"| WER | {agg['macro_wer']:.2%} |",
        f"| Word F1 | {agg['macro_word_f1']:.2%} |",
        f"| Similarity | {agg['macro_similarity']:.2%} |",
        f"| **Number F1 (macro)** | **{agg['macro_number_f1']:.2%}** |",
        f"| Number P/R (micro) | {agg['micro_number']['precision']:.2%} / "
        f"{agg['micro_number']['recall']:.2%} "
        f"({agg['micro_number']['matched']}/{agg['micro_number']['gold']}) |",
        "",
        "## Per page",
        "| Page | CharAcc | CER | WER | WordF1 | NumF1 | Num matched |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, s in result["per_page"].items():
        lines.append(
            f"| {name} | {s['char_accuracy']:.2%} | {s['cer']:.2%} | {s['wer']:.2%} "
            f"| {s['word_f1']:.2%} | {s['number_f1']:.2%} "
            f"| {s['numbers_matched']}/{s['gold_numbers']} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tests.ocr.evaluate")
    ap.add_argument("--doc", default="2021_bctc_hop_nhat")
    ap.add_argument("--pages", type=int, nargs="+", default=[13, 14])
    ap.add_argument("--out", default="ocr_benchmark")
    args = ap.parse_args(argv)

    result = run(args.doc, args.pages)
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"{args.out}_{args.doc}_p{args.pages[0]}-{args.pages[-1]}"
    (BENCH_DIR / f"{stem}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    report = _markdown_report(result)
    (BENCH_DIR / f"{stem}.md").write_text(report, encoding="utf-8")

    print(report)
    print(f"saved: {BENCH_DIR / stem}.json  and  .md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
