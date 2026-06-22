"""Metrics for the Finsight RAG benchmark.

Two tiers, matching ``data/rag/EVALUATION_METHODS.md``:

* **Deterministic** (no API): classic IR retrieval metrics (Recall@k, Precision@k,
  Hit@k, MRR, nDCG@k), FinanceBench-style **numeric exact-match**, token-F1 and
  ROUGE-L answer overlap, and **abstention** accuracy for unanswerable questions.
* **LLM-judge** (optional, reuses the Groq client): RAGAS/TruLens-style
  **Faithfulness**, **Answer Relevancy** and **Answer Correctness**.

Everything here is pure-Python (only stdlib) so the deterministic tier runs in CI
with no model download and no API key.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata

# --------------------------------------------------------------------------- #
#  Retrieval metrics (page-level relevance labels)
# --------------------------------------------------------------------------- #


def recall_at_k(retrieved: list[int], relevant: set[int], k: int) -> float:
    """Fraction of relevant pages that appear in the top-k retrieved pages."""
    if not relevant:
        return float("nan")
    top = set(retrieved[:k])
    return len(top & relevant) / len(relevant)


def precision_at_k(retrieved: list[int], relevant: set[int], k: int) -> float:
    if k == 0:
        return 0.0
    top = retrieved[:k]
    if not top:
        return 0.0
    return sum(1 for p in top if p in relevant) / len(top)


def hit_at_k(retrieved: list[int], relevant: set[int], k: int) -> float:
    """1.0 if at least one relevant page is in the top-k, else 0.0."""
    return 1.0 if set(retrieved[:k]) & relevant else 0.0


def reciprocal_rank(retrieved: list[int], relevant: set[int]) -> float:
    for i, p in enumerate(retrieved, start=1):
        if p in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(retrieved: list[int], relevant: set[int], k: int) -> float:
    """Binary-gain nDCG@k over page-level labels."""
    if not relevant:
        return float("nan")
    dcg = 0.0
    for i, p in enumerate(retrieved[:k], start=1):
        if p in relevant:
            dcg += 1.0 / math.log2(i + 1)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevant), k) + 1))
    return dcg / ideal if ideal else 0.0


def average_precision(retrieved: list[int], relevant: set[int]) -> float:
    if not relevant:
        return float("nan")
    hits = 0
    score = 0.0
    for i, p in enumerate(retrieved, start=1):
        if p in relevant:
            hits += 1
            score += hits / i
    return score / len(relevant)


# --------------------------------------------------------------------------- #
#  Numeric exact-match (the finance-critical metric)
# --------------------------------------------------------------------------- #

# A financial figure: digit groups separated by "." or "," (thousands), optional
# decimal tail. Captures "125.780.761", "(2.108.989)", "4,5", "685".
_NUMBER_RE = re.compile(r"\d[\d.,]*\d|\d")


def _canon_number(token: str) -> str | None:
    """Normalize a Vietnamese-formatted number to a comparable canonical form.

    VN reports use "." as the thousands separator and "," as the decimal mark.
    We strip thousands separators and keep an explicit decimal part, so
    ``"125.780.761" -> "125780761"`` and ``"4,5" -> "4.5"``. Pure-integer tokens
    with stray separators collapse to their digits.
    """
    t = token.strip().strip("().%").replace(" ", "")
    if not t:
        return None
    # Decimal comma (one comma, short tail) -> treat as decimal point.
    if "," in t and t.count(",") == 1 and len(t.split(",")[1]) <= 2:
        intpart, dec = t.split(",")
        intpart = intpart.replace(".", "").replace(",", "")
        dec = dec.rstrip("0")
        return f"{int(intpart)}.{dec}" if dec else str(int(intpart or 0))
    digits = re.sub(r"[.,]", "", t)
    if not digits.isdigit():
        return None
    return str(int(digits))


def extract_numbers(text: str) -> set[str]:
    out: set[str] = set()
    for m in _NUMBER_RE.findall(text or ""):
        c = _canon_number(m)
        if c is not None:
            out.add(c)
    return out


def numeric_match(answer: str, gold_numbers: list[str]) -> dict:
    """How many of the gold figures appear (canonically) in the answer.

    Returns recall (the headline number), plus whether *all* gold numbers were
    found (strict exact-match, FinanceBench style).
    """
    gold = {c for g in gold_numbers if (c := _canon_number(g)) is not None}
    if not gold:
        return {"applicable": False, "recall": float("nan"), "all_present": float("nan")}
    found = extract_numbers(answer)
    matched = gold & found
    return {
        "applicable": True,
        "recall": len(matched) / len(gold),
        "all_present": 1.0 if matched == gold else 0.0,
        "n_gold": len(gold),
        "n_matched": len(matched),
    }


# --------------------------------------------------------------------------- #
#  Lexical overlap (token-F1, ROUGE-L)
# --------------------------------------------------------------------------- #


def _tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", (text or "").lower())
    return re.findall(r"\w+", text, flags=re.UNICODE)


def token_f1(answer: str, reference: str) -> float:
    a, b = _tokenize(answer), _tokenize(reference)
    if not a or not b:
        return 0.0
    from collections import Counter

    common = Counter(a) & Counter(b)
    overlap = sum(common.values())
    if overlap == 0:
        return 0.0
    p, r = overlap / len(a), overlap / len(b)
    return 2 * p * r / (p + r)


def rouge_l(answer: str, reference: str) -> float:
    """ROUGE-L F1 via longest-common-subsequence over tokens."""
    a, b = _tokenize(answer), _tokenize(reference)
    if not a or not b:
        return 0.0
    # LCS length (rolling DP to keep memory at O(min)).
    if len(a) < len(b):
        a, b = b, a
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0] * (len(b) + 1)
        for j, y in enumerate(b, start=1):
            cur[j] = prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1])
        prev = cur
    lcs = prev[len(b)]
    if lcs == 0:
        return 0.0
    p, r = lcs / len(a), lcs / len(b)
    return 2 * p * r / (p + r)


# --------------------------------------------------------------------------- #
#  Abstention (for unanswerable questions)
# --------------------------------------------------------------------------- #

_REFUSAL_MARKERS = (
    "không tìm thấy",
    "không thể trả lời",
    "không có thông tin",
    "không được trình bày",
    "không nêu",
    "không cung cấp",
    "không có trong",
    "không đủ thông tin",
    "tài liệu không",
    "couldn't find",
    "could not find",
    "cannot be answered",
    "not provided",
    "does not disclose",
    "no information",
    "not contain",
    "not found in",
)


def is_abstention(answer: str) -> bool:
    a = (answer or "").lower()
    return any(m in a for m in _REFUSAL_MARKERS)


# --------------------------------------------------------------------------- #
#  Context recall, number-grounded (deterministic RAGAS context-recall proxy)
# --------------------------------------------------------------------------- #


def context_number_recall(context: str, gold_numbers: list[str]) -> float:
    """Fraction of the gold figures that actually appear in the retrieved context.

    A deterministic stand-in for RAGAS *context recall*: if the number needed for
    the answer isn't in the retrieved context, retrieval failed regardless of what
    the LLM later says. Returns NaN when the item has no gold numbers (text Qs).
    """
    gold = {c for g in gold_numbers if (c := _canon_number(g)) is not None}
    if not gold:
        return float("nan")
    found = extract_numbers(context)
    return len(gold & found) / len(gold)



# --------------------------------------------------------------------------- #
#  LLM-as-judge (RAGAS / TruLens style) — optional, needs a chat client
# --------------------------------------------------------------------------- #

_JUDGE_SYSTEM = (
    "You are a meticulous evaluator of financial question-answering systems. "
    "You return ONLY a compact JSON object, no prose."
)


def _ask_judge(chat, prompt: str, *, retries: int = 4) -> dict:
    """Call the chat client and parse the first JSON object from its reply.

    Retries on transient rate-limit errors (Groq free tier is ~12k TPM), honouring
    the "try again in Xs" hint when present so a long RAGAS run actually completes.
    """
    import time

    for attempt in range(retries + 1):
        try:
            reply = chat([
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user", "content": prompt},
            ])
            break
        except Exception as exc:  # noqa: BLE001 - retry only rate limits
            msg = str(exc)
            if ("429" in msg or "rate limit" in msg.lower()) and attempt < retries:
                m = re.search(r"try again in ([\d.]+)s", msg)
                time.sleep(min(float(m.group(1)) + 0.5 if m else 2.0 * (attempt + 1), 30.0))
                continue
            raise
    m = re.search(r"\{.*\}", reply, flags=re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def judge_faithfulness(chat, answer: str, context: str) -> float:
    """Fraction of the answer's factual claims supported by the retrieved context
    (RAGAS Faithfulness / TruLens Groundedness)."""
    prompt = (
        "Given a CONTEXT and an ANSWER, decide what fraction of the factual claims "
        "in the ANSWER are directly supported by the CONTEXT. Numbers must match. "
        'Reply as JSON: {"supported": <int>, "total": <int>}.\n\n'
        f"CONTEXT:\n{context}\n\nANSWER:\n{answer}"
    )
    r = _ask_judge(chat, prompt)
    total = r.get("total") or 0
    if not total:
        return float("nan")
    return max(0.0, min(1.0, r.get("supported", 0) / total))


def judge_answer_relevancy(chat, question: str, answer: str) -> float:
    prompt = (
        "Rate from 0.0 to 1.0 how directly the ANSWER addresses the QUESTION "
        "(ignore correctness, judge only relevance/on-topic-ness). "
        'Reply as JSON: {"score": <float 0..1>}.\n\n'
        f"QUESTION:\n{question}\n\nANSWER:\n{answer}"
    )
    r = _ask_judge(chat, prompt)
    s = r.get("score")
    return float("nan") if s is None else max(0.0, min(1.0, float(s)))


def judge_context_precision(chat, question: str, context: str) -> float:
    """RAGAS Context Precision: fraction of the retrieved context that is relevant
    to answering the question (signal-to-noise of retrieval)."""
    prompt = (
        "Given a QUESTION and the retrieved CONTEXT, estimate from 0.0 to 1.0 how "
        "much of the CONTEXT is relevant to answering the QUESTION (1.0 = all "
        "relevant, 0.0 = mostly irrelevant). "
        'Reply as JSON: {"score": <float 0..1>}.\n\n'
        f"QUESTION:\n{question}\n\nCONTEXT:\n{context}"
    )
    r = _ask_judge(chat, prompt)
    s = r.get("score")
    return float("nan") if s is None else max(0.0, min(1.0, float(s)))


def judge_context_recall(chat, reference: str, context: str) -> float:
    """RAGAS Context Recall: fraction of the reference answer's claims that are
    supported by the retrieved context (did retrieval bring back what's needed)."""
    prompt = (
        "Given a CONTEXT and a REFERENCE answer, decide what fraction of the claims "
        "in the REFERENCE are supported by the CONTEXT. Numbers must match. "
        'Reply as JSON: {"supported": <int>, "total": <int>}.\n\n'
        f"CONTEXT:\n{context}\n\nREFERENCE:\n{reference}"
    )
    r = _ask_judge(chat, prompt)
    total = r.get("total") or 0
    return float("nan") if not total else max(0.0, min(1.0, r.get("supported", 0) / total))


def judge_answer_correctness(chat, question: str, answer: str, reference: str) -> float:
    prompt = (
        "Compare the ANSWER to the REFERENCE answer for the QUESTION. Score 1.0 if "
        "it conveys the same key facts and figures, 0.0 if wrong or contradictory, "
        "partial credit in between. Different wording/language is fine if the facts "
        'and numbers match. Reply as JSON: {"score": <float 0..1>}.\n\n'
        f"QUESTION:\n{question}\n\nREFERENCE:\n{reference}\n\nANSWER:\n{answer}"
    )
    r = _ask_judge(chat, prompt)
    s = r.get("score")
    return float("nan") if s is None else max(0.0, min(1.0, float(s)))
