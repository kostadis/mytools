import io
import json
import logging
import sys
from pathlib import Path

import click
import pytest

from notetaker.cli import _invoke_with_crash_capture
from notetaker.utils.logging import (
    clear_contextvars,
    configure_logging,
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


def _flush():
    for handler in logging.getLogger().handlers:
        handler.flush()


def _records(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_logs_unhandled_exception_to_file(tmp_path: Path, monkeypatch):
    """A non-Click exception inside the invocation must be captured as an
    `unhandled_exception` record before being re-raised."""
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    log_path = tmp_path / "run.log"
    configure_logging(level="INFO", fmt="console", file_path=log_path)

    def boom():
        raise RuntimeError("test_boom")

    with pytest.raises(RuntimeError, match="test_boom"):
        _invoke_with_crash_capture(boom)

    _flush()
    crashes = [r for r in _records(log_path) if r.get("event_category") == "unhandled_exception"]
    assert len(crashes) == 1
    assert crashes[0]["exc_type"] == "RuntimeError"
    assert "test_boom" in crashes[0]["traceback"]
    assert crashes[0]["message"] == "test_boom"


def test_does_not_log_systemexit(tmp_path: Path, monkeypatch):
    """SystemExit (typer/click's normal control flow) must NOT produce an
    unhandled_exception record."""
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    log_path = tmp_path / "run.log"
    configure_logging(level="INFO", fmt="console", file_path=log_path)

    def quit_zero():
        raise SystemExit(0)

    with pytest.raises(SystemExit):
        _invoke_with_crash_capture(quit_zero)

    _flush()
    if log_path.exists() and log_path.read_text().strip():
        crashes = [r for r in _records(log_path) if r.get("event_category") == "unhandled_exception"]
        assert crashes == []


def test_captures_keyboard_interrupt(tmp_path: Path, monkeypatch):
    """Ctrl-C during a long capture should leave a clear post-mortem record."""
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    log_path = tmp_path / "run.log"
    configure_logging(level="INFO", fmt="console", file_path=log_path)

    def interrupt():
        raise KeyboardInterrupt()

    with pytest.raises(SystemExit):
        # KeyboardInterrupt is converted to a SystemExit(1) so the shell sees
        # the right exit code. The unhandled_exception record is the diagnostic.
        _invoke_with_crash_capture(interrupt)

    _flush()
    crashes = [r for r in _records(log_path) if r.get("event_category") == "unhandled_exception"]
    assert len(crashes) == 1
    assert crashes[0]["exc_type"] == "KeyboardInterrupt"


def test_click_user_error_is_not_logged_as_crash(tmp_path: Path, monkeypatch):
    """ClickException (UsageError, BadParameter, etc.) is user-friendly noise,
    not a crash. It must NOT pollute the run log."""
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    log_path = tmp_path / "run.log"
    configure_logging(level="INFO", fmt="console", file_path=log_path)

    def usage_error():
        raise click.exceptions.UsageError("you passed the wrong flag")

    with pytest.raises(SystemExit):
        _invoke_with_crash_capture(usage_error)

    _flush()
    if log_path.exists() and log_path.read_text().strip():
        crashes = [r for r in _records(log_path) if r.get("event_category") == "unhandled_exception"]
        assert crashes == []
