#!/usr/bin/env python3
"""End-to-end RAG benchmark for Finsight.

Drives the **real** retrieval+generation pipeline (`src/rag`) over a fixed,
verified corpus and the labelled Q&A set in `data/rag/`, then scores it with the
metrics in `metrics.py` (see `data/rag/EVALUATION_METHODS.md` for the rationale).

Pipeline per question:

    question ─► RAGPipeline.retrieve ─► retrieved pages ─► IR metrics
            └─► RAGPipeline.answer   ─► answer text     ─► numeric / lexical /
                                                           abstention / LLM-judge

Two tiers, selectable by flags:

  * default            — index corpus, retrieve, generate, score deterministic
                         metrics (needs Qdrant + a Groq key for generation).
  * --retrieval-only   — index + retrieve + IR metrics only (no Groq key needed).
  * --judge            — additionally run the RAGAS-style LLM judge (uses Groq).

Examples
--------
    # bring infra up first (Qdrant): docker compose up -d qdrant
    python -m benchmark.rag.evaluate_rag --retrieval-only
    python -m benchmark.rag.evaluate_rag --judge --limit 20

Run from the repo root (so `src` and `data` resolve), or rely on the path shim
below.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# --- make `src` importable when run as a plain script from anywhere ----------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmark.rag import metrics as M  # noqa: E402

_HERE = Path(__file__).resolve().parent
_DEFAULT_DATASET = _REPO_ROOT / "data" / "rag" / "finsight_finqa_eval_v2.jsonl"
_DEFAULT_CORPUS = _REPO_ROOT / "data" / "rag" / "corpus"  # file or directory
_DEFAULT_OUTDIR = _HERE / "results"
_EVAL_SESSION = "benchmark-rag-eval"
_K_VALUES = (1, 3, 5, 8)


# --------------------------------------------------------------------------- #
#  Dataset
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class Item:
    id: str
    question: str
    ground_truth: str
    answer_type: str
    relevant_pages: set[int]      # v1 page-level labels (may be empty)
    relevant_years: set[int]      # v2 period labels (may be empty)
    gold_numbers: list[str]
    raw: dict = field(default_factory=dict)


def load_dataset(path: Path, limit: int | None = None) -> list[Item]:
    items: list[Item] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        items.append(
            Item(
                id=r["id"],
                question=r["question"],
                ground_truth=r["ground_truth"],
                answer_type=r["answer_type"],
                relevant_pages=set(r.get("relevant_pages") or []),
                relevant_years=set(r.get("relevant_years") or []),
                gold_numbers=r.get("gold_numbers") or [],
                raw=r,
            )
        )
    return items[:limit] if limit else items


# --------------------------------------------------------------------------- #
#  Pipeline wiring (mirrors src/serving/deps.py + routes/documents.py)
# --------------------------------------------------------------------------- #

_YEAR_BY_FILENAME = __import__("re").compile(r"(19|20)\d{2}")


def _doc_year(filename: str, markdown: str) -> int | None:
    m = _YEAR_BY_FILENAME.search(filename) or _YEAR_BY_FILENAME.search(markdown[:2000])
    return int(m.group(0)) if m else None


def build_pipeline(retrieval_only: bool, known_years: list[int] | None = None):
    """Construct Embedder + VectorStore (+ optional Groq) exactly like serving."""
    from src.rag import Embedder, RAGPipeline, VectorStore
    from src.serving.config import get_settings

    s = get_settings()
    embedder = Embedder(
        s.embed_model,
        sparse_model_name=s.sparse_model,
        enable_sparse=s.use_hybrid,
        threads=s.embed_threads or None,
        batch_size=s.embed_batch,
    )
    store = VectorStore(
        embedder, url=s.qdrant_url, collection=s.qdrant_collection, dim=s.embed_dim
    )

    llm = None
    if not retrieval_only:
        from src.rag import GroqClient

        llm = GroqClient(s.groq_api_key, model=s.groq_model)

    pipeline = RAGPipeline(
        llm if llm is not None else _NullLLM(),
        store,
        reranker=None,
        top_k=s.top_k,
        candidates=s.retrieve_candidates,
        mmr_lambda=s.mmr_lambda,
        score_threshold=s.score_threshold,
        use_routing=s.use_routing,
        use_graph=s.use_graph,
        known_years=known_years or [],
    )
    return pipeline, store, s


class _NullLLM:
    """Stand-in so RAGPipeline builds in --retrieval-only mode (never called)."""

    def chat(self, *_a, **_k):  # noqa: D401
        raise RuntimeError("generation requested in retrieval-only mode")


def _corpus_files(corpus: Path) -> list[Path]:
    if corpus.is_dir():
        return sorted(corpus.glob("*.md"))
    return [corpus]


def index_corpus(store, settings, corpus: Path, *, reset: bool) -> tuple[int, list[int]]:
    """Index a corpus file or every .md in a corpus directory (one doc each).

    Returns (chunks_indexed, years_present) — the year list drives the Graph-RAG
    fan-out's "all years" expansion.
    """
    from src.rag import chunk_markdown

    if reset:
        store.delete_session(_EVAL_SESSION)

    total, years = 0, set()
    for path in _corpus_files(corpus):
        markdown = path.read_text(encoding="utf-8")
        year = _doc_year(path.name, markdown)
        if year:
            years.add(year)
        ctx = f"Tài liệu: {path.name}" + (f" · Năm: {year}" if year else "")
        chunks = chunk_markdown(
            markdown,
            doc_id=path.stem,
            doc_name=path.name,
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap,
            doc_context=ctx,
            year=year,
        )
        total += store.add(_EVAL_SESSION, chunks)
    return total, sorted(years)


# --------------------------------------------------------------------------- #
#  Per-item evaluation
# --------------------------------------------------------------------------- #


def retrieved_pages(sources) -> list[int]:
    """Ordered, de-duplicated list of pages from the retrieved chunks."""
    pages: list[int] = []
    for s in sources:
        if s.page is not None and s.page not in pages:
            pages.append(s.page)
    return pages


_DOCYEAR_RE = __import__("re").compile(r"(19|20)\d{2}")


def _hit_year(source) -> int | None:
    """Year of a retrieved chunk, read from its document name (e.g.
    ``2023_bctc_hop_nhat_tables.md``)."""
    m = _DOCYEAR_RE.search(getattr(source, "doc_name", "") or "")
    return int(m.group(0)) if m else None


def eval_item(pipeline, item: Item, *, retrieval_only: bool, judge: bool) -> dict:
    answerable = item.answer_type != "unanswerable"
    res: dict = {"id": item.id, "answer_type": item.answer_type}

    sources = pipeline.retrieve(_EVAL_SESSION, item.question)
    context = "\n\n".join(s.text for s in sources)
    pages = retrieved_pages(sources)
    res["retrieved_pages"] = pages
    res["retrieved_years"] = sorted({y for s in sources if (y := _hit_year(s)) is not None})

    # ---- retrieval metrics ----
    # v1 has page labels; v2 uses number-grounded context recall (RAGAS-style) and
    # period coverage, which need no per-page labels for the multi-year corpus.
    if answerable and item.relevant_pages:
        rel = item.relevant_pages
        for k in _K_VALUES:
            res[f"recall@{k}"] = M.recall_at_k(pages, rel, k)
            res[f"precision@{k}"] = M.precision_at_k(pages, rel, k)
            res[f"hit@{k}"] = M.hit_at_k(pages, rel, k)
            res[f"ndcg@{k}"] = M.ndcg_at_k(pages, rel, k)
        res["mrr"] = M.reciprocal_rank(pages, rel)
        res["map"] = M.average_precision(pages, rel)
    if answerable and item.gold_numbers:
        res["context_recall_num"] = M.context_number_recall(context, item.gold_numbers)
    if answerable and item.relevant_years:
        got = set(res["retrieved_years"])
        res["year_coverage"] = len(item.relevant_years & got) / len(item.relevant_years)

    if retrieval_only:
        return res

    # ---- generation ----
    # A long run can hit transient LLM errors (rate limits, timeouts). Record the
    # failure for that item and keep going rather than aborting the whole run.
    try:
        rag = pipeline.answer(_EVAL_SESSION, item.question)
        answer = rag.answer
    except Exception as exc:  # noqa: BLE001
        res["error"] = f"generation: {exc}"
        return res
    res["answer"] = answer

    res["abstained"] = M.is_abstention(answer)
    if answerable:
        # an answerable question should NOT be refused
        res["false_abstention"] = 1.0 if res["abstained"] else 0.0
        nm = M.numeric_match(answer, item.gold_numbers)
        if nm["applicable"]:
            res["numeric_recall"] = nm["recall"]
            res["numeric_exact"] = nm["all_present"]
        res["token_f1"] = M.token_f1(answer, item.ground_truth)
        res["rouge_l"] = M.rouge_l(answer, item.ground_truth)
    else:
        # correct behaviour = abstain
        res["abstention_correct"] = 1.0 if res["abstained"] else 0.0

    if judge:
        chat = pipeline.llm.chat
        # Each judge call is its own LLM request; a failed one shouldn't sink the
        # others or the run. Missing scores are simply dropped from the average.
        def _safe(fn, *a):
            try:
                return fn(chat, *a)
            except Exception as exc:  # noqa: BLE001
                res.setdefault("judge_errors", []).append(str(exc))
                return float("nan")

        # The four RAGAS metrics: two retrieval-side, two generation-side.
        res["ragas_context_precision"] = _safe(M.judge_context_precision, item.question, context)
        res["ragas_faithfulness"] = _safe(M.judge_faithfulness, answer, context)
        res["ragas_answer_relevancy"] = _safe(M.judge_answer_relevancy, item.question, answer)
        if answerable:
            res["ragas_context_recall"] = _safe(M.judge_context_recall, item.ground_truth, context)
            res["ragas_answer_correctness"] = _safe(
                M.judge_answer_correctness, item.question, answer, item.ground_truth
            )
    return res


# --------------------------------------------------------------------------- #
#  Aggregation
# --------------------------------------------------------------------------- #


def _mean(values) -> float | None:
    vals = [v for v in values if isinstance(v, (int, float)) and v == v]  # drop NaN
    return statistics.fmean(vals) if vals else None


# metric -> which items it applies to (predicate on answer_type)
_ALL = lambda t: True  # noqa: E731
_ANSWERABLE = lambda t: t != "unanswerable"  # noqa: E731
_UNANSWERABLE = lambda t: t == "unanswerable"  # noqa: E731


def aggregate(rows: list[dict], *, retrieval_only: bool, judge: bool) -> dict:
    metric_keys: list[tuple[str, callable]] = []
    for k in _K_VALUES:
        for name in ("recall", "precision", "hit", "ndcg"):
            metric_keys.append((f"{name}@{k}", _ANSWERABLE))
    metric_keys += [
        ("mrr", _ANSWERABLE), ("map", _ANSWERABLE),
        ("context_recall_num", _ANSWERABLE),  # number-grounded RAGAS context recall
        ("year_coverage", _ANSWERABLE),       # cross-period retrieval coverage
    ]
    if not retrieval_only:
        metric_keys += [
            ("numeric_recall", _ANSWERABLE),
            ("numeric_exact", _ANSWERABLE),
            ("token_f1", _ANSWERABLE),
            ("rouge_l", _ANSWERABLE),
            ("false_abstention", _ANSWERABLE),
            ("abstention_correct", _UNANSWERABLE),
        ]
    if judge:
        metric_keys += [
            ("ragas_context_precision", _ALL),
            ("ragas_context_recall", _ANSWERABLE),
            ("ragas_faithfulness", _ALL),
            ("ragas_answer_relevancy", _ALL),
            ("ragas_answer_correctness", _ANSWERABLE),
        ]

    overall: dict = {}
    for key, pred in metric_keys:
        overall[key] = _mean(r[key] for r in rows if pred(r["answer_type"]) and key in r)

    # break the headline metrics down by answer_type
    by_type: dict = {}
    types = sorted({r["answer_type"] for r in rows})
    headline = ["context_recall_num", "year_coverage", "numeric_exact", "token_f1",
                "ragas_answer_correctness", "abstention_correct", "false_abstention"]
    for t in types:
        sub = [r for r in rows if r["answer_type"] == t]
        by_type[t] = {
            "n": len(sub),
            **{m: _mean(r[m] for r in sub if m in r) for m in headline},
        }
    return {"overall": overall, "by_type": by_type, "n_items": len(rows)}


# --------------------------------------------------------------------------- #
#  Reporting
# --------------------------------------------------------------------------- #


def _fmt(v) -> str:
    return "—" if v is None else f"{v:.3f}"


def _rel(p: Path) -> str:
    """Path relative to the repo root when possible, else as given (handles
    relative --dataset/--corpus args that aren't under the repo)."""
    try:
        return str(p.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        return str(p)


def write_reports(agg: dict, rows: list[dict], outdir: Path, meta: dict) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = meta["timestamp"].replace(":", "").replace("-", "")[:15]
    json_path = outdir / f"rag_eval_{stamp}.json"
    md_path = outdir / f"rag_eval_{stamp}.md"
    latest_md = outdir / "latest.md"

    json_path.write_text(
        json.dumps({"meta": meta, "aggregate": agg, "items": rows},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    o = agg["overall"]
    lines = [
        "# Finsight RAG Benchmark — Report",
        "",
        f"- Run: `{meta['timestamp']}`",
        f"- Dataset: `{meta['dataset']}` ({agg['n_items']} questions)",
        f"- Corpus: `{meta['corpus']}` ({meta['chunks_indexed']} chunks indexed)",
        f"- Mode: {meta['mode']}  |  Hybrid: {meta['hybrid']}  |  Routing: {meta['routing']}  |  Graph: {meta.get('graph')}",
        f"- Model: `{meta['embed_model']}` (dense) + BM25  →  `{meta['llm_model']}`",
        f"- Wall time: {meta['seconds']:.1f}s",
        "",
        "## Retrieval (answerable questions)",
        "",
        "| Metric | Score |",
        "|---|---|",
        f"| Context recall — number-grounded (RAGAS proxy) | {_fmt(o.get('context_recall_num'))} |",
        f"| Period coverage (cross-year fan-out) | {_fmt(o.get('year_coverage'))} |",
    ]
    if o.get("recall@5") is not None:  # v1 page-level labels present
        lines.append(f"| Recall@5 (page-level) | {_fmt(o.get('recall@5'))} |")
        lines.append(f"| MRR (page-level) | {_fmt(o.get('mrr'))} |")
    lines.append("")
    if "numeric_exact" in o:
        lines += [
            "## Generation",
            "",
            "| Metric | Score |",
            "|---|---|",
            f"| Numeric exact-match (all gold figures present) | {_fmt(o.get('numeric_exact'))} |",
            f"| Numeric recall (fraction of gold figures present) | {_fmt(o.get('numeric_recall'))} |",
            f"| Token-F1 vs reference | {_fmt(o.get('token_f1'))} |",
            f"| ROUGE-L vs reference | {_fmt(o.get('rouge_l'))} |",
            f"| Abstention accuracy (unanswerable items) | {_fmt(o.get('abstention_correct'))} |",
            f"| False-abstention rate (answerable, lower=better) | {_fmt(o.get('false_abstention'))} |",
            "",
        ]
    if "ragas_faithfulness" in o:
        lines += [
            f"## RAGAS metrics (LLM judge, n={meta.get('judged', '?')} sampled)",
            "",
            "| RAGAS metric | Score |",
            "|---|---|",
            f"| Context Precision | {_fmt(o.get('ragas_context_precision'))} |",
            f"| Context Recall | {_fmt(o.get('ragas_context_recall'))} |",
            f"| Faithfulness | {_fmt(o.get('ragas_faithfulness'))} |",
            f"| Answer Relevancy | {_fmt(o.get('ragas_answer_relevancy'))} |",
            f"| Answer Correctness | {_fmt(o.get('ragas_answer_correctness'))} |",
            "",
        ]

    lines += ["## Breakdown by question type", "",
              "| Type | n | CtxRecall# | YearCov | NumExact | TokenF1 | Correctness | Abstain✓ | FalseAbstain |",
              "|---|---|---|---|---|---|---|---|---|"]
    for t, d in agg["by_type"].items():
        lines.append(
            f"| {t} | {d['n']} | {_fmt(d.get('context_recall_num'))} | {_fmt(d.get('year_coverage'))} "
            f"| {_fmt(d.get('numeric_exact'))} | {_fmt(d.get('token_f1'))} "
            f"| {_fmt(d.get('ragas_answer_correctness'))} | {_fmt(d.get('abstention_correct'))} "
            f"| {_fmt(d.get('false_abstention'))} |"
        )
    lines.append("")

    md = "\n".join(lines)
    md_path.write_text(md, encoding="utf-8")
    latest_md.write_text(md, encoding="utf-8")
    return md_path


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #


def main() -> int:
    ap = argparse.ArgumentParser(description="Finsight RAG benchmark")
    ap.add_argument("--dataset", type=Path, default=_DEFAULT_DATASET)
    ap.add_argument("--corpus", type=Path, default=_DEFAULT_CORPUS)
    ap.add_argument("--outdir", type=Path, default=_DEFAULT_OUTDIR)
    ap.add_argument("--limit", type=int, default=None, help="evaluate only the first N items")
    ap.add_argument("--retrieval-only", action="store_true",
                    help="skip generation; IR metrics only (no Groq key needed)")
    ap.add_argument("--judge", action="store_true",
                    help="also run the RAGAS-style LLM judge (uses Groq)")
    ap.add_argument("--judge-sample", type=int, default=40,
                    help="run the RAGAS LLM judge on only the first N items "
                         "(rate-limit friendly; deterministic metrics still cover all)")
    ap.add_argument("--no-index", action="store_true",
                    help="reuse an already-indexed eval session (skip re-embedding)")
    args = ap.parse_args()

    items = load_dataset(args.dataset, args.limit)
    print(f"[finsight-eval] {len(items)} questions from {args.dataset}")

    # known corpus years drive the Graph-RAG "all years" expansion
    known_years = sorted({y for it in items for y in it.relevant_years})
    try:
        pipeline, store, settings = build_pipeline(args.retrieval_only, known_years)
    except Exception as exc:  # noqa: BLE001
        print(f"[finsight-eval] failed to build pipeline: {exc}")
        print("  Is Qdrant running?  ->  docker compose up -d qdrant")
        return 2

    t0 = time.perf_counter()
    n_chunks = "(reused)"
    if not args.no_index:
        print(f"[finsight-eval] indexing corpus {args.corpus} …")
        n_chunks, corpus_years = index_corpus(store, settings, args.corpus, reset=True)
        if corpus_years:
            pipeline.known_years = corpus_years
        print(f"[finsight-eval] indexed {n_chunks} chunks; years={corpus_years}")

    judged = 0
    rows: list[dict] = []
    for i, item in enumerate(items, 1):
        # judge only the first --judge-sample items to respect Groq rate limits
        do_judge = args.judge and i <= args.judge_sample
        if do_judge:
            judged += 1
        rows.append(eval_item(pipeline, item,
                              retrieval_only=args.retrieval_only, judge=do_judge))
        if i % 10 == 0 or i == len(items):
            print(f"[finsight-eval] {i}/{len(items)} done")

    elapsed = time.perf_counter() - t0
    mode = ("retrieval-only" if args.retrieval_only
            else ("generation+RAGAS" if args.judge else "generation"))
    meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": _rel(args.dataset),
        "corpus": _rel(args.corpus),
        "chunks_indexed": n_chunks,
        "mode": mode,
        "hybrid": settings.use_hybrid,
        "routing": settings.use_routing,
        "graph": settings.use_graph,
        "judged": judged,
        "embed_model": settings.embed_model,
        "llm_model": settings.groq_model,
        "top_k": settings.top_k,
        "seconds": elapsed,
    }
    agg = aggregate(rows, retrieval_only=args.retrieval_only, judge=args.judge)
    md_path = write_reports(agg, rows, args.outdir, meta)

    o = agg["overall"]
    print("\n=== Finsight RAG benchmark ===")
    print(f"  CtxRecall#: {_fmt(o.get('context_recall_num'))}   YearCov: {_fmt(o.get('year_coverage'))}")
    if not args.retrieval_only:
        print(f"  NumExact : {_fmt(o.get('numeric_exact'))}   TokenF1: {_fmt(o.get('token_f1'))}")
        print(f"  Abstain✓ : {_fmt(o.get('abstention_correct'))}   FalseAbstain: {_fmt(o.get('false_abstention'))}")
    if args.judge:
        print(f"  RAGAS(n={judged}): faith {_fmt(o.get('ragas_faithfulness'))} "
              f"| ctx_prec {_fmt(o.get('ragas_context_precision'))} "
              f"| correctness {_fmt(o.get('ragas_answer_correctness'))}")
    print(f"  Report   : {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
