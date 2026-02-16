"""Configuration management — loads .env and exposes a Settings singleton."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (two levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _int_env(key: str, default: int) -> int:
    raw = os.getenv(key, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logging.getLogger(__name__).warning(
            "Invalid integer for %s=%r, using default %d", key, raw, default,
        )
        return default


def _path_env(key: str, default: str) -> Path:
    raw = os.getenv(key, default)
    path = Path(raw)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    return path


class _LazyDir:
    """Path-like wrapper that defers mkdir to first actual filesystem access."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._ensured = False

    def _ensure(self) -> Path:
        if not self._ensured:
            self._path.mkdir(parents=True, exist_ok=True)
            self._ensured = True
        return self._path

    def __truediv__(self, other: str) -> Path:
        return self._ensure() / other

    def __str__(self) -> str:
        return str(self._ensure())

    def __fspath__(self) -> str:
        return os.fspath(self._ensure())


@dataclass(frozen=True)
class Settings:
    # LLM (OpenAI-compatible) — default (non-reasoning) model
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY"))
    llm_base_url: str = field(
        default_factory=lambda: _env(
            "LLM_BASE_URL", "https://api.deepseek.com/v1"
        )
    )
    llm_model: str = field(
        default_factory=lambda: _env("LLM_MODEL", "deepseek-chat")
    )

    # Reasoning LLM — used for planning / judging (falls back to llm_* if unset)
    reasoning_llm_api_key: str = field(
        default_factory=lambda: _env("REASONING_LLM_API_KEY") or _env("LLM_API_KEY")
    )
    reasoning_llm_base_url: str = field(
        default_factory=lambda: _env("REASONING_LLM_BASE_URL")
        or _env("LLM_BASE_URL", "https://api.deepseek.com/v1")
    )
    reasoning_llm_model: str = field(
        default_factory=lambda: _env("REASONING_LLM_MODEL")
        or _env("LLM_MODEL", "deepseek-chat")
    )

    # Neo4j
    neo4j_uri: str = field(
        default_factory=lambda: _env("NEO4J_URI", "bolt://localhost:7687")
    )
    neo4j_username: str = field(
        default_factory=lambda: _env("NEO4J_USERNAME", "neo4j")
    )
    neo4j_password: str = field(
        default_factory=lambda: _env("NEO4J_PASSWORD", "neo4j")
    )
    neo4j_database: str = field(
        default_factory=lambda: _env("NEO4J_DATABASE", "neo4j")
    )

    # Embedding
    embedding_api_key: str = field(
        default_factory=lambda: _env("EMBEDDING_API_KEY")
    )
    embedding_base_url: str = field(
        default_factory=lambda: _env("EMBEDDING_BASE_URL")
    )
    embedding_model: str = field(
        default_factory=lambda: _env("EMBEDDING_MODEL", "Qwen3-Embedding-8B")
    )
    embedding_dim: int = field(
        default_factory=lambda: _int_env("EMBEDDING_DIM", 4096)
    )

    # Firecrawl
    firecrawl_api_key: str = field(
        default_factory=lambda: _env("FIRECRAWL_API_KEY")
    )

    # Chunking / Retrieval
    chunk_size: int = field(default_factory=lambda: _int_env("CHUNK_SIZE", 8192))
    chunk_overlap: int = field(
        default_factory=lambda: _int_env("CHUNK_OVERLAP", 64)
    )
    top_k: int = field(default_factory=lambda: _int_env("TOP_K", 5))

    # Agent
    max_iterations: int = field(
        default_factory=lambda: _int_env("MAX_ITERATIONS", 3)
    )
    agent_concurrency: int = field(
        default_factory=lambda: _int_env("AGENT_CONCURRENCY", 3)
    )

    # Concurrency
    llm_concurrency: int = field(
        default_factory=lambda: _int_env("LLM_CONCURRENCY", 50)
    )
    storage_concurrency: int = field(
        default_factory=lambda: _int_env("STORAGE_CONCURRENCY", 50)
    )
    file_concurrency: int = field(
        default_factory=lambda: _int_env("FILE_CONCURRENCY", 25)
    )
    llm_request_timeout: int = field(
        default_factory=lambda: _int_env("LLM_REQUEST_TIMEOUT", 600)
    )

    # Paths
    data_dir: _LazyDir = field(
        default_factory=lambda: _LazyDir(_PROJECT_ROOT / _env("DATA_DIR", "data"))
    )

    # Session persistence
    session_db_path: Path = field(
        default_factory=lambda: _path_env("SESSION_DB_PATH", "data/sessions.sqlite3")
    )

    # JWT Authentication
    jwt_secret_key: str = field(
        default_factory=lambda: _env("JWT_SECRET_KEY", "dev-secret-change-in-production")
    )
    jwt_expire_hours: int = field(
        default_factory=lambda: _int_env("JWT_EXPIRE_HOURS", 24)
    )

    # API
    api_host: str = field(default_factory=lambda: _env("API_HOST", "0.0.0.0"))
    api_port: int = field(default_factory=lambda: _int_env("API_PORT", 8000))
    session_history_rounds: int = field(
        default_factory=lambda: _int_env("SESSION_HISTORY_ROUNDS", 5)
    )


# Module-level singleton — import and use directly
settings = Settings()

_logger = logging.getLogger(__name__)
if settings.neo4j_password == "neo4j":
    _logger.warning(
        "Neo4j is using the default password. "
        "Set NEO4J_PASSWORD in .env for production use."
    )
