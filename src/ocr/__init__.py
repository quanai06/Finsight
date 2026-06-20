"""OCR pipeline for Finsight.

Turns scanned-image Vietnamese financial PDFs (BCTC) into structured Markdown
(text + tables) using a swappable OCR engine (default: PaddleOCR-VL).

Quick start:
    from src.ocr import OCRConfig, OCRPipeline
    doc = OCRPipeline(OCRConfig(input_path="data/raw/2021_bctc_hop_nhat.pdf",
                               max_pages=3)).run()
    print(doc.to_markdown())
"""

from .batch import BatchProcessor, FileOutcome
from .config import OCRConfig
from .engine import ENGINES, OCREngine, PaddleOCRVLEngine, build_engine
from .models import DocumentResult, PageImage, PageResult
from .pipeline import OCRPipeline
from .postprocess import PostProcessor, PostResult, TableRecord

__all__ = [
    "OCRConfig",
    "OCRPipeline",
    "BatchProcessor",
    "FileOutcome",
    "PostProcessor",
    "PostResult",
    "TableRecord",
    "OCREngine",
    "PaddleOCRVLEngine",
    "build_engine",
    "ENGINES",
    "DocumentResult",
    "PageResult",
    "PageImage",
]
