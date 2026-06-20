"""Domain models for the OCR pipeline.

These are plain data containers (no behaviour beyond simple derivations) shared
across the loader, engine and writer so each component stays decoupled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class PageImage:
    """A single rendered PDF page ready to be fed to an OCR engine."""

    index: int                # 0-based page number
    path: Path                # path to the rendered PNG on disk
    width: int
    height: int
    dpi: int


@dataclass(slots=True)
class PageResult:
    """The OCR output for one page."""

    index: int                # 0-based page number
    markdown: str             # page content as Markdown (tables included)
    elapsed_s: float          # OCR wall-clock time for this page
    raw: dict = field(default_factory=dict, repr=False)  # engine's structured JSON

    @property
    def n_chars(self) -> int:
        return len(self.markdown)

    @property
    def n_tables(self) -> int:
        # count HTML tables and Markdown pipe-tables
        return self.markdown.count("<table") + self.markdown.count("|---")


@dataclass(slots=True)
class DocumentResult:
    """Aggregated OCR result for a whole document."""

    source: Path
    engine: str
    pages: list[PageResult] = field(default_factory=list)
    render_s: float = 0.0     # time spent rasterising the PDF

    @property
    def num_pages(self) -> int:
        return len(self.pages)

    @property
    def ocr_s(self) -> float:
        return sum(p.elapsed_s for p in self.pages)

    @property
    def total_chars(self) -> int:
        return sum(p.n_chars for p in self.pages)

    @property
    def total_tables(self) -> int:
        return sum(p.n_tables for p in self.pages)

    def to_markdown(self, *, page_separators: bool = True) -> str:
        """Concatenate every page into one Markdown document."""
        parts: list[str] = []
        for page in self.pages:
            if page_separators:
                parts.append(f"<!-- ===== page {page.index + 1} ===== -->")
            parts.append(page.markdown.strip())
        return "\n\n".join(parts) + "\n"
