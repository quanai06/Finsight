"""Batch OCR over many PDFs.

OCR is compute-bound (the model saturates the CPU/GPU on a single page), so on
one machine the right strategy is *sequential* processing with the model loaded
**once** and reused across files — not multiprocessing, which would just cause
the workers to fight over the same cores.

    BatchProcessor
      ├─ build ONE engine (shared)
      ├─ for each pdf:
      │     skip if markdown already exists (resume-safe)
      │     OCRPipeline(file_cfg, engine=shared).run()
      │     record outcome (one bad file never kills the batch)
      └─ write a batch report CSV
"""

from __future__ import annotations

import csv
import dataclasses
import logging
import time
from pathlib import Path

from .config import OCRConfig
from .engine import OCREngine, build_engine
from .pipeline import OCRPipeline

logger = logging.getLogger(__name__)


@dataclasses.dataclass(slots=True)
class FileOutcome:
    """Result of OCR'ing one file within a batch."""

    path: Path
    status: str          # "done" | "skipped" | "failed"
    pages: int = 0
    ocr_s: float = 0.0
    markdown: Path | None = None
    error: str = ""


class BatchProcessor:
    """Run the OCR pipeline over a set of PDFs, reusing a single engine."""

    def __init__(self, base_config: OCRConfig, engine: OCREngine | None = None) -> None:
        self.base_config = base_config
        # one shared engine for the whole batch (model loaded once)
        self.engine = engine or build_engine(base_config.engine,
                                              device=base_config.device)

    @staticmethod
    def discover(input_dir: str | Path, pattern: str = "*.pdf") -> list[Path]:
        files = sorted(Path(input_dir).glob(pattern))
        logger.info("Discovered %d file(s) in %s matching %s",
                    len(files), input_dir, pattern)
        return files

    def run(self, pdf_paths: list[Path], *, overwrite: bool = False) -> list[FileOutcome]:
        self.engine.warm_up()  # pay the model-load cost exactly once
        outcomes: list[FileOutcome] = []
        t0 = time.perf_counter()

        for i, pdf in enumerate(pdf_paths, 1):
            cfg = dataclasses.replace(self.base_config, input_path=pdf)

            # resume-safe: skip files already OCR'd
            if cfg.markdown_path.exists() and not overwrite:
                logger.info("[%d/%d] skip (exists): %s", i, len(pdf_paths), pdf.name)
                outcomes.append(FileOutcome(pdf, "skipped",
                                            markdown=cfg.markdown_path))
                continue

            logger.info("[%d/%d] OCR: %s", i, len(pdf_paths), pdf.name)
            try:
                doc = OCRPipeline(cfg, engine=self.engine).run()
                outcomes.append(FileOutcome(
                    pdf, "done", pages=doc.num_pages, ocr_s=doc.ocr_s,
                    markdown=cfg.markdown_path))
            except Exception as exc:  # noqa: BLE001 — isolate per-file failures
                logger.exception("[%d/%d] FAILED: %s", i, len(pdf_paths), pdf.name)
                outcomes.append(FileOutcome(pdf, "failed", error=str(exc)))

        self._report(outcomes, time.perf_counter() - t0)
        return outcomes

    def _report(self, outcomes: list[FileOutcome], elapsed: float) -> None:
        done = [o for o in outcomes if o.status == "done"]
        skipped = [o for o in outcomes if o.status == "skipped"]
        failed = [o for o in outcomes if o.status == "failed"]

        report_path = self.base_config.output_dir / "_batch_report.csv"
        self.base_config.output_dir.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["file", "status", "pages", "ocr_s", "markdown", "error"])
            for o in outcomes:
                w.writerow([o.path.name, o.status, o.pages, f"{o.ocr_s:.1f}",
                            o.markdown or "", o.error])

        bar = "=" * 46
        logger.info(
            "\n%s\nBATCH SUMMARY\n%s\n"
            "files        : %d (done %d, skipped %d, failed %d)\n"
            "pages OCR'd  : %d\n"
            "wall time    : %.1f s\n"
            "report       : %s\n%s",
            bar, bar, len(outcomes), len(done), len(skipped), len(failed),
            sum(o.pages for o in done), elapsed, report_path, bar,
        )
        if failed:
            logger.warning("Failed files: %s", ", ".join(o.path.name for o in failed))
