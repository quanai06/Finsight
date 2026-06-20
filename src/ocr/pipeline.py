"""Orchestrates the end-to-end OCR flow: PDF -> images -> OCR -> Markdown.

    PDFLoader  --pages-->  OCREngine  --PageResults-->  MarkdownWriter

The pipeline owns no model logic itself; it wires the components together and
collects timing, so the engine can be swapped without touching this file.
"""

from __future__ import annotations

import logging
import time

from .config import OCRConfig
from .engine import OCREngine, build_engine
from .markdown_writer import MarkdownWriter
from .models import DocumentResult
from .pdf_loader import PDFLoader

logger = logging.getLogger(__name__)


class OCRPipeline:
    """High-level entry point. Inject a custom engine, or let it build one."""

    def __init__(self, config: OCRConfig, engine: OCREngine | None = None) -> None:
        self.config = config
        self.loader = PDFLoader(dpi=config.dpi)
        self.engine = engine or build_engine(config.engine, device=config.device)
        self.writer = MarkdownWriter(config)

    def run(self) -> DocumentResult:
        cfg = self.config
        logger.info("OCR run | doc=%s | engine=%s | device=%s",
                    cfg.input_path.name, self.engine.name, cfg.device)

        pages, render_s = self.loader.render(
            cfg.input_path, cfg.work_dir,
            first_page=cfg.first_page, last_page=cfg.last_page,
            max_pages=cfg.max_pages,
        )

        self.engine.warm_up()
        doc = DocumentResult(source=cfg.input_path, engine=self.engine.name,
                             render_s=render_s)

        t0 = time.perf_counter()
        for page in pages:
            result = self.engine.recognize(page.path, page.index)
            doc.pages.append(result)
            logger.info("page %3d/%d  %5.2fs  chars=%6d  tables=%d",
                        page.index + 1, len(pages), result.elapsed_s,
                        result.n_chars, result.n_tables)
        logger.info("OCR finished: %d pages in %.1fs", doc.num_pages,
                    time.perf_counter() - t0)

        md_path = self.writer.write(doc)
        self._log_summary(doc, md_path)
        return doc

    @staticmethod
    def _log_summary(doc: DocumentResult, md_path) -> None:
        ocr_s = doc.ocr_s or 1e-9
        bar = "=" * 46
        # build with f-strings (thousands separators aren't valid in %-logging)
        summary = (
            f"\n{bar}\nPERFORMANCE SUMMARY\n{bar}\n"
            f"pages        : {doc.num_pages}\n"
            f"render time  : {doc.render_s:.1f} s\n"
            f"ocr time     : {doc.ocr_s:.1f} s  "
            f"({doc.num_pages / ocr_s:.2f} pages/s, "
            f"{ocr_s / max(doc.num_pages, 1):.2f} s/page)\n"
            f"total chars  : {doc.total_chars:,}\n"
            f"total tables : {doc.total_tables}\n"
            f"markdown     : {md_path}\n{bar}"
        )
        logger.info(summary)
