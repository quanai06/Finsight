"""Document upload / list / delete endpoints.

Upload flow (runs in FastAPI's threadpool because the route is ``def``):
    save original → ingest to Markdown → chunk → embed+store in Qdrant → mark ready
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from src.rag import VectorStore, chunk_markdown

from ..config import get_settings
from ..db import Database
from ..deps import get_db, get_files, get_vectorstore
from ..files import FileStore
from ..ingest import SUPPORTED_EXTENSIONS, detect_kind, ingest_file
from ..schemas import DocumentInfo

router = APIRouter(prefix="/api/sessions/{sid}/documents", tags=["documents"])


@router.get("", response_model=list[DocumentInfo])
def list_documents(sid: str, db: Database = Depends(get_db)):
    if not db.session_exists(sid):
        raise HTTPException(status_code=404, detail="Session not found")
    return [DocumentInfo(**d) for d in db.list_documents(sid)]


@router.post("", response_model=DocumentInfo, status_code=201)
def upload_document(
    sid: str,
    file: UploadFile,
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

    doc = db.create_document(sid, filename, detect_kind(filename))
    doc_id = doc["id"]
    upload_path = files.save_upload(sid, doc_id, ext, raw)

    try:
        markdown, source = ingest_file(upload_path)
        files.save_processed(sid, doc_id, markdown)
        chunks = chunk_markdown(
            markdown,
            doc_id=doc_id,
            doc_name=filename,
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap,
        )
        n = vectors.add(sid, chunks)
        return DocumentInfo(
            **db.update_document(
                doc_id, status="ready", chunk_count=n, chars=len(markdown), source=source
            )
        )
    except Exception as exc:  # noqa: BLE001 - report failure to the UI, keep the file
        return DocumentInfo(**db.update_document(doc_id, status="failed", error=str(exc)))


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
