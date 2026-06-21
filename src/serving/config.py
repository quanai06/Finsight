"""Runtime settings for the backend.

Reads configuration from environment variables, with a tiny ``.env`` loader so
local development just works without exporting anything by hand. Secrets (the
Groq API key) must never be hard-coded — keep them in ``.env`` (git-ignored).
"""

from __future__ import annotations

import os
import re
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
        value = value.strip()
        if value[:1] in ("'", '"'):  # quoted value — strip the quotes, keep contents
            quote = value[0]
            end = value.find(quote, 1)
            value = value[1:end] if end != -1 else value[1:]
        else:  # unquoted — drop any inline "# comment"
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        os.environ.setdefault(key.strip(), value)


_load_dotenv(_REPO_ROOT / ".env")


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


class Settings:
    """Process-wide configuration, resolved once at import time."""

    def __init__(self) -> None:
        self.repo_root = _REPO_ROOT
        # File storage for original uploads + normalized Markdown (metadata lives in Postgres)
        self.sessions_dir = Path(
            _env("FINSIGHT_SESSIONS_DIR", str(_REPO_ROOT / "data" / "sessions"))
        )

        # --- LLM (Groq) ---
        self.groq_api_key = _env("GROQ_API_KEY", "")
        self.groq_model = _env("GROQ_MODEL", "llama-3.3-70b-versatile")

        # --- Infrastructure ---
        self.database_url = _env(
            "DATABASE_URL",
            "postgresql+psycopg://finsight:finsight@localhost:5432/finsight",
        )
        self.qdrant_url = _env("QDRANT_URL", "http://localhost:6333")
        self.qdrant_collection = _env("QDRANT_COLLECTION", "finsight_chunks")
        self.redis_url = _env("REDIS_URL", "redis://localhost:6379/0")

        # --- Embedding / rerank (FastEmbed, ONNX CPU) ---
        self.embed_model = _env("FINSIGHT_EMBED_MODEL", "intfloat/multilingual-e5-large")
        self.embed_dim = int(_env("FINSIGHT_EMBED_DIM", "1024"))
        self.rerank_model = _env(
            "FINSIGHT_RERANK_MODEL", "jinaai/jina-reranker-v2-base-multilingual"
        )
        self.use_reranker = _env("FINSIGHT_USE_RERANKER", "true").lower() == "true"

        # --- Retrieval ---
        self.retrieve_candidates = int(_env("FINSIGHT_RETRIEVE_CANDIDATES", "30"))
        self.top_k = int(_env("FINSIGHT_TOP_K", "6"))

        # --- Chunking ---
        self.chunk_size = int(_env("FINSIGHT_CHUNK_SIZE", "1000"))
        self.chunk_overlap = int(_env("FINSIGHT_CHUNK_OVERLAP", "150"))

        # --- Short-term memory (Redis) ---
        self.memory_window = int(_env("FINSIGHT_MEMORY_WINDOW", "6"))   # turns fed to the LLM
        self.memory_ttl = int(_env("FINSIGHT_MEMORY_TTL", "86400"))     # seconds

        # --- Misc ---
        self.cors_origins = [
            o.strip()
            for o in _env(
                "FINSIGHT_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            ).split(",")
            if o.strip()
        ]
        self.max_upload_mb = int(_env("FINSIGHT_MAX_UPLOAD_MB", "50"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
