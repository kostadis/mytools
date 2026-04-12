#!/usr/bin/env python3
"""Tests for the favorites feature (user_data.db ATTACH, set/unset, search integration)."""

import json
import os
import sqlite3
import tempfile
import unittest

from library_api.db import (
    get_book,
    get_books_by_ids,
    init_user_db,
    search_books,
    search_facets,
    set_favorite,
    unset_favorite,
)


def _make_library_db(path: str) -> None:
    """Create a minimal library DB on disk (read-only later)."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE books (
            id              INTEGER PRIMARY KEY,
            filename        TEXT NOT NULL,
            filepath        TEXT NOT NULL DEFAULT '',
            relative_path   TEXT NOT NULL DEFAULT '',
            source          TEXT,
            publisher       TEXT,
            collection      TEXT,
            pdf_title       TEXT,
            pdf_author      TEXT,
            pdf_creator     TEXT,
            page_count      INTEGER,
            has_bookmarks   INTEGER NOT NULL DEFAULT 0,
            first_page_text TEXT,
            date_indexed    TEXT NOT NULL DEFAULT '2026-01-01',
            game_system     TEXT,
            product_type    TEXT,
            description     TEXT,
            date_enriched   TEXT,
            is_old_version  INTEGER NOT NULL DEFAULT 0,
            version_generation INTEGER,
            product_id      TEXT,
            product_version TEXT,
            tags            TEXT,
            series          TEXT,
            display_title   TEXT,
            is_draft        INTEGER NOT NULL DEFAULT 0,
            is_duplicate    INTEGER NOT NULL DEFAULT 0,
            min_level       INTEGER,
            max_level       INTEGER
        );
        CREATE TABLE bookmarks (
            id          INTEGER PRIMARY KEY,
            book_id     INTEGER NOT NULL,
            level       INTEGER NOT NULL,
            title       TEXT NOT NULL,
            page_number INTEGER
        );
    """)
    conn.commit()
    conn.close()


def _add_book(conn, book_id, filename, **kwargs):
    """Insert a test book into the library DB."""
    defaults = dict(
        display_title=filename.replace(".pdf", ""),
        publisher=None, game_system=None, product_type=None,
        series=None, tags=None, description=None, page_count=100,
        is_old_version=0, is_draft=0, is_duplicate=0, date_enriched=None,
    )
    defaults.update(kwargs)
    d = defaults
    conn.execute(
        """INSERT INTO books
               (id, filename, display_title, publisher, game_system, product_type,
                series, tags, description, page_count, is_old_version, is_draft,
                is_duplicate, date_enriched)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (book_id, filename, d["display_title"], d["publisher"],
         d["game_system"], d["product_type"], d["series"],
         json.dumps(d["tags"]) if d["tags"] is not None else None,
         d["description"], d["page_count"], d["is_old_version"],
         d["is_draft"], d["is_duplicate"], d["date_enriched"]),
    )
    conn.commit()


def _open_attached(lib_path: str, user_path: str) -> sqlite3.Connection:
    """Open the library DB read-only with user_data attached (like the server)."""
    conn = sqlite3.connect(f"file:{lib_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("ATTACH DATABASE ? AS user_data", (user_path,))
    return conn


class TestInitUserDb(unittest.TestCase):
    def test_creates_schema(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            init_user_db(path)
            conn = sqlite3.connect(path)
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            self.assertIn("favorites", tables)
            conn.close()
        finally:
            os.unlink(path)

    def test_idempotent(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            init_user_db(path)
            init_user_db(path)  # should not raise
        finally:
            os.unlink(path)


class TestFavoritesCrud(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.lib_path = os.path.join(self.tmpdir, "lib.db")
        self.user_path = os.path.join(self.tmpdir, "user.db")
        _make_library_db(self.lib_path)
        init_user_db(self.user_path)

        # Seed books via a rw connection
        rw = sqlite3.connect(self.lib_path)
        rw.row_factory = sqlite3.Row
        _add_book(rw, 1, "a.pdf", game_system="D&D 5e", tags=["horror"])
        _add_book(rw, 2, "b.pdf", game_system="D&D 5e", tags=["dungeon"])
        _add_book(rw, 3, "c.pdf", game_system="OSR", tags=["horror"])
        rw.close()

        self.conn = _open_attached(self.lib_path, self.user_path)

    def tearDown(self):
        self.conn.close()
        os.unlink(self.lib_path)
        os.unlink(self.user_path)
        os.rmdir(self.tmpdir)

    def test_set_and_unset(self):
        set_favorite(self.conn, 1)
        row = self.conn.execute(
            "SELECT book_id FROM user_data.favorites WHERE book_id = 1"
        ).fetchone()
        self.assertIsNotNone(row)

        unset_favorite(self.conn, 1)
        row = self.conn.execute(
            "SELECT book_id FROM user_data.favorites WHERE book_id = 1"
        ).fetchone()
        self.assertIsNone(row)

    def test_set_idempotent(self):
        set_favorite(self.conn, 1)
        set_favorite(self.conn, 1)  # INSERT OR IGNORE — should not raise
        count = self.conn.execute(
            "SELECT COUNT(*) FROM user_data.favorites WHERE book_id = 1"
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_unset_nonexistent_no_error(self):
        unset_favorite(self.conn, 999)  # should not raise

    def test_search_returns_is_favorite(self):
        set_favorite(self.conn, 1)
        result = search_books(self.conn, grouped=False)
        fav_flags = {r["id"]: r["is_favorite"] for r in result["results"]}
        self.assertTrue(fav_flags[1])
        self.assertFalse(fav_flags[2])
        self.assertFalse(fav_flags[3])

    def test_favorites_only_filter(self):
        set_favorite(self.conn, 1)
        set_favorite(self.conn, 3)
        result = search_books(self.conn, favorites_only=True, grouped=False)
        self.assertEqual(result["total"], 2)
        ids = {r["id"] for r in result["results"]}
        self.assertEqual(ids, {1, 3})

    def test_favorites_only_composes_with_other_filters(self):
        set_favorite(self.conn, 1)
        set_favorite(self.conn, 3)
        result = search_books(
            self.conn, game_system="D&D 5e", favorites_only=True, grouped=False,
        )
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["results"][0]["id"], 1)

    def test_favorites_only_with_facets(self):
        set_favorite(self.conn, 1)
        set_favorite(self.conn, 3)
        facets = search_facets(self.conn, favorites_only=True)
        self.assertEqual(facets["total"], 2)
        systems = {f["value"]: f["count"] for f in facets["game_system"]}
        self.assertEqual(systems["D&D 5e"], 1)
        self.assertEqual(systems["OSR"], 1)

    def test_get_book_returns_is_favorite(self):
        set_favorite(self.conn, 2)
        book = get_book(self.conn, 2)
        self.assertTrue(book["is_favorite"])
        book1 = get_book(self.conn, 1)
        self.assertFalse(book1["is_favorite"])

    def test_get_books_by_ids_returns_is_favorite(self):
        set_favorite(self.conn, 2)
        books = get_books_by_ids(self.conn, [1, 2])
        fav_flags = {b["id"]: b["is_favorite"] for b in books}
        self.assertFalse(fav_flags[1])
        self.assertTrue(fav_flags[2])

    def test_grouped_search_returns_is_favorite(self):
        set_favorite(self.conn, 1)
        result = search_books(self.conn, grouped=True)
        fav_flags = {r["id"]: r["is_favorite"] for r in result["results"]}
        self.assertTrue(fav_flags[1])

    def test_library_db_still_read_only(self):
        """Writes to the library DB (main) should fail — it's opened read-only."""
        with self.assertRaises(sqlite3.OperationalError):
            self.conn.execute("INSERT INTO books (id, filename) VALUES (99, 'x.pdf')")


if __name__ == "__main__":
    unittest.main()
