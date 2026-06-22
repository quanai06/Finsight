# Finsight RAG Evaluation Data

Everything needed to evaluate Finsight's RAG pipeline on **Vietnamese financial
statements**: a verified corpus, a labelled Q&A set, and the research that decided
which metrics to use. The runnable harness lives in `benchmark/rag/`.

```
data/rag/
├── README.md                          # this file
├── EVALUATION_METHODS.md              # survey of RAG eval methods + Finsight fit
├── corpus/
│   └── vingroup_2021_bctc_hop_nhat.md # the verified document under test
└── finsight_finqa_eval_v1.jsonl       # 112 labelled questions
```

## Corpus

`corpus/vingroup_2021_bctc_hop_nhat.md` is the Vingroup (VIC) **2021 consolidated
financial statements** — balance sheet, income statement, cash-flow statement and
notes — reconstructed from the project's **human-verified gold OCR**
(`data/golden/2021_bctc_hop_nhat/`, plus the audited balance-sheet figures from
`data/processed/`). Numbers were cross-checked against the gold pages, so every
ground-truth answer is exact.

Each section carries a `<!-- ===== page N ===== -->` marker (PDF page numbers),
which is what `src/rag/chunking.py` reads to tag chunks with a `page`. That makes
**page-level retrieval labels** possible: a question's `relevant_pages` is checked
against the pages of the chunks the retriever returns.

## Q&A dataset — `finsight_finqa_eval_v1.jsonl`

112 questions (JSON Lines, UTF-8). Grounded line-by-line in the corpus and
designed to stress the things finance RAG actually gets wrong: pulling an **exact
figure** from a table, picking the **right year/column**, reading an **accounting
policy**, and **abstaining** when the document doesn't hold the answer.

### Schema

| field | type | meaning |
|---|---|---|
| `id` | str | stable id, `fin-001 …` |
| `question` | str | the question (mostly Vietnamese, 7 English for cross-lingual) |
| `ground_truth` | str | reference answer (exact figure + unit + period) |
| `answer_type` | str | `numeric_single` · `numeric_compare` · `factual` · `policy` · `reasoning` · `unanswerable` |
| `statement_type` | str | `cdkt` (balance) · `kqkd` (P&L) · `lctt` (cash flow) · `thuyet_minh` (notes) · `thong_tin_chung` |
| `note_no` | int/null | thuyết-minh note number when relevant (matches the routing layer) |
| `year` | int | period the question targets |
| `unit` | str | `triệu VND` · `VND` · `năm` · `người` · `công ty` · "" |
| `relevant_pages` | int[] | corpus pages that contain the answer (retrieval gold); empty for `unanswerable` |
| `gold_numbers` | str[] | the exact figures that must appear in a correct answer (numeric scoring) |
| `difficulty` | str | `easy` · `medium` · `hard` |
| `lang` | str | `vi` · `en` |

### Composition

- **62** `numeric_single` — one figure from a statement (the core skill)
- **12** `numeric_compare` — year-over-year / cross-line comparison
- **15** `factual` — company info, board, auditor, key events
- **13** `policy` — accounting-policy questions from the notes
- **3** `reasoning` — multi-figure interpretation
- **7** `unanswerable` — answer not in the corpus → the system should refuse

Statement coverage: P&L 33 · balance sheet 24 · notes 26 · cash flow 22 ·
general info 5. Difficulty: easy 23 · medium 61 · hard 28.

### Example

```json
{"id": "fin-001", "question": "Doanh thu bán hàng và cung cấp dịch vụ của Vingroup năm 2021 là bao nhiêu?",
 "ground_truth": "Doanh thu bán hàng và cung cấp dịch vụ năm 2021 là 125.780.761 triệu VND.",
 "answer_type": "numeric_single", "statement_type": "kqkd", "note_no": null, "year": 2021,
 "unit": "triệu VND", "relevant_pages": [13], "gold_numbers": ["125.780.761"],
 "difficulty": "easy", "lang": "vi"}
```

## How it's used

`benchmark/rag/evaluate_rag.py` indexes the corpus into a throwaway session via the
**real** `src/rag` pipeline, asks every question, and scores:

- **retrieval** — Recall@k / Precision@k / Hit@k / MRR / nDCG@k against `relevant_pages`;
- **generation** — numeric exact-match against `gold_numbers` (FinanceBench-style),
  token-F1 / ROUGE-L against `ground_truth`, and abstention accuracy on the
  `unanswerable` items;
- **LLM judge (optional)** — RAGAS-style faithfulness, answer relevancy, answer correctness.

See `EVALUATION_METHODS.md` for why these metrics, and `benchmark/rag/README.md`
for how to run.

## Provenance & versioning

`v1` is built solely from VIC FY2021. To extend: add more years from
`data/processed/ocr_clean/` as new corpus files, append questions with the same
schema, and bump the dataset filename to `…_v2.jsonl`. Keep `gold_numbers`
copied verbatim from the source (Vietnamese `.` thousands separators) — the scorer
canonicalizes them.
