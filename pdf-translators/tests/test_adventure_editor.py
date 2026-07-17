#!/usr/bin/env python3
"""Tests for adventure_editor.py — server-side logic and API routes.

Run:
    pytest test_adventure_editor.py -v
"""

import json
import os
import tempfile
from pathlib import Path

import pytest
from flask import Flask

import editors.adventure_editor as ae
import lib.fix_adventure_json as _fix

_test_app = Flask(__name__)
_test_app.register_blueprint(ae.bp)


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
    """Flask test client (adventure Blueprint only) with a loaded adventure."""
    _test_app.config["TESTING"] = True
    ae._sessions.clear()
    with _test_app.test_client() as client:
        # Load the adventure
        resp = client.post("/api/adv/load", json={"path": str(sample_adventure)})
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
    def test_files_returns_list(self, app_client):
        client, path = app_client
        resp = client.get("/api/adv/files")
        assert resp.status_code == 200
        files = resp.get_json()
        assert isinstance(files, list)

    def test_load_returns_data(self, app_client):
        client, path = app_client
        resp = client.post("/api/adv/load", json={"path": path})
        result = resp.get_json()
        assert "data" in result
        assert len(result["data"]) == 2
        assert result["meta"]["name"] == "Test Adventure"

    def test_load_returns_undolog(self, app_client):
        client, path = app_client
        resp = client.post("/api/adv/load", json={"path": path})
        result = resp.get_json()
        assert "undolog" in result
        assert result["undolog"]["position"] == -1
        assert result["undolog"]["entries"] == []

    def test_load_nonexistent_file(self, app_client):
        client, path = app_client
        resp = client.post("/api/adv/load", json={"path": "/nonexistent.json"})
        assert resp.status_code == 400

    def test_save_writes_file(self, app_client):
        client, path = app_client
        # Modify data
        resp = client.post("/api/adv/load", json={"path": path})
        data = resp.get_json()["data"]
        data[0]["name"] = "Modified Chapter"
        resp = client.post("/api/adv/save", json={"path": path, "data": data})
        result = resp.get_json()
        assert result["ok"] is True
        assert result["sections"] == 2
        # Verify on disk
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["adventureData"][0]["data"][0]["name"] == "Modified Chapter"

    def test_save_creates_backup(self, app_client):
        client, path = app_client
        resp = client.post("/api/adv/load", json={"path": path})
        data = resp.get_json()["data"]
        resp = client.post("/api/adv/save", json={"path": path, "data": data})
        assert resp.get_json()["ok"] is True
        bak = Path(path).with_suffix(".bak")
        assert bak.exists()


# Note: the old "no pk in onclick attributes" regression test (TestNoPkInOnclick)
# was removed here — it guarded against a hand-rolled-HTML hazard (JSON path
# keys with embedded quotes breaking onclick="..." attribute strings) that no
# longer exists now that the UI is Vue with @click bindings: Vue never
# serializes JS values into HTML attribute strings for event handlers, so the
# whole bug class is structurally impossible.

# ---------------------------------------------------------------------------
# Undo log API
# ---------------------------------------------------------------------------

class TestUndoLog:
    def test_push_and_list(self, app_client):
        client, path = app_client
        snapshot = [{"type": "section", "name": "Snap", "entries": []}]
        resp = client.post("/api/adv/undolog/push", json={
            "path": path, "action": "test action", "data": snapshot,
        })
        result = resp.get_json()
        assert result["ok"] is True
        assert result["position"] == 0
        assert result["total"] == 1
        # List
        resp = client.get(f"/api/adv/undolog?path={path}")
        result = resp.get_json()
        assert len(result["entries"]) == 1
        assert result["entries"][0]["action"] == "test action"
        assert result["position"] == 0

    def test_undo(self, app_client):
        client, path = app_client
        snap1 = [{"type": "section", "name": "Before", "entries": []}]
        client.post("/api/adv/undolog/push", json={"path": path, "action": "edit", "data": snap1})
        resp = client.post("/api/adv/undolog/undo", json={"path": path})
        result = resp.get_json()
        assert result["ok"] is True
        assert result["data"][0]["name"] == "Before"
        assert result["position"] == -1

    def test_undo_empty_returns_error(self, app_client):
        client, path = app_client
        resp = client.post("/api/adv/undolog/undo", json={"path": path})
        assert resp.status_code == 400

    def test_redo(self, app_client):
        client, path = app_client
        snap1 = [{"type": "section", "name": "State1", "entries": []}]
        snap2 = [{"type": "section", "name": "State2", "entries": []}]
        client.post("/api/adv/undolog/push", json={"path": path, "action": "edit1", "data": snap1})
        client.post("/api/adv/undolog/push", json={"path": path, "action": "edit2", "data": snap2})
        # Undo back to edit1
        client.post("/api/adv/undolog/undo", json={"path": path})
        # Redo to edit2
        resp = client.post("/api/adv/undolog/redo", json={"path": path})
        result = resp.get_json()
        assert result["ok"] is True
        assert result["data"][0]["name"] == "State2"

    def test_push_truncates_redo(self, app_client):
        client, path = app_client
        for i in range(3):
            client.post("/api/adv/undolog/push", json={
                "path": path, "action": f"edit{i}",
                "data": [{"type": "section", "name": f"S{i}", "entries": []}],
            })
        # Undo twice
        client.post("/api/adv/undolog/undo", json={"path": path})
        client.post("/api/adv/undolog/undo", json={"path": path})
        # Push new — should truncate redo history
        client.post("/api/adv/undolog/push", json={
            "path": path, "action": "new",
            "data": [{"type": "section", "name": "New", "entries": []}],
        })
        resp = client.get(f"/api/adv/undolog?path={path}")
        result = resp.get_json()
        # Should have entries 0 (edit0), 1 (new) — edit1 and edit2 truncated
        assert len(result["entries"]) == 2
        assert result["entries"][1]["action"] == "new"

    def test_jump(self, app_client):
        client, path = app_client
        for i in range(5):
            client.post("/api/adv/undolog/push", json={
                "path": path, "action": f"edit{i}",
                "data": [{"type": "section", "name": f"S{i}", "entries": []}],
            })
        resp = client.post("/api/adv/undolog/jump", json={"path": path, "idx": 2})
        result = resp.get_json()
        assert result["ok"] is True
        assert result["data"][0]["name"] == "S2"
        assert result["position"] == 2

    def test_undolog_persisted_to_disk(self, app_client):
        client, path = app_client
        client.post("/api/adv/undolog/push", json={
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
        client.post("/api/adv/undolog/push", json={
            "path": path, "action": "before reload",
            "data": [{"type": "section", "name": "BR", "entries": []}],
        })
        # Re-load the file
        resp = client.post("/api/adv/load", json={"path": path})
        result = resp.get_json()
        assert result["undolog"]["entries"][0]["action"] == "before reload"
        assert result["undolog"]["position"] == 0


# ---------------------------------------------------------------------------
# Undo log helpers
# ---------------------------------------------------------------------------

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
    """Test the _flags metadata system.

    Note: pure path/mutation logic for flags (toggle/bulk-flag/bulk-clear/
    count) is now tested against the real TS port in
    frontend/src/lib/adventureTree.test.ts. This class keeps only the
    save/load round-trip check, which exercises real backend logic
    (save_adventure must not strip an unrecognized `_flags` key).
    """

    def test_flags_survive_save(self, sample_adventure):
        """Flags stored as _flags are preserved through save/load cycle."""
        sess = ae.load_adventure(sample_adventure)
        sess["data"][0]["_flags"] = ["1e"]
        sess["data"][0]["entries"][1]["_flags"] = ["review", "todo"]
        ae.save_adventure(sess, sess["data"])
        # Write and reload
        p = sample_adventure
        with open(p, "w", encoding="utf-8") as f:
            json.dump(sess["raw"], f, indent="\t", ensure_ascii=False)
        sess2 = ae.load_adventure(p)
        assert sess2["data"][0]["_flags"] == ["1e"]
        assert sess2["data"][0]["entries"][1]["_flags"] == ["review", "todo"]
