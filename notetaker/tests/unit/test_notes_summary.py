"""Tests for the post-render Haiku summary call (spec 005, T011)."""

from __future__ import annotations

import io
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from notetaker.config import Config
from notetaker.notes.summary import generate_summary
from notetaker.utils.logging import configure_logging


@pytest.fixture(autouse=True)
def _capture_stderr_json(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buf)
    configure_logging(level="INFO", fmt="json")
    yield buf


def _mock_response(text: str, in_tok: int = 600, out_tok: int = 30):
    return SimpleNamespace(
        content=[SimpleNamespace(text=text)],
        usage=SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok),
    )


def _records(buf: io.StringIO) -> list[dict]:
    return [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]


def _ev(records: list[dict], name: str) -> list[dict]:
    return [r for r in records if r.get("event") == name]


def test_success_path_returns_summary(_capture_stderr_json):
    cfg = Config()
    client = MagicMock()
    client.messages.create.return_value = _mock_response(
        '{"summary": "Roadmap, headcount, OKRs"}'
    )

    result = generate_summary("# Notes\n...", cfg, client=client)

    assert result.outcome == "success"
    assert result.text == "Roadmap, headcount, OKRs"
    assert result.total_attempts == 1
    assert result.total_input_tokens == 600
    assert result.total_output_tokens == 30
    assert result.total_cost_usd > 0

    recs = _records(_capture_stderr_json)
    renders = _ev(recs, "notes.summary_render")
    assert len(renders) == 1
    assert renders[0]["outcome"] == "success"


def test_over_length_response_truncated(_capture_stderr_json):
    cfg = Config()
    long = "x " * 100  # 200 chars
    client = MagicMock()
    client.messages.create.return_value = _mock_response(
        json.dumps({"summary": long})
    )

    result = generate_summary("notes", cfg, client=client)
    assert result.outcome == "success"
    assert len(result.text) <= cfg.notes.summary_max_chars


def test_malformed_json_returns_fallback(_capture_stderr_json):
    cfg = Config()
    client = MagicMock()
    client.messages.create.return_value = _mock_response(
        "this is not json at all"
    )

    result = generate_summary("notes", cfg, client=client)

    assert result.outcome == "fallback"
    assert result.text == "no-summary"

    recs = _records(_capture_stderr_json)
    fallbacks = _ev(recs, "notes.summary_fallback")
    assert len(fallbacks) == 1
    assert fallbacks[0]["reason"] == "parse_error"


def test_json_with_wrong_shape_returns_fallback(_capture_stderr_json):
    cfg = Config()
    client = MagicMock()
    client.messages.create.return_value = _mock_response('{"label": "wrong key"}')

    result = generate_summary("notes", cfg, client=client)
    assert result.outcome == "fallback"


def test_fenced_json_is_accepted(_capture_stderr_json):
    cfg = Config()
    client = MagicMock()
    client.messages.create.return_value = _mock_response(
        '```json\n{"summary": "fenced ok"}\n```'
    )
    result = generate_summary("notes", cfg, client=client)
    assert result.outcome == "success"
    assert result.text == "fenced ok"


def test_api_exception_returns_fallback_after_retries(_capture_stderr_json):
    cfg = Config()
    cfg.api.retry_count = 3
    cfg.api.retry_delay_seconds = 0.0

    class APIConnectionError(Exception):
        pass

    client = MagicMock()
    client.messages.create.side_effect = APIConnectionError("transient")

    result = generate_summary("notes", cfg, client=client)

    assert result.outcome == "fallback"
    assert result.text == "no-summary"
    assert result.total_attempts == 3

    recs = _records(_capture_stderr_json)
    renders = _ev(recs, "notes.summary_render")
    # Two retries + one final api_error.
    assert len(renders) == 3
    assert renders[0]["outcome"] == "retryable"
    assert renders[2]["outcome"] == "api_error"


def test_non_retryable_exception_short_circuits(_capture_stderr_json):
    cfg = Config()
    cfg.api.retry_count = 3
    cfg.api.retry_delay_seconds = 0.0

    client = MagicMock()
    client.messages.create.side_effect = ValueError("bad")

    result = generate_summary("notes", cfg, client=client)
    assert result.outcome == "fallback"
    recs = _records(_capture_stderr_json)
    renders = _ev(recs, "notes.summary_render")
    assert len(renders) == 1
    assert renders[0]["outcome"] == "api_error"


def test_cost_calculation_matches_pricing(_capture_stderr_json):
    cfg = Config()
    client = MagicMock()
    client.messages.create.return_value = _mock_response(
        '{"summary": "label"}', in_tok=1000, out_tok=100
    )

    result = generate_summary("notes", cfg, client=client)
    expected = (
        1000 / 1_000_000 * cfg.notes.summary_input_token_price_per_million
        + 100 / 1_000_000 * cfg.notes.summary_output_token_price_per_million
    )
    assert round(result.total_cost_usd, 6) == round(expected, 6)
