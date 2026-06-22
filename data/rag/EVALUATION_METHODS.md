# RAG Evaluation Methods — Research & Fit for Finsight

This note surveys how the literature evaluates Retrieval-Augmented Generation
(RAG), then argues which subset best fits **Finsight** (hybrid dense+BM25
retrieval over Vietnamese financial statements, Groq LLM generation). The chosen
metrics are the ones implemented in `benchmark/rag/`.

---

## 1. What a RAG system can get wrong

A RAG answer has two failure surfaces, and good evaluation separates them:

1. **Retrieval** — did we put the right evidence in the context window? If the
   chunk with the number is never retrieved, no LLM can answer faithfully.
2. **Generation** — given the retrieved context, did the LLM produce an answer
   that is *correct*, *grounded in the context* (not hallucinated), and *relevant*
   to the question?

Most frameworks below decompose the score along exactly this retrieval ↔
generation split (and the interaction between them).

---

## 2. The metric families

### 2.1 Classic Information-Retrieval metrics (retrieval only)

Order-aware and set-based metrics from IR, computed against a set of
ground-truth relevant documents/chunks/pages:

- **Recall@k** — fraction of relevant items that appear in the top-k. *The single
  most important retrieval metric for QA*: if recall is low the answer is
  impossible regardless of the LLM.
- **Precision@k** — fraction of top-k that are relevant.
- **Hit@k / Success@k** — was at least one relevant item in the top-k (binary).
- **MRR (Mean Reciprocal Rank)** — 1/rank of the first relevant item; rewards
  putting evidence early.
- **MAP (Mean Average Precision)** and **nDCG@k** (Järvelin & Kekäläinen, 2002) —
  graded, rank-discounted quality.

Cheap, deterministic, no LLM needed — but they require labelled relevant items.

### 2.2 RAGAS — reference-free LLM-graded metrics

*RAGAS: Automated Evaluation of Retrieval Augmented Generation*
(Es et al., 2023, arXiv:2309.15217). Uses an LLM as judge so it needs **no human
references** for most metrics. Four core metrics:

- **Faithfulness** — break the answer into atomic claims, check each is entailed
  by the retrieved context. Directly measures **hallucination / groundedness**.
- **Answer Relevancy** — does the answer actually address the question (generate
  questions from the answer and compare to the original).
- **Context Precision** — are the relevant chunks ranked high in the retrieved set.
- **Context Recall** — is every claim of the *ground-truth answer* supported by
  the retrieved context (this one needs a reference answer).

### 2.3 TruLens "RAG Triad"

A practitioner framing (TruLens/TruEra) of three LLM-judged scores:
**Context Relevance** (retrieved chunks vs question), **Groundedness** (answer vs
chunks), **Answer Relevance** (answer vs question). Same idea as RAGAS, expressed
as a triangle you can monitor in production.

### 2.4 ARES — trained judges + statistical correction

*ARES: An Automated Evaluation Framework for RAG Systems*
(Saad-Falcon et al., 2023, arXiv:2311.09476). Fine-tunes lightweight LLM judges
for context relevance / answer faithfulness / answer relevance and uses
**prediction-powered inference (PPI)** with a small human-labelled set to give
statistically sound estimates. More robust than a single prompt-based judge, but
needs training data and labels.

### 2.5 RAGChecker — fine-grained claim-level diagnosis

*RAGChecker: A Fine-grained Framework for Diagnosing RAG*
(Ru et al., 2024, arXiv:2408.08067). Uses claim-level entailment to produce
**overall** metrics plus **retriever** metrics (claim recall, context precision)
and **generator** metrics (faithfulness, hallucination, noise sensitivity). Good
when you want to attribute a failure to retriever vs generator.

### 2.6 LLM-as-a-judge / G-Eval (answer correctness)

- *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena* (Zheng et al., 2023,
  arXiv:2306.05685) — establishes that a strong LLM grader correlates well with
  humans (with known biases: position, verbosity, self-preference).
- *G-Eval* (Liu et al., 2023, arXiv:2303.16634) — chain-of-thought + form-filling
  LLM scoring; the basis of DeepEval's metrics.
- **Answer Correctness** = LLM judges the candidate answer against a **reference
  answer** (semantic equivalence, not string match). Essential when the same fact
  can be phrased many ways.

### 2.7 Lexical / semantic overlap (cheap reference-based)

**Exact Match**, **token-level F1** (SQuAD-style), **ROUGE-L**, **BLEU**,
**BERTScore** (Zhang et al., 2020). Fast and deterministic but brittle for long
free-text answers — most useful for short factoid answers and as a sanity layer
under the LLM judge.

### 2.8 Domain benchmark: FinanceBench (the finance-specific one)

*FinanceBench: A New Benchmark for Financial Question Answering*
(Islam et al., 2023, arXiv:2311.11944). 10,231 questions over public filings;
every question carries a verbatim **evidence string + source page**, and answers
are graded for **numeric correctness with tolerance rules**. Its headline result —
a GPT-4-Turbo RAG system failed or refused **81%** of questions — is precisely
the *retrieve-the-right-number* problem Finsight faces. Two lessons we adopt:

1. **Numeric exactness is a first-class metric** — a financial answer that is off
   by one digit is wrong, however fluent.
2. **Refusal is acceptable and must be measured** — abstaining when the document
   lacks the answer is correct behaviour, not a failure.

Related: *FinanceQA* (arXiv:2501.18062) and *TAT-QA* (Zhu et al., 2021) stress
multi-step numerical reasoning over tables — relevant to our `numeric_compare` /
`reasoning` items.

### 2.9 Surveys

*Evaluation of Retrieval-Augmented Generation: A Survey* (Yu et al., 2024,
arXiv:2405.07437) catalogues benchmarks (RGB, RECALL, CRUD-RAG) and the
retrievable/generation metric split used above.

---

## 3. Which method fits Finsight best

**Finsight's profile** (see `src/rag/`): hybrid retrieval (e5-large dense + BM25
sparse, RRF) → dedup + MMR → Groq `llama-3.3-70b` generation, over Vietnamese
consolidated financial statements (BCTC). The whole point of adding BM25 was to
**pin exact figures, codes and years** that dense vectors blur. So the evaluation
must reward exactly that.

| Need | Best-fit method | Why |
|---|---|---|
| Is the right figure retrieved at all? | **IR Recall@k / MRR / Hit@k** (per-page labels) | The bottleneck per the project's own audit (`error_upgrade.md`): "couldn't pull the number" = retrieval miss. |
| Does the answer hallucinate a number? | **RAGAS Faithfulness / TruLens Groundedness** (LLM judge) | Finance demands no invented figures; the system prompt already forbids it — verify it. |
| Is the figure actually correct? | **FinanceBench-style numeric exact-match** + **LLM Answer-Correctness vs reference** | A number is right or wrong; phrasing varies (VN/EN, "triệu VND"). |
| Does it abstain when it should? | **Refusal/abstention accuracy** on `unanswerable` items | FinanceBench shows refusal is correct behaviour; the pipeline has a no-context fallback. |
| Is the answer on-topic? | **RAGAS Answer Relevancy** (LLM judge) | Catches verbose/evasive answers. |

**Conclusion — a RAGAS-lite + FinanceBench-numeric hybrid, keyed on page-level
relevance labels.** Concretely the harness computes:

- **Retrieval (deterministic, no API):** Recall@k, Precision@k, Hit@k, MRR, nDCG@k
  using each item's `relevant_pages` against the `page` payload the chunker emits.
- **Generation (deterministic):** numeric exact-match over `gold_numbers`
  (the finance-critical metric), token-F1 and ROUGE-L vs `ground_truth`, and
  abstention accuracy on `unanswerable` items.
- **Generation (LLM judge, optional, reuses the Groq client):** Faithfulness,
  Answer Relevancy, Answer Correctness — RAGAS/TruLens-style, prompted in the
  answer's language.

This split lets the deterministic tier run anywhere (CI, no API budget) and the
LLM-judge tier add RAGAS-grade depth when a Groq key is available. We deliberately
**do not** adopt ARES (needs trained judges + labels we don't have) or heavy
embedding metrics like BERTScore (the e5 model is already loaded for retrieval and
numeric match is more decisive for finance).

### Why not just RAGAS off-the-shelf?

RAGAS is excellent but (a) its defaults assume English and an OpenAI judge, (b) it
underweights *numeric* exactness — its faithfulness can call a fluent answer with a
wrong-but-grounded-looking number "faithful", and (c) pulling the full `ragas`
dependency tree conflicts with the project's CPU-only, single-`requirements.txt`
constraint. We therefore reimplement the three RAGAS metrics that matter against
the **Groq judge already in the stack**, and add the numeric/abstention metrics
RAGAS lacks.

---

## 4. References

- Es et al. *RAGAS*. arXiv:2309.15217 (2023).
- Saad-Falcon et al. *ARES*. arXiv:2311.09476 (2023).
- Ru et al. *RAGChecker*. arXiv:2408.08067 (2024).
- Zheng et al. *Judging LLM-as-a-Judge (MT-Bench)*. arXiv:2306.05685 (2023).
- Liu et al. *G-Eval*. arXiv:2303.16634 (2023).
- Islam et al. *FinanceBench*. arXiv:2311.11944 (2023).
- *FinanceQA*. arXiv:2501.18062 (2025).
- Zhu et al. *TAT-QA*. ACL 2021.
- Yu et al. *Evaluation of RAG: A Survey*. arXiv:2405.07437 (2024).
- Zhang et al. *BERTScore*. ICLR 2020.
- Järvelin & Kekäläinen. *Cumulated gain-based evaluation of IR (nDCG)*. ACM TOIS 2002.
- TruLens RAG Triad — https://www.trulens.org/getting_started/core_concepts/rag_triad/
- RAGAS docs — https://docs.ragas.io/
