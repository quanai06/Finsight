# Finsight RAG Benchmark

Evaluates the **real** `src/rag` pipeline (hybrid dense+BM25 retrieval → MMR →
Groq generation) on the labelled Vietnamese-finance Q&A set in
[`data/rag/`](../../data/rag/). Metric choices are justified in
[`data/rag/EVALUATION_METHODS.md`](../../data/rag/EVALUATION_METHODS.md): a
**RAGAS-lite + FinanceBench-numeric** design keyed on page-level relevance labels.

```
benchmark/rag/
├── README.md
├── build_dataset.py    # generate the ~480-question multi-year v2 set (verified)
├── evaluate_rag.py     # end-to-end harness (index → retrieve → generate → score)
├── metrics.py          # IR + numeric + lexical + abstention + RAGAS judge metrics
└── results/            # timestamped JSON + Markdown reports (latest.md = newest)
```

## RAGAS metrics + Graph-RAG

The harness defaults to the multi-year v2 dataset and the whole `data/rag/corpus/`
directory (5 years indexed). It reports the four **RAGAS** metrics — Context
Precision, Context Recall, Faithfulness, Answer Relevancy (+ Answer Correctness) —
via an LLM judge with **rate-limit backoff**, plus deterministic proxies (number-
grounded context recall, period coverage, numeric exact-match) on every item.

Because Groq's free tier is ~12k TPM, the LLM judge runs on a **sample**
(`--judge-sample N`, default 40); deterministic metrics still cover all questions.

```bash
python -m benchmark.rag.evaluate_rag --retrieval-only          # all items, no Groq
python -m benchmark.rag.evaluate_rag --judge --judge-sample 40 # RAGAS on a sample
```

A/B the Graph-RAG cross-period fan-out (helps `multi_year` questions most):

```bash
FINSIGHT_USE_GRAPH=true  python -m benchmark.rag.evaluate_rag --retrieval-only
FINSIGHT_USE_GRAPH=false python -m benchmark.rag.evaluate_rag --retrieval-only
```

## What it measures

**Retrieval** (deterministic, vs each question's `relevant_pages`):
Recall@k, Precision@k, Hit@k, MRR, nDCG@k for k ∈ {1, 3, 5, 8}.

**Generation** (deterministic):
- **Numeric exact-match** — do all `gold_numbers` appear in the answer (canonicalized
  for VN `.`-thousands)? The decisive metric for financial figures.
- **Token-F1 / ROUGE-L** vs the reference answer.
- **Abstention accuracy** — `unanswerable` questions should be refused; answerable
  ones should *not* (false-abstention rate).

**Generation** (optional `--judge`, RAGAS/TruLens-style, reuses the Groq client):
Faithfulness/groundedness, Answer relevancy, Answer correctness.

## Prerequisites

- **Qdrant** running: `docker compose up -d qdrant` (the pipeline's vector store).
- Python deps from `requirements.txt` (`fastembed`, `qdrant-client`). The first run
  downloads the e5-large ONNX model (~2 GB), cached afterwards.
- **For generation/judge only:** `GROQ_API_KEY` in `.env`.

## Usage

Run from the repo root:

```bash
# Retrieval quality only — no Groq key needed, fully deterministic
python -m benchmark.rag.evaluate_rag --retrieval-only

# Full: retrieval + generation + deterministic answer metrics
python -m benchmark.rag.evaluate_rag

# Add the RAGAS-style LLM judge (more Groq calls)
python -m benchmark.rag.evaluate_rag --judge

# Quick iteration
python -m benchmark.rag.evaluate_rag --retrieval-only --limit 20
```

Flags: `--dataset` / `--corpus` / `--outdir` to override paths; `--limit N` for the
first N questions; `--no-index` to reuse an already-embedded eval session (skip
re-embedding when only generation settings changed).

The harness indexes the corpus into a dedicated, isolated session
(`benchmark-rag-eval`) in the configured collection and resets it each run, so it
never disturbs real user sessions.

## Output

Each run writes `results/rag_eval_<timestamp>.{json,md}` and refreshes
`results/latest.md`. The JSON holds per-item scores (including retrieved pages and
the generated answer) for error analysis; the Markdown is the human summary with an
overall table and a per-`answer_type` breakdown.

## Tuning loop

The benchmark is built to compare configurations. Toggle a knob via env (all read
by `src/serving/config.py`) and re-run:

| Env var | What it changes |
|---|---|
| `FINSIGHT_USE_HYBRID` | dense-only vs dense+BM25 (expect numeric recall to drop without BM25) |
| `FINSIGHT_USE_ROUTING` | statement/note/year soft-filtering on/off |
| `FINSIGHT_USE_RERANKER` | swap MMR for the cross-encoder reranker |
| `FINSIGHT_TOP_K`, `FINSIGHT_RETRIEVE_CANDIDATES`, `FINSIGHT_MMR_LAMBDA` | retrieval depth/diversity |

Example A/B (does BM25 actually help pull exact figures?):

```bash
FINSIGHT_USE_HYBRID=true  python -m benchmark.rag.evaluate_rag --retrieval-only
FINSIGHT_USE_HYBRID=false python -m benchmark.rag.evaluate_rag --retrieval-only
```

## Note on the OCR benchmark

OCR-quality benchmarking (character/word/number accuracy of the OCR step) lives in
[`benchmark/ocr/`](../ocr/) and is upstream of this RAG benchmark — good OCR is a
precondition for good retrieval, but the two measure different stages.
