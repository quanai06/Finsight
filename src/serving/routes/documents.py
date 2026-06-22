"""Document upload / list / status / delete endpoints.

Upload is split in two so the request never blocks on the heavy work:
    POST   → validate, save original, create row (status=processing), return now
    (bg)   → ingest to Markdown → chunk → embed+store in Qdrant → mark ready/failed
    GET id → poll the document's current status until it is ready/failed

The embed step (CPU-heavy ONNX inference) runs in a FastAPI background task, so
the client gets an immediate 201 and the API stays responsive while indexing.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


class _IndexJobs:
    """Tracks in-flight document indexing so a cancelled upload actually stops.

    Single-process (matches the dev single-worker setup). ``DELETE`` flags a job;
    the background embedding loop polls ``is_cancelled`` and bails out instead of
    grinding through every chunk on the CPU.
    """

    def __init__(self) -> None:
        self._active: set[str] = set()
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()

    def start(self, doc_id: str) -> None:
        with self._lock:
            self._cancelled.discard(doc_id)
            self._active.add(doc_id)

    def finish(self, doc_id: str) -> None:
        with self._lock:
            self._active.discard(doc_id)
            self._cancelled.discard(doc_id)

    def cancel(self, doc_id: str) -> bool:
        """Flag a running job for cancellation; True if it was actually running."""
        with self._lock:
            if doc_id in self._active:
                self._cancelled.add(doc_id)
                return True
            return False

    def is_cancelled(self, doc_id: str) -> bool:
        with self._lock:
            return doc_id in self._cancelled


_jobs = _IndexJobs()


class _Cancelled(Exception):
    """Raised inside the indexing task when the document was cancelled."""


def _doc_year(filename: str, markdown: str) -> int | None:
    m = _YEAR_RE.search(filename) or _YEAR_RE.search(markdown[:2000])
    return int(m.group(0)) if m else None


def _doc_context(filename: str, year: int | None) -> str:
    """A short descriptor prepended to every chunk so retrieval can tell apart
    otherwise-identical lines across reports/years (e.g. revenue in 2022 vs 2023).
    """
    ctx = f"Tài liệu: {filename}"
    if year is not None:
        ctx += f" · Năm: {year}"
    return ctx

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile

from src.rag import VectorStore, chunk_markdown

from ..config import Settings, get_settings
from ..db import Database
from ..deps import get_db, get_files, get_vectorstore
from ..files import FileStore
from ..ingest import SUPPORTED_EXTENSIONS, detect_kind, ingest_file
from ..schemas import DocumentInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions/{sid}/documents", tags=["documents"])


@router.get("", response_model=list[DocumentInfo])
def list_documents(sid: str, db: Database = Depends(get_db)):
    if not db.session_exists(sid):
        raise HTTPException(status_code=404, detail="Session not found")
    return [DocumentInfo(**d) for d in db.list_documents(sid)]


@router.get("/{doc_id}", response_model=DocumentInfo)
def get_document(sid: str, doc_id: str, db: Database = Depends(get_db)):
    """Poll a single document's current status (processing → ready/failed)."""
    if not db.session_exists(sid):
        raise HTTPException(status_code=404, detail="Session not found")
    doc = db.get_document(sid, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentInfo(**doc)


@router.post("", response_model=DocumentInfo, status_code=201)
def upload_document(
    sid: str,
    file: UploadFile,
    background: BackgroundTasks,
    db: Database = Depends(get_db),
    files: FileStore = Depends(get_files),
    vectors: VectorStore = Depends(get_vectorstore),
):
    if not db.session_exists(sid):
        raise HTTPException(status_code=404, detail="Session not found")

    filename = Path(file.filename or "upload").name
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: PDF, Markdown, JSON.",
        )

    settings = get_settings()
    raw = file.file.read()
    if len(raw) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413, detail=f"File exceeds the {settings.max_upload_mb} MB limit."
        )

    # Persist the upload and record it as "processing", then hand the heavy
    # ingest+embed work to a background task and return immediately. The client
    # polls GET /{doc_id} to learn when it becomes "ready" or "failed".
    doc = db.create_document(sid, filename, detect_kind(filename))
    doc_id = doc["id"]
    upload_path = files.save_upload(sid, doc_id, ext, raw)
    background.add_task(
        _process_document,
        db=db,
        files=files,
        vectors=vectors,
        settings=settings,
        sid=sid,
        doc_id=doc_id,
        upload_path=upload_path,
        filename=filename,
    )
    return DocumentInfo(**doc)


def _process_document(
    *,
    db: Database,
    files: FileStore,
    vectors: VectorStore,
    settings: Settings,
    sid: str,
    doc_id: str,
    upload_path: Path,
    filename: str,
) -> None:
    """Heavy indexing pipeline, run off the request thread (FastAPI threadpool).

    ingest → chunk → embed+store. Embedding is the CPU/RAM-intensive step; doing
    it here keeps the upload response instant and the API responsive. The result
    is written back to the document row as ``ready`` (with counts) or ``failed``.
    """
    _jobs.start(doc_id)
    t0 = time.perf_counter()
    try:
        markdown, source = ingest_file(upload_path, enable_ocr=settings.enable_api_ocr)
        files.save_processed(sid, doc_id, markdown)
        t_ingest = time.perf_counter()

        year = _doc_year(filename, markdown)
        chunks = chunk_markdown(
            markdown,
            doc_id=doc_id,
            doc_name=filename,
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap,
            doc_context=_doc_context(filename, year),
            year=year,
        )
        t_chunk = time.perf_counter()
        if _jobs.is_cancelled(doc_id):
            raise _Cancelled

        # Map embedding progress onto 5..95% (parse/chunk = first 5%, the final
        # write-back to "ready" is 100%). Throttle DB writes to every +5% so a
        # doc with thousands of chunks doesn't hammer Postgres.
        last_pct = 0

        def on_progress(done: int, total: int) -> None:
            nonlocal last_pct
            pct = 5 + int(done / total * 90)
            if pct - last_pct >= 5 or done == total:
                last_pct = pct
                db.update_document(doc_id, progress=min(pct, 99))

        db.update_document(doc_id, chars=len(markdown), source=source, progress=5)
        n = vectors.add(
            sid,
            chunks,
            progress_cb=on_progress,
            should_cancel=lambda: _jobs.is_cancelled(doc_id),
        )
        if _jobs.is_cancelled(doc_id):
            raise _Cancelled
        t_embed = time.perf_counter()

        db.update_document(doc_id, status="ready", chunk_count=n, progress=100)
        logger.info(
            "Document %s indexed: %d chunks (%s) | timing: ingest=%.1fs chunk=%.2fs "
            "embed=%.1fs total=%.1fs",
            doc_id, n, source,
            t_ingest - t0, t_chunk - t_ingest, t_embed - t_chunk, t_embed - t0,
        )
    except _Cancelled:
        # Upload was cancelled mid-flight: stop and remove any partial vectors.
        logger.info("Document %s cancelled during indexing; cleaning up", doc_id)
        try:
            vectors.delete_doc(sid, doc_id)
        except Exception:  # noqa: BLE001 - row/vectors may already be gone
            pass
    except Exception as exc:  # noqa: BLE001 - report failure to the UI, keep the file
        logger.warning("Document %s failed to index: %s", doc_id, exc)
        db.update_document(doc_id, status="failed", error=str(exc))
    finally:
        _jobs.finish(doc_id)


@router.delete("/{doc_id}", status_code=204)
def delete_document(
    sid: str,
    doc_id: str,
    db: Database = Depends(get_db),
    files: FileStore = Depends(get_files),
    vectors: VectorStore = Depends(get_vectorstore),
):
    if not db.session_exists(sid):
        raise HTTPException(status_code=404, detail="Session not found")
    # Signal any in-flight indexing to stop *before* removing the row, so the
    # background task quits early and self-cleans instead of running to the end.
    _jobs.cancel(doc_id)
    if db.remove_document(sid, doc_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    vectors.delete_doc(sid, doc_id)
    files.delete_document_files(sid, doc_id)
