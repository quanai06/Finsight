"""Structure-aware Markdown chunking.

A naive fixed-width window splits tables mid-row and severs headings from their
content, which hurts both retrieval and the LLM's reading. This splitter instead
respects document structure:

  * **Page markers** (``<!-- ===== page N ===== -->``) and **headings** never get
    cut across; each chunk records its page and its heading breadcrumb.
  * **Markdown tables** are kept intact: the header row is repeated for every
    row-group so each table chunk is self-contained (critical for financial
    tables where a stray row of numbers is meaningless without its header). A
    table's **caption and unit-of-measure** ("Đơn vị tính: triệu đồng"), which
    sit in the prose just before it, are captured and attached — otherwise a
    figure loses its 1000× scale. Each row-group child also carries the *whole*
    table as ``parent_text`` (small-to-big): retrieval matches the precise group,
    generation gets the full table (totals, sibling rows).
  * **Prose** is packed paragraph-by-paragraph up to the target size, only
    falling back to a sentence/word window for a single oversized paragraph.

A short ``doc_context`` (e.g. document name + year) is prepended to every chunk
so retrieval can tell apart otherwise-identical lines across reports/years.

Every chunk carries ``page`` and ``heading`` metadata used for citations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .financial_sections import detect_note_no, detect_statement_type

_PAGE_RE = re.compile(r"<!--\s*=+\s*page\s+(\d+)\s*=+\s*-->", re.IGNORECASE)
_SECTION_PARENT_MAX = 4000  # only expand a prose section to its parent if it fits
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}")
# "Đơn vị tính: triệu đồng" / "Unit: million VND" — capture the unit phrase.
_UNIT_RE = re.compile(r"(đơn\s*vị\s*tính|unit)\s*[:\.]?\s*(.+)", re.IGNORECASE)


@dataclass(slots=True)
class Chunk:
    text: str
    doc_id: str
    doc_name: str
    page: int | None = None
    heading: str = ""           # breadcrumb of enclosing headings, "A > B"
    ordinal: int = 0
    parent_id: str = ""         # groups a table's row-groups / a section's prose
    parent_text: str = ""       # the whole table / section, fetched for generation
    # --- financial-report hierarchy (used for routing + small-to-big) ---
    statement_type: str = ""    # cdkt | kqkd | lctt | thuyet_minh | kiem_toan | bgd
    note_no: int | None = None  # thuyết-minh note number, when applicable
    section_id: str = ""        # stable id of the enclosing heading section
    parent_section_id: str = ""  # id of the parent section in the tree
    year: int | None = None     # document period, for per-year filtering
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
    caption: str = ""           # table only: nearest prose line before it
    unit: str = ""              # table only: "đơn vị tính" carried forward


def _parse_blocks(markdown: str) -> list[_Block]:
    blocks: list[_Block] = []
    page: int | None = None
    heading_stack: list[tuple[int, str]] = []
    text_buf: list[str] = []
    caption = ""                # last short prose line — likely a table title
    unit = ""                   # most recent unit-of-measure, carried forward

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
            caption = title       # a heading is a strong caption candidate
            i += 1
            continue

        if _is_table_line(line):
            flush_text()
            table: list[str] = []
            while i < len(lines) and _is_table_line(lines[i]):
                table.append(lines[i])
                i += 1
            if len(table) >= 2:
                blocks.append(
                    _Block("table", page, breadcrumb(), table, caption, unit)
                )
            else:
                text_buf.extend(table)  # a lone pipe line — treat as prose
            continue

        # plain prose line — track caption + unit so the next table inherits them
        m_unit = _UNIT_RE.search(line)
        if m_unit:
            unit = m_unit.group(0).strip()
        if line.strip():
            caption = line.strip()
        text_buf.append(line)
        i += 1

    flush_text()
    return blocks


def _split_prose(text: str, size: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    size = max(size, 200)
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


def _table_header(lines: list[str]) -> tuple[str, int]:
    """Return (header_markdown, body_start_index)."""
    header: list[str] = []
    body_start = 0
    if lines:
        header.append(lines[0])
        if len(lines) > 1 and _TABLE_SEP_RE.match(lines[1]):
            header.append(lines[1])
            body_start = 2
        else:
            body_start = 1
    return "\n".join(header), body_start


def _split_table(block: _Block, size: int) -> tuple[list[str], str]:
    """Split a table into row-groups (header repeated), returning (children, parent).

    ``parent`` is the whole table prefixed with its caption + unit so a retrieved
    row-group can be expanded to the full table at generation time.
    """
    lines = block.lines
    header_text, body_start = _table_header(lines)
    # caption/unit context line sits above the header so it travels with the table;
    # skip anything already in the header or heading, and any near-duplicate
    # (the "caption" is often the unit line itself).
    ctx_parts: list[str] = []
    for p in (block.caption, block.unit):
        if not p or p in header_text or p in block.heading:
            continue
        if any(p in q or q in p for q in ctx_parts):
            continue
        ctx_parts.append(p)
    ctx = " — ".join(ctx_parts)
    head_block = f"{ctx}\n{header_text}" if ctx else header_text

    rows = lines[body_start:]
    parent = f"{ctx}\n" + "\n".join(lines) if ctx else "\n".join(lines)
    if not rows:
        return ([head_block] if head_block.strip() else []), parent

    budget = max(size - len(head_block), 200)
    chunks: list[str] = []
    group: list[str] = []
    cur_len = 0
    for row in rows:
        if group and cur_len + len(row) + 1 > budget:
            chunks.append(head_block + "\n" + "\n".join(group))
            group = []
            cur_len = 0
        group.append(row)
        cur_len += len(row) + 1
    if group:
        chunks.append(head_block + "\n" + "\n".join(group))
    return chunks, parent


@dataclass(slots=True)
class _Section:
    section_id: str
    parent_section_id: str
    statement_type: str
    note_no: int | None


def _assign_sections(blocks: list[_Block], doc_id: str) -> tuple[list[_Section], dict[str, str]]:
    """Walk the blocks once, giving each a section identity from its heading
    breadcrumb and inheriting the financial statement type down the tree.

    Ancestor sections are registered even when they hold no content of their own
    (a parent heading with only subsections), so ``parent_section_id`` always
    points at a real node in the tree.
    """
    meta: dict[str, _Section] = {}   # breadcrumb -> section
    counter = [0]

    def register(crumb: str) -> _Section:
        if crumb in meta:
            return meta[crumb]
        parts = crumb.split(" > ") if crumb else []
        parent = register(" > ".join(parts[:-1])) if parts[:-1] else None
        counter[0] += 1
        # statement type: this breadcrumb's own match, else inherit from ancestor
        stype = detect_statement_type(crumb) or (parent.statement_type if parent else "")
        leaf = parts[-1] if parts else ""
        note = detect_note_no(leaf) if stype == "thuyet_minh" else None
        sec = _Section(
            section_id=f"{doc_id}:s{counter[0]}",
            parent_section_id=parent.section_id if parent else "",
            statement_type=stype,
            note_no=note,
        )
        meta[crumb] = sec
        return sec

    sections: list[_Section] = []
    prose_by_section: dict[str, list[str]] = {}
    for block in blocks:
        cur = register(block.heading)
        sections.append(cur)
        if block.kind == "text":
            prose_by_section.setdefault(cur.section_id, []).append("\n".join(block.lines))

    # a prose section small enough to fit is expanded to its parent (small-to-big)
    parents: dict[str, str] = {}
    for sid, parts in prose_by_section.items():
        joined = "\n\n".join(p.strip() for p in parts if p.strip()).strip()
        if joined and len(joined) <= _SECTION_PARENT_MAX:
            parents[sid] = joined
    return sections, parents


def chunk_markdown(
    markdown: str,
    *,
    doc_id: str,
    doc_name: str,
    chunk_size: int = 1800,
    overlap: int = 250,
    doc_context: str = "",
    year: int | None = None,
) -> list[Chunk]:
    """Turn a Markdown document into structure-aware, page/heading-tagged chunks.

    Beyond page/heading/table structure, each chunk is tagged with its financial
    statement type and section in the document tree (see ``financial_sections``),
    enabling query routing and small-to-big expansion. ``doc_context`` and the
    heading breadcrumb are prepended to each chunk's text so the embedding carries
    that context; size budgets account for the prefix so chunks stay near target.
    """
    prefix_base = doc_context.strip()
    blocks = _parse_blocks(markdown)
    sections, section_parents = _assign_sections(blocks, doc_id)

    chunks: list[Chunk] = []
    ordinal = 0
    table_no = 0
    for block, sec in zip(blocks, sections):
        prefix = "\n".join(p for p in (prefix_base, block.heading) if p)
        budget = max(chunk_size - len(prefix), 200)

        if block.kind == "table":
            pieces, table_parent = _split_table(block, budget)
            table_no += 1
            parent_id = f"{doc_id}:t{table_no}"   # each table is its own parent
            parent_text = table_parent
        else:
            pieces = _split_prose("\n".join(block.lines), budget, overlap)
            # only attach a section parent when the whole section was small enough
            section_parent = section_parents.get(sec.section_id, "")
            parent_id = sec.section_id if section_parent else ""
            parent_text = section_parent

        for piece in pieces:
            text = f"{prefix}\n\n{piece}" if prefix else piece
            chunks.append(
                Chunk(
                    text=text,
                    doc_id=doc_id,
                    doc_name=doc_name,
                    page=block.page,
                    heading=block.heading,
                    ordinal=ordinal,
                    parent_id=parent_id,
                    parent_text=parent_text,
                    statement_type=sec.statement_type,
                    note_no=sec.note_no,
                    section_id=sec.section_id,
                    parent_section_id=sec.parent_section_id,
                    year=year,
                )
            )
            ordinal += 1
    return chunks
