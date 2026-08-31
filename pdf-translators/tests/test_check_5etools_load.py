#!/usr/bin/env python3
"""Tests for lib/check_5etools_load.py — the "stuck on loading" diagnostic."""

import json

from lib.check_5etools_load import (
    check_file,
    collect_map_parent_refs,
    find_duplicate_ids,
    iter_id_nodes,
    repair_duplicate_ids,
)


def _doc(data, prop="adventureData"):
    return {
        "_meta": {"sources": [{"json": "T", "abbreviation": "T", "full": "T"}]},
        "adventure" if prop == "adventureData" else "book": [
            {"name": "T", "id": "T", "source": "T", "contents": []},
        ],
        prop: [{"id": "T", "source": "T", "data": data}],
    }


def _all_ids(doc):
    return [node["id"] for _label, data in [("", doc["adventureData"][0]["data"])]
            for node, _path in iter_id_nodes(data)]


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

class TestFindDuplicateIds:
    def test_clean_document(self):
        doc = _doc([
            {"type": "section", "name": "A", "id": "000", "entries": [
                {"type": "entries", "name": "A1", "id": "001", "entries": []},
            ]},
        ])
        assert find_duplicate_ids(doc) == []

    def test_detects_duplicate(self):
        doc = _doc([
            {"type": "section", "name": "A", "id": "000", "entries": [
                {"type": "insetReadaloud", "id": "000", "entries": ["Boxed."]},
            ]},
        ])
        dupes = find_duplicate_ids(doc)
        assert len(dupes) == 1
        eid, first, dup = dupes[0]
        assert eid == "000"
        assert first == "adventureData[0].data[0]"
        assert dup == "adventureData[0].data[0].entries[0]"

    def test_detects_duplicate_in_book_format(self):
        doc = _doc([
            {"type": "section", "name": "A", "id": "000", "entries": [
                {"type": "entries", "name": "A1", "id": "000", "entries": []},
            ]},
        ], prop="bookData")
        assert len(find_duplicate_ids(doc)) == 1

    def test_map_parent_is_a_reference_not_a_definition(self):
        # 5etools blocklists "mapParent" when building its id lookup, so an id
        # repeated there is legitimate and must not be reported.
        doc = _doc([
            {"type": "section", "name": "A", "id": "000", "entries": [
                {"type": "image", "id": "001", "href": {"type": "internal", "path": "x.webp"}},
                {"type": "image", "id": "002", "href": {"type": "internal", "path": "y.webp"},
                 "mapParent": {"id": "001"}},
            ]},
        ])
        assert find_duplicate_ids(doc) == []

    def test_non_string_ids_are_ignored(self):
        doc = _doc([{"type": "section", "name": "A", "id": 1, "entries": [
            {"type": "entries", "name": "B", "id": 1, "entries": []},
        ]}])
        assert find_duplicate_ids(doc) == []


class TestCollectMapParentRefs:
    def test_collects(self):
        doc = _doc([{"type": "section", "name": "A", "id": "000", "entries": [
            {"type": "image", "id": "002", "mapParent": {"id": "001"}},
        ]}])
        assert collect_map_parent_refs(doc) == {"001"}


# ---------------------------------------------------------------------------
# Repair
# ---------------------------------------------------------------------------

class TestRepairDuplicateIds:
    def test_first_occurrence_keeps_its_id(self):
        doc = _doc([
            {"type": "section", "name": "A", "id": "000", "entries": [
                {"type": "insetReadaloud", "id": "000", "entries": ["Boxed."]},
            ]},
        ])
        renames = repair_duplicate_ids(doc)
        data = doc["adventureData"][0]["data"]
        assert data[0]["id"] == "000"
        assert data[0]["entries"][0]["id"] != "000"
        assert len(renames) == 1
        assert renames[0][1] == "000"

    def test_result_has_no_duplicates(self):
        doc = _doc([
            {"type": "section", "name": "A", "id": "000", "entries": [
                {"type": "entries", "name": "A1", "id": "001", "entries": []},
                {"type": "insetReadaloud", "id": "001", "entries": ["x"]},
                {"type": "inset", "id": "000", "entries": ["y"]},
            ]},
        ])
        repair_duplicate_ids(doc)
        assert find_duplicate_ids(doc) == []

    def test_non_colliding_ids_are_left_alone(self):
        # Blanket renumbering would break "mapParent" linkage, so the repair
        # must only touch the nodes that actually collide.
        doc = _doc([
            {"type": "section", "name": "A", "id": "000", "entries": [
                {"type": "image", "id": "001", "mapParent": {"id": "000"}},
                {"type": "entries", "name": "A1", "id": "001", "entries": []},
            ]},
        ])
        repair_duplicate_ids(doc)
        data = doc["adventureData"][0]["data"]
        assert data[0]["id"] == "000"
        assert data[0]["entries"][0]["id"] == "001"
        assert data[0]["entries"][0]["mapParent"] == {"id": "000"}
        assert find_duplicate_ids(doc) == []

    def test_new_ids_do_not_reuse_existing_ones(self):
        doc = _doc([
            {"type": "section", "name": "A", "id": "000", "entries": [
                {"type": "entries", "name": "A1", "id": "001", "entries": []},
                {"type": "entries", "name": "A2", "id": "002", "entries": []},
                {"type": "insetReadaloud", "id": "000", "entries": ["x"]},
            ]},
        ])
        renames = repair_duplicate_ids(doc)
        assert renames[0][2] == "003"

    def test_handles_non_numeric_ids(self):
        doc = _doc([
            {"type": "section", "name": "A", "id": "41b", "entries": [
                {"type": "entries", "name": "A1", "id": "41b", "entries": []},
            ]},
        ])
        repair_duplicate_ids(doc)
        assert find_duplicate_ids(doc) == []


# ---------------------------------------------------------------------------
# CLI-level behaviour
# ---------------------------------------------------------------------------

class TestCheckFile:
    def _write(self, tmp_path, doc):
        path = tmp_path / "adventure.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path

    def test_clean_file_passes(self, tmp_path):
        path = self._write(tmp_path, _doc([
            {"type": "section", "name": "A", "id": "000", "entries": []},
        ]))
        assert check_file(path, fix=False, fivetools=None) is True

    def test_broken_file_fails_without_fix(self, tmp_path):
        path = self._write(tmp_path, _doc([
            {"type": "section", "name": "A", "id": "000", "entries": [
                {"type": "insetReadaloud", "id": "000", "entries": ["x"]},
            ]},
        ]))
        assert check_file(path, fix=False, fivetools=None) is False
        # untouched
        assert find_duplicate_ids(json.loads(path.read_text(encoding="utf-8")))

    def test_fix_repairs_and_backs_up(self, tmp_path):
        path = self._write(tmp_path, _doc([
            {"type": "section", "name": "A", "id": "000", "entries": [
                {"type": "insetReadaloud", "id": "000", "entries": ["x"]},
            ]},
        ]))
        assert check_file(path, fix=True, fivetools=None) is True

        backup = path.with_suffix(path.suffix + ".bak")
        assert backup.exists()
        assert find_duplicate_ids(json.loads(backup.read_text(encoding="utf-8")))
        assert find_duplicate_ids(json.loads(path.read_text(encoding="utf-8"))) == []

    def test_non_adventure_json_is_skipped(self, tmp_path):
        path = tmp_path / "tsconfig.json"
        path.write_text(json.dumps({"compilerOptions": {}}), encoding="utf-8")
        assert check_file(path, fix=False, fivetools=None) is True

    def test_unreadable_json_is_skipped(self, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        assert check_file(path, fix=False, fivetools=None) is True


class TestDuplicateScopeIsPerDataBlock:
    """PROBE_JS calls getEntryIdLookup(block.data) once per block, so an id
    only has to be unique inside its own block. A document-wide check reports
    a multi-block homebrew as broken when 5etools loads it fine — and --fix
    then renumbers to repair a non-problem."""

    def _two_blocks(self, prop="adventureData"):
        return {
            "_meta": {"sources": [{"json": "T"}]},
            prop: [
                {"source": "T", "data": [
                    {"type": "section", "name": "A", "id": "000",
                     "entries": [{"type": "entries", "name": "A1", "id": "001",
                                  "entries": ["x"]}]},
                ]},
                {"source": "T", "data": [
                    {"type": "section", "name": "B", "id": "000",
                     "entries": [{"type": "entries", "name": "B1", "id": "001",
                                  "entries": ["y"]}]},
                ]},
            ],
        }

    def test_same_ids_in_separate_blocks_are_not_duplicates(self):
        assert find_duplicate_ids(self._two_blocks()) == []

    def test_same_ids_across_adventure_and_book_blocks_are_fine(self):
        doc = self._two_blocks()
        doc["bookData"] = doc.pop("adventureData")[1:]
        doc["adventureData"] = [{"source": "T", "data": [
            {"type": "section", "name": "A", "id": "000", "entries": ["x"]},
        ]}]
        assert find_duplicate_ids(doc) == []

    def test_a_real_duplicate_inside_one_block_is_still_caught(self):
        doc = self._two_blocks()
        doc["adventureData"][0]["data"][0]["entries"][0]["id"] = "000"
        dupes = find_duplicate_ids(doc)
        assert [d[0] for d in dupes] == ["000"]

    def test_repair_leaves_cross_block_reuse_alone(self):
        doc = self._two_blocks()
        assert repair_duplicate_ids(doc) == []
        assert doc["adventureData"][1]["data"][0]["id"] == "000"
