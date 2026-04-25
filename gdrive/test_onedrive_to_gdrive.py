"""Unit tests for the deterministic parts of `onedrive_to_gdrive`.

Covers pure functions (path parsing, query escaping, byte formatting) and
the JSONL/state helpers via tmp_path + monkeypatch. Network-facing code
(download_onedrive, upload_gdrive, Drive find/create, the thread pool) is
intentionally out of scope — that needs mocks against real SDK objects.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import onedrive_to_gdrive as mod


# ---------- onedrive_full_path ----------

class TestOneDriveFullPath:
    def test_strips_drive_root_prefix(self):
        rec = {"parentPath": "/drive/root:/Folder/Sub", "name": "file.pdf"}
        assert mod.onedrive_full_path(rec) == "/Folder/Sub/file.pdf"

    def test_url_decodes(self):
        rec = {"parentPath": "/drive/root:/Dungeons%20and%20Dragons", "name": "X"}
        assert mod.onedrive_full_path(rec) == "/Dungeons and Dragons/X"

    def test_root_level_file(self):
        """parentPath '/drive/root:' means the drive root itself."""
        rec = {"parentPath": "/drive/root:", "name": "file.pdf"}
        assert mod.onedrive_full_path(rec) == "/file.pdf"

    def test_missing_parent_path(self):
        rec = {"name": "file.pdf"}
        assert mod.onedrive_full_path(rec) == "/file.pdf"


# ---------- escape_q ----------

class TestEscapeQ:
    def test_no_special_chars(self):
        assert mod.escape_q("hello") == "hello"

    def test_apostrophe_escaped(self):
        assert mod.escape_q("don't") == r"don\'t"

    def test_backslash_escaped(self):
        # Single backslash becomes double: `foo\bar` -> `foo\\bar`
        assert mod.escape_q("foo\\bar") == r"foo\\bar"

    def test_backslash_before_apostrophe_order(self):
        # Input chars:  a '  \  b
        # After step 1 (backslash doubled):  a '  \  \  b
        # After step 2 (apostrophe prefixed):  a \  '  \  \  b
        assert mod.escape_q("a'\\b") == "a\\'\\\\b"


# ---------- human_bytes ----------

@pytest.mark.parametrize("n,expected", [
    (0, "0.0B"),
    (1023, "1023.0B"),
    (1024, "1.0KB"),
    (1536, "1.5KB"),
    (1024 * 1024, "1.0MB"),
    (1024 ** 3, "1.0GB"),
    (1024 ** 4, "1.0TB"),
    (1024 ** 5, "1.0PB"),
])
def test_human_bytes(n, expected):
    assert mod.human_bytes(n) == expected


# ---------- load_source_files ----------

def _write_jsonl(path: Path, recs: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in recs) + "\n")


class TestLoadSourceFiles:
    def test_filters_by_source_and_attaches_relpath(self, tmp_path: Path):
        jsonl = tmp_path / "onedrive.jsonl"
        _write_jsonl(jsonl, [
            {"id": "a", "name": "a.pdf", "mimeType": "application/pdf",
             "parentPath": "/drive/root:/Foo", "size": 100},
            {"id": "b", "name": "b.pdf", "mimeType": "application/pdf",
             "parentPath": "/drive/root:/Foo/sub", "size": 200},
            {"id": "c", "name": "c.pdf", "mimeType": "application/pdf",
             "parentPath": "/drive/root:/Other", "size": 300},
        ])

        out = mod.load_source_files(str(jsonl), "/Foo")

        # 'c' is outside scope; 'a' and 'b' remain, sorted by _relpath.
        assert {r["id"]: r["_relpath"] for r in out} == {
            "a": "a.pdf",
            "b": "sub/b.pdf",
        }

    def test_sorted_by_relpath(self, tmp_path: Path):
        jsonl = tmp_path / "onedrive.jsonl"
        _write_jsonl(jsonl, [
            {"id": "z", "name": "z.pdf", "mimeType": "x/y",
             "parentPath": "/drive/root:/S", "size": 1},
            {"id": "a", "name": "a.pdf", "mimeType": "x/y",
             "parentPath": "/drive/root:/S", "size": 1},
        ])
        out = mod.load_source_files(str(jsonl), "/S")
        assert [r["_relpath"] for r in out] == ["a.pdf", "z.pdf"]

    def test_skips_folders(self, tmp_path: Path):
        jsonl = tmp_path / "onedrive.jsonl"
        _write_jsonl(jsonl, [
            {"id": "fldr", "name": "Sub", "mimeType": "folder",
             "parentPath": "/drive/root:/S"},
            {"id": "f", "name": "x.pdf", "mimeType": "x/y",
             "parentPath": "/drive/root:/S", "size": 1},
        ])
        out = mod.load_source_files(str(jsonl), "/S")
        assert [r["id"] for r in out] == ["f"]

    def test_source_prefix_must_be_full_segment(self, tmp_path: Path):
        """Path '/Foo' does not match a record under '/Foobar'."""
        jsonl = tmp_path / "onedrive.jsonl"
        _write_jsonl(jsonl, [
            {"id": "wrong", "name": "x.pdf", "mimeType": "x/y",
             "parentPath": "/drive/root:/Foobar", "size": 1},
            {"id": "right", "name": "x.pdf", "mimeType": "x/y",
             "parentPath": "/drive/root:/Foo", "size": 1},
        ])
        out = mod.load_source_files(str(jsonl), "/Foo")
        assert [r["id"] for r in out] == ["right"]

    def test_source_with_url_encoded_path(self, tmp_path: Path):
        """Source path is plain, record parentPath is URL-encoded; should match."""
        jsonl = tmp_path / "onedrive.jsonl"
        _write_jsonl(jsonl, [
            {"id": "a", "name": "f.pdf", "mimeType": "x/y",
             "parentPath": "/drive/root:/Dungeons%20and%20Dragons/KickStarter",
             "size": 1},
        ])
        out = mod.load_source_files(str(jsonl), "/Dungeons and Dragons/KickStarter")
        assert [r["id"] for r in out] == ["a"]


# ---------- SQLite state ----------

@pytest.fixture
def db(tmp_path: Path, monkeypatch):
    """Isolated DB per test; also resets the thread-local connection cache."""
    monkeypatch.setattr(mod, "DB_PATH", tmp_path / "copy-state.sqlite")
    monkeypatch.setattr(mod, "LEGACY_JSON_PATH", tmp_path / "copy-state.json")
    if hasattr(mod._tls, "conn"):
        del mod._tls.conn
    conn = mod.open_db()
    yield conn
    conn.close()
    if hasattr(mod._tls, "conn"):
        try:
            mod._tls.conn.close()
        except Exception:
            pass
        del mod._tls.conn


class TestSqliteState:
    def test_schema_created_idempotently(self, db):
        # open_db already ran once via the fixture; running again should not error.
        conn2 = mod.open_db()
        cols = [r[1] for r in conn2.execute("PRAGMA table_info(copied)").fetchall()]
        assert cols == [
            "onedrive_id", "gdrive_id", "rel_path", "size",
            "action", "error_kind", "error_msg", "ts",
        ]
        conn2.close()

    def test_record_and_already_done(self, db):
        mod.record("a", "ga", "dir/a.pdf", 100, "uploaded")
        mod.record("b", "gb", "dir/b.pdf", 200, "skipped_existing")
        mod.record(
            "c", None, "dir/c.pdf", 300, "failed",
            error_kind="SSLError", error_msg="bad record mac",
        )
        assert mod.already_done_ids(db) == {"a", "b"}

    def test_insert_or_replace(self, db):
        """A failed attempt that later succeeds ends up with action='uploaded'."""
        mod.record("x", None, "x.pdf", 10, "failed",
                   error_kind="ConnectionError", error_msg="reset")
        mod.record("x", "gx", "x.pdf", 10, "uploaded")
        rows = db.execute(
            "SELECT action, gdrive_id FROM copied WHERE onedrive_id='x'"
        ).fetchall()
        assert rows == [("uploaded", "gx")]

    def test_migration_from_json(self, tmp_path: Path, monkeypatch):
        """Legacy JSON gets imported once; file is left on disk."""
        monkeypatch.setattr(mod, "DB_PATH", tmp_path / "copy-state.sqlite")
        monkeypatch.setattr(mod, "LEGACY_JSON_PATH", tmp_path / "copy-state.json")
        if hasattr(mod._tls, "conn"):
            del mod._tls.conn
        (tmp_path / "copy-state.json").write_text(json.dumps({
            "copied": {
                "a": {"gdrive_id": "ga", "rel_path": "a.pdf",
                      "size": 100, "action": "uploaded", "ts": "2026-04-17T00:00:00"},
                "b": {"gdrive_id": "gb", "rel_path": "b.pdf",
                      "size": 200, "action": "skipped_existing", "ts": "2026-04-17T00:00:01"},
            }
        }))
        conn = mod.open_db()
        n = mod.maybe_migrate_from_json(conn)
        assert n == 2
        assert mod.already_done_ids(conn) == {"a", "b"}
        assert (tmp_path / "copy-state.json").exists(), "JSON must be left on disk"
        conn.close()

    def test_migration_skipped_when_db_nonempty(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(mod, "DB_PATH", tmp_path / "copy-state.sqlite")
        monkeypatch.setattr(mod, "LEGACY_JSON_PATH", tmp_path / "copy-state.json")
        if hasattr(mod._tls, "conn"):
            del mod._tls.conn
        conn = mod.open_db()
        # DB already has one row.
        mod.record("pre", "gpre", "pre.pdf", 1, "uploaded")
        (tmp_path / "copy-state.json").write_text(json.dumps({
            "copied": {
                "new": {"gdrive_id": "gnew", "rel_path": "new.pdf",
                        "size": 2, "action": "uploaded", "ts": "2026-04-17T00:00:00"},
            }
        }))
        n = mod.maybe_migrate_from_json(conn)
        assert n == 0
        assert mod.already_done_ids(conn) == {"pre"}
        conn.close()
