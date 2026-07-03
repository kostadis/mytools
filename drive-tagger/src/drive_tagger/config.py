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


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
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
    # "local" uses fastembed (all-MiniLM-L6-v2, 384-dim, no network).
    # "dgx" uses the Ollama OpenAI-compat endpoint on spark2 (qwen3-embedding:0.6b, 1024-dim).
    # Switching providers requires `drive-tagger reset` — vectors from different models
    # are incompatible even if you set DT_EMBED_DIM correctly.
    embed_provider: str = field(default_factory=lambda: _env("DT_EMBED_PROVIDER", "local"))
    embed_model: str = field(
        default_factory=lambda: _env("DT_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    )
    embed_dim: int = field(
        default_factory=lambda: _env_int(
            "DT_EMBED_DIM",
            1024 if _env("DT_EMBED_PROVIDER", "local") == "dgx" else 384,
        )
    )

    # DGX embedding endpoint (Ollama on spark2, OpenAI-compat /v1/embeddings).
    dgx_embed_endpoint: str = field(
        default_factory=lambda: _env("DT_DGX_EMBED_ENDPOINT", "http://192.168.1.121:11434/v1")
    )
    dgx_embed_model: str = field(
        default_factory=lambda: _env("DT_DGX_EMBED_MODEL", "qwen3-embedding:0.6b")
    )

    # --- provider selection --------------------------------------------------
    # cursor | anthropic | openrouter | dgx
    provider: str = field(default_factory=lambda: _env("DT_PROVIDER", "cursor"))

    # --- OpenRouter ----------------------------------------------------------
    openrouter_base_url: str = field(
        default_factory=lambda: _env("DT_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    )
    # Reads OPENROUTER_API_KEY by convention (same name most tools use).
    openrouter_api_key: str = field(
        default_factory=lambda: _env("OPENROUTER_API_KEY", "")
    )

    # --- DGX Spark -----------------------------------------------------------
    dgx_endpoint: str = field(
        default_factory=lambda: _env("DT_DGX_ENDPOINT", "http://192.168.1.121:8001/v1")
    )
    # Model running on the DGX; verify with /spark-status before changing.
    dgx_model: str = field(
        default_factory=lambda: _env(
            "DT_DGX_MODEL", "Qwen/Qwen3-Next-80B-A3B-Instruct-FP8"
        )
    )

    # --- agent / retrieval tunables -----------------------------------------
    model: str = field(default_factory=lambda: _env("DT_MODEL", "claude-haiku-4-5"))
    similar_k: int = field(default_factory=lambda: _env_int("DT_SIMILAR_K", 8))
    max_chars: int = field(default_factory=lambda: _env_int("DT_MAX_CHARS", 12000))
    max_files_per_run: int = field(default_factory=lambda: _env_int("DT_MAX_FILES", 50))
    batch_size: int = field(default_factory=lambda: _env_int("DT_BATCH_SIZE", 10))

    # --- deterministic pipeline (`drive-tagger pipeline`) --------------------
    pipeline_workers: int = field(default_factory=lambda: _env_int("DT_PIPELINE_WORKERS", 4))
    judge_chars: int = field(default_factory=lambda: _env_int("DT_JUDGE_CHARS", 2500))

    # --- optional local mount fast-path -------------------------------------
    drive_mount: str = field(default_factory=lambda: _env("DT_DRIVE_MOUNT", "/mnt/g"))

    # --- scan ----------------------------------------------------------------
    all_drives: bool = field(default_factory=lambda: _env("DT_ALL_DRIVES", "0") == "1")

    # --- rpg-lib worklist filter (opt-in) ---------------------------------------
    # Set DT_RPG_LIB_URL to the rpg-lib base URL (e.g. http://localhost:8000) to
    # restrict the worklist to books curated by that service.  Empty = disabled.
    rpg_lib_url: str = field(default_factory=lambda: _env("DT_RPG_LIB_URL", ""))

    # Which files count as taggable: "documents" (PDF/Docs/docx/markdown/slides)
    # or "all" (also text/plain, json, csv, xml).
    processable_mode: str = field(
        default_factory=lambda: _env("DT_PROCESSABLE_MODE", "documents")
    )

    # --- post-run category consolidation (`drive-tagger consolidate`) -------
    # Cosine distance threshold for single-linkage clustering of near-duplicate
    # categories (turbovecdb metric is cosine: 0 = identical vectors). This is
    # a CALIBRATED PLACEHOLDER, not a universal constant.
    #
    # Measured against the real data/db on 2026-07-03 (1197 categories, 5041
    # docs, DT_EMBED_PROVIDER=dgx / qwen3-embedding:0.6b / 1024-dim): nearest-
    # neighbor category distances have p1=0.0004, p5=0.049 (singular/plural and
    # synonym pairs live under ~0.03). Single-linkage chaining crosses a cliff
    # around 0.06 (largest cluster 20 members) -> 0.08 (94 members) -> 0.15 (371
    # members, i.e. the taxonomy collapsing into one blob). 0.05 sits just below
    # that cliff. Run `consolidate collect --diagnostics` to see this
    # distribution for yourself before trusting the number.
    #
    # This value does NOT transfer to a different embed model. The *default*
    # embed provider elsewhere in this file is "local" (MiniLM, 384-dim) but
    # this default was calibrated on dgx/qwen3-1024 data (the only real corpus
    # available). If DT_EMBED_PROVIDER=local, re-run `--diagnostics` and repick
    # a threshold just below that model's own chaining cliff before trusting
    # `consolidate collect` output.
    consolidate_cluster_threshold: float = field(
        default_factory=lambda: _env_float("DT_CONSOLIDATE_CLUSTER_THRESHOLD", 0.05)
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

    @property
    def consolidation_dir(self) -> Path:
        return self.reports_dir / "consolidation"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.consolidation_dir.mkdir(parents=True, exist_ok=True)


CONFIG = Config()
