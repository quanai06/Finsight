"""Rasterise a (scanned-image) PDF into per-page PNGs using PyMuPDF.

PyMuPDF is a pure-wheel dependency, so this avoids the system-level ``poppler``
requirement that ``pdf2image`` needs.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from .models import PageImage

logger = logging.getLogger(__name__)


class PDFLoader:
    """Render a PDF to image files on disk."""

    def __init__(self, dpi: int = 200) -> None:
        self.dpi = dpi

    def render(
        self,
        pdf_path: Path,
        work_dir: Path,
        first_page: Optional[int] = None,
        last_page: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> tuple[list[PageImage], float]:
        """Render ``pdf_path`` into ``work_dir``; return (pages, elapsed_seconds).

        ``first_page``/``last_page`` are 1-based and inclusive; ``max_pages``
        further caps the count from ``first_page``.
        """
        import fitz  # PyMuPDF — imported lazily so the module loads without it

        pdf_path = Path(pdf_path)
        work_dir.mkdir(parents=True, exist_ok=True)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        t0 = time.perf_counter()
        pages: list[PageImage] = []
        with fitz.open(pdf_path) as doc:
            start = (first_page - 1) if first_page else 0
            start = max(0, min(start, doc.page_count))
            end = last_page if last_page else doc.page_count
            end = max(start, min(end, doc.page_count))
            if max_pages is not None:
                end = min(end, start + max_pages)
            logger.info("Rendering pages %d-%d of %d @ %d DPI",
                        start + 1, end, doc.page_count, self.dpi)
            for i in range(start, end):
                page = doc.load_page(i)
                pix = page.get_pixmap(dpi=self.dpi)
                out = work_dir / f"{pdf_path.stem}_p{i + 1:03d}.png"
                pix.save(out)
                pages.append(
                    PageImage(index=i, path=out, width=pix.width,
                              height=pix.height, dpi=self.dpi)
                )
        elapsed = time.perf_counter() - t0
        logger.info("Rendered %d pages in %.1fs", len(pages), elapsed)
        return pages, elapsed
