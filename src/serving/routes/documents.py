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
from pathlib import Path

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
    try:
        markdown, source = ingest_file(upload_path, enable_ocr=settings.enable_api_ocr)
        files.save_processed(sid, doc_id, markdown)
        chunks = chunk_markdown(
            markdown,
            doc_id=doc_id,
            doc_name=filename,
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap,
        )

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
        n = vectors.add(sid, chunks, progress_cb=on_progress)
        db.update_document(doc_id, status="ready", chunk_count=n, progress=100)
        logger.info("Document %s indexed: %d chunks (%s)", doc_id, n, source)
    except Exception as exc:  # noqa: BLE001 - report failure to the UI, keep the file
        logger.warning("Document %s failed to index: %s", doc_id, exc)
        db.update_document(doc_id, status="failed", error=str(exc))


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
    if db.remove_document(sid, doc_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    vectors.delete_doc(sid, doc_id)
    files.delete_document_files(sid, doc_id)
