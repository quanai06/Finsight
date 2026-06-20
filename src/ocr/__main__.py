"""CLI entry point.

Usage:
    python -m src.ocr --input data/raw/2021_bctc_hop_nhat.pdf --max-pages 3
    python -m src.ocr --config configs/ocr.yaml
"""

from __future__ import annotations

import argparse
import logging
import sys

from .config import OCRConfig
from .pipeline import OCRPipeline


def _build_config(argv: list[str]) -> OCRConfig:
    p = argparse.ArgumentParser(prog="python -m src.ocr",
                                description="PDF -> Markdown OCR (PaddleOCR-VL).")
    p.add_argument("--config", help="YAML config file (overridden by flags below)")
    p.add_argument("--input", help="path to the PDF in data/raw")
    p.add_argument("--output-dir", default="data/processed/ocr")
    p.add_argument("--engine", default="paddleocr-vl")
    p.add_argument("--device", default="cpu", choices=["cpu", "gpu"])
    p.add_argument("--dpi", type=int, default=200)
    p.add_argument("--first-page", type=int, default=None,
                   help="1-based start page (inclusive)")
    p.add_argument("--last-page", type=int, default=None,
                   help="1-based end page (inclusive)")
    p.add_argument("--max-pages", type=int, default=None,
                   help="cap the number of pages (useful on CPU)")
    args = p.parse_args(argv)

    if args.config:
        cfg = OCRConfig.from_yaml(args.config)
        if args.input:        # allow CLI to override the YAML input
            cfg.input_path = args.input  # type: ignore[assignment]
            cfg.__post_init__()
        return cfg

    if not args.input:
        p.error("--input is required when --config is not given")

    return OCRConfig(
        input_path=args.input,
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
    cfg = _build_config(argv if argv is not None else sys.argv[1:])
    OCRPipeline(cfg).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
