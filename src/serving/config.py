"""Runtime settings for the backend.

Reads configuration from environment variables, with a tiny ``.env`` loader so
local development just works without exporting anything by hand. Secrets (the
Groq API key) must never be hard-coded — keep them in ``.env`` (git-ignored).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Populate os.environ from a .env file (only keys not already set)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(_REPO_ROOT / ".env")


class Settings:
    """Process-wide configuration, resolved once at import time."""

    def __init__(self) -> None:
        self.repo_root = _REPO_ROOT
        self.sessions_dir = Path(
            os.environ.get("FINSIGHT_SESSIONS_DIR", _REPO_ROOT / "data" / "sessions")
        )
        self.groq_api_key = os.environ.get("GROQ_API_KEY", "")
        self.groq_model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.top_k = int(os.environ.get("FINSIGHT_TOP_K", "5"))
        # comma-separated list of allowed CORS origins for the React dev server
        self.cors_origins = [
            o.strip()
            for o in os.environ.get(
                "FINSIGHT_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            ).split(",")
            if o.strip()
        ]
        self.max_upload_mb = int(os.environ.get("FINSIGHT_MAX_UPLOAD_MB", "50"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
