"""Turn an uploaded file into normalized Markdown for indexing.

Three accepted kinds, mirroring the project's OCR->RAG flow but staying usable
without a GPU:

  * ``.md``   — used as-is (the fast path you want while there is no GPU).
  * ``.json`` — rendered to readable Markdown (works for OCR-export JSON or any
                nested structure).
  * ``.pdf``  — extract the embedded text layer with PyMuPDF (instant, CPU). If
                the PDF is scanned (no text layer), fall back to the project's
                OCR pipeline; if OCR isn't available, the document is flagged so
                the user knows it needs a GPU/OCR run.

Returns ``(markdown, source_label)`` where ``source_label`` records which path
produced the text, surfaced in the UI for transparency.
"""

from __future__ import annotations

import json
from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".md", ".markdown", ".json"}


def detect_kind(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in (".md", ".markdown"):
        return "md"
    if ext == ".json":
        return "json"
    raise ValueError(f"Unsupported file type: {ext or '(none)'}")


def ingest_file(path: Path, enable_ocr: bool = False) -> tuple[str, str]:
    """Dispatch on extension and return (markdown, source_label).

    ``enable_ocr`` controls the scanned-PDF fallback: when False (default) a PDF
    with no text layer is rejected instead of spinning up PaddleOCR-VL in-process.
    """
    kind = detect_kind(path.name)
    if kind == "md":
        return path.read_text(encoding="utf-8", errors="replace"), "markdown"
    if kind == "json":
        return _json_to_markdown(path), "json"
    return _pdf_to_markdown(path, enable_ocr=enable_ocr)


# --------------------------------------------------------------------- json
def _json_to_markdown(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # not valid JSON — index the raw text rather than failing the upload
        return raw

    # Recognised schema: the project's OCR table export
    #   {"tables": [{index, n_rows, n_cols, header: [...], rows: [[...], ...]}]}
    tables = _extract_table_export(data)
    if tables is not None:
        return _render_table_export(path.stem, tables)

    lines: list[str] = [f"# {path.stem}", ""]
    _render_json(data, lines, depth=0)
    return "\n".join(lines).strip() + "\n"


def _extract_table_export(data) -> list | None:
    """Return a list of table objects if ``data`` is an OCR table export."""
    tables = data.get("tables") if isinstance(data, dict) else data
    if (
        isinstance(tables, list)
        and tables
        and all(isinstance(t, dict) and "rows" in t for t in tables)
    ):
        return tables
    return None


def _render_table_export(stem: str, tables: list) -> str:
    """Render each OCR-extracted table as a clean Markdown pipe table.

    The structural metadata (index/n_rows/n_cols) is dropped so the chunk holds
    only the table's text + numbers — exactly what retrieval and the LLM need.
    """
    lines: list[str] = [f"# {stem}", ""]
    for i, table in enumerate(tables):
        header = [_scalar(c) for c in (table.get("header") or [])]
        rows = table.get("rows") or []
        lines.append(f"## Table {table.get('index', i)}")
        if header and any(h.strip() for h in header):
            lines.append("| " + " | ".join(_cell(h) for h in header) + " |")
            lines.append("| " + " | ".join("---" for _ in header) + " |")
        width = len(header) or (len(rows[0]) if rows else 0)
        for row in rows:
            cells = [_cell(_scalar(c)) for c in row]
            cells += [""] * (width - len(cells))  # pad ragged rows
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _cell(value: str) -> str:
    """Make a value safe to place inside a Markdown table cell."""
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _render_json(node, lines: list[str], depth: int) -> None:
    indent = "  " * depth
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{indent}- **{key}**:")
                _render_json(value, lines, depth + 1)
            else:
                lines.append(f"{indent}- **{key}**: {_scalar(value)}")
    elif isinstance(node, list):
        # a list of flat dicts renders nicely as a Markdown table
        if node and all(isinstance(x, dict) for x in node) and _flat_dicts(node):
            _render_table(node, lines, indent)
        else:
            for item in node:
                if isinstance(item, (dict, list)):
                    _render_json(item, lines, depth)
                else:
                    lines.append(f"{indent}- {_scalar(item)}")
    else:
        lines.append(f"{indent}{_scalar(node)}")


def _flat_dicts(rows: list[dict]) -> bool:
    return all(
        all(not isinstance(v, (dict, list)) for v in row.values()) for row in rows
    )


def _render_table(rows: list[dict], lines: list[str], indent: str) -> None:
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    lines.append(indent + "| " + " | ".join(columns) + " |")
    lines.append(indent + "| " + " | ".join("---" for _ in columns) + " |")
    for row in rows:
        cells = [_scalar(row.get(c, "")) for c in columns]
        lines.append(indent + "| " + " | ".join(cells) + " |")
    lines.append("")


def _scalar(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).replace("\n", " ").strip()


# ---------------------------------------------------------------------- pdf
def _pdf_to_markdown(path: Path, enable_ocr: bool = False) -> tuple[str, str]:
    """Prefer the embedded text layer; fall back to OCR only if needed."""
    text = _extract_pdf_text(path)
    if text and len(text.strip()) > 40:
        return text, "pdf-text"

    # No usable text layer -> scanned PDF. In-API OCR is gated: PaddleOCR-VL
    # loads a multi-GB VLM into this process and isn't released, so it stays off
    # unless explicitly enabled (FINSIGHT_ENABLE_API_OCR=true).
    if not enable_ocr:
        raise RuntimeError(
            "This PDF has no extractable text layer (it looks scanned). In-API "
            "OCR is disabled to protect memory. Run OCR offline first "
            "(python -m src.ocr ...) and upload the Markdown/JSON export, or set "
            "FINSIGHT_ENABLE_API_OCR=true to OCR inside the API."
        )

    ocr_md = _try_ocr(path)
    if ocr_md is not None:
        return ocr_md, "ocr"

    raise RuntimeError(
        "This PDF has no extractable text layer (it looks scanned) and OCR is "
        "not available on this machine. Upload a Markdown/JSON export instead, "
        "or run OCR on a GPU machine first."
    )


def _extract_pdf_text(path: Path) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return ""
    parts: list[str] = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc):
            body = page.get_text("text").strip()
            if body:
                parts.append(f"<!-- ===== page {i + 1} ===== -->")
                parts.append(body)
    return "\n\n".join(parts)


def _try_ocr(path: Path) -> str | None:
    try:
        from src.ocr import OCRConfig, OCRPipeline
    except Exception:  # noqa: BLE001 - paddle/ocr extras may be absent
        return None
    try:
        config = OCRConfig(input_path=path)
        doc = OCRPipeline(config).run()
        return doc.to_markdown()
    except Exception:  # noqa: BLE001 - OCR may need a GPU / model weights
        return None
