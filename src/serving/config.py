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

        # --- Embedding / rerank ---
        # Dense backend: "local" = FastEmbed/ONNX on CPU (correct but ~99% of
        # index time); "api" = hosted model over HTTP (dense moves off the box,
        # indexing drops from ~11 min to seconds). Sparse BM25 stays local either
        # way. Both default to 1024-dim, so switching needs no Qdrant schema
        # change — but vectors from a different model are incompatible, so
        # re-index existing documents after switching.
        self.embed_backend = _env("FINSIGHT_EMBED_BACKEND", "local").lower()
        self.embed_model = _env("FINSIGHT_EMBED_MODEL", "intfloat/multilingual-e5-large")
        self.embed_dim = int(_env("FINSIGHT_EMBED_DIM", "1024"))
        # API dense backend (used when FINSIGHT_EMBED_BACKEND=api). Default model
        # is a BGE-M3 Vietnamese fine-tune (1024-dim, tops Vietnamese MTEB, no
        # word segmentation). HF_API_TOKEN authenticates the Inference API; point
        # FINSIGHT_API_EMBED_ENDPOINT at a dedicated/TEI endpoint to scale up.
        self.hf_api_token = _env("HF_API_TOKEN", "") or _env("HF_TOKEN", "")
        self.api_embed_model = _env(
            "FINSIGHT_API_EMBED_MODEL", "AITeamVN/Vietnamese_Embedding"
        )
        self.api_embed_batch = int(_env("FINSIGHT_API_EMBED_BATCH", "32"))
        self.api_embed_endpoint = _env("FINSIGHT_API_EMBED_ENDPOINT", "")
        # Hybrid retrieval: dense + sparse BM25 fused with RRF. BM25 is the lexical
        # layer that pins exact figures/codes/years that dense vectors blur.
        self.use_hybrid = _env("FINSIGHT_USE_HYBRID", "true").lower() == "true"
        self.sparse_model = _env("FINSIGHT_SPARSE_MODEL", "Qdrant/bm25")
        # ONNX intra-op threads (0 = let onnxruntime decide — measured fastest;
        # forcing the logical-core count was slower). Batch size for embedding.
        self.embed_threads = int(_env("FINSIGHT_EMBED_THREADS", "0"))
        self.embed_batch = int(_env("FINSIGHT_EMBED_BATCH", "16"))
        self.rerank_model = _env(
            "FINSIGHT_RERANK_MODEL", "jinaai/jina-reranker-v2-base-multilingual"
        )
        # Reranker is OFF by default: heaviest stage on CPU. Hybrid + MMR recover
        # most of its benefit far more cheaply (see src/rag/pipeline.py).
        self.use_reranker = _env("FINSIGHT_USE_RERANKER", "false").lower() == "true"

        # Auto-run PaddleOCR-VL inside the API for scanned PDFs (no text layer).
        # OFF by default: it loads a 3-5 GB VLM into the uvicorn process per
        # request and is never released -> OOM risk on low-RAM machines. When
        # off, scanned PDFs are rejected with a hint to OCR offline first.
        self.enable_api_ocr = _env("FINSIGHT_ENABLE_API_OCR", "false").lower() == "true"

        # --- Retrieval ---
        # Hybrid over-fetches candidates, then MMR trims to top_k. Bigger pools
        # help long reports where the answer chunk sits past the first handful.
        self.retrieve_candidates = int(_env("FINSIGHT_RETRIEVE_CANDIDATES", "50"))
        self.top_k = int(_env("FINSIGHT_TOP_K", "8"))
        self.mmr_lambda = float(_env("FINSIGHT_MMR_LAMBDA", "0.6"))  # 1=relevance, 0=diversity
        # Route a question to its financial statement / note / year and soft-filter
        # retrieval to that branch (falls back to unfiltered if it comes back empty).
        self.use_routing = _env("FINSIGHT_USE_ROUTING", "true").lower() == "true"
        # Graph-RAG cross-period fan-out: questions spanning several years search
        # each year and merge, so cross-file/cross-year answers see every period.
        self.use_graph = _env("FINSIGHT_USE_GRAPH", "true").lower() == "true"
        # Strict-grounding cutoff on the top retrieval score; 0 disables it (a
        # non-zero value can reject BM25-only exact matches — tune per corpus).
        self.score_threshold = float(_env("FINSIGHT_SCORE_THRESHOLD", "0.0"))

        # --- Chunking (character budgets; prose packs larger than the old 1000) ---
        self.chunk_size = int(_env("FINSIGHT_CHUNK_SIZE", "1800"))
        self.chunk_overlap = int(_env("FINSIGHT_CHUNK_OVERLAP", "250"))

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

    @property
    def active_embed_model(self) -> str:
        """The dense model actually in use, given the selected backend."""
        return self.api_embed_model if self.embed_backend == "api" else self.embed_model


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
