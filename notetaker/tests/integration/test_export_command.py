"""End-to-end integration tests for `notetaker export <directory>` (spec 005, T022)."""

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


URL_A = "https://zoom.us/rec/play/cache-export-A"
URL_B = "https://zoom.us/rec/play/cache-export-B"
URL_C = "https://zoom.us/rec/play/cache-export-C"


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


def _seed(cache_root: Path, url: str, *, title: str, summary: str | None,
          legacy: bool = False, partial: bool = False, content: str = "# notes\n"):
    cache = Cache(cache_root, url)
    cache.initialise(meeting_title=title, recording_date="2026-04-15")
    if summary is not None and not partial:
        meta = cache.read_meta()
        assert meta is not None
        meta = meta.model_copy(update={"summary": summary})
        meta.write(cache.root / "meta.json")
    if not partial:
        cache.notes_dir_path.mkdir(parents=True, exist_ok=True)
        if legacy:
            (cache.notes_dir_path / "notes.md").write_text(content)
        else:
            name = _hr(title, summary)
            (cache.notes_dir_path / name).write_text(content)


@pytest.fixture
def env(tmp_path, monkeypatch):
    cache_root = tmp_path / "cache"
    log_root = tmp_path / "logs"
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
    return SimpleNamespace(tmp_path=tmp_path, cache_root=cache_root)


@pytest.fixture
def runner():
    return CliRunner()


def test_export_against_populated_cache(env, runner):
    _seed(env.cache_root, URL_A, title="Meeting A", summary="Summary A", content="# A\n")
    _seed(env.cache_root, URL_B, title="Meeting B", summary="Summary B", content="# B\n")
    target = env.tmp_path / "out"

    result = runner.invoke(app, ["export", str(target)])

    assert result.exit_code == 0, result.output + result.stderr
    assert "copied=2" in result.output
    assert "skipped_no_notes=0" in result.output
    assert "skipped_collision=0" in result.output
    assert (target / _hr("Meeting A", "Summary A")).read_text() == "# A\n"
    assert (target / _hr("Meeting B", "Summary B")).read_text() == "# B\n"


def test_export_against_empty_cache(env, runner):
    target = env.tmp_path / "out"
    result = runner.invoke(app, ["export", str(target)])
    assert result.exit_code == 0
    assert "copied=0" in result.output
    assert target.exists()


def test_export_creates_target_dir(env, runner):
    _seed(env.cache_root, URL_A, title="A", summary="X")
    target = env.tmp_path / "deep" / "nested" / "out"
    assert not target.exists()
    result = runner.invoke(app, ["export", str(target)])
    assert result.exit_code == 0
    assert target.exists()


def test_export_collision_skip_default(env, runner):
    _seed(env.cache_root, URL_A, title="A", summary="X", content="# fresh\n")
    target = env.tmp_path / "out"
    target.mkdir(parents=True, exist_ok=True)
    name = _hr("A", "X")
    (target / name).write_text("# stale user edits\n")

    result = runner.invoke(app, ["export", str(target)])
    assert result.exit_code == 0
    assert "skipped_collision=1" in result.output
    assert (target / name).read_text() == "# stale user edits\n"


def test_export_collision_overwrite_flag(env, runner):
    _seed(env.cache_root, URL_A, title="A", summary="X", content="# fresh\n")
    target = env.tmp_path / "out"
    target.mkdir(parents=True, exist_ok=True)
    name = _hr("A", "X")
    (target / name).write_text("# stale\n")

    result = runner.invoke(app, ["export", str(target), "--overwrite"])
    assert result.exit_code == 0
    assert "copied=1" in result.output
    assert (target / name).read_text() == "# fresh\n"


def test_export_legacy_notes_md_resolved(env, runner):
    _seed(
        env.cache_root,
        URL_A,
        title="Legacy Meeting",
        summary="Legacy Summary",
        legacy=True,
        content="# legacy content\n",
    )
    target = env.tmp_path / "out"

    result = runner.invoke(app, ["export", str(target)])

    assert result.exit_code == 0
    assert "copied=1" in result.output
    assert "legacy_resolved=1" in result.output
    expected = target / _hr("Legacy Meeting", "Legacy Summary")
    assert expected.exists()
    assert expected.read_text() == "# legacy content\n"
    # Cache copy preserved as legacy notes.md.
    cache = Cache(env.cache_root, URL_A)
    assert (cache.notes_dir_path / "notes.md").exists()


def test_export_skips_partial_entry(env, runner):
    _seed(env.cache_root, URL_A, title="Has Notes", summary="X", content="# yes\n")
    _seed(env.cache_root, URL_B, title="No Notes", summary=None, partial=True)
    target = env.tmp_path / "out"

    result = runner.invoke(app, ["export", str(target)])
    assert result.exit_code == 0
    assert "copied=1" in result.output
    assert "skipped_no_notes=1" in result.output


def test_export_idempotent(env, runner):
    _seed(env.cache_root, URL_A, title="A", summary="X")
    target = env.tmp_path / "out"

    runner.invoke(app, ["export", str(target)])
    second = runner.invoke(app, ["export", str(target)])

    assert second.exit_code == 0
    assert "copied=0" in second.output
    assert "skipped_collision=1" in second.output
