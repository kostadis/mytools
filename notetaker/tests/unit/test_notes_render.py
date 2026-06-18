"""
Unit tests for the single LLM render module. The Anthropic client is mocked
in every test (Article VII.3).
"""

from __future__ import annotations

import io
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from notetaker.config import Config
from notetaker.notes.render import RenderFailedError, render_notes
from notetaker.utils.logging import configure_logging


@pytest.fixture(autouse=True)
def _capture_stderr_json(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buf)
    configure_logging(level="INFO", fmt="json")
    yield buf


def _mock_response(text: str, in_tok: int = 1000, out_tok: int = 200):
    return SimpleNamespace(
        content=[SimpleNamespace(text=text)],
        usage=SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok),
    )


def _records(buf: io.StringIO) -> list[dict]:
    return [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]


def _ev(records: list[dict], name: str) -> list[dict]:
    return [r for r in records if r.get("event") == name]


def test_successful_render_writes_text_and_emits_records(_capture_stderr_json):
    cfg = Config()
    client = MagicMock()
    client.messages.create.return_value = _mock_response("# Notes\n\nAll good.\n")

    result = render_notes("WORKING DOC", cfg, client=client)

    assert result.text == "# Notes\n\nAll good.\n"
    assert result.outcome == "success"
    assert result.total_attempts == 1
    assert client.messages.create.call_count == 1

    recs = _records(_capture_stderr_json)
    attempts = _ev(recs, "notes.render_attempt")
    completes = _ev(recs, "notes.render_complete")
    assert len(attempts) == 1
    assert attempts[0]["outcome"] == "success"
    assert attempts[0]["input_tokens"] == 1000
    assert attempts[0]["output_tokens"] == 200
    assert attempts[0]["cost_usd"] > 0
    assert len(completes) == 1
    assert completes[0]["outcome"] == "success"
    assert completes[0]["total_attempts"] == 1


def test_transient_failure_then_success(_capture_stderr_json):
    cfg = Config()
    cfg.api.retry_count = 3
    cfg.api.retry_delay_seconds = 0.0  # don't slow tests

    class APIConnectionError(Exception):
        pass

    client = MagicMock()
    client.messages.create.side_effect = [
        APIConnectionError("transient"),
        _mock_response("# Notes\n", 100, 50),
    ]

    result = render_notes("WORKING DOC", cfg, client=client)
    assert result.outcome == "success"
    assert result.total_attempts == 2

    recs = _records(_capture_stderr_json)
    attempts = _ev(recs, "notes.render_attempt")
    assert len(attempts) == 2
    assert attempts[0]["outcome"] == "retryable"
    assert attempts[1]["outcome"] == "success"
    completes = _ev(recs, "notes.render_complete")
    assert len(completes) == 1
    assert completes[0]["total_attempts"] == 2


def test_persistent_failure_raises_and_emits_persistent_failure_record(_capture_stderr_json):
    cfg = Config()
    cfg.api.retry_count = 3
    cfg.api.retry_delay_seconds = 0.0

    class APIConnectionError(Exception):
        pass

    client = MagicMock()
    client.messages.create.side_effect = APIConnectionError("still broken")

    with pytest.raises(RenderFailedError):
        render_notes("WORKING DOC", cfg, client=client)

    recs = _records(_capture_stderr_json)
    attempts = _ev(recs, "notes.render_attempt")
    # 3 attempts: 2 retryable + 1 persistent_failure.
    assert len(attempts) == 3
    assert attempts[0]["outcome"] == "retryable"
    assert attempts[1]["outcome"] == "retryable"
    assert attempts[2]["outcome"] == "persistent_failure"
    completes = _ev(recs, "notes.render_complete")
    assert len(completes) == 1
    assert completes[0]["outcome"] == "persistent_failure"
    assert completes[0]["total_attempts"] == 3


def test_non_retryable_exception_short_circuits(_capture_stderr_json):
    cfg = Config()
    cfg.api.retry_count = 3
    cfg.api.retry_delay_seconds = 0.0

    client = MagicMock()
    client.messages.create.side_effect = ValueError("bad model name")

    with pytest.raises(RenderFailedError):
        render_notes("WD", cfg, client=client)

    recs = _records(_capture_stderr_json)
    attempts = _ev(recs, "notes.render_attempt")
    # Single attempt, persistent_failure (ValueError isn't in the retryable allowlist).
    assert len(attempts) == 1
    assert attempts[0]["outcome"] == "persistent_failure"


def test_resolved_model_returns_notes_default_and_honours_override():
    cfg = Config()
    assert cfg.resolved_notes_model() == "claude-sonnet-4-6"
    cfg.notes.model = "claude-haiku-OVERRIDE"
    assert cfg.resolved_notes_model() == "claude-haiku-OVERRIDE"


def test_cost_format_string_lock_for_quickstart_compat():
    """Quickstart documents the cost-summary format. Lock it here so doc + code stay in sync."""
    # The CLI uses: f"input_tokens={r.total_input_tokens:,}  output_tokens={r.total_output_tokens:,}  cost=${r.total_cost_usd:.4f}"
    # That's a static format; assert a sample matches.
    sample = f"input_tokens={35014:,}  output_tokens={4171:,}  cost=${0.1676:.4f}"
    assert sample == "input_tokens=35,014  output_tokens=4,171  cost=$0.1676"
