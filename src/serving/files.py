"""On-disk storage for original uploads and normalized Markdown.

Binary uploads and extracted text don't belong in Postgres, so they live on the
filesystem under ``data/sessions/<id>/``. Everything else (metadata, chat, the
vector index) lives in Postgres / Qdrant / Redis.
"""

from __future__ import annotations

import shutil
from pathlib import Path


class FileStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def session_dir(self, sid: str) -> Path:
        return self.root / sid

    def uploads_dir(self, sid: str) -> Path:
        d = self.session_dir(sid) / "uploads"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def processed_dir(self, sid: str) -> Path:
        d = self.session_dir(sid) / "processed"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_upload(self, sid: str, doc_id: str, ext: str, data: bytes) -> Path:
        path = self.uploads_dir(sid) / f"{doc_id}{ext}"
        path.write_bytes(data)
        return path

    def find_upload(self, sid: str, doc_id: str) -> Path | None:
        matches = list(self.uploads_dir(sid).glob(f"{doc_id}.*"))
        return matches[0] if matches else None

    def save_processed(self, sid: str, doc_id: str, markdown: str) -> Path:
        path = self.processed_dir(sid) / f"{doc_id}.md"
        path.write_text(markdown, encoding="utf-8")
        return path

    def delete_document_files(self, sid: str, doc_id: str) -> None:
        for path in self.uploads_dir(sid).glob(f"{doc_id}.*"):
            path.unlink(missing_ok=True)
        (self.processed_dir(sid) / f"{doc_id}.md").unlink(missing_ok=True)

    def delete_session(self, sid: str) -> None:
        shutil.rmtree(self.session_dir(sid), ignore_errors=True)
