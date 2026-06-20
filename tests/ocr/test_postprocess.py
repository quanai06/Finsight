"""Tests for HTML-table -> Markdown + JSON post-processing.

Run:  python -m pytest tests/ocr/test_postprocess.py -v
"""

from __future__ import annotations

from src.ocr.postprocess import PostProcessor, parse_table, rows_to_markdown

_HTML = (
    "Header text\n"
    "<table border=1 style='x'>"
    "<tr><td style='a'>Mã số</td><td>Năm nay</td></tr>"
    "<tr><td>01</td><td>125.780.761</td></tr>"
    "<tr><td>02</td><td>(92.891)</td></tr>"
    "</table>\n"
    "<div style='center'><img src='imgs/seal_983_605.jpg'/></div>\n"
)


def test_parse_table_grid():
    rows = parse_table("<table><tr><td>a</td><td>b</td></tr>"
                       "<tr><td>1</td><td>2</td></tr></table>")
    assert rows == [["a", "b"], ["1", "2"]]


def test_rows_to_markdown_shape():
    md = rows_to_markdown([["h1", "h2"], ["x", "y"]])
    assert md.splitlines() == ["| h1 | h2 |", "|---|---|", "| x | y |"]


def test_pipe_in_cell_escaped():
    md = rows_to_markdown([["a|b"], ["c"]])
    assert "a\\|b" in md


def test_process_converts_and_extracts():
    res = PostProcessor(strip_html=True).process_text(_HTML)
    # HTML table replaced by Markdown
    assert "| Mã số | Năm nay |" in res.markdown
    assert "<table" not in res.markdown
    # residual <img>/<div> (seal box) stripped
    assert "<img" not in res.markdown and "seal_983_605" not in res.markdown
    # structured extraction
    assert len(res.tables) == 1
    t = res.tables[0]
    assert t.header == ["Mã số", "Năm nay"]
    assert t.rows == [["01", "125.780.761"], ["02", "(92.891)"]]


def test_keep_html_option():
    res = PostProcessor(strip_html=False).process_text(_HTML)
    assert "seal_983_605" in res.markdown        # img kept when strip_html=False
