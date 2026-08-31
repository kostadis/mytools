"""Tests for the saved-response cache that ``--reuse-responses`` reads.

The cache file is written when the *first* provider response lands, before
``call_claude``'s recovery paths run. If it is left at that first response,
resuming a run silently discards every repair the original run made — a
corrected ``{@tag}``, a recovered ``max_tokens`` tail, a rebuilt malformed
chunk. These tests pin the cache to the value ``call_claude`` actually
returned.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import lib.claude_api as _api


class FakeBackend:
    """Backend stub returning a scripted list of ``(text, stop_reason)``."""

    kind = "fake"
    supports_batch = False
    anthropic_client = None

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls: list[str] = []

    def complete(self, system, user, model, max_tokens):
        self.calls.append(user)
        if not self._responses:
            raise AssertionError("FakeBackend ran out of scripted responses")
        return self._responses.pop(0)


def _entries(text: str) -> list[dict]:
    return [{"type": "entries", "name": "Room 1", "entries": [text]}]


def _json(text: str) -> str:
    return json.dumps(_entries(text))


def _call(backend, debug_dir, chunk_text="body text"):
    return _api.call_claude(
        backend, chunk_text, "test-model", "SYSTEM", False,
        debug_dir=debug_dir, chunk_id="007-throne-room",
    )


CACHED = "007-throne-room-response.txt"
ORIGINAL = "007-throne-room-response.orig.txt"


class TestCacheReflectsFinalResult:
    def test_clean_response_leaves_the_raw_cache_untouched(self, tmp_path: Path):
        raw = _json("nothing wrong here")
        backend = FakeBackend((raw, "stop"))
        result = _call(backend, tmp_path)

        assert result == _entries("nothing wrong here")
        assert (tmp_path / CACHED).read_text(encoding="utf-8") == raw
        assert not (tmp_path / ORIGINAL).exists()

    def test_tag_fix_retry_is_written_back_to_the_cache(self, tmp_path: Path):
        backend = FakeBackend(
            (_json("read the {@scroll fireball}"), "stop"),
            (_json("read the {@item scroll of fireball}"), "stop"),
        )
        result = _call(backend, tmp_path)

        assert result == _entries("read the {@item scroll of fireball}")
        cached = json.loads((tmp_path / CACHED).read_text(encoding="utf-8"))
        assert cached == result, "cache must hold the corrected entries"
        assert "{@scroll" not in (tmp_path / CACHED).read_text(encoding="utf-8")

    def test_the_pre_retry_response_is_kept_alongside(self, tmp_path: Path):
        backend = FakeBackend(
            (_json("read the {@scroll fireball}"), "stop"),
            (_json("read the {@item scroll of fireball}"), "stop"),
        )
        _call(backend, tmp_path)
        assert "{@scroll fireball}" in (tmp_path / ORIGINAL).read_text(encoding="utf-8")

    def test_resuming_after_a_tag_fix_gets_the_corrected_entries(self, tmp_path: Path):
        """The whole point: a resume must not reintroduce the bad tag."""
        backend = FakeBackend(
            (_json("read the {@scroll fireball}"), "stop"),
            (_json("read the {@item scroll of fireball}"), "stop"),
        )
        _call(backend, tmp_path)

        # What --reuse-responses does on the next run.
        raw = (tmp_path / CACHED).read_text(encoding="utf-8")
        reused, ok = _api._parse_claude_response(
            raw, False, debug_dir=None, chunk_id="007-throne-room", from_cache=True,
        )
        assert ok
        assert reused == _entries("read the {@item scroll of fireball}")
        assert _api.validate_entries(reused, "c") == []

    def test_rejected_tag_retry_leaves_the_cache_alone(self, tmp_path: Path):
        # A retry that changes the entry shape is rejected, so nothing was
        # repaired and there is nothing to write back.
        raw = _json("read the {@scroll fireball}")
        backend = FakeBackend(
            (raw, "stop"),
            (json.dumps(_entries("a") + _entries("b")), "stop"),
        )
        result = _call(backend, tmp_path)

        assert result == _entries("read the {@scroll fireball}")
        assert (tmp_path / CACHED).read_text(encoding="utf-8") == raw
        assert not (tmp_path / ORIGINAL).exists()

    def test_max_tokens_tail_recovery_is_written_back(self, tmp_path: Path):
        backend = FakeBackend(
            (_json("first half"), "max_tokens"),
            (_json("recovered tail"), "stop"),
        )
        result = _call(backend, tmp_path, chunk_text="a" * 200 + "\n--- Page 2\n" + "b" * 200)

        assert len(result) == 2
        cached = json.loads((tmp_path / CACHED).read_text(encoding="utf-8"))
        assert cached == result, "cache must include the recovered tail"

    def test_split_retry_result_is_written_back(self, tmp_path: Path):
        backend = FakeBackend(
            ("[{unparseable", "stop"),
            (_json("first half"), "stop"),
            (_json("second half"), "stop"),
        )
        result = _call(backend, tmp_path, chunk_text="a" * 100 + "\n--- Page 2\n" + "b" * 100)

        assert len(result) == 2
        cached = json.loads((tmp_path / CACHED).read_text(encoding="utf-8"))
        assert cached == result

    def test_parsed_json_debug_file_tracks_the_cache(self, tmp_path: Path):
        backend = FakeBackend(
            (_json("read the {@scroll fireball}"), "stop"),
            (_json("read the {@item scroll of fireball}"), "stop"),
        )
        result = _call(backend, tmp_path)
        parsed = json.loads(
            (tmp_path / "007-throne-room-parsed.json").read_text(encoding="utf-8")
        )
        assert parsed == result

    def test_preserved_original_is_invisible_to_the_replay_glob(self, tmp_path: Path):
        """--replay-responses counts ``*-response.txt`` and must not see it."""
        backend = FakeBackend(
            (_json("read the {@scroll fireball}"), "stop"),
            (_json("read the {@item scroll of fireball}"), "stop"),
        )
        _call(backend, tmp_path)
        names = {p.name for p in tmp_path.glob("*-response.txt")}
        assert CACHED in names
        assert ORIGINAL not in names

    def test_no_debug_dir_means_no_cache_write(self, tmp_path: Path):
        backend = FakeBackend(
            (_json("read the {@scroll fireball}"), "stop"),
            (_json("read the {@item scroll of fireball}"), "stop"),
        )
        result = _api.call_claude(
            backend, "body", "test-model", "SYSTEM", False,
            debug_dir=None, chunk_id="007-throne-room",
        )
        assert result == _entries("read the {@item scroll of fireball}")
        assert list(tmp_path.iterdir()) == []


class TestStaleCacheWarning:
    def test_cached_response_with_unknown_tags_is_flagged(self, capsys):
        _api._parse_claude_response(
            _json("read the {@scroll fireball}"), False,
            debug_dir=None, chunk_id="007-throne-room", from_cache=True,
        )
        out = capsys.readouterr().out
        assert "[STALE-CACHE]" in out
        assert "validate_tags.py" in out

    def test_clean_cached_response_is_silent(self, capsys):
        _api._parse_claude_response(
            _json("all good"), False,
            debug_dir=None, chunk_id="007-throne-room", from_cache=True,
        )
        assert "[STALE-CACHE]" not in capsys.readouterr().out

    def test_a_live_response_is_never_flagged_as_stale(self, capsys):
        _api._parse_claude_response(
            _json("read the {@scroll fireball}"), False,
            debug_dir=None, chunk_id="007-throne-room",
        )
        assert "[STALE-CACHE]" not in capsys.readouterr().out

    def test_brace_repaired_cached_response_is_also_flagged(self, capsys):
        # A response that only parses after _repair_doubled_braces must not
        # skip the stale-tag check on its way out.
        doubled = '[{{"type": "entries", "name": "Room 1", ' \
                  '"entries": ["read the {@scroll fireball}"]}}]'
        result, ok = _api._parse_claude_response(
            doubled, False, debug_dir=None,
            chunk_id="007-throne-room", from_cache=True,
        )
        assert ok and result == _entries("read the {@scroll fireball}")
        out = capsys.readouterr().out
        assert "[REPAIR]" in out
        assert "[STALE-CACHE]" in out
