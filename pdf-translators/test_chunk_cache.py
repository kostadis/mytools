"""Tests for chunk_cache.py + the extract/split/encode seam.

Two load-bearing claims:

1. **Split reproduction** — ``split_to_chunks`` over stored ``units`` produces
   the same chunks as the in-PDF ``build_chunks_from_*`` helpers. If it didn't,
   re-splitting from the extract cache would diverge from a fresh conversion.

2. **Round-trip identity** — serializing the structural extraction and reloading
   it, then splitting + assembling, yields *byte-identical* JSON to the direct
   in-memory path. ``assemble_adventure`` groups by ``id(spec.root)`` and walks
   the tree by ``id(node)``; the stable-key remap in chunk_cache keeps that
   identity internally consistent after a reload.
"""
from __future__ import annotations

import json

import pytest

import chunk_cache as cc
import pdf_to_5etools_v2 as v2
from pdf_utils import TocNode


META = {"short_id": "TST", "name": "Test", "output_type": "adventure",
        "page_count": 6, "source_kind": "marker"}


def _assemble(chunks, entries_by_index):
    return v2.assemble_adventure(
        name=META["name"], source=META["short_id"],
        chunk_results=[(c, entries_by_index[i]) for i, c in enumerate(chunks)],
        author="Me", is_book=False,
    ).to_dict()


class TestSplitReproduction:
    def test_lines_split_matches_build_chunks_from_markdown(self):
        """split_to_chunks(kind='lines') == build_chunks_from_markdown."""
        # A root with two children, each a slice of the markdown lines.
        a = TocNode(level=2, title="A", start_page=2, end_page=3)
        b = TocNode(level=2, title="B", start_page=4, end_page=6)
        root = TocNode(level=1, title="R", start_page=1, end_page=6,
                       children=[a, b])
        lines = [f"line {i}" for i in range(6)]

        ref = v2.build_chunks_from_markdown([root], lines)
        got = v2.split_to_chunks([root], lines, "lines")

        assert [c.body for c in got] == [c.body for c in ref]
        assert [c.is_prose_stub for c in got] == [c.is_prose_stub for c in ref]
        assert [c.target_node.title for c in got] == \
            [c.target_node.title for c in ref]

    def test_pages_body_has_page_markers(self):
        """kind='pages' reconstructs the `=== page N ===` markers verbatim."""
        node = TocNode(level=1, title="R", start_page=2, end_page=3)
        units = ["p1", "p2", "p3", "p4"]  # 1-indexed: units[1] is page 2
        body = v2._body_from_units(node, units, "pages")
        assert body == "=== page 2 ===\np2\n\n=== page 3 ===\np3"

    def test_pages_clamps_out_of_range(self):
        node = TocNode(level=1, title="R", start_page=1, end_page=9)
        units = ["only one page"]
        body = v2._body_from_units(node, units, "pages")
        assert body == "=== page 1 ===\nonly one page"


class TestExtractRoundTrip:
    def _fixture(self):
        a = TocNode(level=2, title="A", start_page=2, end_page=3)
        b = TocNode(level=2, title="B", start_page=4, end_page=6)
        root = TocNode(level=1, title="R", start_page=1, end_page=6,
                       children=[a, b])
        lines = [f"line {i}" for i in range(6)]
        return [root], lines

    def test_reload_then_split_assembles_identically(self, tmp_path):
        roots, units = self._fixture()

        direct = v2.split_to_chunks(roots, units, "lines")
        entries = {i: [f"content {i}"] for i in range(len(direct))}
        before = _assemble(direct, entries)

        p = tmp_path / "doc-extract.json"
        cc.serialize_extract(p, roots, units, "lines", META)
        roots2, units2, kind2, meta2 = cc.load_extract(p)
        assert kind2 == "lines"
        assert meta2 == META
        assert units2 == units

        reloaded = v2.split_to_chunks(roots2, units2, kind2)
        after = _assemble(reloaded, entries)

        assert before == after

    def test_reloaded_chunk_identity_is_consistent(self, tmp_path):
        roots, units = self._fixture()
        p = tmp_path / "doc-extract.json"
        cc.serialize_extract(p, roots, units, "lines", META)
        roots2, units2, kind2, _ = cc.load_extract(p)
        chunks = v2.split_to_chunks(roots2, units2, kind2)

        tree_ids = {id(n) for r in roots2 for n in r.walk()}
        # Every chunk's root/target are objects from the reloaded tree.
        assert all(id(c.root) in tree_ids for c in chunks)
        assert all(id(c.target_node) in tree_ids for c in chunks)
        # All chunks share the single reloaded root -> one section on assembly.
        assert len({id(c.root) for c in chunks}) == 1


class TestCorruptionGuards:
    def test_bad_version_raises(self, tmp_path):
        root = TocNode(level=1, title="R", start_page=1, end_page=1)
        p = tmp_path / "c.json"
        cc.serialize_extract(p, [root], ["x"], "lines", META)
        data = json.loads(p.read_text())
        data["version"] = 999
        p.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="version"):
            cc.load_extract(p)

    def test_bad_kind_on_serialize_raises(self, tmp_path):
        root = TocNode(level=1, title="R", start_page=1, end_page=1)
        with pytest.raises(ValueError, match="kind"):
            cc.serialize_extract(tmp_path / "c.json", [root], ["x"], "bogus",
                                 META)

    def test_bad_kind_on_load_raises(self, tmp_path):
        root = TocNode(level=1, title="R", start_page=1, end_page=1)
        p = tmp_path / "c.json"
        cc.serialize_extract(p, [root], ["x"], "lines", META)
        data = json.loads(p.read_text())
        data["kind"] = "bogus"
        p.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="kind"):
            cc.load_extract(p)
