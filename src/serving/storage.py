"""Disk-backed persistence for sessions, documents, and chat history.

"Proper memory": everything a session knows survives a server restart. Each
session is a self-contained folder so a session can be inspected, backed up, or
deleted as a unit:

    data/sessions/<id>/
        meta.json          session name/description/created_at
        documents.json      list of uploaded documents + their status
        chat.json           full conversation history (with citations)
        uploads/            the original uploaded files, untouched
        processed/<doc>.md  normalized Markdown extracted from each upload
        index/index.pkl     the TF-IDF retrieval index

A single in-process lock serialises writes — fine for the single-worker dev
server this ships with.
"""

from __future__ import annotations

import json
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.rag import SessionIndex


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)  # atomic on POSIX


class SessionStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # ------------------------------------------------------------- paths
    def dir(self, sid: str) -> Path:
        return self.root / sid

    def _meta_path(self, sid: str) -> Path:
        return self.dir(sid) / "meta.json"

    def _docs_path(self, sid: str) -> Path:
        return self.dir(sid) / "documents.json"

    def _chat_path(self, sid: str) -> Path:
        return self.dir(sid) / "chat.json"

    def uploads_dir(self, sid: str) -> Path:
        return self.dir(sid) / "uploads"

    def processed_dir(self, sid: str) -> Path:
        return self.dir(sid) / "processed"

    def index_dir(self, sid: str) -> Path:
        return self.dir(sid) / "index"

    def exists(self, sid: str) -> bool:
        return self._meta_path(sid).exists()

    # ---------------------------------------------------------- sessions
    def create_session(self, name: str, description: str = "") -> dict:
        sid = uuid.uuid4().hex[:12]
        with self._lock:
            meta = {
                "id": sid,
                "name": name.strip(),
                "description": description.strip(),
                "created_at": _now(),
            }
            _write_json(self._meta_path(sid), meta)
            _write_json(self._docs_path(sid), [])
            _write_json(self._chat_path(sid), [])
            self.uploads_dir(sid).mkdir(parents=True, exist_ok=True)
            self.processed_dir(sid).mkdir(parents=True, exist_ok=True)
        return meta

    def get_meta(self, sid: str) -> dict | None:
        return _read_json(self._meta_path(sid), None)

    def list_sessions(self) -> list[dict]:
        sessions = []
        for child in self.root.iterdir():
            if not child.is_dir():
                continue
            meta = _read_json(child / "meta.json", None)
            if meta:
                sessions.append(meta)
        sessions.sort(key=lambda m: m.get("created_at", ""), reverse=True)
        return sessions

    def delete_session(self, sid: str) -> bool:
        with self._lock:
            if not self.exists(sid):
                return False
            shutil.rmtree(self.dir(sid), ignore_errors=True)
            return True

    # --------------------------------------------------------- documents
    def list_documents(self, sid: str) -> list[dict]:
        return _read_json(self._docs_path(sid), [])

    def get_document(self, sid: str, doc_id: str) -> dict | None:
        for d in self.list_documents(sid):
            if d["id"] == doc_id:
                return d
        return None

    def upsert_document(self, sid: str, doc: dict) -> None:
        with self._lock:
            docs = self.list_documents(sid)
            for i, d in enumerate(docs):
                if d["id"] == doc["id"]:
                    docs[i] = doc
                    break
            else:
                docs.append(doc)
            _write_json(self._docs_path(sid), docs)

    def remove_document(self, sid: str, doc_id: str) -> dict | None:
        with self._lock:
            docs = self.list_documents(sid)
            removed = next((d for d in docs if d["id"] == doc_id), None)
            if removed is None:
                return None
            docs = [d for d in docs if d["id"] != doc_id]
            _write_json(self._docs_path(sid), docs)
        return removed

    # ------------------------------------------------------------- index
    def load_index(self, sid: str) -> SessionIndex:
        with self._lock:
            return SessionIndex.load(self.index_dir(sid))

    def save_index(self, sid: str, index: SessionIndex) -> None:
        with self._lock:
            index.save(self.index_dir(sid))

    # -------------------------------------------------------------- chat
    def list_chat(self, sid: str) -> list[dict]:
        return _read_json(self._chat_path(sid), [])

    def append_chat(self, sid: str, message: dict) -> None:
        with self._lock:
            history = self.list_chat(sid)
            history.append(message)
            _write_json(self._chat_path(sid), history)

    # ------------------------------------------------------------ summary
    def summary(self, sid: str) -> dict | None:
        meta = self.get_meta(sid)
        if meta is None:
            return None
        docs = self.list_documents(sid)
        return {
            **meta,
            "document_count": len(docs),
            "chunk_count": sum(d.get("chunk_count", 0) for d in docs),
        }
