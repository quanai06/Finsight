"""Persist OCR results as Markdown (and a small performance report)."""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from .config import OCRConfig
from .models import DocumentResult

logger = logging.getLogger(__name__)


class MarkdownWriter:
    """Write the merged Markdown, optional per-page Markdown, and a perf CSV."""

    def __init__(self, config: OCRConfig) -> None:
        self.config = config

    def write(self, doc: DocumentResult) -> Path:
        cfg = self.config
        cfg.ensure_dirs()

        # 1) merged document
        merged = doc.to_markdown(page_separators=cfg.page_separators)
        cfg.markdown_path.write_text(merged, encoding="utf-8")
        logger.info("Wrote %s (%d chars)", cfg.markdown_path, len(merged))

        # 2) per-page markdown
        if cfg.save_page_markdown:
            pages_dir = cfg.output_dir / f"{cfg.doc_stem}_pages"
            pages_dir.mkdir(parents=True, exist_ok=True)
            for page in doc.pages:
                (pages_dir / f"page_{page.index + 1:03d}.md").write_text(
                    page.markdown, encoding="utf-8"
                )

        # 3) performance report
        self._write_report(doc)
        return cfg.markdown_path

    def _write_report(self, doc: DocumentResult) -> None:
        with open(self.config.report_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["page", "sec", "chars", "tables"])
            for p in doc.pages:
                w.writerow([p.index + 1, f"{p.elapsed_s:.2f}", p.n_chars, p.n_tables])
        logger.info("Wrote perf report %s", self.config.report_path)
