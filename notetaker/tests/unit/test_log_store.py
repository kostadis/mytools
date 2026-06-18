import os
import re
import time
from pathlib import Path

import pytest

from notetaker.utils.log_store import LogStore


def test_filename_format_with_url_hash(tmp_path: Path):
    store = LogStore(tmp_path, retention_days=30)
    path = store.start_run(recording_url_hash="3f7a91c8b2d0e1f4")
    assert path.parent == tmp_path
    # Filename: <YYYYMMDDTHHMMSSZ>-<hash>.log
    assert re.fullmatch(r"\d{8}T\d{6}Z-3f7a91c8b2d0e1f4\.log", path.name)
    assert path.exists()


def test_filename_without_url_hash(tmp_path: Path):
    store = LogStore(tmp_path, retention_days=30)
    path = store.start_run(recording_url_hash=None)
    assert re.fullmatch(r"\d{8}T\d{6}Z\.log", path.name)


def test_directory_is_autocreated(tmp_path: Path):
    nested = tmp_path / "deep" / "logs"
    assert not nested.exists()
    store = LogStore(nested, retention_days=30)
    path = store.start_run(recording_url_hash="abcdef0123456789")
    assert nested.exists()
    assert path.parent == nested


def test_latest_pointer_resolves_to_run_path(tmp_path: Path):
    store = LogStore(tmp_path, retention_days=30)
    run_path = store.start_run(recording_url_hash="abcdef0123456789")
    latest = tmp_path / "latest.log"
    assert latest.is_symlink()
    # readlink may return the path verbatim as we passed it (relative or abs).
    assert Path(os.readlink(latest)).resolve() == run_path.resolve()


def test_latest_pointer_atomic_replace_on_second_run(tmp_path: Path):
    store1 = LogStore(tmp_path, retention_days=30)
    first = store1.start_run(recording_url_hash="1111111111111111")
    # Sleep briefly so the second filename's timestamp differs.
    time.sleep(1.1)
    store2 = LogStore(tmp_path, retention_days=30)
    second = store2.start_run(recording_url_hash="2222222222222222")
    assert first != second
    latest = tmp_path / "latest.log"
    assert Path(os.readlink(latest)).resolve() == second.resolve()
    # First run log file is still present.
    assert first.exists()


def test_purge_stale_zero_keeps_forever(tmp_path: Path):
    # Pre-populate an old file.
    old = tmp_path / "20200101T000000Z-deadbeefdeadbeef.log"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text("")
    os.utime(old, (0, 0))  # epoch — very old

    store = LogStore(tmp_path, retention_days=0)
    removed, kept = store.purge_stale()
    assert removed == 0
    # `kept` is reported as 0 in the disabled path; the file survives regardless.
    assert old.exists()


def test_purge_stale_removes_old_files_keeps_recent(tmp_path: Path):
    old = tmp_path / "20200101T000000Z-deadbeefdeadbeef.log"
    new = tmp_path / "20260509T120000Z-feedfacefeedface.log"
    tmp_path.mkdir(parents=True, exist_ok=True)
    old.write_text("")
    new.write_text("")
    sixty_days_ago = time.time() - 60 * 86400
    one_day_ago = time.time() - 86400
    os.utime(old, (sixty_days_ago, sixty_days_ago))
    os.utime(new, (one_day_ago, one_day_ago))

    store = LogStore(tmp_path, retention_days=30)
    removed, kept = store.purge_stale()

    assert removed == 1
    assert kept == 1
    assert not old.exists()
    assert new.exists()


def test_update_latest_pointer_atomic_replace(tmp_path: Path):
    # Two distinct targets should both be reachable via latest.log in turn,
    # without the symlink ever being missing or dangling at any observed point.
    target_a = tmp_path / "20260508T120000Z-aaaaaaaaaaaaaaaa.log"
    target_b = tmp_path / "20260509T120000Z-bbbbbbbbbbbbbbbb.log"
    target_a.write_text("a")
    target_b.write_text("b")

    store = LogStore(tmp_path, retention_days=30)
    store.update_latest_pointer(target_a)
    latest = tmp_path / "latest.log"
    assert latest.is_symlink()
    assert Path(os.readlink(latest)).resolve() == target_a.resolve()

    store.update_latest_pointer(target_b)
    assert latest.is_symlink()
    assert Path(os.readlink(latest)).resolve() == target_b.resolve()


def test_update_latest_pointer_handles_symlink_failure(tmp_path: Path, monkeypatch, capsys):
    """When os.symlink raises (e.g. on Windows without dev mode), the call
    must not propagate — the rest of the run still succeeds."""
    target = tmp_path / "20260509T120000Z-feedfacefeedface.log"
    target.write_text("")

    def boom(*args, **kwargs):
        raise OSError("symlink not supported")

    monkeypatch.setattr(os, "symlink", boom)
    store = LogStore(tmp_path, retention_days=30)
    # Must not raise.
    store.update_latest_pointer(target)
    captured = capsys.readouterr()
    assert "WARNING: cannot update latest.log" in captured.err


def test_purge_stale_skips_latest_symlink(tmp_path: Path):
    # latest.log is a symlink and must never be unlinked by purge_stale,
    # regardless of the underlying target's mtime.
    target = tmp_path / "20260509T120000Z-feedfacefeedface.log"
    target.write_text("")
    latest = tmp_path / "latest.log"
    os.symlink(target, latest)

    sixty_days_ago = time.time() - 60 * 86400
    os.utime(target, (sixty_days_ago, sixty_days_ago))

    store = LogStore(tmp_path, retention_days=30)
    removed, kept = store.purge_stale()
    # `latest.log` is a symlink so purge_stale skips it; the actual log file
    # gets purged though (mtime < cutoff). The symlink becomes dangling but
    # that's fine — the next start_run() will atomically replace it.
    assert latest.is_symlink()
    assert not target.exists()
    assert removed == 1
