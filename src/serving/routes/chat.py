"""RAG chat endpoints: ask a grounded question, read conversation history."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from src.rag import RAGPipeline
from src.rag.llm import LLMError

from ..deps import get_pipeline, get_store
from ..schemas import ChatMessage, ChatRequest, ChatResponse, Citation
from ..storage import SessionStore

router = APIRouter(prefix="/api/sessions/{sid}/chat", tags=["chat"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@router.get("", response_model=list[ChatMessage])
def get_history(sid: str, store: SessionStore = Depends(get_store)):
    if not store.exists(sid):
        raise HTTPException(status_code=404, detail="Session not found")
    return [ChatMessage(**m) for m in store.list_chat(sid)]


@router.post("", response_model=ChatResponse)
def ask(
    sid: str,
    payload: ChatRequest,
    store: SessionStore = Depends(get_store),
    pipeline: RAGPipeline = Depends(get_pipeline),
):
    if not store.exists(sid):
        raise HTTPException(status_code=404, detail="Session not found")

    index = store.load_index(sid)
    history = store.list_chat(sid)

    try:
        result = pipeline.answer(index, payload.question, history=history)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    citations = [
        Citation(
            rank=s.rank,
            doc_id=s.doc_id,
            doc_name=s.doc_name,
            page=s.page,
            score=s.score,
            snippet=s.text[:400],
        )
        for s in result.sources
    ]

    # persist both turns so the conversation is durable memory
    store.append_chat(
        sid, {"role": "user", "content": payload.question, "created_at": _now(), "citations": []}
    )
    store.append_chat(
        sid,
        {
            "role": "assistant",
            "content": result.answer,
            "created_at": _now(),
            "citations": [c.model_dump() for c in citations],
        },
    )
    return ChatResponse(answer=result.answer, citations=citations)
