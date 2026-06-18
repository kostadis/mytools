import asyncio
import io
import json
import logging
import sys
import time
from pathlib import Path
from typing import List
from unittest.mock import patch

import pytest

from notetaker.utils.heartbeat import HeartbeatTracker, stage_lifecycle
from notetaker.utils.logging import (
    clear_contextvars,
    configure_logging,
    get_logger,
)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
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


def _read_records(path: Path) -> List[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_tick_throttles_within_window(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    log_path = tmp_path / "run.log"
    configure_logging(level="INFO", fmt="console", file_path=log_path)

    tracker = HeartbeatTracker(interval_seconds=10.0)
    for _ in range(10):
        tracker.tick("capture", "frames", frames=1)

    for handler in logging.getLogger().handlers:
        handler.flush()
    records = _read_records(log_path)
    heartbeats = [r for r in records if r.get("event_category") == "heartbeat"]
    assert len(heartbeats) == 1


def test_tick_emits_again_after_interval(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    log_path = tmp_path / "run.log"
    configure_logging(level="INFO", fmt="console", file_path=log_path)

    # Use a tiny interval and a fake clock to avoid real-time waits.
    fake_now = [1000.0]

    def fake_monotonic():
        return fake_now[0]

    with patch("notetaker.utils.heartbeat.time.monotonic", fake_monotonic):
        tracker = HeartbeatTracker(interval_seconds=1.0)
        tracker.tick("capture", "frames", frames=1)
        fake_now[0] += 1.1
        tracker.tick("capture", "frames", frames=2)

    for handler in logging.getLogger().handlers:
        handler.flush()
    records = _read_records(log_path)
    heartbeats = [r for r in records if r.get("event_category") == "heartbeat"]
    assert len(heartbeats) == 2


def test_different_keys_throttle_independently(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    log_path = tmp_path / "run.log"
    configure_logging(level="INFO", fmt="console", file_path=log_path)

    tracker = HeartbeatTracker(interval_seconds=10.0)
    tracker.tick("capture", "frames", frames=1)
    tracker.tick("capture", "transcript", utterances=1)
    tracker.tick("capture", "frames", frames=2)  # throttled
    tracker.tick("capture", "transcript", utterances=2)  # throttled

    for handler in logging.getLogger().handlers:
        handler.flush()
    records = _read_records(log_path)
    heartbeats = [r for r in records if r.get("event_category") == "heartbeat"]
    keys = sorted(r["heartbeat_key"] for r in heartbeats)
    assert keys == ["frames", "transcript"]


def test_stage_lifecycle_clean_exit_emits_start_and_end(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    log_path = tmp_path / "run.log"
    configure_logging(level="INFO", fmt="console", file_path=log_path)
    tracker = HeartbeatTracker(interval_seconds=10.0)

    async def run():
        async with stage_lifecycle("extract", tracker=tracker) as life:
            life.end_payload["total_slides"] = 17
            life.end_payload["unique_slides"] = 5
        return None

    asyncio.run(run())

    for handler in logging.getLogger().handlers:
        handler.flush()
    records = _read_records(log_path)
    starts = [r for r in records if r.get("event_category") == "stage_start"]
    ends = [r for r in records if r.get("event_category") == "stage_end"]
    assert len(starts) == 1 and starts[0]["stage"] == "extract"
    assert len(ends) == 1 and ends[0]["stage"] == "extract"
    assert ends[0]["elapsed_seconds"] >= 0
    assert ends[0]["total_slides"] == 17
    assert ends[0]["unique_slides"] == 5


def test_stage_lifecycle_on_exception_emits_no_end(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    log_path = tmp_path / "run.log"
    configure_logging(level="INFO", fmt="console", file_path=log_path)
    tracker = HeartbeatTracker(interval_seconds=10.0)

    async def run():
        async with stage_lifecycle("understand", tracker=tracker) as life:
            life.end_payload["should_not_appear"] = True
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(run())

    for handler in logging.getLogger().handlers:
        handler.flush()
    records = _read_records(log_path)
    starts = [r for r in records if r.get("event_category") == "stage_start"]
    ends = [r for r in records if r.get("event_category") == "stage_end"]
    assert len(starts) == 1 and starts[0]["stage"] == "understand"
    assert ends == []


def test_stage_lifecycle_binds_recording_url_hash(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    log_path = tmp_path / "run.log"
    configure_logging(level="INFO", fmt="console", file_path=log_path)
    tracker = HeartbeatTracker(interval_seconds=10.0)

    async def run():
        async with stage_lifecycle(
            "capture",
            tracker=tracker,
            recording_url_hash="3f7a91c8b2d0e1f4",
        ) as life:
            life.tick("frames", frames=1)
            life.end_payload["frames"] = 1

    asyncio.run(run())

    for handler in logging.getLogger().handlers:
        handler.flush()
    records = _read_records(log_path)
    # Every record emitted inside the body carries the bound contextvars.
    in_body = [r for r in records if r.get("stage") == "capture"]
    assert in_body, "expected at least one record from inside the stage body"
    for r in in_body:
        assert r.get("recording_url_hash") == "3f7a91c8b2d0e1f4"
