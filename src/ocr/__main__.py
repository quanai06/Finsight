"""CLI entry point.

Single file:
    python -m src.ocr --input data/raw/2021_bctc_hop_nhat.pdf --max-pages 3
    python -m src.ocr --config configs/ocr.yaml

Batch (all PDFs in a folder, model loaded once, resume-safe):
    python -m src.ocr --input-dir data/raw
    python -m src.ocr --input-dir data/raw --overwrite
"""

from __future__ import annotations

import argparse
import logging
import sys

from .batch import BatchProcessor
from .config import OCRConfig
from .pipeline import OCRPipeline


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m src.ocr",
                                description="PDF -> Markdown OCR (PaddleOCR-VL).")
    p.add_argument("--config", help="YAML config file (overridden by flags below)")
    p.add_argument("--input", help="path to a single PDF")
    p.add_argument("--input-dir", help="folder of PDFs to OCR in batch")
    p.add_argument("--pattern", default="*.pdf", help="glob for --input-dir")
    p.add_argument("--overwrite", action="store_true",
                   help="re-OCR files even if their Markdown already exists")
    p.add_argument("--output-dir", default="data/processed/ocr")
    p.add_argument("--engine", default="paddleocr-vl")
    p.add_argument("--device", default="auto", choices=["auto", "cpu", "gpu"],
                   help="auto = use GPU if available, else CPU")
    p.add_argument("--dpi", type=int, default=200)
    p.add_argument("--first-page", type=int, default=None,
                   help="1-based start page (inclusive)")
    p.add_argument("--last-page", type=int, default=None,
                   help="1-based end page (inclusive)")
    p.add_argument("--max-pages", type=int, default=None,
                   help="cap the number of pages (useful on CPU)")
    return p.parse_args(argv)


def _config_from_args(args: argparse.Namespace, *, input_path: str) -> OCRConfig:
    if args.config:
        cfg = OCRConfig.from_yaml(args.config)
        cfg.input_path = input_path          # type: ignore[assignment]
        cfg.__post_init__()
        return cfg
    return OCRConfig(
        input_path=input_path,
        output_dir=args.output_dir,
        engine=args.engine,
        device=args.device,
        dpi=args.dpi,
        first_page=args.first_page,
        last_page=args.last_page,
        max_pages=args.max_pages,
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    # --- batch mode ---
    if args.input_dir:
        # input_path is a placeholder; BatchProcessor swaps it per file
        base = _config_from_args(args, input_path="__placeholder__.pdf")
        proc = BatchProcessor(base)
        files = proc.discover(args.input_dir, args.pattern)
        if not files:
            print(f"No files in {args.input_dir} matching {args.pattern}")
            return 1
        proc.run(files, overwrite=args.overwrite)
        return 0

    # --- single-file mode ---
    if not (args.input or args.config):
        print("error: provide --input, --config, or --input-dir", file=sys.stderr)
        return 2
    cfg = _config_from_args(args, input_path=args.input) if args.input \
        else OCRConfig.from_yaml(args.config)
    OCRPipeline(cfg).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
