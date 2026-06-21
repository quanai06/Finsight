"""Structure-aware Markdown chunking.

A naive fixed-width window splits tables mid-row and severs headings from their
content, which hurts both retrieval and the LLM's reading. This splitter instead
respects document structure:

  * **Page markers** (``<!-- ===== page N ===== -->``) and **headings** never get
    cut across; each chunk records its page and its heading breadcrumb.
  * **Markdown tables** are kept intact: the header row is repeated for every
    row-group so each table chunk is self-contained (critical for financial
    tables where a stray row of numbers is meaningless without its header).
  * **Prose** is packed paragraph-by-paragraph up to the target size, only
    falling back to a sentence/word window for a single oversized paragraph.

Every chunk carries ``page`` and ``heading`` metadata used for citations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_PAGE_RE = re.compile(r"<!--\s*=+\s*page\s+(\d+)\s*=+\s*-->", re.IGNORECASE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}")


@dataclass(slots=True)
class Chunk:
    text: str
    doc_id: str
    doc_name: str
    page: int | None = None
    heading: str = ""           # breadcrumb of enclosing headings, "A > B"
    ordinal: int = 0
    metadata: dict = field(default_factory=dict)


def _is_table_line(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.count("|") >= 2


@dataclass(slots=True)
class _Block:
    kind: str                   # "text" | "table"
    page: int | None
    heading: str
    lines: list[str]


def _parse_blocks(markdown: str) -> list[_Block]:
    blocks: list[_Block] = []
    page: int | None = None
    heading_stack: list[tuple[int, str]] = []
    text_buf: list[str] = []

    def breadcrumb() -> str:
        return " > ".join(title for _, title in heading_stack)

    def flush_text() -> None:
        if any(l.strip() for l in text_buf):
            blocks.append(_Block("text", page, breadcrumb(), text_buf.copy()))
        text_buf.clear()

    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]

        m_page = _PAGE_RE.search(line)
        if m_page:
            flush_text()
            page = int(m_page.group(1))
            i += 1
            continue

        m_head = _HEADING_RE.match(line)
        if m_head:
            flush_text()
            level = len(m_head.group(1))
            title = m_head.group(2).strip()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            i += 1
            continue

        if _is_table_line(line):
            flush_text()
            table: list[str] = []
            while i < len(lines) and _is_table_line(lines[i]):
                table.append(lines[i])
                i += 1
            if len(table) >= 2:
                blocks.append(_Block("table", page, breadcrumb(), table))
            else:
                text_buf.extend(table)  # a lone pipe line — treat as prose
            continue

        text_buf.append(line)
        i += 1

    flush_text()
    return blocks


def _split_prose(text: str, size: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    paras = re.split(r"\n{2,}", text)
    chunks: list[str] = []
    cur = ""
    for para in paras:
        para = para.strip()
        if not para:
            continue
        if len(para) > size:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.extend(_window(para, size, overlap))
        elif len(cur) + len(para) + 2 <= size:
            cur = f"{cur}\n\n{para}" if cur else para
        else:
            chunks.append(cur)
            cur = para
    if cur:
        chunks.append(cur)
    return chunks


def _window(text: str, size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    start, n = 0, len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            window = text[start:end]
            for sep in (". ", "\n", " "):
                cut = window.rfind(sep)
                if cut > size * 0.5:
                    end = start + cut + len(sep)
                    break
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


def _split_table(lines: list[str], size: int) -> list[str]:
    """Split a Markdown table into row-groups, repeating the header each time."""
    header: list[str] = []
    body_start = 0
    if lines:
        header.append(lines[0])
        if len(lines) > 1 and _TABLE_SEP_RE.match(lines[1]):
            header.append(lines[1])
            body_start = 2
        else:
            body_start = 1
    header_text = "\n".join(header)
    rows = lines[body_start:]
    if not rows:
        return [header_text] if header_text.strip() else []

    chunks: list[str] = []
    group: list[str] = []
    cur_len = len(header_text)
    for row in rows:
        if group and cur_len + len(row) + 1 > size:
            chunks.append(header_text + "\n" + "\n".join(group))
            group = []
            cur_len = len(header_text)
        group.append(row)
        cur_len += len(row) + 1
    if group:
        chunks.append(header_text + "\n" + "\n".join(group))
    return chunks


def chunk_markdown(
    markdown: str,
    *,
    doc_id: str,
    doc_name: str,
    chunk_size: int = 1000,
    overlap: int = 150,
) -> list[Chunk]:
    """Turn a Markdown document into structure-aware, page/heading-tagged chunks."""
    chunks: list[Chunk] = []
    ordinal = 0
    for block in _parse_blocks(markdown):
        if block.kind == "table":
            pieces = _split_table(block.lines, chunk_size)
        else:
            pieces = _split_prose("\n".join(block.lines), chunk_size, overlap)

        for piece in pieces:
            # prepend the heading breadcrumb so the chunk carries its context
            text = f"{block.heading}\n\n{piece}" if block.heading else piece
            chunks.append(
                Chunk(
                    text=text,
                    doc_id=doc_id,
                    doc_name=doc_name,
                    page=block.page,
                    heading=block.heading,
                    ordinal=ordinal,
                )
            )
            ordinal += 1
    return chunks
