"""Tests for batch_state.StateDB (batch_convert's SQLite state store)."""
import sqlite3

import lib.batch_state as bs


def _scan_doc(status="pending", **kw):
    d = {"status": status, "reason": "", "size": 100, "mtime": 5,
         "pages": 10, "text_chars": 2000, "is_pf": 0, "eligible_small": 0,
         "endpoint": "", "attempts": 0, "exit": None, "duration_s": 0.0,
         "log": ""}
    d.update(kw)
    return d


def test_roundtrip(tmp_path):
    db = bs.StateDB(str(tmp_path / "s.db"))
    docs = {"a/x.pdf": _scan_doc(is_pf=1, text_chars=3000),
            "b/y.pdf": _scan_doc(status="skipped", reason="library:old_version")}
    db.save_docs(docs)
    loaded = bs.StateDB(str(tmp_path / "s.db")).load_docs()
    assert set(loaded) == {"a/x.pdf", "b/y.pdf"}
    assert loaded["a/x.pdf"]["is_pf"] == 1
    assert loaded["a/x.pdf"]["text_chars"] == 3000
    assert loaded["b/y.pdf"]["status"] == "skipped"
    assert loaded["b/y.pdf"]["reason"] == "library:old_version"


def test_exists_with_docs(tmp_path):
    db = bs.StateDB(str(tmp_path / "s.db"))
    assert not db.exists_with_docs()
    db.save_docs({"a.pdf": _scan_doc()})
    assert db.exists_with_docs()


def test_update_progress_touches_one_row(tmp_path):
    db = bs.StateDB(str(tmp_path / "s.db"))
    db.save_docs({"a.pdf": _scan_doc(), "b.pdf": _scan_doc()})
    db.update_progress("a.pdf", status="done", endpoint="spark1", attempts=2,
                       exit=0, duration_s=12.5, log="/l/a.log")
    loaded = db.load_docs()
    assert loaded["a.pdf"]["status"] == "done"
    assert loaded["a.pdf"]["endpoint"] == "spark1"
    assert loaded["a.pdf"]["attempts"] == 2
    assert loaded["a.pdf"]["duration_s"] == 12.5
    # b untouched
    assert loaded["b.pdf"]["status"] == "pending"
    assert loaded["b.pdf"]["endpoint"] == ""


def test_meta(tmp_path):
    db = bs.StateDB(str(tmp_path / "s.db"))
    db.set_meta(root="/mnt/x", source="fresh", api_base="http://h:8000")
    assert db.get_meta("root") == "/mnt/x"
    assert db.get_meta("source") == "fresh"
    assert db.get_meta("saved_at") is not None
    # re-set updates in place (no duplicate keys)
    db.set_meta(root="/mnt/y", source="reuse", api_base="http://h:8000")
    assert db.get_meta("root") == "/mnt/y"
    assert db.get_meta("source") == "reuse"


def test_exit_null_roundtrips(tmp_path):
    db = bs.StateDB(str(tmp_path / "s.db"))
    db.save_docs({"a.pdf": _scan_doc(exit=None)})
    assert db.load_docs()["a.pdf"]["exit"] is None
    db.update_progress("a.pdf", status="failed", endpoint="spark2", attempts=3,
                       exit=124, duration_s=1.0, log="x")
    assert db.load_docs()["a.pdf"]["exit"] == 124


def test_readonly_sees_committed_during_open_writer(tmp_path):
    """A read-only reader gets the last committed snapshot while the writer
    holds the connection open (WAL concurrent read)."""
    p = str(tmp_path / "s.db")
    db = bs.StateDB(p)
    db.save_docs({"a.pdf": _scan_doc(status="done")})
    ro = bs.open_readonly(p)
    rows = {r["rel"]: r["status"] for r in ro.execute("SELECT rel, status FROM docs")}
    assert rows == {"a.pdf": "done"}
    # writer commits more; reader (new query) sees it
    db.save_docs({"a.pdf": _scan_doc(status="done"), "b.pdf": _scan_doc()})
    rows = {r["rel"]: r["status"] for r in ro.execute("SELECT rel, status FROM docs")}
    assert set(rows) == {"a.pdf", "b.pdf"}
    ro.close()


def test_readonly_cannot_write(tmp_path):
    p = str(tmp_path / "s.db")
    bs.StateDB(p).save_docs({"a.pdf": _scan_doc()})
    ro = bs.open_readonly(p)
    try:
        ro.execute("UPDATE docs SET status='x'")
        assert False, "read-only connection should reject writes"
    except sqlite3.OperationalError:
        pass
    finally:
        ro.close()
