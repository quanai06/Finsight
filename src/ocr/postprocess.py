"""Post-process OCR Markdown: HTML tables -> clean Markdown + structured JSON.

PaddleOCR-VL emits tables as verbose HTML (inline ``style=`` on every cell),
which roughly doubles token cost and isn't query-able. This module:

  1. parses each ``<table>`` into a grid (stdlib HTML parser, no bs4 dependency),
  2. rewrites it as a clean Markdown pipe table (≈2× fewer tokens),
  3. extracts every table as structured records (header + rows) for RAG/analysis,
  4. optionally strips residual HTML (``<img>`` seal boxes, ``<div>`` wrappers).

Runs on existing OCR output — no need to re-run the (slow) OCR.

CLI:
    python -m src.ocr.postprocess --input data/processed/ocr/2021_bctc_hop_nhat_pages
    python -m src.ocr.postprocess --input page_013.md --out-md clean.md --out-json t.json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

_TABLE_RE = re.compile(r"<table.*?</table>", re.DOTALL | re.IGNORECASE)
_HTML_TAG = re.compile(r"<[^>]+>")
_BLANKS = re.compile(r"\n{3,}")


class _TableParser(HTMLParser):
    """Collect ``<table>`` content as a list of rows (each row a list of cells)."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append("".join(self._cell).strip())  # type: ignore[union-attr]
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def parse_table(html: str) -> list[list[str]]:
    p = _TableParser()
    p.feed(html)
    return p.rows


def _esc(cell: str) -> str:
    return cell.replace("|", "\\|").replace("\n", " ").strip()


def rows_to_markdown(rows: list[list[str]]) -> str:
    """Render a grid as a Markdown pipe table (first row = header)."""
    if not rows:
        return ""
    ncols = max(len(r) for r in rows)
    rows = [r + [""] * (ncols - len(r)) for r in rows]
    out = ["| " + " | ".join(_esc(c) for c in rows[0]) + " |",
           "|" + "|".join(["---"] * ncols) + "|"]
    out += ["| " + " | ".join(_esc(c) for c in r) + " |" for r in rows[1:]]
    return "\n".join(out)


@dataclass(slots=True)
class TableRecord:
    index: int
    n_rows: int
    n_cols: int
    header: list[str]
    rows: list[list[str]]

    def as_dict(self) -> dict:
        return {"index": self.index, "n_rows": self.n_rows, "n_cols": self.n_cols,
                "header": self.header, "rows": self.rows}


@dataclass(slots=True)
class PostResult:
    markdown: str
    tables: list[TableRecord] = field(default_factory=list)


class PostProcessor:
    """Convert OCR Markdown's HTML tables to clean Markdown + extract records."""

    def __init__(self, *, strip_html: bool = True) -> None:
        self.strip_html = strip_html

    def process_text(self, text: str) -> PostResult:
        tables: list[TableRecord] = []
        for i, m in enumerate(_TABLE_RE.finditer(text)):
            grid = parse_table(m.group(0))
            if grid:
                ncols = max(len(r) for r in grid)
                tables.append(TableRecord(index=i, n_rows=len(grid), n_cols=ncols,
                                          header=grid[0], rows=grid[1:]))

        md = _TABLE_RE.sub(lambda m: rows_to_markdown(parse_table(m.group(0))), text)
        if self.strip_html:
            md = _HTML_TAG.sub("", md)          # drop <img>/<div> seal-box leftovers
        md = _BLANKS.sub("\n\n", md).strip() + "\n"
        return PostResult(markdown=md, tables=tables)

    def process_file(self, path: Path, out_md: Path | None = None,
                     out_json: Path | None = None) -> PostResult:
        res = self.process_text(Path(path).read_text(encoding="utf-8"))
        if out_md:
            out_md.parent.mkdir(parents=True, exist_ok=True)
            out_md.write_text(res.markdown, encoding="utf-8")
        if out_json:
            out_json.parent.mkdir(parents=True, exist_ok=True)
            out_json.write_text(
                json.dumps({"tables": [t.as_dict() for t in res.tables]},
                           ensure_ascii=False, indent=2), encoding="utf-8")
        return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m src.ocr.postprocess")
    ap.add_argument("--input", required=True, help="a .md file or a folder of .md")
    ap.add_argument("--pattern", default="*.md")
    ap.add_argument("--out-dir", default="data/processed/ocr_clean")
    ap.add_argument("--keep-html", action="store_true",
                    help="keep <img>/<div> instead of stripping them")
    args = ap.parse_args(argv)

    proc = PostProcessor(strip_html=not args.keep_html)
    inp = Path(args.input)
    files = sorted(inp.glob(args.pattern)) if inp.is_dir() else [inp]
    out_dir = Path(args.out_dir)

    total_in = total_out = total_tables = 0
    for f in files:
        res = proc.process_file(
            f, out_md=out_dir / f.name,
            out_json=out_dir / f"{f.stem}_tables.json")
        total_in += len(f.read_text(encoding="utf-8"))
        total_out += len(res.markdown)
        total_tables += len(res.tables)
        print(f"{f.name}: {len(res.tables)} table(s), "
              f"{len(f.read_text(encoding='utf-8'))} -> {len(res.markdown)} chars")

    if total_in:
        print(f"\nTotal: {len(files)} file(s), {total_tables} table(s), "
              f"{total_in} -> {total_out} chars "
              f"({100 * (1 - total_out / total_in):.0f}% smaller) -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
