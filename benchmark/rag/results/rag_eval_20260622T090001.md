# Finsight RAG Benchmark — Report

- Run: `2026-06-22T09:00:01+00:00`
- Dataset: `data/rag/finsight_finqa_eval_v1.jsonl` (112 questions)
- Corpus: `data/rag/corpus/vingroup_2021_bctc_hop_nhat.md` (43 chunks indexed)
- Mode: retrieval-only  |  Hybrid: True  |  Routing: True
- Model: `intfloat/multilingual-e5-large` (dense) + BM25  →  `llama-3.3-70b-versatile`
- Wall time: 67.3s

## Retrieval (answerable questions)

| k | Recall@k | Precision@k | Hit@k | nDCG@k |
|---|---|---|---|---|
| 1 | 0.652 | 0.667 | 0.667 | 0.667 |
| 3 | 0.981 | 0.337 | 0.981 | 0.857 |
| 5 | 1.000 | 0.206 | 1.000 | 0.865 |
| 8 | 1.000 | 0.151 | 1.000 | 0.865 |

- **MRR**: 0.818   **MAP**: 0.818

## Breakdown by question type

| Type | n | Recall@5 | MRR | NumExact | TokenF1 | Correctness | Abstain✓ | FalseAbstain |
|---|---|---|---|---|---|---|---|---|
| factual | 15 | 1.000 | 0.900 | — | — | — | — | — |
| numeric_compare | 12 | 1.000 | 0.792 | — | — | — | — | — |
| numeric_single | 62 | 1.000 | 0.783 | — | — | — | — | — |
| policy | 13 | 1.000 | 0.962 | — | — | — | — | — |
| reasoning | 3 | 1.000 | 0.611 | — | — | — | — | — |
| unanswerable | 7 | — | — | — | — | — | — | — |
