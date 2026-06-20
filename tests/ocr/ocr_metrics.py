"""OCR quality metrics — pure Python, no external dependencies.

The comparison is **structure-agnostic**: HTML tables, Markdown pipe tables and
heading/emphasis markers are stripped so we score the *content* (text + numbers),
not the table layout (the OCR emits HTML tables while the gold uses Markdown).

Metrics
-------
- CER  (Character Error Rate)  + character accuracy
- WER  (Word Error Rate)       + word accuracy
- Word precision / recall / F1 (multiset over tokens)
- Number precision / recall / F1 (the financial KPI — exact numeric match)
- Levenshtein distance + normalized similarity
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass

# ---------------------------------------------------------------- normalization

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_TAG = re.compile(r"<[^>]+>")
_MD_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}.*$", re.MULTILINE)  # |---|---| rows
_MD_MARKERS = re.compile(r"[#*`>]")                               # heading/bold/code/quote
_WS = re.compile(r"\s+")


def normalize_text(text: str, *, strip_tables: bool = True, lower: bool = False) -> str:
    """Canonicalise OCR/gold text so only content is compared.

    Removes HTML comments + tags, Markdown table separators, pipes and emphasis
    markers, applies Unicode NFC, and collapses whitespace.
    """
    text = _HTML_COMMENT.sub(" ", text)
    if strip_tables:
        text = _HTML_TAG.sub(" ", text)          # <td ...> -> space, keep cell text
        text = _MD_TABLE_SEP.sub(" ", text)      # drop |---|---| rows
        text = text.replace("|", " ")            # drop pipe column separators
    text = _MD_MARKERS.sub(" ", text)
    text = unicodedata.normalize("NFC", text)
    if lower:
        text = text.lower()
    return _WS.sub(" ", text).strip()


# ---------------------------------------------------------------- number parsing

# Vietnamese financial numbers: optional ( ), digit groups separated by '.'(thousands)
# optional ',' decimal, e.g. 125.780.761  (92.891)  4,5  2021
_NUMBER = re.compile(r"\(?\s*\d[\d.]*(?:,\d+)?\s*\)?")


def extract_numbers(text: str) -> list[str]:
    """Return canonical numeric strings: thousands '.' stripped, '( )' -> '-'."""
    out: list[str] = []
    for raw in _NUMBER.findall(text):
        tok = raw.strip()
        neg = tok.startswith("(") and tok.endswith(")")
        tok = tok.strip("()").strip()
        tok = tok.replace(".", "")          # strip thousands separators
        tok = tok.replace(",", ".")         # decimal comma -> dot
        if not tok or not any(c.isdigit() for c in tok):
            continue
        out.append(("-" if neg else "") + tok)
    return out


# ---------------------------------------------------------------- edit distance

def levenshtein(a, b) -> int:
    """Edit distance over any two sequences (strings or token lists)."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * lb
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[lb]


def _prf(pred: list[str], gold: list[str]) -> tuple[float, float, float, int]:
    """Multiset precision / recall / F1 over tokens."""
    cp, cg = Counter(pred), Counter(gold)
    matched = sum((cp & cg).values())
    precision = matched / len(pred) if pred else 0.0
    recall = matched / len(gold) if gold else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1, matched


# ---------------------------------------------------------------- result model

@dataclass(slots=True)
class OCRScore:
    # sizes
    gold_chars: int
    pred_chars: int
    gold_words: int
    pred_words: int
    # character level
    char_edits: int
    cer: float
    char_accuracy: float
    similarity: float          # 1 - lev/maxlen
    # word level
    word_edits: int
    wer: float
    word_accuracy: float
    word_precision: float
    word_recall: float
    word_f1: float
    # numbers (financial KPI)
    gold_numbers: int
    pred_numbers: int
    numbers_matched: int
    number_precision: float
    number_recall: float
    number_f1: float

    def as_dict(self) -> dict:
        return asdict(self)


def evaluate_pair(pred_md: str, gold_md: str, *, lower: bool = False) -> OCRScore:
    """Compute all metrics for one (prediction, gold) Markdown pair."""
    pred = normalize_text(pred_md, lower=lower)
    gold = normalize_text(gold_md, lower=lower)

    # character level
    char_edits = levenshtein(pred, gold)
    maxlen = max(len(pred), len(gold)) or 1
    cer = char_edits / (len(gold) or 1)
    similarity = 1 - char_edits / maxlen

    # word level
    pred_w, gold_w = pred.split(), gold.split()
    word_edits = levenshtein(pred_w, gold_w)
    wer = word_edits / (len(gold_w) or 1)
    wp, wr, wf1, _ = _prf(pred_w, gold_w)

    # numbers — extract from NORMALIZED text so HTML comments and <img> tags
    # (e.g. seal-box coordinates in image filenames) don't leak in as numbers
    pred_n, gold_n = extract_numbers(pred), extract_numbers(gold)
    np_, nr, nf1, nmatched = _prf(pred_n, gold_n)

    return OCRScore(
        gold_chars=len(gold), pred_chars=len(pred),
        gold_words=len(gold_w), pred_words=len(pred_w),
        char_edits=char_edits, cer=round(cer, 4),
        char_accuracy=round(max(0.0, 1 - cer), 4), similarity=round(similarity, 4),
        word_edits=word_edits, wer=round(wer, 4),
        word_accuracy=round(max(0.0, 1 - wer), 4),
        word_precision=round(wp, 4), word_recall=round(wr, 4), word_f1=round(wf1, 4),
        gold_numbers=len(gold_n), pred_numbers=len(pred_n), numbers_matched=nmatched,
        number_precision=round(np_, 4), number_recall=round(nr, 4),
        number_f1=round(nf1, 4),
    )
