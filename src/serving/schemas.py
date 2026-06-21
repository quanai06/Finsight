"""Pydantic request/response models — the API contract shared with the frontend."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

DocStatus = Literal["processing", "ready", "failed"]


# ----------------------------------------------------------------- sessions
class SessionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field("", max_length=500)


class SessionSummary(BaseModel):
    id: str
    name: str
    description: str
    created_at: str
    document_count: int
    chunk_count: int


class SessionDetail(SessionSummary):
    documents: list["DocumentInfo"]


# ---------------------------------------------------------------- documents
class DocumentInfo(BaseModel):
    id: str
    filename: str
    kind: Literal["pdf", "md", "json"]
    status: DocStatus
    chunk_count: int
    chars: int
    uploaded_at: str
    source: str = ""          # how text was extracted: "markdown" | "json" | "ocr" | "pdf-text"
    error: str = ""


# -------------------------------------------------------------------- chat
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)


class Citation(BaseModel):
    rank: int
    doc_id: str
    doc_name: str
    page: Optional[int] = None
    score: float
    snippet: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: str
    citations: list[Citation] = []


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]


SessionDetail.model_rebuild()
