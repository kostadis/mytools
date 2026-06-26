"""Central configuration for drive-tagger.

Values come from environment variables with sensible defaults so the agent can
run with zero setup beyond ``CURSOR_API_KEY`` and a working ``gdrive-cli``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_path(name: str, default: Path) -> Path:
    return Path(os.environ[name]).expanduser() if name in os.environ else default


# Project root = the drive-tagger repo directory (two parents up from this file).
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Config:
    # --- storage locations ---------------------------------------------------
    data_dir: Path = field(default_factory=lambda: _env_path("DT_DATA_DIR", PROJECT_ROOT / "data"))
    reports_dir: Path = field(
        default_factory=lambda: _env_path("DT_REPORTS_DIR", PROJECT_ROOT / "reports")
    )

    # --- gdrive-cli ----------------------------------------------------------
    # Path to the built gdrive-cli binary; falls back to PATH lookup of "gdrive-cli".
    gdrive_cli_bin: str = field(
        default_factory=lambda: _env(
            "DT_GDRIVE_CLI",
            str(PROJECT_ROOT.parent / "gdrive-cli" / "target" / "release" / "gdrive-cli"),
        )
    )

    # --- embeddings ----------------------------------------------------------
    embed_model: str = field(
        default_factory=lambda: _env("DT_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    )
    embed_dim: int = field(default_factory=lambda: _env_int("DT_EMBED_DIM", 384))

    # --- agent / retrieval tunables -----------------------------------------
    model: str = field(default_factory=lambda: _env("DT_MODEL", "claude-haiku-4-5"))
    similar_k: int = field(default_factory=lambda: _env_int("DT_SIMILAR_K", 8))
    max_chars: int = field(default_factory=lambda: _env_int("DT_MAX_CHARS", 12000))
    max_files_per_run: int = field(default_factory=lambda: _env_int("DT_MAX_FILES", 50))
    batch_size: int = field(default_factory=lambda: _env_int("DT_BATCH_SIZE", 10))

    # --- optional local mount fast-path -------------------------------------
    drive_mount: str = field(default_factory=lambda: _env("DT_DRIVE_MOUNT", "/mnt/g"))

    # --- scan ----------------------------------------------------------------
    all_drives: bool = field(default_factory=lambda: _env("DT_ALL_DRIVES", "0") == "1")

    # Which files count as taggable: "documents" (PDF/Docs/docx/markdown/slides)
    # or "all" (also text/plain, json, csv, xml).
    processable_mode: str = field(
        default_factory=lambda: _env("DT_PROCESSABLE_MODE", "documents")
    )

    @property
    def db_dir(self) -> Path:
        return self.data_dir / "db"

    @property
    def graph_db(self) -> Path:
        return self.data_dir / "graph.sqlite"

    @property
    def scan_path(self) -> Path:
        return self.data_dir / "scan.jsonl"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.db_dir.mkdir(parents=True, exist_ok=True)


CONFIG = Config()
