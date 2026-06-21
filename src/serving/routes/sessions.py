"""Session CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_store
from ..schemas import DocumentInfo, SessionCreate, SessionDetail, SessionSummary
from ..storage import SessionStore

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=SessionSummary, status_code=201)
def create_session(payload: SessionCreate, store: SessionStore = Depends(get_store)):
    meta = store.create_session(payload.name, payload.description)
    # summary() adds the derived document/chunk counts (0 for a new session)
    return store.summary(meta["id"])


@router.get("", response_model=list[SessionSummary])
def list_sessions(store: SessionStore = Depends(get_store)):
    return [store.summary(m["id"]) for m in store.list_sessions()]


@router.get("/{sid}", response_model=SessionDetail)
def get_session(sid: str, store: SessionStore = Depends(get_store)):
    summary = store.summary(sid)
    if summary is None:
        raise HTTPException(status_code=404, detail="Session not found")
    documents = [DocumentInfo(**d) for d in store.list_documents(sid)]
    return SessionDetail(**summary, documents=documents)


@router.delete("/{sid}", status_code=204)
def delete_session(sid: str, store: SessionStore = Depends(get_store)):
    if not store.delete_session(sid):
        raise HTTPException(status_code=404, detail="Session not found")
