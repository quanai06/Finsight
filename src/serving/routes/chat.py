"""RAG chat endpoints: ask a grounded question, read conversation history.

Memory model:
  * Postgres  — durable, complete chat history (this is the source of truth).
  * Redis     — fast short-term window fed back into the LLM prompt. Primed from
                Postgres on a cache miss so coherence survives restarts.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.rag import RAGPipeline
from src.rag.llm import LLMError

from ..db import Database
from ..deps import get_db, get_memory, get_pipeline
from ..memory import ShortTermMemory
from ..schemas import ChatMessage, ChatRequest, ChatResponse, Citation

router = APIRouter(prefix="/api/sessions/{sid}/chat", tags=["chat"])


@router.get("", response_model=list[ChatMessage])
def get_history(sid: str, db: Database = Depends(get_db)):
    if not db.session_exists(sid):
        raise HTTPException(status_code=404, detail="Session not found")
    return [ChatMessage(**m) for m in db.list_chat(sid)]


@router.post("", response_model=ChatResponse)
def ask(
    sid: str,
    payload: ChatRequest,
    db: Database = Depends(get_db),
    pipeline: RAGPipeline = Depends(get_pipeline),
    memory: ShortTermMemory = Depends(get_memory),
):
    if not db.session_exists(sid):
        raise HTTPException(status_code=404, detail="Session not found")

    # recent turns from the cache; if empty, prime it from durable history
    history = memory.recent(sid)
    if not history:
        durable = db.list_chat(sid)
        if durable:
            memory.prime(sid, durable)
            history = memory.recent(sid)

    try:
        result = pipeline.answer(sid, payload.question, history=history)
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

    # durable history (Postgres) + short-term window (Redis)
    db.append_message(sid, "user", payload.question)
    db.append_message(
        sid, "assistant", result.answer, [c.model_dump() for c in citations]
    )
    memory.add_turn(sid, "user", payload.question)
    memory.add_turn(sid, "assistant", result.answer)

    return ChatResponse(answer=result.answer, citations=citations)
