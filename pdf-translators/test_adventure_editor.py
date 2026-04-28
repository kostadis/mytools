#!/usr/bin/env python3
"""Tests for adventure_editor.py — server-side logic and API routes.

Run:
    pytest test_adventure_editor.py -v
"""

import copy
import json
import os
import tempfile
from pathlib import Path

import pytest

import adventure_editor as ae
import fix_adventure_json as _fix


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_adventure(tmp_path):
    """Create a minimal valid adventure JSON file."""
    data = {
        "adventure": [{
            "name": "Test Adventure",
            "id": "TEST",
            "contents": [
                {"name": "Chapter 1", "headers": ["Room A", "Room B"]},
                {"name": "Chapter 2", "headers": ["Room C"]},
            ],
        }],
        "adventureData": [{
            "id": "TEST",
            "data": [
                {
                    "type": "section",
                    "name": "Chapter 1",
                    "id": "000",
                    "entries": [
                        "Intro paragraph.",
                        {
                            "type": "entries",
                            "name": "Room A",
                            "id": "001",
                            "entries": [
                                "Room A description.",
                                {
                                    "type": "inset",
                                    "name": "Sidebar",
                                    "id": "002",
                                    "entries": ["Sidebar text."],
                                },
                            ],
                        },
                        {
                            "type": "entries",
                            "name": "Room B",
                            "id": "003",
                            "entries": ["Room B description."],
                        },
                    ],
                },
                {
                    "type": "section",
                    "name": "Chapter 2",
                    "id": "004",
                    "entries": [
                        {
                            "type": "entries",
                            "name": "Room C",
                            "id": "005",
                            "entries": [
                                "Room C description.",
                                {
                                    "type": "table",
                                    "colLabels": ["Roll", "Result"],
                                    "colStyles": ["", ""],
                                    "rows": [["1", "Nothing"], ["2", "Treasure"]],
                                },
                            ],
                        },
                    ],
                },
            ],
        }],
    }
    p = tmp_path / "adventure-test.json"
    p.write_text(json.dumps(data, indent="\t", ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def app_client(sample_adventure):
    """Flask test client with a loaded adventure."""
    ae.app.config["TESTING"] = True
    ae._sessions.clear()
    with ae.app.test_client() as client:
        # Load the adventure
        resp = client.post("/api/load", json={"path": str(sample_adventure)})
        assert resp.status_code == 200
        yield client, str(sample_adventure)
    ae._sessions.clear()


# ---------------------------------------------------------------------------
# Server-side: load_adventure
# ---------------------------------------------------------------------------

class TestLoadAdventure:
    def test_load_valid_adventure(self, sample_adventure):
        sess = ae.load_adventure(sample_adventure)
        assert sess["index_key"] == "adventure"
        assert sess["data_key"] == "adventureData"
        assert len(sess["data"]) == 2
        assert sess["data"][0]["name"] == "Chapter 1"
        assert sess["data"][1]["name"] == "Chapter 2"

    def test_load_preserves_nested_structure(self, sample_adventure):
        sess = ae.load_adventure(sample_adventure)
        ch1 = sess["data"][0]
        assert ch1["entries"][0] == "Intro paragraph."
        assert ch1["entries"][1]["type"] == "entries"
        assert ch1["entries"][1]["name"] == "Room A"
        assert ch1["entries"][1]["entries"][1]["type"] == "inset"

    def test_load_invalid_json_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text('{"foo": "bar"}', encoding="utf-8")
        with pytest.raises(ValueError, match="Not a valid"):
            ae.load_adventure(p)

    def test_load_book_format(self, tmp_path):
        data = {
            "book": [{"name": "Test Book", "id": "TB", "contents": []}],
            "bookData": [{"id": "TB", "data": [
                {"type": "section", "name": "Ch1", "entries": []},
            ]}],
        }
        p = tmp_path / "book-test.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        sess = ae.load_adventure(p)
        assert sess["index_key"] == "book"
        assert len(sess["data"]) == 1


# ---------------------------------------------------------------------------
# Server-side: save_adventure (ID + TOC rebuild)
# ---------------------------------------------------------------------------

class TestSaveAdventure:
    def test_save_rebuilds_ids(self, sample_adventure):
        sess = ae.load_adventure(sample_adventure)
        # Strip all IDs
        _fix.reset_ids()
        def strip_ids(entries):
            for e in entries:
                if isinstance(e, dict):
                    e.pop("id", None)
                    if "entries" in e:
                        strip_ids(e["entries"])
        strip_ids(sess["data"])
        # Save should reassign
        ae.save_adventure(sess, sess["data"])
        assert sess["data"][0].get("id") is not None
        assert sess["data"][0]["entries"][1].get("id") is not None

    def test_save_rebuilds_toc(self, sample_adventure):
        sess = ae.load_adventure(sample_adventure)
        # Rename a section
        sess["data"][0]["name"] = "Renamed Chapter"
        ae.save_adventure(sess, sess["data"])
        toc = sess["meta"]["contents"]
        assert toc[0]["name"] == "Renamed Chapter"
        assert toc[1]["name"] == "Chapter 2"

    def test_save_toc_headers(self, sample_adventure):
        sess = ae.load_adventure(sample_adventure)
        ae.save_adventure(sess, sess["data"])
        toc = sess["meta"]["contents"]
        # Chapter 1 has Room A and Room B as headers
        assert "Room A" in toc[0]["headers"]
        assert "Room B" in toc[0]["headers"]
        # Chapter 2 has Room C
        assert "Room C" in toc[1]["headers"]

    def test_save_promotes_non_section_top_level(self, sample_adventure):
        sess = ae.load_adventure(sample_adventure)
        # Inject a non-section entry at top level
        sess["data"].append({"type": "entries", "name": "Orphan", "entries": ["text"]})
        warnings = ae.save_adventure(sess, sess["data"])
        assert len(warnings) == 1
        assert "promoted to 'section'" in warnings[0]
        assert sess["data"][-1]["type"] == "section"

    def test_save_wraps_bare_string(self, sample_adventure):
        sess = ae.load_adventure(sample_adventure)
        sess["data"].append("bare string at top level")
        warnings = ae.save_adventure(sess, sess["data"])
        assert len(warnings) == 1
        assert "wrapped in a section" in warnings[0]
        assert sess["data"][-1]["type"] == "section"
        assert sess["data"][-1]["entries"] == ["bare string at top level"]

    def test_save_toc_aligned_after_fix(self, sample_adventure):
        sess = ae.load_adventure(sample_adventure)
        # Add non-section — should be auto-promoted
        sess["data"].append({"type": "entries", "name": "Extra", "entries": []})
        ae.save_adventure(sess, sess["data"])
        toc = sess["meta"]["contents"]
        data = sess["data"]
        # TOC and data should be aligned
        assert len(toc) == len(data)
        for i, entry in enumerate(data):
            assert entry["type"] == "section"
            assert toc[i]["name"] == entry["name"]


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

class TestAPIRoutes:
    def test_index_returns_html(self, app_client):
        client, path = app_client
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Adventure Editor" in resp.data

    def test_files_returns_list(self, app_client):
        client, path = app_client
        resp = client.get("/api/files")
        assert resp.status_code == 200
        files = resp.get_json()
        assert isinstance(files, list)

    def test_load_returns_data(self, app_client):
        client, path = app_client
        resp = client.post("/api/load", json={"path": path})
        result = resp.get_json()
        assert "data" in result
        assert len(result["data"]) == 2
        assert result["meta"]["name"] == "Test Adventure"

    def test_load_returns_undolog(self, app_client):
        client, path = app_client
        resp = client.post("/api/load", json={"path": path})
        result = resp.get_json()
        assert "undolog" in result
        assert result["undolog"]["position"] == -1
        assert result["undolog"]["entries"] == []

    def test_load_nonexistent_file(self, app_client):
        client, path = app_client
        resp = client.post("/api/load", json={"path": "/nonexistent.json"})
        assert resp.status_code == 400

    def test_save_writes_file(self, app_client):
        client, path = app_client
        # Modify data
        resp = client.post("/api/load", json={"path": path})
        data = resp.get_json()["data"]
        data[0]["name"] = "Modified Chapter"
        resp = client.post("/api/save", json={"path": path, "data": data})
        result = resp.get_json()
        assert result["ok"] is True
        assert result["sections"] == 2
        # Verify on disk
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["adventureData"][0]["data"][0]["name"] == "Modified Chapter"

    def test_save_creates_backup(self, app_client):
        client, path = app_client
        resp = client.post("/api/load", json={"path": path})
        data = resp.get_json()["data"]
        resp = client.post("/api/save", json={"path": path, "data": data})
        assert resp.get_json()["ok"] is True
        bak = Path(path).with_suffix(".bak")
        assert bak.exists()


# ---------------------------------------------------------------------------
# Code quality: no pk in onclick attributes
# ---------------------------------------------------------------------------

class TestNoPkInOnclick:
    """Verify that no onclick attributes interpolate JSON path keys.

    Path keys like [0,"entries",2] break HTML attributes because of the
    double quotes. This was a recurring bug — this test catches regressions.
    """

    def test_html_has_no_pk_in_onclick(self, app_client):
        client, path = app_client
        resp = client.get("/")
        html = resp.data.decode("utf-8")
        # Extract all JS source (between <script> tags)
        import re
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        js = "\n".join(scripts)
        # Look for the dangerous pattern: onclick="someFunc('${pk}')"
        # This would appear in the JS template literals
        dangerous = re.findall(r'''onclick="[^"]*\$\{pk\}''', js)
        assert dangerous == [], (
            f"Found onclick attributes interpolating pk — this breaks on nested paths. "
            f"Use addEventListener instead. Matches: {dangerous}"
        )


# ---------------------------------------------------------------------------
# Undo log API
# ---------------------------------------------------------------------------

class TestUndoLog:
    def test_push_and_list(self, app_client):
        client, path = app_client
        snapshot = [{"type": "section", "name": "Snap", "entries": []}]
        resp = client.post("/api/undolog/push", json={
            "path": path, "action": "test action", "data": snapshot,
        })
        result = resp.get_json()
        assert result["ok"] is True
        assert result["position"] == 0
        assert result["total"] == 1
        # List
        resp = client.get(f"/api/undolog?path={path}")
        result = resp.get_json()
        assert len(result["entries"]) == 1
        assert result["entries"][0]["action"] == "test action"
        assert result["position"] == 0

    def test_undo(self, app_client):
        client, path = app_client
        snap1 = [{"type": "section", "name": "Before", "entries": []}]
        client.post("/api/undolog/push", json={"path": path, "action": "edit", "data": snap1})
        resp = client.post("/api/undolog/undo", json={"path": path})
        result = resp.get_json()
        assert result["ok"] is True
        assert result["data"][0]["name"] == "Before"
        assert result["position"] == -1

    def test_undo_empty_returns_error(self, app_client):
        client, path = app_client
        resp = client.post("/api/undolog/undo", json={"path": path})
        assert resp.status_code == 400

    def test_redo(self, app_client):
        client, path = app_client
        snap1 = [{"type": "section", "name": "State1", "entries": []}]
        snap2 = [{"type": "section", "name": "State2", "entries": []}]
        client.post("/api/undolog/push", json={"path": path, "action": "edit1", "data": snap1})
        client.post("/api/undolog/push", json={"path": path, "action": "edit2", "data": snap2})
        # Undo back to edit1
        client.post("/api/undolog/undo", json={"path": path})
        # Redo to edit2
        resp = client.post("/api/undolog/redo", json={"path": path})
        result = resp.get_json()
        assert result["ok"] is True
        assert result["data"][0]["name"] == "State2"

    def test_push_truncates_redo(self, app_client):
        client, path = app_client
        for i in range(3):
            client.post("/api/undolog/push", json={
                "path": path, "action": f"edit{i}",
                "data": [{"type": "section", "name": f"S{i}", "entries": []}],
            })
        # Undo twice
        client.post("/api/undolog/undo", json={"path": path})
        client.post("/api/undolog/undo", json={"path": path})
        # Push new — should truncate redo history
        client.post("/api/undolog/push", json={
            "path": path, "action": "new",
            "data": [{"type": "section", "name": "New", "entries": []}],
        })
        resp = client.get(f"/api/undolog?path={path}")
        result = resp.get_json()
        # Should have entries 0 (edit0), 1 (new) — edit1 and edit2 truncated
        assert len(result["entries"]) == 2
        assert result["entries"][1]["action"] == "new"

    def test_jump(self, app_client):
        client, path = app_client
        for i in range(5):
            client.post("/api/undolog/push", json={
                "path": path, "action": f"edit{i}",
                "data": [{"type": "section", "name": f"S{i}", "entries": []}],
            })
        resp = client.post("/api/undolog/jump", json={"path": path, "idx": 2})
        result = resp.get_json()
        assert result["ok"] is True
        assert result["data"][0]["name"] == "S2"
        assert result["position"] == 2

    def test_undolog_persisted_to_disk(self, app_client):
        client, path = app_client
        client.post("/api/undolog/push", json={
            "path": path, "action": "persist test",
            "data": [{"type": "section", "name": "X", "entries": []}],
        })
        log_path = ae._undolog_path(path)
        assert log_path.exists()
        with open(log_path, encoding="utf-8") as f:
            log = json.load(f)
        assert len(log["entries"]) == 1
        assert log["entries"][0]["action"] == "persist test"

    def test_undolog_loaded_on_file_load(self, app_client):
        client, path = app_client
        # Push some entries
        client.post("/api/undolog/push", json={
            "path": path, "action": "before reload",
            "data": [{"type": "section", "name": "BR", "entries": []}],
        })
        # Re-load the file
        resp = client.post("/api/load", json={"path": path})
        result = resp.get_json()
        assert result["undolog"]["entries"][0]["action"] == "before reload"
        assert result["undolog"]["position"] == 0


# ---------------------------------------------------------------------------
# JS logic tests — pure data operations (no DOM)
# These test the Python equivalents of the JS path-manipulation functions
# to verify promote/demote/move correctness.
# ---------------------------------------------------------------------------

def _get_by_path(data, path):
    obj = data
    for seg in path:
        obj = obj[seg]
    return obj


def _get_parent_array(data, path):
    if len(path) == 1:
        return data
    return _get_by_path(data, path[:-1])


def _make_test_data():
    """Create a test data[] array matching what the JS state would hold."""
    return [
        {
            "type": "section",
            "name": "Chapter 1",
            "entries": [
                "Para 1",
                {"type": "entries", "name": "Room A", "entries": ["Room A text."]},
                {"type": "entries", "name": "Room B", "entries": ["Room B text."]},
            ],
        },
        {
            "type": "section",
            "name": "Chapter 2",
            "entries": [
                {"type": "entries", "name": "Room C", "entries": ["Room C text."]},
            ],
        },
    ]


class TestMoveNode:
    def test_move_top_level_section_down(self):
        data = _make_test_data()
        # Move section at [0] down to [1]
        parent = data  # top level
        parent[0], parent[1] = parent[1], parent[0]
        assert data[0]["name"] == "Chapter 2"
        assert data[1]["name"] == "Chapter 1"

    def test_move_top_level_section_up(self):
        data = _make_test_data()
        parent = data
        parent[0], parent[1] = parent[1], parent[0]
        # Now move it back
        parent[0], parent[1] = parent[1], parent[0]
        assert data[0]["name"] == "Chapter 1"

    def test_move_nested_entry_down(self):
        data = _make_test_data()
        # Move Room A [0, "entries", 1] down to [0, "entries", 2]
        entries = data[0]["entries"]
        entries[1], entries[2] = entries[2], entries[1]
        assert data[0]["entries"][1]["name"] == "Room B"
        assert data[0]["entries"][2]["name"] == "Room A"

    def test_move_at_boundary_does_nothing(self):
        data = _make_test_data()
        # Try to move [1] down — already at end
        idx = 1
        new_idx = idx + 1
        assert new_idx >= len(data)  # Can't move


class TestPromoteNode:
    """Test the promote (outdent) operation — Python equivalent of JS promoteNode."""

    def _promote(self, data, path):
        """Python implementation of promoteNode logic."""
        if len(path) <= 1:
            return False
        if len(path) < 3:
            return False

        idx = path[-1]
        children_key = path[-2]  # "entries" or "items"
        parent_obj_path = path[:-2]

        parent_array = _get_by_path(data, path[:-1]) if len(path) > 1 else data
        node = parent_array.pop(idx)

        if len(parent_obj_path) == 0:
            parent_array.insert(idx, node)  # put back
            return False

        grandparent_array = _get_parent_array(data, parent_obj_path)
        parent_idx = parent_obj_path[-1]
        grandparent_array.insert(parent_idx + 1, node)
        return True

    def test_promote_nested_entry_to_section_level(self):
        data = _make_test_data()
        # Promote Room B at [0, "entries", 2] up to section level
        result = self._promote(data, [0, "entries", 2])
        assert result is True
        # Room B should now be at data[1], Chapter 2 at data[2]
        assert data[1]["name"] == "Room B"
        assert data[2]["name"] == "Chapter 2"
        # Chapter 1 should now only have Para 1 + Room A
        assert len(data[0]["entries"]) == 2

    def test_promote_top_level_returns_false(self):
        data = _make_test_data()
        result = self._promote(data, [0])
        assert result is False

    def test_promote_deeply_nested(self):
        data = _make_test_data()
        # Add a deeper level: Room A > SubRoom
        data[0]["entries"][1]["entries"].append(
            {"type": "entries", "name": "SubRoom", "entries": []}
        )
        # Promote SubRoom at [0, "entries", 1, "entries", 1] to Room level
        result = self._promote(data, [0, "entries", 1, "entries", 1])
        assert result is True
        # SubRoom should now be at [0, "entries", 2], Room B at [0, "entries", 3]
        assert data[0]["entries"][2]["name"] == "SubRoom"
        assert data[0]["entries"][3]["name"] == "Room B"


class TestDemoteNode:
    """Test the demote (indent) operation — Python equivalent of JS demoteNode."""

    def _demote(self, data, path):
        """Python implementation of demoteNode logic."""
        idx = path[-1]
        if idx == 0:
            return False

        parent = _get_parent_array(data, path)
        prev_sibling = parent[idx - 1]

        if isinstance(prev_sibling, str):
            return False

        sib_child_key = "items" if prev_sibling.get("type") == "list" else "entries"
        if sib_child_key not in prev_sibling:
            prev_sibling[sib_child_key] = []

        node = parent.pop(idx)
        prev_sibling[sib_child_key].append(node)
        return True

    def test_demote_entry_into_sibling(self):
        data = _make_test_data()
        # Demote Room B [0, "entries", 2] into Room A [0, "entries", 1]
        result = self._demote(data, [0, "entries", 2])
        assert result is True
        # Room B should now be inside Room A's entries
        room_a = data[0]["entries"][1]
        assert room_a["name"] == "Room A"
        assert room_a["entries"][-1]["name"] == "Room B"
        # Chapter 1 entries should be: Para 1, Room A (with Room B inside)
        assert len(data[0]["entries"]) == 2

    def test_demote_first_entry_returns_false(self):
        data = _make_test_data()
        # Can't demote the first entry (no preceding sibling)
        result = self._demote(data, [0, "entries", 0])
        assert result is False

    def test_demote_into_string_returns_false(self):
        data = _make_test_data()
        # Entry at [0, "entries", 1] (Room A) — preceding sibling is "Para 1" (a string)
        result = self._demote(data, [0, "entries", 1])
        assert result is False

    def test_demote_top_level_section(self):
        data = _make_test_data()
        # Demote Chapter 2 [1] into Chapter 1 [0]
        result = self._demote(data, [1])
        assert result is True
        assert len(data) == 1
        assert data[0]["entries"][-1]["name"] == "Chapter 2"

    def test_promote_then_demote_roundtrip(self):
        data = _make_test_data()
        original = copy.deepcopy(data)
        # Promote Room B out of Chapter 1
        entries = data[0]["entries"]
        room_b = entries.pop(2)
        data.insert(1, room_b)
        assert data[1]["name"] == "Room B"
        # Demote Room B back into Chapter 1
        node = data.pop(1)
        data[0]["entries"].append(node)
        assert data[0]["entries"][-1]["name"] == "Room B"
        # Structure should match original (entry order may differ)
        assert len(data) == len(original)
        assert len(data[0]["entries"]) == len(original[0]["entries"])


# ---------------------------------------------------------------------------
# Dissolve node
# ---------------------------------------------------------------------------

class TestDissolveNode:
    """Test dissolving a node — removing it but keeping its children in place."""

    def _dissolve(self, data, path):
        """Python implementation of dissolveNode logic."""
        node = _get_by_path(data, path)
        child_key = "items" if node.get("type") == "list" else "entries"
        children = node.get(child_key, [])
        idx = path[-1]
        parent = _get_parent_array(data, path)
        parent[idx:idx + 1] = children

    def test_dissolve_section_promotes_children(self):
        data = _make_test_data()
        # Dissolve Chapter 1 at [0] — its entries should become top-level
        ch1_entries = data[0]["entries"][:]  # 3 items: string, Room A, Room B
        self._dissolve(data, [0])
        # data should now be: Para 1, Room A, Room B, Chapter 2
        assert len(data) == 4
        assert data[0] == "Para 1"
        assert data[1]["name"] == "Room A"
        assert data[2]["name"] == "Room B"
        assert data[3]["name"] == "Chapter 2"

    def test_dissolve_nested_entry(self):
        data = _make_test_data()
        # Dissolve Room A at [0, "entries", 1] — its entries go into Chapter 1
        # Room A has entries: ["Room A text."]
        self._dissolve(data, [0, "entries", 1])
        # Chapter 1 entries: "Para 1", "Room A text.", {Room B}
        assert len(data[0]["entries"]) == 3
        assert data[0]["entries"][0] == "Para 1"
        assert data[0]["entries"][1] == "Room A text."
        assert data[0]["entries"][2]["name"] == "Room B"

    def test_dissolve_empty_node_just_removes(self):
        data = _make_test_data()
        # Clear Room B's entries
        data[0]["entries"][2]["entries"] = []
        self._dissolve(data, [0, "entries", 2])
        # Chapter 1 should now have: Para 1, Room A (Room B gone, nothing spliced)
        assert len(data[0]["entries"]) == 2

    def test_dissolve_preserves_sibling_order(self):
        data = _make_test_data()
        # Add Room D after Room C in Chapter 2
        data[1]["entries"].append(
            {"type": "entries", "name": "Room D", "entries": ["Room D text."]}
        )
        # Dissolve Room C at [1, "entries", 0] — "Room C text." + table should appear before Room D
        room_c_count = len(data[1]["entries"][0]["entries"])
        self._dissolve(data, [1, "entries", 0])
        # Chapter 2 entries: Room C's children..., Room D
        assert data[1]["entries"][-1]["name"] == "Room D"
        assert len(data[1]["entries"]) == room_c_count + 1


# ---------------------------------------------------------------------------
# Bulk operations (multi-select)
# ---------------------------------------------------------------------------

def _group_by_parent(data, paths):
    """Group paths by parent array. Returns [{parent_path, parent, indices}]."""
    from collections import OrderedDict
    groups = OrderedDict()
    for path in paths:
        pp = tuple(path[:-1])
        if pp not in groups:
            groups[pp] = {"parent_path": list(pp), "indices": []}
        groups[pp]["indices"].append(path[-1])
    result = []
    for pp, g in groups.items():
        g["indices"].sort()
        g["parent"] = data if len(g["parent_path"]) == 0 else _get_by_path(data, g["parent_path"])
        result.append(g)
    return result


def _bulk_demote(data, paths):
    """Python implementation of bulkDemote — group by parent, all go into same target."""
    groups = _group_by_parent(data, paths)
    for group in groups:
        parent = group["parent"]
        indices = group["indices"]
        first_idx = indices[0]
        if first_idx == 0:
            continue
        target = parent[first_idx - 1]
        if isinstance(target, str) or not isinstance(target, dict):
            continue
        sib_child_key = "items" if target.get("type") == "list" else "entries"
        if sib_child_key not in target:
            target[sib_child_key] = []
        nodes = []
        for idx in reversed(indices):
            nodes.insert(0, parent.pop(idx))
        target[sib_child_key].extend(nodes)


def _bulk_promote(data, paths):
    """Python implementation of bulkPromote — group by parent, all go into grandparent."""
    groups = _group_by_parent(data, paths)
    for group in reversed(groups):
        parent_path = group["parent_path"]
        parent = group["parent"]
        indices = group["indices"]
        if len(parent_path) < 2:
            continue
        parent_obj_path = parent_path[:-1]
        grandparent = _get_parent_array(data, parent_obj_path)
        if not isinstance(grandparent, list):
            continue
        parent_idx = parent_obj_path[-1]
        nodes = []
        for idx in reversed(indices):
            nodes.insert(0, parent.pop(idx))
        grandparent[parent_idx + 1:parent_idx + 1] = nodes


def _bulk_delete(data, paths):
    """Python implementation of bulkDelete — process in reverse order."""
    for path in reversed(paths):
        parent = _get_parent_array(data, path)
        idx = path[-1]
        if isinstance(parent, list) and idx < len(parent):
            parent.pop(idx)


def _bulk_move(data, paths, direction):
    """Python implementation of bulkMove — move selected block as a unit."""
    groups = _group_by_parent(data, paths)
    for group in groups:
        parent = group["parent"]
        indices = group["indices"]  # sorted ascending
        if direction < 0:
            if indices[0] <= 0:
                continue
            before_idx = indices[0] - 1
            item = parent.pop(before_idx)
            insert_at = indices[-1]  # shifted down by 1 after pop
            parent.insert(insert_at, item)
        else:
            last_idx = indices[-1]
            if last_idx >= len(parent) - 1:
                continue
            after_idx = last_idx + 1
            item = parent.pop(after_idx)
            parent.insert(indices[0], item)


def _bulk_dissolve(data, paths):
    """Python implementation of bulkDissolve — process in reverse order."""
    for path in reversed(paths):
        node = _get_by_path(data, path)
        if isinstance(node, str):
            continue
        child_key = "items" if node.get("type") == "list" else "entries"
        children = node.get(child_key, [])
        idx = path[-1]
        parent = _get_parent_array(data, path)
        parent[idx:idx + 1] = children


class TestBulkDemote:
    def test_demote_skips_when_preceding_is_string(self):
        """Demote Room A and Room B — preceding is string, so whole group is skipped."""
        data = _make_test_data()
        # Chapter 1 entries: "Para 1" (idx 0), Room A (idx 1), Room B (idx 2)
        # Group target is parent[0] = "Para 1" (string) — can't nest into it
        _bulk_demote(data, [[0, "entries", 1], [0, "entries", 2]])
        # Nothing should change
        assert len(data[0]["entries"]) == 3

    def test_demote_consecutive_range_all_into_same_target(self):
        """Demote B, C, D — all go into A (the sibling before B), not cascading."""
        data = [{"type": "section", "name": "S", "entries": [
            {"type": "entries", "name": "A", "entries": []},
            {"type": "entries", "name": "B", "entries": []},
            {"type": "entries", "name": "C", "entries": []},
            {"type": "entries", "name": "D", "entries": []},
            {"type": "entries", "name": "E", "entries": []},
        ]}]
        _bulk_demote(data, [[0, "entries", 1], [0, "entries", 2], [0, "entries", 3]])
        # Should have: A (with B, C, D as children), E
        assert len(data[0]["entries"]) == 2
        assert data[0]["entries"][0]["name"] == "A"
        assert data[0]["entries"][1]["name"] == "E"
        # A has B, C, D as flat children (not nested)
        a_children = data[0]["entries"][0]["entries"]
        assert len(a_children) == 3
        assert a_children[0]["name"] == "B"
        assert a_children[1]["name"] == "C"
        assert a_children[2]["name"] == "D"

    def test_demote_top_level_sections(self):
        data = _make_test_data()
        # Demote Chapter 2 [1] into Chapter 1 [0]
        _bulk_demote(data, [[1]])
        assert len(data) == 1
        assert data[0]["entries"][-1]["name"] == "Chapter 2"

    def test_demote_preserves_order(self):
        """Selected nodes appear in the target in their original order."""
        data = [{"type": "section", "name": "S", "entries": [
            {"type": "entries", "name": "X", "entries": []},
            {"type": "entries", "name": "A", "entries": []},
            {"type": "entries", "name": "B", "entries": []},
            {"type": "entries", "name": "C", "entries": []},
        ]}]
        _bulk_demote(data, [[0, "entries", 1], [0, "entries", 2], [0, "entries", 3]])
        x_children = data[0]["entries"][0]["entries"]
        assert [c["name"] for c in x_children] == ["A", "B", "C"]


class TestBulkPromote:
    def test_promote_multiple_from_same_parent(self):
        data = _make_test_data()
        # Promote Room A and Room B out of Chapter 1
        _bulk_promote(data, [[0, "entries", 1], [0, "entries", 2]])
        # Both should be top-level now, inserted after Chapter 1
        assert len(data) == 4  # Chapter 1, Room A, Room B, Chapter 2
        assert data[0]["name"] == "Chapter 1"
        assert data[1]["name"] == "Room A"
        assert data[2]["name"] == "Room B"
        assert data[3]["name"] == "Chapter 2"
        # Chapter 1 should only have "Para 1"
        assert len(data[0]["entries"]) == 1
        assert data[0]["entries"][0] == "Para 1"

    def test_promote_top_level_is_noop(self):
        data = _make_test_data()
        original_len = len(data)
        _bulk_promote(data, [[0], [1]])
        assert len(data) == original_len  # nothing changed

    def test_promote_preserves_order(self):
        """Promoted nodes appear in grandparent in their original order."""
        data = [{"type": "section", "name": "S", "entries": [
            {"type": "entries", "name": "A", "entries": []},
            {"type": "entries", "name": "B", "entries": []},
            {"type": "entries", "name": "C", "entries": []},
        ]}]
        _bulk_promote(data, [[0, "entries", 0], [0, "entries", 1], [0, "entries", 2]])
        # All promoted to top level after S
        assert len(data) == 4
        assert data[0]["name"] == "S"
        assert data[1]["name"] == "A"
        assert data[2]["name"] == "B"
        assert data[3]["name"] == "C"


class TestBulkMove:
    def test_move_block_up(self):
        """Move B and C up by one — A should end up after C."""
        data = [{"type": "section", "name": "S", "entries": [
            {"type": "entries", "name": "A", "entries": []},
            {"type": "entries", "name": "B", "entries": []},
            {"type": "entries", "name": "C", "entries": []},
            {"type": "entries", "name": "D", "entries": []},
        ]}]
        _bulk_move(data, [[0, "entries", 1], [0, "entries", 2]], -1)
        names = [e["name"] for e in data[0]["entries"]]
        assert names == ["B", "C", "A", "D"]

    def test_move_block_down(self):
        """Move B and C down by one — D should end up before B."""
        data = [{"type": "section", "name": "S", "entries": [
            {"type": "entries", "name": "A", "entries": []},
            {"type": "entries", "name": "B", "entries": []},
            {"type": "entries", "name": "C", "entries": []},
            {"type": "entries", "name": "D", "entries": []},
        ]}]
        _bulk_move(data, [[0, "entries", 1], [0, "entries", 2]], 1)
        names = [e["name"] for e in data[0]["entries"]]
        assert names == ["A", "D", "B", "C"]

    def test_move_up_at_top_is_noop(self):
        """Can't move up when first selected is at index 0."""
        data = [{"type": "section", "name": "S", "entries": [
            {"type": "entries", "name": "A", "entries": []},
            {"type": "entries", "name": "B", "entries": []},
        ]}]
        _bulk_move(data, [[0, "entries", 0], [0, "entries", 1]], -1)
        names = [e["name"] for e in data[0]["entries"]]
        assert names == ["A", "B"]

    def test_move_down_at_bottom_is_noop(self):
        """Can't move down when last selected is at the end."""
        data = [{"type": "section", "name": "S", "entries": [
            {"type": "entries", "name": "A", "entries": []},
            {"type": "entries", "name": "B", "entries": []},
        ]}]
        _bulk_move(data, [[0, "entries", 0], [0, "entries", 1]], 1)
        names = [e["name"] for e in data[0]["entries"]]
        assert names == ["A", "B"]

    def test_move_top_level_sections_up(self):
        data = _make_test_data()
        _bulk_move(data, [[1]], -1)
        assert data[0]["name"] == "Chapter 2"
        assert data[1]["name"] == "Chapter 1"

    def test_move_top_level_sections_down(self):
        data = _make_test_data()
        _bulk_move(data, [[0]], 1)
        assert data[0]["name"] == "Chapter 2"
        assert data[1]["name"] == "Chapter 1"

    def test_move_preserves_non_selected(self):
        """Move middle elements, verify surrounding elements stay put."""
        data = [{"type": "section", "name": "S", "entries": [
            {"type": "entries", "name": "A", "entries": []},
            {"type": "entries", "name": "B", "entries": []},
            {"type": "entries", "name": "C", "entries": []},
            {"type": "entries", "name": "D", "entries": []},
            {"type": "entries", "name": "E", "entries": []},
        ]}]
        # Move C down — D hops over to before C
        _bulk_move(data, [[0, "entries", 2]], 1)
        names = [e["name"] for e in data[0]["entries"]]
        assert names == ["A", "B", "D", "C", "E"]


class TestBulkDelete:
    def test_delete_multiple_siblings(self):
        data = _make_test_data()
        # Delete Room A and Room B from Chapter 1
        _bulk_delete(data, [[0, "entries", 1], [0, "entries", 2]])
        assert len(data[0]["entries"]) == 1
        assert data[0]["entries"][0] == "Para 1"

    def test_delete_top_level_sections(self):
        data = _make_test_data()
        _bulk_delete(data, [[0], [1]])
        assert len(data) == 0

    def test_delete_preserves_unselected(self):
        data = [{"type": "section", "name": "S", "entries": [
            {"type": "entries", "name": "A", "entries": []},
            {"type": "entries", "name": "B", "entries": []},
            {"type": "entries", "name": "C", "entries": []},
            {"type": "entries", "name": "D", "entries": []},
        ]}]
        # Delete B and D (indices 1, 3)
        _bulk_delete(data, [[0, "entries", 1], [0, "entries", 3]])
        assert len(data[0]["entries"]) == 2
        assert data[0]["entries"][0]["name"] == "A"
        assert data[0]["entries"][1]["name"] == "C"


class TestBulkDissolve:
    def test_dissolve_multiple(self):
        data = _make_test_data()
        # Dissolve both Room A and Room B — their children get spliced into Chapter 1
        _bulk_dissolve(data, [[0, "entries", 1], [0, "entries", 2]])
        # Room B dissolved first (reverse): "Room B text." replaces Room B
        # Then Room A dissolved: "Room A text." replaces Room A
        # Chapter 1 entries: "Para 1", "Room A text.", "Room B text."
        assert len(data[0]["entries"]) == 3
        assert data[0]["entries"][0] == "Para 1"
        assert data[0]["entries"][1] == "Room A text."
        assert data[0]["entries"][2] == "Room B text."

    def test_dissolve_skips_strings(self):
        data = _make_test_data()
        original_len = len(data[0]["entries"])
        # Try dissolving a string entry — should be skipped
        _bulk_dissolve(data, [[0, "entries", 0]])
        assert len(data[0]["entries"]) == original_len  # unchanged


# ---------------------------------------------------------------------------
# Undo log helpers
# ---------------------------------------------------------------------------

class TestJoinLines:
    """Test the joinLines logic — Python equivalent of the JS function."""

    @staticmethod
    def _join_lines(text):
        """Python port of the JS joinLines function."""
        lines = text.split("\n")
        parts = []
        for i, line in enumerate(lines):
            if line.strip() == "":
                parts.append("\n\n")
            elif line.endswith("-") and i + 1 < len(lines) and lines[i + 1].strip() != "":
                parts.append(line[:-1])
            else:
                parts.append(line)
                if i + 1 < len(lines) and lines[i + 1].strip() != "":
                    parts.append(" ")
        import re
        result = "".join(parts)
        result = re.sub(r" +", " ", result)
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result.strip()

    def test_simple_line_join(self):
        text = "Five guards are alert here at all times. One fac-\ning the door"
        result = self._join_lines(text)
        assert result == "Five guards are alert here at all times. One facing the door"

    def test_hyphenated_word_join(self):
        text = "sur-\ncoats"
        result = self._join_lines(text)
        assert result == "surcoats"

    def test_soft_wrap_join(self):
        text = "the guards alert\narea 130 (or 128, as appropriate)."
        result = self._join_lines(text)
        assert result == "the guards alert area 130 (or 128, as appropriate)."

    def test_blank_line_preserves_paragraph(self):
        text = "First paragraph.\n\nSecond paragraph."
        result = self._join_lines(text)
        assert result == "First paragraph.\n\nSecond paragraph."

    def test_full_pdf_paste(self):
        text = (
            "Five guards are alert here at all times. One fac-\n"
            "ing the door, and another posted ten feet up\n"
            "the northeast corridor (position G on the\n"
            "map), are armed with heavy crossbows and\n"
            "longswords."
        )
        result = self._join_lines(text)
        assert "fac-" not in result
        assert "facing the door" in result
        assert "\n" not in result
        assert result.startswith("Five guards")
        assert result.endswith("longswords.")

    def test_multiple_paragraphs_with_hyphens(self):
        text = "First para-\ngraph text.\n\nSecond para-\ngraph text."
        result = self._join_lines(text)
        assert result == "First paragraph text.\n\nSecond paragraph text."

    def test_empty_string(self):
        assert self._join_lines("") == ""

    def test_single_line(self):
        assert self._join_lines("No breaks here.") == "No breaks here."


class TestUndoLogHelpers:
    def test_undolog_path(self):
        p = ae._undolog_path("adventure-foo.json")
        assert p == Path("adventure-foo.undolog.json")

    def test_load_missing_undolog(self):
        log = ae._load_undolog("/nonexistent/path.json")
        assert log == {"entries": [], "position": -1}

    def test_save_and_load_roundtrip(self, tmp_path):
        path = str(tmp_path / "test.json")
        undolog = {
            "entries": [{"ts": 1.0, "action": "test", "data": []}],
            "position": 0,
        }
        ae._save_undolog(path, undolog)
        loaded = ae._load_undolog(path)
        assert loaded["entries"][0]["action"] == "test"
        assert loaded["position"] == 0

    def test_summary_strips_data(self):
        undolog = {
            "entries": [
                {"ts": 1.0, "action": "edit", "data": [{"big": "data"}]},
            ],
            "position": 0,
        }
        summary = ae._undolog_summary(undolog)
        assert len(summary) == 1
        assert summary[0]["action"] == "edit"
        assert "data" not in summary[0]


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------

class TestFlags:
    """Test the _flags metadata system."""

    def test_add_flag(self):
        data = _make_test_data()
        node = data[0]["entries"][1]  # Room A
        assert "_flags" not in node
        node["_flags"] = ["1e"]
        assert node["_flags"] == ["1e"]

    def test_multiple_flags(self):
        data = _make_test_data()
        node = data[0]
        node["_flags"] = ["1e", "review"]
        assert "1e" in node["_flags"]
        assert "review" in node["_flags"]

    def test_toggle_flag_off(self):
        data = _make_test_data()
        node = data[0]
        node["_flags"] = ["1e", "review"]
        node["_flags"].remove("1e")
        assert node["_flags"] == ["review"]

    def test_clear_flags(self):
        data = _make_test_data()
        node = data[0]
        node["_flags"] = ["1e"]
        del node["_flags"]
        assert "_flags" not in node

    def test_bulk_flag(self):
        data = _make_test_data()
        targets = [data[0]["entries"][1], data[0]["entries"][2]]  # Room A, Room B
        for node in targets:
            if not isinstance(node, dict):
                continue
            if "_flags" not in node:
                node["_flags"] = []
            if "1e" not in node["_flags"]:
                node["_flags"].append("1e")
        assert data[0]["entries"][1]["_flags"] == ["1e"]
        assert data[0]["entries"][2]["_flags"] == ["1e"]

    def test_bulk_clear_flags(self):
        data = _make_test_data()
        data[0]["_flags"] = ["1e", "review"]
        data[0]["entries"][1]["_flags"] = ["todo"]
        targets = [data[0], data[0]["entries"][1]]
        for node in targets:
            if isinstance(node, dict) and "_flags" in node:
                del node["_flags"]
        assert "_flags" not in data[0]
        assert "_flags" not in data[0]["entries"][1]

    def test_flags_survive_save(self, sample_adventure):
        """Flags stored as _flags are preserved through save/load cycle."""
        sess = ae.load_adventure(sample_adventure)
        sess["data"][0]["_flags"] = ["1e"]
        sess["data"][0]["entries"][1]["_flags"] = ["review", "todo"]
        ae.save_adventure(sess, sess["data"])
        # Write and reload
        import shutil
        p = sample_adventure
        with open(p, "w", encoding="utf-8") as f:
            json.dump(sess["raw"], f, indent="\t", ensure_ascii=False)
        sess2 = ae.load_adventure(p)
        assert sess2["data"][0]["_flags"] == ["1e"]
        assert sess2["data"][0]["entries"][1]["_flags"] == ["review", "todo"]

    def test_count_flagged(self):
        """Count all flagged nodes in a tree."""
        data = _make_test_data()
        data[0]["_flags"] = ["1e"]
        data[0]["entries"][1]["_flags"] = ["review"]
        count = 0
        def walk(entries):
            nonlocal count
            for e in entries:
                if isinstance(e, dict):
                    if e.get("_flags"):
                        count += 1
                    if "entries" in e:
                        walk(e["entries"])
        walk(data)
        assert count == 2
