"""Configuration for the OCR pipeline.

A single immutable ``OCRConfig`` drives every component. It can be built from
code, from CLI arguments, or loaded from a YAML file under ``configs/``.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional


@dataclass(slots=True)
class OCRConfig:
    """All knobs for one OCR run."""

    # --- I/O ---
    input_path: Path                       # PDF to process
    output_dir: Path = Path("data/processed/ocr")
    work_dir: Path = Path("data/processed/ocr/_pages")  # rendered page images

    # --- rendering ---
    dpi: int = 200                         # raise to 300-400 for weak diacritics

    # --- engine ---
    engine: str = "paddleocr-vl"           # registry key (see engine.ENGINES)
    device: str = "cpu"                    # "cpu" or "gpu"

    # --- run control ---
    first_page: Optional[int] = None       # 1-based start page (inclusive)
    last_page: Optional[int] = None        # 1-based end page (inclusive)
    max_pages: Optional[int] = None        # cap pages (handy for CPU/testing)
    save_page_markdown: bool = True        # also write one .md per page
    page_separators: bool = True           # insert page markers in merged md

    def __post_init__(self) -> None:
        # accept str paths from CLI / YAML and normalise to Path
        self.input_path = Path(self.input_path)
        self.output_dir = Path(self.output_dir)
        self.work_dir = Path(self.work_dir)

    @property
    def doc_stem(self) -> str:
        return self.input_path.stem

    @property
    def markdown_path(self) -> Path:
        return self.output_dir / f"{self.doc_stem}.md"

    @property
    def report_path(self) -> Path:
        return self.output_dir / f"{self.doc_stem}_perf.csv"

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: (str(v) if isinstance(v, Path) else v) for k, v in d.items()}

    @classmethod
    def from_yaml(cls, path: str | Path) -> "OCRConfig":
        import yaml  # optional dependency, only needed for this path

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(**data)
