"""
T010: when the live transcript scrape's panel selector times out, the adapter
emits exactly one structured warning record carrying the documented fields and
sets `_transcript_unavailable = True` (so the surrounding capture flow exits
successfully — FR-015).
"""

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
    configure_logging(level="WARNING", fmt="json")
    yield buf


@pytest.mark.asyncio
async def test_panel_timeout_emits_renamed_warning_with_recovery_hint(_capture_stderr_json):
    cfg = Config()
    adapter = ZoomAdapter(cfg, debug=False, force=False)

    page = MagicMock()
    locator = MagicMock()
    locator.wait_for = AsyncMock(side_effect=TimeoutError("panel never appeared"))
    page.locator = MagicMock(return_value=locator)

    life = MagicMock()
    life.tick = MagicMock()

    await adapter._scrape_transcript(page, life)

    assert adapter._transcript_unavailable is True

    lines = [ln for ln in _capture_stderr_json.getvalue().splitlines() if ln.strip()]
    records = [json.loads(ln) for ln in lines]
    matching = [r for r in records if r.get("event") == "capture.transcript_unavailable"]
    assert len(matching) == 1, f"expected exactly one transcript_unavailable record, got {len(matching)}"

    record = matching[0]
    assert record["level"] == "warning"
    assert record["event_category"] == "warning"
    assert record["selector_used"] == ".transcript-panel__content"
    assert "HOWTO.md" in record["recovery_hint"]
    assert "post-capture" in record["recovery_hint"]


@pytest.mark.asyncio
async def test_old_event_name_no_longer_emitted(_capture_stderr_json):
    """Ensures the rename is durable — old name must not appear anywhere."""
    cfg = Config()
    adapter = ZoomAdapter(cfg, debug=False, force=False)

    page = MagicMock()
    locator = MagicMock()
    locator.wait_for = AsyncMock(side_effect=TimeoutError("nope"))
    page.locator = MagicMock(return_value=locator)
    life = MagicMock()
    life.tick = MagicMock()

    await adapter._scrape_transcript(page, life)

    out = _capture_stderr_json.getvalue()
    assert "transcript_panel_not_found" not in out
