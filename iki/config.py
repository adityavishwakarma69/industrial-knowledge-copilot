"""Central configuration. All values can be overridden via environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    """Runtime settings for the IKI platform."""

    # --- Storage -------------------------------------------------------------
    data_dir: Path = field(default_factory=lambda: Path(_env("IKI_DATA_DIR", "iki_store")))
    index_filename: str = "knowledge_index.json"

    # --- AI backend ----------------------------------------------------------
    # "offline" (default, no API key), "openai", or "anthropic".
    ai_provider: str = field(default_factory=lambda: _env("IKI_AI_PROVIDER", "offline"))
    embedding_model: str = field(default_factory=lambda: _env("IKI_EMBEDDING_MODEL", "text-embedding-3-small"))
    generation_model: str = field(default_factory=lambda: _env("IKI_GENERATION_MODEL", "gpt-4o-mini"))
    embedding_dim: int = field(default_factory=lambda: _env_int("IKI_EMBEDDING_DIM", 512))

    # --- Retrieval / chunking ------------------------------------------------
    chunk_size: int = field(default_factory=lambda: _env_int("IKI_CHUNK_SIZE", 900))
    chunk_overlap: int = field(default_factory=lambda: _env_int("IKI_CHUNK_OVERLAP", 150))
    top_k: int = field(default_factory=lambda: _env_int("IKI_TOP_K", 6))
    min_score: float = field(default_factory=lambda: _env_float("IKI_MIN_SCORE", 0.04))

    @property
    def index_path(self) -> Path:
        return self.data_dir / self.index_filename

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


# A module-level singleton is convenient for a demo app.
settings = Settings()
