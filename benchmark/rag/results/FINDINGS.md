# Finsight RAG — Benchmark Findings (2026-06-22)

Record of what the v2 benchmark measured and the improvements it drove. The RAGAS
LLM-judge pass was deferred (stopped before completion); deterministic + retrieval
metrics below are complete.

## Setup
- Dataset: `data/rag/finsight_finqa_eval_v2.jsonl` — 483 questions, 2021–2025,
  auto-generated from statement tables, gold verified by cross-report consistency.
- Corpus: `data/rag/corpus/` — 5 years of Vingroup BCTC (561 chunks indexed).
- Pipeline: hybrid (e5-large dense + BM25) + RRF + routing + **Graph-RAG** + MMR,
  Groq `llama-3.3-70b`. CPU-only.

## v2 retrieval baseline (first full run, before the Graph-RAG fix)
Overall: number-grounded context recall **0.486**, period coverage **0.658**.

| Type | n | CtxRecall# | YearCov |
|---|---|---|---|
| factual | 15 | 1.000 | 1.000 |
| policy | 13 | 1.000 | 1.000 |
| numeric_single | 195 | 0.713 | 0.995 |
| numeric_compare | 140 | 0.393 | 0.486 |
| multi_year | 32 | 0.156 | 0.250 |
| reasoning | 81 | 0.148 | 0.185 |

Read: single-year routing is strong (year coverage ~1.0); the weak spot is
**multi-period** questions (multi_year, and the 2-year numeric_compare/reasoning).

## Two bugs the benchmark caught (now fixed)
1. **`relative_to` crash** in `evaluate_rag.py` — a relative `--dataset` path made
   report-writing throw *after* all the work was done. Fixed with a `_rel()` helper.
2. **Graph-RAG cross-period fan-out was being neutralised** — the statement-type
   routing filter emptied each per-year search on the (untagged) rendered-table
   corpus, so multi-year questions silently fell back to a single search; and MMR's
   diversity penalty then dropped the same-line-item-across-years chunks. Fixed in
   `src/rag/graph_retrieval.py` (per-year filter degradation) + `src/rag/pipeline.py`
   (multi-period keeps the year-balanced order instead of MMR; top_k scales with #years).

## Validated improvement (multi_year subset, A/B)
| multi_year (32 Q) | Graph OFF | Graph ON (fixed) |
|---|---|---|
| Period coverage | 0.419 | **1.000** |
| Number-grounded context recall | 0.445 | **0.692** |

→ "doanh thu các năm 2021–2025" now retrieves every year's figure. The same fix
also benefits the 140 two-year `numeric_compare` questions (not re-measured in full).

## Deferred
- Full v2 retrieval re-run with the fix (to refresh the overall table) — stopped.
- RAGAS LLM-judge pass (faithfulness / answer relevancy / answer correctness /
  context precision-recall) on the stratified 49-item sample — stopped. Harness is
  ready: `python -m benchmark.rag.evaluate_rag --judge --judge-sample 49`.
