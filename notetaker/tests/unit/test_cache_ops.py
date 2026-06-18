"""Unit tests for cache_ops.export_notes and purge_cache (spec 005, T020 + T025)."""

from __future__ import annotations

from pathlib import Path

import pytest

from notetaker.cache import Cache
from notetaker.cache_ops import (
    ExportSummary,
    PurgeSummary,
    export_notes,
    purge_cache,
)
from notetaker.config import Config
from notetaker.contracts.recording_meta import RecordingMetaSchema
from notetaker.notes.naming import derive_notes_filename


def _populate_entry(
    cache_root: Path,
    url: str,
    *,
    meeting_title: str | None,
    summary: str | None,
    notes_filename: str | None = None,
    notes_text: str = "# notes\n",
) -> tuple[str, str | None]:
    """
    Build a synthetic cache entry. Returns (url_hash, on_disk_notes_filename
    or None).

    If ``notes_filename`` is None, no notes file is written (partial entry).
    """
    cache = Cache(cache_root, url)
    cache.initialise(meeting_title=meeting_title, recording_date="2026-04-15")
    if summary is not None:
        meta = cache.read_meta()
        assert meta is not None
        meta = meta.model_copy(update={"summary": summary})
        meta.write(cache.root / "meta.json")
    if notes_filename is not None:
        (cache.notes_dir_path).mkdir(parents=True, exist_ok=True)
        (cache.notes_dir_path / notes_filename).write_text(notes_text)
    return cache._hash, notes_filename


def _human_readable(meeting: str | None, summary: str | None) -> str:
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


# ---------------- export_notes ----------------


def test_export_copies_modern_and_legacy_skips_partial(tmp_path):
    cfg = Config()
    cache_root = tmp_path / "cache"
    target = tmp_path / "out"

    # (a) modern: human-readable file already on disk.
    name_a = _human_readable("Meeting A", "Summary A")
    _populate_entry(
        cache_root,
        "https://zoom.us/rec/play/A",
        meeting_title="Meeting A",
        summary="Summary A",
        notes_filename=name_a,
        notes_text="# A\n",
    )

    # (b) legacy: only notes.md present.
    _populate_entry(
        cache_root,
        "https://zoom.us/rec/play/B",
        meeting_title="Meeting B",
        summary="Summary B",
        notes_filename="notes.md",
        notes_text="# B (legacy)\n",
    )

    # (c) partial: meta.json but no notes file.
    _populate_entry(
        cache_root,
        "https://zoom.us/rec/play/C",
        meeting_title="Meeting C",
        summary=None,
        notes_filename=None,
    )

    summary = export_notes(cache_root, target, cfg)

    assert summary.copied == 2
    assert summary.skipped_no_notes == 1
    assert summary.skipped_collision == 0
    assert summary.legacy_resolved == 1

    expected_a = target / _human_readable("Meeting A", "Summary A")
    expected_b = target / _human_readable("Meeting B", "Summary B")
    assert expected_a.exists()
    assert expected_a.read_text() == "# A\n"
    assert expected_b.exists()
    assert expected_b.read_text() == "# B (legacy)\n"


def test_export_creates_target_dir_if_missing(tmp_path):
    cfg = Config()
    cache_root = tmp_path / "cache"
    target = tmp_path / "deeply" / "nested" / "out"

    _populate_entry(
        cache_root,
        "https://zoom.us/rec/play/A",
        meeting_title="A",
        summary="X",
        notes_filename=_human_readable("A", "X"),
    )

    assert not target.exists()
    summary = export_notes(cache_root, target, cfg)
    assert target.exists()
    assert summary.copied == 1


def test_export_preserves_cache_originals(tmp_path):
    cfg = Config()
    cache_root = tmp_path / "cache"
    target = tmp_path / "out"

    name = _human_readable("A", "X")
    _populate_entry(
        cache_root,
        "https://zoom.us/rec/play/A",
        meeting_title="A",
        summary="X",
        notes_filename=name,
    )

    export_notes(cache_root, target, cfg)

    # Cache copy is intact.
    cache = Cache(cache_root, "https://zoom.us/rec/play/A")
    assert (cache.notes_dir_path / name).exists()


def test_export_skips_collision_without_overwrite(tmp_path):
    cfg = Config()
    cache_root = tmp_path / "cache"
    target = tmp_path / "out"

    name = _human_readable("A", "X")
    _populate_entry(
        cache_root,
        "https://zoom.us/rec/play/A",
        meeting_title="A",
        summary="X",
        notes_filename=name,
        notes_text="# A v2\n",
    )

    # Pre-populate the destination with different content.
    target.mkdir(parents=True, exist_ok=True)
    (target / name).write_text("# preexisting user edits\n")

    summary = export_notes(cache_root, target, cfg)

    assert summary.copied == 0
    assert summary.skipped_collision == 1
    # Pre-existing file untouched.
    assert (target / name).read_text() == "# preexisting user edits\n"


def test_export_overwrites_when_flag_set(tmp_path):
    cfg = Config()
    cache_root = tmp_path / "cache"
    target = tmp_path / "out"

    name = _human_readable("A", "X")
    _populate_entry(
        cache_root,
        "https://zoom.us/rec/play/A",
        meeting_title="A",
        summary="X",
        notes_filename=name,
        notes_text="# fresh\n",
    )

    target.mkdir(parents=True, exist_ok=True)
    (target / name).write_text("# stale\n")

    summary = export_notes(cache_root, target, cfg, overwrite=True)

    assert summary.copied == 1
    assert summary.skipped_collision == 0
    assert (target / name).read_text() == "# fresh\n"


def test_export_idempotent_in_steady_state(tmp_path):
    cfg = Config()
    cache_root = tmp_path / "cache"
    target = tmp_path / "out"

    name = _human_readable("A", "X")
    _populate_entry(
        cache_root,
        "https://zoom.us/rec/play/A",
        meeting_title="A",
        summary="X",
        notes_filename=name,
    )

    first = export_notes(cache_root, target, cfg)
    second = export_notes(cache_root, target, cfg)

    assert first.copied == 1
    assert second.copied == 0
    assert second.skipped_collision == 1


def test_export_against_empty_cache(tmp_path):
    cfg = Config()
    summary = export_notes(tmp_path / "missing-cache", tmp_path / "out", cfg)
    assert summary.copied == 0
    assert summary.skipped_no_notes == 0


# ---------------- purge_cache ----------------


def test_purge_confirmed_removes_all_entries(tmp_path):
    cfg = Config()
    cache_root = tmp_path / "cache"

    # Populate two entries.
    for i in range(2):
        _populate_entry(
            cache_root,
            f"https://zoom.us/rec/play/{i}",
            meeting_title=f"M{i}",
            summary=f"S{i}",
            notes_filename=_human_readable(f"M{i}", f"S{i}"),
            notes_text="x" * 1000,
        )

    # Sibling logs/ directory next to cache: must survive.
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "run.log").write_text("preserve me")

    summary = purge_cache(cache_root, confirmed=True)

    assert summary.cancelled is False
    assert summary.entries_removed == 2
    assert summary.bytes_reclaimed > 0
    # Cache root itself preserved; entries gone.
    assert cache_root.exists()
    assert list(cache_root.iterdir()) == []
    # logs/ untouched.
    assert (logs_dir / "run.log").read_text() == "preserve me"


def test_purge_unconfirmed_is_noop(tmp_path):
    cfg = Config()
    cache_root = tmp_path / "cache"
    _populate_entry(
        cache_root,
        "https://zoom.us/rec/play/A",
        meeting_title="A",
        summary="X",
        notes_filename=_human_readable("A", "X"),
    )

    summary = purge_cache(cache_root, confirmed=False)

    assert summary.cancelled is True
    assert summary.entries_removed == 0
    # Entry intact.
    assert any(cache_root.iterdir())


def test_purge_missing_cache_root_is_noop(tmp_path):
    cfg = Config()
    summary = purge_cache(tmp_path / "does-not-exist", confirmed=True)
    assert summary.entries_removed == 0
    assert summary.bytes_reclaimed == 0
    assert summary.cancelled is False


def test_purge_preserves_cache_root_directory(tmp_path):
    cfg = Config()
    cache_root = tmp_path / "cache"
    _populate_entry(
        cache_root,
        "https://zoom.us/rec/play/A",
        meeting_title="A",
        summary="X",
        notes_filename=_human_readable("A", "X"),
    )

    purge_cache(cache_root, confirmed=True)

    # Directory itself stays — only its children removed.
    assert cache_root.exists()
    assert cache_root.is_dir()
