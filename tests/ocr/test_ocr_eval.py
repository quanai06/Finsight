"""Tests for the OCR metrics + an integration check on pages 13-14.

Run:  python -m pytest tests/ocr/test_ocr_eval.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .evaluate import run
from .ocr_metrics import evaluate_pair, extract_numbers, levenshtein, normalize_text


# ------------------------------------------------------------------ unit tests

def test_normalize_strips_html_and_pipes():
    html = "<table><tr><td>Doanh thu</td><td>125.780.761</td></tr></table>"
    md = "| Doanh thu | 125.780.761 |"
    assert normalize_text(html) == normalize_text(md) == "Doanh thu 125.780.761"


def test_normalize_nfc_equivalence():
    # 'ế' composed vs decomposed must compare equal after NFC
    composed, decomposed = "ế", "ế"
    assert normalize_text(composed) == normalize_text(decomposed)


def test_levenshtein_basic():
    assert levenshtein("kitten", "kitten") == 0
    assert levenshtein("kitten", "sitting") == 3
    assert levenshtein(["a", "b"], ["a", "c"]) == 1


def test_extract_numbers_vietnamese_format():
    nums = extract_numbers("Doanh thu 125.780.761, giảm trừ (92.891) năm 2021")
    assert "125780761" in nums
    assert "-92891" in nums          # parentheses -> negative
    assert "2021" in nums


def test_perfect_match_scores_one():
    text = "Lợi nhuận 3.146.451"
    s = evaluate_pair(text, text)
    assert s.cer == 0.0
    assert s.char_accuracy == 1.0
    assert s.number_f1 == 1.0


def test_number_mismatch_lowers_number_f1():
    gold = "Doanh thu 125.780.761"
    pred = "Doanh thu 125.780.701"          # one wrong digit
    s = evaluate_pair(pred, gold)
    assert s.number_f1 < 1.0
    assert s.numbers_matched == 0           # exact-match: no partial credit


# ------------------------------------------------------- integration (real data)

_HAVE_DATA = (
    Path("data/processed/ocr/2021_bctc_hop_nhat_pages/page_013.md").exists()
    and Path("data/golden/2021_bctc_hop_nhat/page_013.md").exists()
)


@pytest.mark.skipif(not _HAVE_DATA, reason="OCR output / gold for p13-14 not present")
def test_pages_13_14_benchmark_sane():
    result = run("2021_bctc_hop_nhat", [13, 14])
    agg = result["aggregate"]
    assert agg["pages_scored"] == 2
    # sanity bounds — not a quality bar, just guards against a broken pipeline
    assert 0.0 <= agg["macro_cer"] <= 1.0
    assert 0.0 <= agg["macro_number_f1"] <= 1.0
    assert result["per_page"]["page_013"]["gold_numbers"] > 0
