"""One-off migration: file-based sessions  ->  Postgres + Qdrant.

The earlier prototype stored session metadata/documents/chat as JSON files and
the index as a TF-IDF pickle. This re-creates those sessions in Postgres and
re-embeds their uploaded files into Qdrant with the new bge-class model. The
original uploads under ``uploads/`` are the source of truth and are untouched.

Idempotent: a session/document already present in Postgres is skipped.

    python scripts/migrate_to_postgres.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root on sys.path

from src.rag import chunk_markdown
from src.serving.config import get_settings
from src.serving.db import Database, DocumentRow, SessionRow
from src.serving.deps import get_vectorstore
from src.serving.files import FileStore
from src.serving.ingest import ingest_file


def main() -> None:
    settings = get_settings()
    db = Database(settings.database_url)
    db.create_all()
    vs = get_vectorstore()
    files = FileStore(settings.sessions_dir)
    root = settings.sessions_dir

    if not root.exists():
        print("no sessions dir; nothing to migrate")
        return

    for sdir in sorted(p for p in root.iterdir() if p.is_dir()):
        meta_p = sdir / "meta.json"
        if not meta_p.exists():
            continue
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        sid = meta["id"]

        with db._Session.begin() as s:  # noqa: SLF001 - migration touches internals
            if s.get(SessionRow, sid) is not None:
                print(f"skip (exists): {sid} {meta['name']}")
                continue
            s.add(
                SessionRow(
                    id=sid,
                    name=meta["name"],
                    description=meta.get("description", ""),
                    created_at=datetime.fromisoformat(meta["created_at"]),
                )
            )
        print(f"session: {sid} {meta['name']}")

        docs_p = sdir / "documents.json"
        docs = json.loads(docs_p.read_text(encoding="utf-8")) if docs_p.exists() else []
        for d in docs:
            did = d["id"]
            with db._Session.begin() as s:  # noqa: SLF001
                if s.get(DocumentRow, did) is not None:
                    continue
                s.add(
                    DocumentRow(
                        id=did,
                        session_id=sid,
                        filename=d["filename"],
                        kind=d["kind"],
                        status="processing",
                        uploaded_at=datetime.fromisoformat(d["uploaded_at"]),
                    )
                )
            upload = files.find_upload(sid, did)
            if upload is None:
                db.update_document(did, status="failed", error="upload missing")
                print(f"  ! missing upload for {d['filename']}")
                continue
            try:
                markdown, source = ingest_file(upload)
                files.save_processed(sid, did, markdown)
                chunks = chunk_markdown(
                    markdown,
                    doc_id=did,
                    doc_name=d["filename"],
                    chunk_size=settings.chunk_size,
                    overlap=settings.chunk_overlap,
                )
                n = vs.add(sid, chunks)
                db.update_document(
                    did, status="ready", chunk_count=n, chars=len(markdown), source=source
                )
                print(f"  {d['filename'][:46]:46} -> {n} chunks ({source})")
            except Exception as exc:  # noqa: BLE001
                db.update_document(did, status="failed", error=str(exc))
                print(f"  ! failed {d['filename']}: {exc}")

        chat_p = sdir / "chat.json"
        chat = json.loads(chat_p.read_text(encoding="utf-8")) if chat_p.exists() else []
        for m in chat:
            db.append_message(sid, m["role"], m["content"], m.get("citations", []))
        if chat:
            print(f"  chat: {len(chat)} messages")

    print("migration done")


if __name__ == "__main__":
    main()
