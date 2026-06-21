"""Split Markdown documents into retrieval chunks.

Chunking is character-window based with overlap, but it respects the natural
structure of OCR output: page markers (``<!-- ===== page N ===== -->``) and
Markdown headings start a new chunk so a retrieved snippet stays coherent and
can be cited back to a page.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_PAGE_RE = re.compile(r"<!--\s*=+\s*page\s+(\d+)\s*=+\s*-->", re.IGNORECASE)
_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)


@dataclass(slots=True)
class Chunk:
    """One retrievable unit of text plus where it came from."""

    text: str
    doc_id: str
    doc_name: str
    page: int | None = None
    ordinal: int = 0                       # position of the chunk within the doc
    metadata: dict = field(default_factory=dict)


def _split_into_sections(markdown: str) -> list[tuple[int | None, str]]:
    """Break the document at page markers; track the current page number."""
    sections: list[tuple[int | None, str]] = []
    last_end = 0
    page: int | None = None
    for m in _PAGE_RE.finditer(markdown):
        body = markdown[last_end:m.start()].strip()
        if body:
            sections.append((page, body))
        page = int(m.group(1))
        last_end = m.end()
    tail = markdown[last_end:].strip()
    if tail:
        sections.append((page, tail))
    return sections or [(None, markdown.strip())]


def _window(text: str, size: int, overlap: int) -> list[str]:
    """Slide a window over ``text``, preferring to break on paragraph breaks."""
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            # try to end on a paragraph/sentence boundary inside the window tail
            window = text[start:end]
            for sep in ("\n\n", "\n", ". "):
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


def chunk_markdown(
    markdown: str,
    *,
    doc_id: str,
    doc_name: str,
    chunk_size: int = 900,
    overlap: int = 150,
) -> list[Chunk]:
    """Turn a Markdown document into overlapping, page-aware chunks."""
    chunks: list[Chunk] = []
    ordinal = 0
    for page, section in _split_into_sections(markdown):
        for piece in _window(section, chunk_size, overlap):
            chunks.append(
                Chunk(
                    text=piece,
                    doc_id=doc_id,
                    doc_name=doc_name,
                    page=page,
                    ordinal=ordinal,
                )
            )
            ordinal += 1
    return chunks
