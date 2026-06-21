"""PostgreSQL persistence (SQLAlchemy 2.0).

Holds the durable, queryable state: sessions, documents, and the full chat
history. Vector data lives in Qdrant; the original uploads + normalized Markdown
live on disk (see ``files.py``). Short-term conversational memory lives in Redis.

The ``Database`` class exposes small task-oriented methods (mirroring the shape
of the routes) so endpoints stay thin and never touch the ORM session directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    delete,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class Base(DeclarativeBase):
    pass


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    documents: Mapped[list["DocumentRow"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    messages: Mapped[list["MessageRow"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class DocumentRow(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_new_id)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(512))
    kind: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(12), default="processing")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    chars: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(16), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    session: Mapped[SessionRow] = relationship(back_populates="documents")


class MessageRow(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(12))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    session: Mapped[SessionRow] = relationship(back_populates="messages")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


class Database:
    """Thin repository over a SQLAlchemy engine."""

    def __init__(self, url: str) -> None:
        self.engine = create_engine(url, pool_pre_ping=True, future=True)
        self._Session = sessionmaker(self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    # ------------------------------------------------------------- sessions
    def create_session(self, name: str, description: str = "") -> dict:
        with self._Session.begin() as s:
            row = SessionRow(name=name.strip(), description=description.strip())
            s.add(row)
            s.flush()
            return {"id": row.id}

    def session_exists(self, sid: str) -> bool:
        with self._Session() as s:
            return s.get(SessionRow, sid) is not None

    def get_summary(self, sid: str) -> dict | None:
        with self._Session() as s:
            row = s.get(SessionRow, sid)
            if row is None:
                return None
            return self._summary(s, row)

    def list_summaries(self) -> list[dict]:
        with self._Session() as s:
            rows = s.scalars(select(SessionRow).order_by(SessionRow.created_at.desc()))
            return [self._summary(s, r) for r in rows]

    def _summary(self, s: Session, row: SessionRow) -> dict:
        doc_count = s.scalar(
            select(func.count())
            .select_from(DocumentRow)
            .where(DocumentRow.session_id == row.id)
        )
        chunk_sum = s.scalar(
            select(func.coalesce(func.sum(DocumentRow.chunk_count), 0)).where(
                DocumentRow.session_id == row.id
            )
        )
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "created_at": _iso(row.created_at),
            "document_count": int(doc_count or 0),
            "chunk_count": int(chunk_sum or 0),
        }

    def delete_session(self, sid: str) -> bool:
        with self._Session.begin() as s:
            row = s.get(SessionRow, sid)
            if row is None:
                return False
            s.delete(row)
            return True

    # --------------------------------------------------------- documents
    def list_documents(self, sid: str) -> list[dict]:
        with self._Session() as s:
            rows = s.scalars(
                select(DocumentRow)
                .where(DocumentRow.session_id == sid)
                .order_by(DocumentRow.uploaded_at.asc())
            )
            return [self._doc_dict(r) for r in rows]

    def get_document(self, sid: str, doc_id: str) -> dict | None:
        with self._Session() as s:
            row = s.get(DocumentRow, doc_id)
            if row is None or row.session_id != sid:
                return None
            return self._doc_dict(row)

    def create_document(self, sid: str, filename: str, kind: str) -> dict:
        with self._Session.begin() as s:
            row = DocumentRow(
                session_id=sid, filename=filename, kind=kind, status="processing"
            )
            s.add(row)
            s.flush()
            return self._doc_dict(row)

    def update_document(self, doc_id: str, **fields: Any) -> dict | None:
        with self._Session.begin() as s:
            row = s.get(DocumentRow, doc_id)
            if row is None:
                return None
            for key, value in fields.items():
                setattr(row, key, value)
            s.flush()
            return self._doc_dict(row)

    def remove_document(self, sid: str, doc_id: str) -> dict | None:
        with self._Session.begin() as s:
            row = s.get(DocumentRow, doc_id)
            if row is None or row.session_id != sid:
                return None
            data = self._doc_dict(row)
            s.delete(row)
            return data

    @staticmethod
    def _doc_dict(row: DocumentRow) -> dict:
        return {
            "id": row.id,
            "filename": row.filename,
            "kind": row.kind,
            "status": row.status,
            "chunk_count": row.chunk_count,
            "chars": row.chars,
            "source": row.source,
            "error": row.error,
            "uploaded_at": _iso(row.uploaded_at),
        }

    # -------------------------------------------------------------- chat
    def list_chat(self, sid: str) -> list[dict]:
        with self._Session() as s:
            rows = s.scalars(
                select(MessageRow)
                .where(MessageRow.session_id == sid)
                .order_by(MessageRow.id.asc())
            )
            return [self._msg_dict(r) for r in rows]

    def append_message(
        self, sid: str, role: str, content: str, citations: list | None = None
    ) -> dict:
        with self._Session.begin() as s:
            row = MessageRow(
                session_id=sid, role=role, content=content, citations=citations or []
            )
            s.add(row)
            s.flush()
            return self._msg_dict(row)

    @staticmethod
    def _msg_dict(row: MessageRow) -> dict:
        return {
            "role": row.role,
            "content": row.content,
            "citations": row.citations or [],
            "created_at": _iso(row.created_at),
        }
