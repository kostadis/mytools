"""End-to-end integration tests for `notetaker purge` (spec 005, T027)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from notetaker.cache import Cache
from notetaker.cli import app
from notetaker.config import Config
from notetaker.contracts.recording_meta import RecordingMetaSchema
from notetaker.notes.naming import derive_notes_filename


URL_A = "https://zoom.us/rec/play/purge-A"
URL_B = "https://zoom.us/rec/play/purge-B"


def _hr(meeting: str | None, summary: str | None) -> str:
    cfg = Config()
    meta = RecordingMetaSchema(
        recording_url="https://x",
        created_at="2026-04-15T00:00:00+00:00",
        meeting_title=meeting,
        recording_date="2026-04-15",
        summary=summary,
    )
    return derive_notes_filename(
        meta,
        max_chars=cfg.notes.filename_max_chars,
        summary_max_chars=cfg.notes.summary_max_chars,
    )


def _seed(cache_root: Path, url: str, *, title: str, summary: str):
    cache = Cache(cache_root, url)
    cache.initialise(meeting_title=title, recording_date="2026-04-15")
    meta = cache.read_meta()
    assert meta is not None
    meta = meta.model_copy(update={"summary": summary})
    meta.write(cache.root / "meta.json")
    cache.notes_dir_path.mkdir(parents=True, exist_ok=True)
    (cache.notes_dir_path / _hr(title, summary)).write_text("# notes\n" + ("x" * 500))


@pytest.fixture
def env(tmp_path, monkeypatch):
    cache_root = tmp_path / "cache"
    log_root = tmp_path / "logs"
    log_root.mkdir()
    (log_root / "preserved.log").write_text("must survive")
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        f"""
[cache]
cache_dir = "{cache_root}"
retention_days = 30

[logging]
log_dir = "{log_root}"
retention_days = 30
"""
    )
    monkeypatch.setenv("NOTETAKER_CONFIG", str(cfg_path))
    return SimpleNamespace(tmp_path=tmp_path, cache_root=cache_root, log_root=log_root)


@pytest.fixture
def runner():
    return CliRunner()


def test_purge_with_yes_flag_removes_entries(env, runner):
    _seed(env.cache_root, URL_A, title="A", summary="X")
    _seed(env.cache_root, URL_B, title="B", summary="Y")

    result = runner.invoke(app, ["purge", "--yes"])
    assert result.exit_code == 0, result.output + result.stderr
    assert "entries_removed=2" in result.output
    assert "bytes_reclaimed=" in result.output

    # Cache directory itself preserved; children gone.
    assert env.cache_root.exists()
    assert list(env.cache_root.iterdir()) == []
    # Sibling logs/ untouched.
    assert (env.log_root / "preserved.log").read_text() == "must survive"


def test_purge_confirmed_via_prompt(env, runner):
    _seed(env.cache_root, URL_A, title="A", summary="X")

    result = runner.invoke(app, ["purge"], input="y\n")
    assert result.exit_code == 0, result.output + result.stderr
    assert "entries_removed=1" in result.output
    assert list(env.cache_root.iterdir()) == []


def test_purge_cancelled_via_prompt(env, runner):
    _seed(env.cache_root, URL_A, title="A", summary="X")

    result = runner.invoke(app, ["purge"], input="n\n")
    assert result.exit_code == 0
    assert "purge cancelled" in result.output
    # Entry intact.
    assert any(env.cache_root.iterdir())


def test_purge_empty_cache_is_noop(env, runner):
    env.cache_root.mkdir(parents=True, exist_ok=True)
    result = runner.invoke(app, ["purge", "--yes"])
    assert result.exit_code == 0
    assert "entries_removed=0" in result.output


def test_purge_missing_cache_is_noop(env, runner):
    # Don't create cache_root at all.
    result = runner.invoke(app, ["purge", "--yes"])
    assert result.exit_code == 0
    assert "entries_removed=0" in result.output


def test_purge_preserves_log_directory(env, runner):
    _seed(env.cache_root, URL_A, title="A", summary="X")

    runner.invoke(app, ["purge", "--yes"])

    assert env.log_root.exists()
    assert (env.log_root / "preserved.log").read_text() == "must survive"
