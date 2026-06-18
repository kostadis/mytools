import json
import time
from pathlib import Path

import pytest

from notetaker.cache import Cache, normalise_url, url_hash


def test_url_tracking_params_stripped():
    clean = normalise_url("https://zoom.us/rec/play/abc?utm_source=email&topic=foo")
    assert "utm_source" not in clean
    assert "topic=foo" in clean


def test_same_hash_with_and_without_tracking():
    h1 = url_hash("https://zoom.us/rec/play/abc")
    h2 = url_hash("https://zoom.us/rec/play/abc?utm_campaign=test")
    assert h1 == h2


def test_different_urls_different_hashes():
    h1 = url_hash("https://zoom.us/rec/play/abc")
    h2 = url_hash("https://zoom.us/rec/play/xyz")
    assert h1 != h2


def test_cache_hit_missing_file(tmp_path):
    cache = Cache(tmp_path, "https://zoom.us/rec/play/abc")
    assert cache.is_hit("extraction", "slide_timeline.json") is False


def test_cache_hit_present_correct_version(tmp_path):
    cache = Cache(tmp_path, "https://zoom.us/rec/play/abc")
    cache.initialise()
    p = cache.artifact_path("extraction", "slide_timeline.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"schema_version": "1.0"}))
    assert cache.is_hit("extraction", "slide_timeline.json", schema_version="1.0") is True


def test_cache_hit_wrong_version(tmp_path):
    cache = Cache(tmp_path, "https://zoom.us/rec/play/abc")
    cache.initialise()
    p = cache.artifact_path("extraction", "slide_timeline.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"schema_version": "2.0"}))
    assert cache.is_hit("extraction", "slide_timeline.json", schema_version="1.0") is False


def test_force_bypasses_cache(tmp_path):
    cache = Cache(tmp_path, "https://zoom.us/rec/play/abc", force=True)
    cache.initialise()
    p = cache.artifact_path("extraction", "slide_timeline.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"schema_version": "1.0"}))
    assert cache.is_hit("extraction", "slide_timeline.json") is False


def test_purge_stale_removes_old_dirs(tmp_path):
    cache = Cache(tmp_path, "https://zoom.us/rec/play/abc")
    cache.initialise()
    meta = cache.root / "meta.json"
    # backdate meta.json to 40 days ago
    old_time = time.time() - 40 * 86400
    import os
    os.utime(meta, (old_time, old_time))

    deleted = cache.purge_stale(tmp_path, retention_days=30)
    assert deleted == 1
    assert not cache.root.exists()


def test_purge_stale_keeps_recent(tmp_path):
    cache = Cache(tmp_path, "https://zoom.us/rec/play/abc")
    cache.initialise()
    deleted = cache.purge_stale(tmp_path, retention_days=30)
    assert deleted == 0
    assert cache.root.exists()


def test_purge_stale_preserves_notes_when_cache_is_stale(tmp_path):
    """FR-018: notes/ + meta.json survive when cache is stale but notes are within retention."""
    import os

    cache = Cache(tmp_path, "https://zoom.us/rec/play/abc")
    cache.initialise()
    notes_dir = cache.notes_dir
    notes_file = notes_dir / "notes.md"
    notes_file.write_text("# Real notes\n")
    working_doc = notes_dir / "working_doc.md"
    working_doc.write_text("# Working doc\n")
    frames_dir = cache.stage_dir("capture")
    frame_file = frames_dir / "frame.jpg"
    frame_file.write_bytes(b"fake-jpeg-bytes")

    meta = cache.root / "meta.json"
    old_time = time.time() - 40 * 86400
    os.utime(meta, (old_time, old_time))

    deleted = Cache.purge_stale(tmp_path, retention_days=30, notes_retention_days=365)
    assert deleted == 0  # Cache root preserved because notes/ is not yet stale.
    assert cache.root.exists()
    assert notes_file.exists()
    assert working_doc.exists()
    assert meta.exists()
    assert not frames_dir.exists()


def test_purge_stale_removes_notes_when_notes_are_stale(tmp_path):
    """notes/ purged when older than notes_retention_days, even if cache is fresh."""
    import os

    cache = Cache(tmp_path, "https://zoom.us/rec/play/abc")
    cache.initialise()
    notes_dir = cache.notes_dir
    (notes_dir / "notes.md").write_text("# Old notes\n")

    very_old = time.time() - 400 * 86400
    os.utime(notes_dir, (very_old, very_old))

    deleted = Cache.purge_stale(tmp_path, retention_days=30, notes_retention_days=365)
    assert deleted == 0
    assert cache.root.exists()
    assert not notes_dir.exists()


def test_purge_stale_full_removal_when_both_cache_and_notes_are_stale(tmp_path):
    """When cache is stale AND notes exceed their own retention, the whole entry is removed."""
    import os

    cache = Cache(tmp_path, "https://zoom.us/rec/play/abc")
    cache.initialise()
    notes_dir = cache.notes_dir
    (notes_dir / "notes.md").write_text("# Notes\n")
    very_old = time.time() - 400 * 86400
    os.utime(notes_dir, (very_old, very_old))
    os.utime(cache.root / "meta.json", (very_old, very_old))

    deleted = Cache.purge_stale(tmp_path, retention_days=30, notes_retention_days=365)
    assert deleted == 1
    assert not cache.root.exists()


def test_purge_stale_zero_notes_retention_means_keep_notes_forever(tmp_path):
    """notes_retention_days=0 means notes never auto-expire by their own clock."""
    import os

    cache = Cache(tmp_path, "https://zoom.us/rec/play/abc")
    cache.initialise()
    notes_dir = cache.notes_dir
    (notes_dir / "notes.md").write_text("# Notes\n")
    very_old = time.time() - 400 * 86400
    os.utime(notes_dir, (very_old, very_old))

    deleted = Cache.purge_stale(tmp_path, retention_days=30, notes_retention_days=0)
    assert deleted == 0
    assert notes_dir.exists()


# ---------------- spec 005: meta.json v2 + iter_entries + notes_file_path ----------------


def test_initialise_writes_v2_meta_json(tmp_path):
    """Cache.initialise writes a meta.json that loads as RecordingMetaSchema v2."""
    from notetaker.contracts.recording_meta import (
        CURRENT_SCHEMA_VERSION,
        RecordingMetaSchema,
    )

    cache = Cache(tmp_path, "https://zoom.us/rec/play/abc")
    cache.initialise(meeting_title="Q2 Planning", recording_date="2026-04-15")

    meta_path = cache.root / "meta.json"
    meta = RecordingMetaSchema.from_path(meta_path)
    assert meta.schema_version == CURRENT_SCHEMA_VERSION
    assert meta.meeting_title == "Q2 Planning"
    assert meta.recording_date == "2026-04-15"


def test_initialise_does_not_overwrite_existing_meta(tmp_path):
    cache = Cache(tmp_path, "https://zoom.us/rec/play/abc")
    cache.initialise(meeting_title="First")
    cache.initialise(meeting_title="Second")  # Should be no-op.

    from notetaker.contracts.recording_meta import RecordingMetaSchema
    meta = RecordingMetaSchema.from_path(cache.root / "meta.json")
    assert meta.meeting_title == "First"


def test_read_meta_returns_none_when_missing(tmp_path):
    cache = Cache(tmp_path, "https://zoom.us/rec/play/abc")
    assert cache.read_meta() is None


def test_read_meta_returns_none_when_malformed(tmp_path):
    cache = Cache(tmp_path, "https://zoom.us/rec/play/abc")
    cache.initialise()
    (cache.root / "meta.json").write_text("not json")
    assert cache.read_meta() is None


def test_notes_file_path_returns_none_when_meta_missing(tmp_path):
    cache = Cache(tmp_path, "https://zoom.us/rec/play/abc")
    assert cache.notes_file_path(filename_max_chars=200, summary_max_chars=50) is None


def test_notes_file_path_derives_human_readable_name(tmp_path):
    cache = Cache(tmp_path, "https://zoom.us/rec/play/abc")
    cache.initialise(meeting_title="Q2 Sync", recording_date="2026-04-15")

    # Populate summary by reading + writing meta.
    from notetaker.contracts.recording_meta import RecordingMetaSchema
    meta = RecordingMetaSchema.from_path(cache.root / "meta.json")
    meta = meta.model_copy(update={"summary": "Roadmap"})
    meta.write(cache.root / "meta.json")

    p = cache.notes_file_path(filename_max_chars=200, summary_max_chars=50)
    assert p is not None
    assert p.name == "2026-04-15--Q2 Sync--Roadmap.md"
    # Path is correct even though the file does not yet exist.
    assert not p.exists()


def test_iter_entries_yields_valid_only(tmp_path):
    # Three valid entries.
    for i in range(3):
        c = Cache(tmp_path, f"https://zoom.us/rec/play/{i}")
        c.initialise(meeting_title=f"Meeting {i}")

    # One entry with no meta.json.
    no_meta = tmp_path / "no_meta_entry"
    no_meta.mkdir()

    # One entry with malformed meta.json.
    malformed = tmp_path / "malformed_entry"
    malformed.mkdir()
    (malformed / "meta.json").write_text("not valid json")

    entries = list(Cache.iter_entries(tmp_path))
    assert len(entries) == 3
    titles = {meta.meeting_title for _hash, meta in entries}
    assert titles == {"Meeting 0", "Meeting 1", "Meeting 2"}


def test_iter_entries_empty_root(tmp_path):
    assert list(Cache.iter_entries(tmp_path)) == []


def test_iter_entries_missing_root(tmp_path):
    assert list(Cache.iter_entries(tmp_path / "does-not-exist")) == []
