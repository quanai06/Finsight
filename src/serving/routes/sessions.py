"""Session CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.rag import VectorStore

from ..db import Database
from ..deps import get_db, get_files, get_memory, get_vectorstore
from ..files import FileStore
from ..memory import ShortTermMemory
from ..schemas import DocumentInfo, SessionCreate, SessionDetail, SessionSummary

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=SessionSummary, status_code=201)
def create_session(payload: SessionCreate, db: Database = Depends(get_db)):
    created = db.create_session(payload.name, payload.description)
    return db.get_summary(created["id"])


@router.get("", response_model=list[SessionSummary])
def list_sessions(db: Database = Depends(get_db)):
    return db.list_summaries()


@router.get("/{sid}", response_model=SessionDetail)
def get_session(sid: str, db: Database = Depends(get_db)):
    summary = db.get_summary(sid)
    if summary is None:
        raise HTTPException(status_code=404, detail="Session not found")
    documents = [DocumentInfo(**d) for d in db.list_documents(sid)]
    return SessionDetail(**summary, documents=documents)


@router.delete("/{sid}", status_code=204)
def delete_session(
    sid: str,
    db: Database = Depends(get_db),
    vectors: VectorStore = Depends(get_vectorstore),
    files: FileStore = Depends(get_files),
    memory: ShortTermMemory = Depends(get_memory),
):
    if not db.delete_session(sid):
        raise HTTPException(status_code=404, detail="Session not found")
    # tear down the session's data in the other stores too
    vectors.delete_session(sid)
    files.delete_session(sid)
    memory.clear(sid)
