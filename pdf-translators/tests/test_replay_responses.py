"""Tests for how ``--replay-responses`` resolves saved response files.

``call_claude``'s retries write their own ``{sub_cid}-response.txt`` next to
the parent chunk's — ``{cid}-tail``, ``{cid}-part0``/``-part1``, ``{cid}-fix``.
A plain ``*-response.txt`` glob counts those as chunks, so replay failed with a
count mismatch on any run where a chunk had been retried, which is exactly the
run you most want to re-parse.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import converters.pdf_to_5etools_v2 as v2
from lib.pdf_utils import TocNode


def _spec(title: str) -> v2.ChunkSpec:
    node = TocNode(level=1, title=title, start_page=1, end_page=2, children=[])
    return v2.ChunkSpec(root=node, target_node=node, is_prose_stub=False, body="x")


def _chunks(*titles: str) -> list[v2.ChunkSpec]:
    return [_spec(t) for t in titles]


def _write(d: Path, name: str, payload="[]") -> Path:
    p = d / name
    p.write_text(payload, encoding="utf-8")
    return p


class TestReplayResponseFiles:
    def test_resolves_each_chunk_by_its_own_id(self, tmp_path: Path):
        chunks = _chunks("The Crypt", "The Vault")
        _write(tmp_path, "001-the-crypt-response.txt")
        _write(tmp_path, "002-the-vault-response.txt")

        files = v2._replay_response_files(tmp_path, chunks)
        assert [p.name for p in files] == [
            "001-the-crypt-response.txt", "002-the-vault-response.txt",
        ]

    def test_ignores_retry_siblings(self, tmp_path: Path):
        chunks = _chunks("The Crypt", "The Vault")
        _write(tmp_path, "001-the-crypt-response.txt")
        _write(tmp_path, "002-the-vault-response.txt")
        # What a retried run leaves behind.
        for extra in ("001-the-crypt-tail-response.txt",
                      "001-the-crypt-fix-response.txt",
                      "002-the-vault-part0-response.txt",
                      "002-the-vault-part1-response.txt",
                      "002-the-vault-part0-tail-response.txt"):
            _write(tmp_path, extra)

        files = v2._replay_response_files(tmp_path, chunks)
        assert [p.name for p in files] == [
            "001-the-crypt-response.txt", "002-the-vault-response.txt",
        ]

    def test_orig_sidecar_is_not_counted(self, tmp_path: Path):
        # _rewrite_cached_response keeps the pre-retry text alongside.
        chunks = _chunks("The Crypt")
        _write(tmp_path, "001-the-crypt-response.txt")
        _write(tmp_path, "001-the-crypt-response.orig.txt")
        assert [p.name for p in v2._replay_response_files(tmp_path, chunks)] \
            == ["001-the-crypt-response.txt"]

    def test_section_named_like_a_retry_suffix_survives(self, tmp_path: Path):
        # "The Tail" and "Quick Fix" slugify to ids that end exactly like a
        # retry artifact; they must still be treated as real chunks.
        chunks = _chunks("The Tail", "Quick Fix")
        _write(tmp_path, "001-the-tail-response.txt")
        _write(tmp_path, "002-quick-fix-response.txt")
        assert [p.name for p in v2._replay_response_files(tmp_path, chunks)] == [
            "001-the-tail-response.txt", "002-quick-fix-response.txt",
        ]

    def test_falls_back_to_sort_order_for_batch_named_files(self, tmp_path: Path):
        # The batch path names its debug files chunk-NNNN-*; those carry no
        # chunk id, so positional mapping still applies.
        chunks = _chunks("The Crypt", "The Vault")
        _write(tmp_path, "chunk-0000-response.txt")
        _write(tmp_path, "chunk-0001-response.txt")
        assert [p.name for p in v2._replay_response_files(tmp_path, chunks)] == [
            "chunk-0000-response.txt", "chunk-0001-response.txt",
        ]

    def test_missing_chunk_is_named_in_the_error(self, tmp_path: Path):
        chunks = _chunks("The Crypt", "The Vault")
        _write(tmp_path, "001-the-crypt-response.txt")
        with pytest.raises(RuntimeError) as exc:
            v2._replay_response_files(tmp_path, chunks)
        msg = str(exc.value)
        assert "002-the-vault-response.txt" in msg
        assert "--reuse-responses" in msg

    def test_retry_siblings_alone_do_not_satisfy_the_count(self, tmp_path: Path):
        # The exact pre-fix failure: one real chunk plus its two split halves
        # used to glob to 3 files and "match" a 3-chunk run.
        chunks = _chunks("A", "B", "C")
        _write(tmp_path, "001-a-response.txt")
        _write(tmp_path, "001-a-part0-response.txt")
        _write(tmp_path, "001-a-part1-response.txt")
        with pytest.raises(RuntimeError):
            v2._replay_response_files(tmp_path, chunks)


class TestIsRetryArtifact:
    @pytest.mark.parametrize("stem", [
        "001-crypt-tail", "001-crypt-fix", "001-crypt-part0", "001-crypt-part11",
        "001-crypt-part0-tail", "001-crypt-part1-fix", "001-crypt-tail-fix",
    ])
    def test_recognises_retry_stems(self, stem):
        assert v2._is_retry_artifact(stem, {"001-crypt"})

    @pytest.mark.parametrize("stem", [
        "001-crypt", "001-the-tail", "002-quick-fix", "chunk-0000", "001-part-1",
    ])
    def test_leaves_real_ids_alone(self, stem):
        assert not v2._is_retry_artifact(
            stem, {"001-crypt", "001-the-tail", "002-quick-fix", "001-part-1"})

    def test_unknown_names_are_kept(self):
        # Nothing peels back to a known id, so it is not ours to drop.
        assert not v2._is_retry_artifact("something-else-tail", {"001-crypt"})
