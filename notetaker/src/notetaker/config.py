from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CaptureConfig:
    slide_element_selector: str = ".vjs-tech"
    transcript_panel_selector: str = ".transcript-panel__content"
    transcript_line_selector: str = ".transcript-panel__content li"
    frame_sample_rate_seconds: int = 1
    browser_profile_path: str = ""
    # CSS selector for the Zoom recording-topic element. Used as a fallback when
    # page.title() returns the generic Zoom document title. Comma-separated list
    # of selectors tried in order.
    recording_title_selector: str = ".recording-topic, .topic-name, h1"


@dataclass
class ExtractionConfig:
    slide_change_threshold: int = 8
    sample_every_n_frames: int = 1


@dataclass
class UnderstandingConfig:
    vision_model: str = "claude-haiku-4-5-20251001"
    budget_ceiling_usd: float = 2.00
    input_token_price_per_million: float = 0.80
    output_token_price_per_million: float = 4.00


@dataclass
class ApiConfig:
    retry_count: int = 3
    retry_delay_seconds: float = 1.0


@dataclass
class CacheConfig:
    cache_dir: str = "~/.local/share/notetaker/cache"
    retention_days: int = 30


@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "console"
    log_dir: str = "~/.local/share/notetaker/logs"
    file_format: str = "json"
    heartbeat_interval_seconds: float = 15.0
    retention_days: int = 30


@dataclass
class NotesConfig:
    # Default model for the post-capture notes render call. Override here to swap models.
    model: str = "claude-sonnet-4-6"
    max_output_tokens: int = 8192
    # 0 = retain forever; default 365 days satisfies VI.2 ("indefinite retention forbidden by default").
    retention_days: int = 365
    working_doc_filename: str = "working_doc.md"
    # Legacy notes filename. Retained as the fallback name detected during the
    # lazy migration to human-readable filenames (spec 005). New runs write
    # under <YYYY-MM-DD>--<meeting>--<summary>.md instead.
    notes_filename: str = "notes.md"
    cost_warn_threshold_usd: float = 0.50
    # Model for the post-render summary call that produces a one-line label
    # used to compose the human-readable notes filename.
    summary_model: str = "claude-haiku-4-5-20251001"
    # Defensive client-side cap on the summary length (FR-002 / SC-003).
    summary_max_chars: int = 50
    # Pricing for the summary call. Mirrors the understanding-stage Haiku knobs.
    summary_input_token_price_per_million: float = 0.80
    summary_output_token_price_per_million: float = 4.00
    # Total notes filename cap (excluding ".md") — keeps names safe across
    # filesystems with 255-byte name limits.
    filename_max_chars: int = 200
    # Length of the URL-hash-prefix disambiguator appended on within-cache-entry
    # filename collisions (FR-007).
    filename_collision_suffix_chars: int = 8


@dataclass
class Config:
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    understanding: UnderstandingConfig = field(default_factory=UnderstandingConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    notes: NotesConfig = field(default_factory=NotesConfig)

    def resolved_notes_model(self) -> str:
        return self.notes.model

    @property
    def cache_dir_path(self) -> Path:
        return Path(self.cache.cache_dir).expanduser()

    @property
    def log_dir_path(self) -> Path:
        return Path(self.logging.log_dir).expanduser()


def _merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], val)
        else:
            result[key] = val
    return result


def _dataclass_from_dict(cls, data: dict):
    import dataclasses
    fields = {f.name for f in dataclasses.fields(cls)}
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        val = data[f.name]
        if dataclasses.is_dataclass(f.type) or (
            isinstance(f.default_factory, type) and dataclasses.is_dataclass(f.default_factory())
            if callable(getattr(f, "default_factory", None)) else False
        ):
            # nested dataclass — handled below
            pass
        kwargs[f.name] = val

    import dataclasses as dc
    for f in dc.fields(cls):
        if f.name not in data:
            continue
        origin_type = f.type
        if isinstance(origin_type, str):
            continue
        if dc.is_dataclass(origin_type) and isinstance(data[f.name], dict):
            kwargs[f.name] = _dataclass_from_dict(origin_type, data[f.name])
    return cls(**kwargs)


def _section(raw: dict, section: str, cls):
    data = raw.get(section, {})
    import dataclasses as dc
    kwargs = {}
    for f in dc.fields(cls):
        if f.name in data:
            kwargs[f.name] = data[f.name]
    return cls(**kwargs)


def load_config(
    config_path: Path | None = None,
    overrides: dict | None = None,
) -> Config:
    """
    Load order:
      1. Compiled defaults (dataclass defaults)
      2. Repo-local config.toml (if present in cwd or repo root)
      3. User config at ~/.config/notetaker/config.toml
      4. Explicit config_path argument
      5. overrides dict (from CLI flags)
    """
    raw: dict = {}

    candidates = [
        Path("config.toml"),
        Path(os.environ.get("NOTETAKER_CONFIG", "")).expanduser() if os.environ.get("NOTETAKER_CONFIG") else None,
        Path.home() / ".config" / "notetaker" / "config.toml",
    ]
    if config_path:
        candidates.append(config_path)

    for path in candidates:
        if path and path.exists():
            with open(path, "rb") as fh:
                raw = _merge(raw, tomllib.load(fh))

    if overrides:
        raw = _merge(raw, overrides)

    return Config(
        capture=_section(raw, "capture", CaptureConfig),
        extraction=_section(raw, "extraction", ExtractionConfig),
        understanding=_section(raw, "understanding", UnderstandingConfig),
        api=_section(raw, "api", ApiConfig),
        cache=_section(raw, "cache", CacheConfig),
        logging=_section(raw, "logging", LoggingConfig),
        notes=_section(raw, "notes", NotesConfig),
    )
