import io
import json
import logging
import sys
from pathlib import Path

import pytest

from notetaker.utils.logging import (
    bind_contextvars,
    clear_contextvars,
    configure_logging,
    get_logger,
)


@pytest.fixture(autouse=True)
def _reset_contextvars():
    clear_contextvars()
    yield
    clear_contextvars()
    # Flush + clear file handlers so per-test tmp_path log files are released
    # before pytest tears the directory down.
    root = logging.getLogger()
    for handler in list(root.handlers):
        try:
            handler.close()
        except Exception:
            pass
        root.removeHandler(handler)


def _capture_stderr(monkeypatch) -> io.StringIO:
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buf)
    return buf


def test_configure_console_emits_without_error(monkeypatch):
    buf = _capture_stderr(monkeypatch)
    configure_logging(level="INFO", fmt="console")
    get_logger("notetaker.test").info("smoke", k="v")
    out = buf.getvalue()
    assert "smoke" in out
    assert "k=v" in out


def test_configure_json_emits_parseable_record(monkeypatch):
    buf = _capture_stderr(monkeypatch)
    configure_logging(level="INFO", fmt="json")
    get_logger("notetaker.test").warning("warn.event", n=1)
    record = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert record["event"] == "warn.event"
    assert record["level"] == "warning"
    assert record["n"] == 1
    assert "timestamp" in record


def test_log_level_filtering(monkeypatch):
    buf = _capture_stderr(monkeypatch)
    configure_logging(level="WARNING", fmt="console")
    log = get_logger("notetaker.test")
    log.info("should.not.appear")
    log.warning("should.appear")
    out = buf.getvalue()
    assert "should.not.appear" not in out
    assert "should.appear" in out


def test_contextvars_merge_into_event(monkeypatch):
    buf = _capture_stderr(monkeypatch)
    configure_logging(level="INFO", fmt="json")
    bind_contextvars(request_id="abc123")
    get_logger("notetaker.test").info("ctx.event")
    record = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert record["request_id"] == "abc123"


# --------------------------------------------------------------------------
# File-sink tests (T009)
# --------------------------------------------------------------------------


def test_file_path_writes_json_record(tmp_path: Path, monkeypatch):
    _capture_stderr(monkeypatch)
    log_path = tmp_path / "run.log"
    configure_logging(level="INFO", fmt="console", file_path=log_path)
    get_logger("notetaker.test").info("file.smoke", k="v")
    # Force flush in case the test runs faster than the implicit flush.
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert log_path.exists()
    lines = log_path.read_text().splitlines()
    assert lines, "log file should have at least one line"
    record = json.loads(lines[-1])
    assert record["event"] == "file.smoke"
    assert record["k"] == "v"
    assert record["level"] == "info"
    assert "timestamp" in record


def test_file_sink_carries_bound_contextvars(tmp_path: Path, monkeypatch):
    _capture_stderr(monkeypatch)
    log_path = tmp_path / "run.log"
    configure_logging(level="INFO", fmt="console", file_path=log_path)
    bind_contextvars(stage="capture")
    get_logger("notetaker.test").info("ctx.in.file")
    for handler in logging.getLogger().handlers:
        handler.flush()
    record = json.loads(log_path.read_text().splitlines()[-1])
    assert record["stage"] == "capture"


def test_file_path_none_creates_no_file(tmp_path: Path, monkeypatch):
    _capture_stderr(monkeypatch)
    configure_logging(level="INFO", fmt="console", file_path=None)
    get_logger("notetaker.test").info("no.file")
    # tmp_path is empty (no run.log was created — file_path was None).
    assert list(tmp_path.iterdir()) == []


def test_file_path_unwritable_does_not_raise(tmp_path: Path, monkeypatch):
    buf = _capture_stderr(monkeypatch)
    # A directory in place of a file makes the open() fail with IsADirectoryError.
    not_writable = tmp_path / "blocked"
    not_writable.mkdir()
    # Must not raise.
    configure_logging(level="INFO", fmt="console", file_path=not_writable)
    # Stderr-only path is intact: a logger.info call still works.
    get_logger("notetaker.test").info("after.failed.file")
    out = buf.getvalue()
    assert "after.failed.file" in out
    # And one warning was surfaced about the failed file.
    assert "WARNING: cannot open log file" in out
