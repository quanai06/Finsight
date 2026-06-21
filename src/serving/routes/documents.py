"""Document upload / list / delete endpoints.

Upload flow (runs in FastAPI's threadpool because the route is ``def``):
    save original -> ingest to Markdown -> chunk -> add to TF-IDF index -> persist
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from src.rag import chunk_markdown

from ..config import get_settings
from ..deps import get_store
from ..ingest import SUPPORTED_EXTENSIONS, detect_kind, ingest_file
from ..schemas import DocumentInfo
from ..storage import SessionStore

router = APIRouter(prefix="/api/sessions/{sid}/documents", tags=["documents"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@router.get("", response_model=list[DocumentInfo])
def list_documents(sid: str, store: SessionStore = Depends(get_store)):
    if not store.exists(sid):
        raise HTTPException(status_code=404, detail="Session not found")
    return [DocumentInfo(**d) for d in store.list_documents(sid)]


@router.post("", response_model=DocumentInfo, status_code=201)
def upload_document(
    sid: str, file: UploadFile, store: SessionStore = Depends(get_store)
):
    if not store.exists(sid):
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
            status_code=413,
            detail=f"File exceeds the {settings.max_upload_mb} MB limit.",
        )

    doc_id = uuid.uuid4().hex[:12]
    stored_name = f"{doc_id}{ext}"
    upload_path = store.uploads_dir(sid) / stored_name
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_bytes(raw)

    doc: dict = {
        "id": doc_id,
        "filename": filename,
        "kind": detect_kind(filename),
        "status": "processing",
        "chunk_count": 0,
        "chars": 0,
        "uploaded_at": _now(),
        "source": "",
        "error": "",
    }
    store.upsert_document(sid, doc)

    try:
        markdown, source = ingest_file(upload_path)
        processed_path = store.processed_dir(sid) / f"{doc_id}.md"
        processed_path.parent.mkdir(parents=True, exist_ok=True)
        processed_path.write_text(markdown, encoding="utf-8")

        chunks = chunk_markdown(markdown, doc_id=doc_id, doc_name=filename)
        index = store.load_index(sid)
        index.add(chunks)
        store.save_index(sid, index)

        doc.update(
            status="ready",
            chunk_count=len(chunks),
            chars=len(markdown),
            source=source,
        )
    except Exception as exc:  # noqa: BLE001 - report failure to the UI, keep file
        doc.update(status="failed", error=str(exc))

    store.upsert_document(sid, doc)
    return DocumentInfo(**doc)


@router.delete("/{doc_id}", status_code=204)
def delete_document(
    sid: str, doc_id: str, store: SessionStore = Depends(get_store)
):
    if not store.exists(sid):
        raise HTTPException(status_code=404, detail="Session not found")
    removed = store.remove_document(sid, doc_id)
    if removed is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # drop its chunks from the index and clean up files
    index = store.load_index(sid)
    index.remove_doc(doc_id)
    store.save_index(sid, index)
    for path in (
        store.processed_dir(sid) / f"{doc_id}.md",
        store.uploads_dir(sid) / f"{doc_id}{Path(removed['filename']).suffix.lower()}",
    ):
        path.unlink(missing_ok=True)
