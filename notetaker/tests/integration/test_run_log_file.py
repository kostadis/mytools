"""Integration test for the run log file.

Runs extract → understand against the synthetic fixture (no browser, no
paid API) with a credential-bearing recording URL, then asserts the run
log file produced by the pipeline contains the expected stage-lifecycle
markers, no crashes, and no leaked credential values.
"""
from __future__ import annotations

import io
import json
import logging
import sys
from pathlib import Path
import pytest
from PIL import Image

from notetaker.config import Config
from notetaker.contracts.frames_manifest import FrameEntry, FramesManifestSchema
from notetaker.contracts.log_record import LogRecord
from notetaker.contracts.transcript import TranscriptSchema, Utterance
from notetaker.utils.heartbeat import HeartbeatTracker
from notetaker.utils.log_store import LogStore
from notetaker.utils.logging import (
    clear_contextvars,
    configure_logging,
)


# Distinctive sentinels chosen so the leak grep cannot be fooled by partial
# matches against unrelated bytes (path components, hashes, etc.).
URL_WITH_CREDS = (
    "https://zoom.us/rec/play/golden-fixture-002"
    "?pwd=SECRETSECRET&access_token=TOKENTOKEN"
)


@pytest.fixture(autouse=True)
def _reset_logging():
    clear_contextvars()
    yield
    clear_contextvars()
    root = logging.getLogger()
    for handler in list(root.handlers):
        try:
            handler.close()
        except Exception:
            pass
        root.removeHandler(handler)


@pytest.fixture
def synthetic_pipeline(tmp_path, monkeypatch):
    """Build a minimal cache (frames + transcript) and a Config pointing at tmp_path."""
    monkeypatch.setattr(sys, "stderr", io.StringIO())

    cfg = Config()
    cfg.cache.cache_dir = str(tmp_path / "cache")
    cfg.logging.log_dir = str(tmp_path / "logs")
    cfg.understanding.budget_ceiling_usd = 0.0  # OCR fallback only — no API calls

    log_dir = Path(cfg.logging.log_dir)
    log_store = LogStore(log_dir, retention_days=cfg.logging.retention_days)
    run_log_path = log_store.start_run(recording_url_hash=None)
    configure_logging(level="INFO", fmt="console", file_path=run_log_path)

    cfg._heartbeat_tracker = HeartbeatTracker(  # type: ignore[attr-defined]
        cfg.logging.heartbeat_interval_seconds
    )

    # Pre-populate cache with frames_manifest + transcript so extract has
    # something to read.
    from notetaker.cache import Cache
    cache_root = Path(cfg.cache.cache_dir)
    cache = Cache(cache_root, URL_WITH_CREDS)
    cache.initialise()

    frames_dir = cache.stage_dir("capture") / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for i, colour in enumerate([(200, 200, 200), (50, 100, 150)]):
        img = Image.new("RGB", (800, 600), color=colour)
        frame_path = frames_dir / f"{i * 5000}.jpg"
        img.save(str(frame_path), "JPEG")
        frames.append(FrameEntry(timestamp_ms=i * 5000, file_path=str(frame_path)))

    manifest = FramesManifestSchema(recording_url=URL_WITH_CREDS, frames=frames)
    cache.artifact_path("capture", "frames_manifest.json").write_text(
        manifest.model_dump_json(indent=2)
    )

    transcript = TranscriptSchema(
        recording_url=URL_WITH_CREDS,
        captured_at="2026-05-09T10:00:00Z",
        utterances=[
            Utterance(start_seconds=1.0, end_seconds=4.0,
                      speaker="Alice", text="Welcome."),
            Utterance(start_seconds=6.0, end_seconds=9.0,
                      speaker="Bob", text="Revenue up 15%."),
        ],
    )
    cache.artifact_path("capture", "transcript.json").write_text(
        transcript.model_dump_json(indent=2)
    )

    return cfg, run_log_path, log_dir


@pytest.mark.asyncio
async def test_run_log_contains_expected_stage_lifecycle(synthetic_pipeline):
    cfg, run_log_path, log_dir = synthetic_pipeline

    from notetaker.stages.extraction import run as run_extraction
    from notetaker.stages.understanding import run as run_understanding

    await run_extraction(URL_WITH_CREDS, cfg)
    await run_understanding(URL_WITH_CREDS, cfg)

    for handler in logging.getLogger().handlers:
        handler.flush()

    # (a) latest.log exists and is a symlink.
    latest = log_dir / "latest.log"
    assert latest.is_symlink()

    # Records load.
    raw_text = run_log_path.read_text()
    records = [json.loads(line) for line in raw_text.splitlines() if line.strip()]
    assert records, "expected at least one record in the run log"

    # (b) ≥2 stage_start / stage_end records, one per executed stage,
    # in pipeline order. (The synthetic fixture skips real capture so we
    # exercise two stages — adapt if real capture is later wired in.)
    starts = [r for r in records if r.get("event_category") == "stage_start"]
    ends = [r for r in records if r.get("event_category") == "stage_end"]
    start_stages = [r["stage"] for r in starts]
    end_stages = [r["stage"] for r in ends]
    assert start_stages == ["extract", "understand"]
    assert end_stages == ["extract", "understand"]

    # (c) Zero unhandled_exception records.
    crashes = [r for r in records if r.get("event_category") == "unhandled_exception"]
    assert crashes == []

    # (d) Every stage_end has positive elapsed_seconds and a non-empty payload.
    for end in ends:
        assert end["elapsed_seconds"] >= 0.0
        # payload fields are merged at top level by structlog. The contract's
        # `payload` is a logical grouping; in JSON-line form the keys are flat.
        # Each stage promised at least one headline metric in end_payload — we
        # check that the record has more keys than just the lifecycle fields.
        lifecycle_keys = {
            "schema_version", "ts", "level", "event", "event_category",
            "stage", "elapsed_seconds", "recording_url_hash", "timestamp",
            "logger",
        }
        extra_keys = set(end.keys()) - lifecycle_keys
        assert extra_keys, f"stage_end for {end['stage']} carries no metrics"

    # (e) Article VI.1 leak check: neither sentinel value appears anywhere
    # in the run log file's bytes. (extract/understand/synthesise log only
    # the URL hash, not the raw URL, but this assertion is the
    # belt-and-suspenders check that no future logger call will start
    # leaking it without test failure.)
    assert "SECRETSECRET" not in raw_text, "credential 'pwd' value leaked to log"
    assert "TOKENTOKEN" not in raw_text, "credential 'access_token' value leaked to log"


@pytest.mark.asyncio
async def test_purge_stale_emits_summary_record(synthetic_pipeline):
    cfg, run_log_path, log_dir = synthetic_pipeline

    # Purge runs from cli._setup() in production; we exercise it directly here.
    store = LogStore(log_dir, retention_days=cfg.logging.retention_days)
    store.purge_stale()

    for handler in logging.getLogger().handlers:
        handler.flush()

    records = [json.loads(line) for line in run_log_path.read_text().splitlines() if line.strip()]
    purges = [r for r in records if r.get("event") == "log_store.purge_stale"]
    # At least one purge record (T022 verification).
    assert len(purges) >= 1
    p = purges[-1]
    assert "removed" in p
    assert "kept" in p
