"""Tests for the Zoom meeting-title scrape (spec 005, T013)."""

from __future__ import annotations

import io
import json
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from notetaker.config import Config
from notetaker.stages.capture.adapters.zoom import ZoomAdapter
from notetaker.utils.logging import configure_logging


@pytest.fixture(autouse=True)
def _capture_stderr_json(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buf)
    configure_logging(level="INFO", fmt="json")
    yield buf


def _records(buf):
    return [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]


def _make_page(title_value=None, title_exc=None, locator_text=None, locator_exc=None):
    page = MagicMock()
    if title_exc is not None:
        page.title = AsyncMock(side_effect=title_exc)
    else:
        page.title = AsyncMock(return_value=title_value)

    locator = MagicMock()
    first = MagicMock()
    if locator_exc is not None:
        first.text_content = AsyncMock(side_effect=locator_exc)
    else:
        first.text_content = AsyncMock(return_value=locator_text)
    locator.first = first
    page.locator = MagicMock(return_value=locator)
    return page


@pytest.mark.asyncio
async def test_page_title_used_when_specific(_capture_stderr_json, tmp_path):
    cfg = Config()
    adapter = ZoomAdapter(cfg, debug=False, force=False)
    page = _make_page(title_value="Q2 Planning Sync")

    title = await adapter._scrape_meeting_title(page, tmp_path)

    assert title == "Q2 Planning Sync"
    page.locator.assert_not_called()  # Fallback not invoked.

    recs = _records(_capture_stderr_json)
    scraped = [r for r in recs if r.get("event") == "capture.meeting_title_scraped"]
    assert len(scraped) == 1
    assert scraped[0]["selector_used"] == "page.title"
    assert scraped[0]["title_len"] == len("Q2 Planning Sync")


@pytest.mark.asyncio
async def test_generic_title_falls_back_to_locator(_capture_stderr_json, tmp_path):
    cfg = Config()
    adapter = ZoomAdapter(cfg, debug=False, force=False)
    page = _make_page(title_value="Zoom", locator_text="The Real Topic")

    title = await adapter._scrape_meeting_title(page, tmp_path)

    assert title == "The Real Topic"
    page.locator.assert_called_once()


@pytest.mark.asyncio
async def test_page_title_raises_falls_back_to_locator(_capture_stderr_json, tmp_path):
    cfg = Config()
    adapter = ZoomAdapter(cfg, debug=False, force=False)
    page = _make_page(title_exc=RuntimeError("boom"), locator_text="From Selector")

    title = await adapter._scrape_meeting_title(page, tmp_path)
    assert title == "From Selector"


@pytest.mark.asyncio
async def test_all_probes_fail_returns_none_and_warns(_capture_stderr_json, tmp_path):
    cfg = Config()
    adapter = ZoomAdapter(cfg, debug=False, force=False)
    page = _make_page(title_value="Zoom", locator_text=None)

    title = await adapter._scrape_meeting_title(page, tmp_path)
    assert title is None

    recs = _records(_capture_stderr_json)
    unavailable = [r for r in recs if r.get("event") == "capture.meeting_title_unavailable"]
    assert len(unavailable) == 1
    assert "title_scrape.json" in unavailable[0]["recovery_hint"]


@pytest.mark.asyncio
async def test_locator_exception_does_not_propagate(_capture_stderr_json, tmp_path):
    cfg = Config()
    adapter = ZoomAdapter(cfg, debug=False, force=False)
    page = _make_page(
        title_value="Zoom",
        locator_exc=RuntimeError("locator broken"),
    )

    title = await adapter._scrape_meeting_title(page, tmp_path)
    assert title is None  # No exception bubbles up.


@pytest.mark.asyncio
async def test_debug_mode_writes_raw_probe_artifact(_capture_stderr_json, tmp_path):
    cfg = Config()
    adapter = ZoomAdapter(cfg, debug=True, force=False)
    page = _make_page(title_value="Q2 Planning Sync")

    cache_root = tmp_path / "abc"
    cache_root.mkdir()
    await adapter._scrape_meeting_title(page, cache_root)

    raw = cache_root / "capture" / "raw" / "title_scrape.json"
    assert raw.exists()
    payload = json.loads(raw.read_text())
    assert payload["result"] == "Q2 Planning Sync"
    assert payload["attempted"][0]["source"] == "page.title"
