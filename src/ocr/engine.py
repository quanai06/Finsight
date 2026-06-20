"""OCR engine abstraction.

``OCREngine`` is the interface every backend implements, so the pipeline is
decoupled from any specific model. ``PaddleOCRVLEngine`` wraps PaddleOCR-VL;
new engines (VietOCR, PP-StructureV3, a cloud VLM, ...) can be added by
subclassing and registering in ``ENGINES``.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable

from .models import PageResult

logger = logging.getLogger(__name__)


def resolve_device(device: str = "auto") -> str:
    """Map ``"auto"`` to ``"gpu"`` when a CUDA device is present, else ``"cpu"``.

    ``"cpu"`` / ``"gpu"`` are returned unchanged so the user can always force one.
    """
    if device != "auto":
        return device
    try:
        import paddle

        if paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0:
            return "gpu"
    except Exception:  # noqa: BLE001 — any failure -> safe CPU fallback
        pass
    return "cpu"


def _markdown_to_text(md: Any) -> str:
    """Extract the Markdown string from PaddleOCR's result object across versions."""
    if isinstance(md, str):
        return md
    for attr in ("markdown_texts", "markdown", "text"):
        v = getattr(md, attr, None)
        if isinstance(v, str):
            return v
    if isinstance(md, dict):
        for key in ("markdown", "markdown_texts", "text"):
            if isinstance(md.get(key), str):
                return md[key]
    return str(md)


class OCREngine(ABC):
    """Interface for a single-page OCR backend."""

    name: str = "base"

    @abstractmethod
    def warm_up(self) -> None:
        """Load models / weights. Called once before the first page."""

    @abstractmethod
    def recognize(self, image_path: Path, index: int) -> PageResult:
        """Run OCR on one page image and return its result."""


class PaddleOCRVLEngine(OCREngine):
    """PaddleOCR-VL backend: layout + table + multilingual text -> Markdown."""

    name = "paddleocr-vl"

    def __init__(self, device: str = "auto", **pipeline_kwargs: Any) -> None:
        self.device = device                 # as requested ("auto"/"cpu"/"gpu")
        self.resolved_device: str | None = None  # actual device after detection
        self._pipeline_kwargs = pipeline_kwargs
        self._pipeline = None  # lazy

    def warm_up(self) -> None:
        if self._pipeline is not None:
            return
        from paddleocr import PaddleOCRVL  # lazy heavy import

        self.resolved_device = resolve_device(self.device)
        if self.device == "auto":
            logger.info("Device auto-detect -> %s", self.resolved_device)
        t0 = time.perf_counter()
        self._pipeline = PaddleOCRVL(device=self.resolved_device,
                                     **self._pipeline_kwargs)
        logger.info("PaddleOCR-VL loaded on %s in %.1fs",
                    self.resolved_device, time.perf_counter() - t0)

    def recognize(self, image_path: Path, index: int) -> PageResult:
        if self._pipeline is None:
            self.warm_up()

        t0 = time.perf_counter()
        outputs = list(self._pipeline.predict(str(image_path)))
        elapsed = time.perf_counter() - t0
        if not outputs:
            logger.warning("No OCR output for page %d (%s)", index + 1, image_path)
            return PageResult(index=index, markdown="", elapsed_s=elapsed)

        res = outputs[0]
        markdown = _markdown_to_text(getattr(res, "markdown", res))
        raw = res.json if hasattr(res, "json") else {}
        return PageResult(index=index, markdown=markdown,
                          elapsed_s=elapsed, raw=raw)


# --- registry: maps a config key -> factory(device, **kwargs) -> OCREngine ---
ENGINES: dict[str, Callable[..., OCREngine]] = {
    "paddleocr-vl": PaddleOCRVLEngine,
}


def build_engine(name: str, device: str = "auto", **kwargs: Any) -> OCREngine:
    try:
        factory = ENGINES[name]
    except KeyError:
        raise ValueError(
            f"Unknown engine '{name}'. Available: {sorted(ENGINES)}"
        ) from None
    return factory(device=device, **kwargs)
