"""
T027 — One opt-in test that exercises the real Anthropic API end-to-end against
the synthetic fixture cache. Excluded from the default `pytest` run by the
existing `addopts = "-m 'not live_api'"` setting in pyproject.toml.

Run on demand with:
    pytest -m live_api tests/integration/test_notes_command_live.py

Assertions are deliberately structural (≥200 bytes, starts with `#`, valid
UTF-8, no prompt-echo strings) — content quality is not deterministically
testable. SC-002 ($0.30 cost ceiling) is checked at end.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from notetaker.cache import url_hash
from notetaker.cli import app


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "notes"
RECORDING_URL = "https://example.invalid/rec/play/synthetic-fixture-12345"


@pytest.mark.live_api
def test_real_anthropic_render_against_fixture(tmp_path, monkeypatch):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set; skipping live API test.")

    cache_root = tmp_path / "cache"
    h = url_hash(RECORDING_URL)
    cache_dir = cache_root / h
    (cache_dir / "understanding").mkdir(parents=True, exist_ok=True)
    (cache_dir / "capture").mkdir(parents=True, exist_ok=True)
    shutil.copy(
        FIXTURE_DIR / "slide_content.json",
        cache_dir / "understanding" / "slide_content.json",
    )
    (cache_dir / "meta.json").write_text(
        json.dumps({"recording_url": RECORDING_URL, "created_at": "2026-05-09T00:00:00+00:00"})
    )

    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        f"""
[cache]
cache_dir = "{cache_root}"
retention_days = 30

[logging]
log_dir = "{tmp_path / 'logs'}"
retention_days = 30

[notes]
retention_days = 365
"""
    )
    monkeypatch.setenv("NOTETAKER_CONFIG", str(cfg_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    transcript = tmp_path / "z.txt"
    shutil.copy(FIXTURE_DIR / "transcript_block.txt", transcript)

    runner = CliRunner()
    result = runner.invoke(app, ["notes", RECORDING_URL, str(transcript)])
    assert result.exit_code == 0, result.output + (result.stderr or "")

    notes_path = cache_dir / "notes" / "notes.md"
    assert notes_path.exists()
    body = notes_path.read_text(encoding="utf-8")

    # Structural invariants from contracts/notes_file.md.
    assert len(body.encode("utf-8")) >= 200, "notes file suspiciously short"
    assert body.lstrip().startswith("# "), "notes must start with a level-1 heading"
    assert body.endswith("\n"), "notes must end with a newline"
    assert "Working doc follows." not in body, "model should not echo the prompt scaffold"

    # SC-002 sanity: a 5-slide / 12-utterance toy meeting is ~4KB; should be well under $0.30.
    # Cost is reported in stdout as "cost=$X.XXXX".
    import re
    m = re.search(r"cost=\$([0-9.]+)", result.output)
    assert m is not None, f"no cost line in stdout: {result.output}"
    cost = float(m.group(1))
    assert cost < 0.30, f"cost {cost} exceeded SC-002 threshold of $0.30"
