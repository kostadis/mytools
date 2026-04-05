#!/usr/bin/env python3
"""Tests for pdf_enricher.py"""

import json
import sqlite3
import unittest

from pdf_enricher import (
    build_book_summary,
    build_series_prompt,
    migrate_enrichment_schema,
    parse_json_response,
    save_enrichments,
    save_series,
    validate_enrichment,
    get_unenriched_books,
)


def make_test_db():
    """Create an in-memory DB with the Phase 1 schema and sample data."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL UNIQUE,
            relative_path TEXT NOT NULL,
            source TEXT,
            publisher TEXT,
            collection TEXT,
            pdf_title TEXT,
            pdf_author TEXT,
            pdf_creator TEXT,
            page_count INTEGER,
            has_bookmarks INTEGER NOT NULL DEFAULT 0,
            is_old_version INTEGER NOT NULL DEFAULT 0,
            version_generation INTEGER,
            product_id TEXT,
            product_version TEXT,
            first_page_text TEXT,
            date_indexed TEXT NOT NULL,
            game_system TEXT,
            product_type TEXT,
            description TEXT,
            date_enriched TEXT
        );
        CREATE TABLE bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            level INTEGER NOT NULL,
            title TEXT NOT NULL,
            page_number INTEGER,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
        );
        CREATE TABLE errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filepath TEXT NOT NULL,
            error_message TEXT NOT NULL,
            date_logged TEXT NOT NULL
        );
    """)
    return conn


def insert_book(conn, id, filename, publisher=None, collection=None,
                pdf_title=None, pdf_author=None, has_bookmarks=0,
                first_page_text=None, is_old_version=0, date_enriched=None):
    conn.execute(
        """INSERT INTO books (id, filename, filepath, relative_path, source,
            publisher, collection, pdf_title, pdf_author, page_count,
            has_bookmarks, is_old_version, first_page_text, date_indexed, date_enriched)
           VALUES (?, ?, ?, ?, 'test', ?, ?, ?, ?, 100, ?, ?, ?, '2026-01-01', ?)""",
        (id, filename, f"/test/{filename}", filename, publisher, collection,
         pdf_title, pdf_author, has_bookmarks, is_old_version, first_page_text,
         date_enriched),
    )
    conn.commit()


def insert_bookmarks(conn, book_id, bookmarks):
    """bookmarks: list of (level, title, page)"""
    conn.executemany(
        "INSERT INTO bookmarks (book_id, level, title, page_number) VALUES (?, ?, ?, ?)",
        [(book_id, level, title, page) for level, title, page in bookmarks],
    )
    conn.commit()


class TestMigration(unittest.TestCase):
    def test_adds_new_columns(self):
        conn = make_test_db()
        migrate_enrichment_schema(conn)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(books)")}
        self.assertIn("tags", cols)
        self.assertIn("series", cols)

    def test_idempotent(self):
        conn = make_test_db()
        migrate_enrichment_schema(conn)
        migrate_enrichment_schema(conn)  # should not fail
        cols = {row[1] for row in conn.execute("PRAGMA table_info(books)")}
        self.assertIn("tags", cols)

    def test_creates_indexes(self):
        conn = make_test_db()
        migrate_enrichment_schema(conn)
        indexes = {row[1] for row in conn.execute(
            "SELECT * FROM sqlite_master WHERE type='index'"
        )}
        self.assertIn("idx_books_game_system", indexes)
        self.assertIn("idx_books_product_type", indexes)
        self.assertIn("idx_books_series", indexes)


class TestGetUnenrichedBooks(unittest.TestCase):
    def setUp(self):
        self.conn = make_test_db()
        migrate_enrichment_schema(self.conn)

    def test_returns_unenriched_only(self):
        insert_book(self.conn, 1, "new.pdf", publisher="Pub")
        insert_book(self.conn, 2, "done.pdf", publisher="Pub", date_enriched="2026-01-01")
        books = get_unenriched_books(self.conn)
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["id"], 1)

    def test_skips_old_versions(self):
        insert_book(self.conn, 1, "current.pdf", publisher="Pub")
        insert_book(self.conn, 2, "old.pdf", publisher="Pub", is_old_version=1)
        books = get_unenriched_books(self.conn)
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["filename"], "current.pdf")

    def test_includes_bookmarks(self):
        insert_book(self.conn, 1, "book.pdf", publisher="Pub", has_bookmarks=1)
        insert_bookmarks(self.conn, 1, [(1, "Chapter 1", 1), (2, "Section 1.1", 3)])
        books = get_unenriched_books(self.conn)
        self.assertEqual(len(books[0]["bookmarks"]), 2)
        self.assertEqual(books[0]["bookmarks"][0], (1, "Chapter 1"))

    def test_limit(self):
        for i in range(20):
            insert_book(self.conn, i + 1, f"book{i}.pdf", publisher="Pub")
        books = get_unenriched_books(self.conn, limit=5)
        self.assertEqual(len(books), 5)

    def test_filter_by_publisher(self):
        insert_book(self.conn, 1, "a.pdf", publisher="Alpha")
        insert_book(self.conn, 2, "b.pdf", publisher="Beta")
        books = get_unenriched_books(self.conn, publisher="Alpha")
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["publisher"], "Alpha")

    def test_force_includes_enriched(self):
        insert_book(self.conn, 1, "done.pdf", publisher="Pub", date_enriched="2026-01-01")
        books = get_unenriched_books(self.conn, force=True)
        self.assertEqual(len(books), 1)


class TestBuildBookSummary(unittest.TestCase):
    def test_with_bookmarks(self):
        book = {
            "id": 1, "filename": "test.pdf", "publisher": "Pub",
            "collection": "Coll", "pdf_title": "Title", "pdf_author": "Author",
            "bookmarks": [(1, "Chapter 1"), (2, "Section 1.1")],
            "first_page_text": None,
        }
        summary = build_book_summary(book)
        self.assertIn("[Book 1]", summary)
        self.assertIn("publisher: Pub", summary)
        self.assertIn("Chapter 1", summary)
        self.assertIn("Section 1.1", summary)

    def test_with_first_page_text(self):
        book = {
            "id": 2, "filename": "nomarks.pdf", "publisher": None,
            "collection": None, "pdf_title": None, "pdf_author": None,
            "bookmarks": [], "first_page_text": "Welcome to this RPG adventure.",
        }
        summary = build_book_summary(book)
        self.assertIn("first_page_text:", summary)
        self.assertIn("Welcome to this RPG", summary)

    def test_no_data(self):
        book = {
            "id": 3, "filename": "mystery.pdf", "publisher": None,
            "collection": None, "pdf_title": None, "pdf_author": None,
            "bookmarks": [], "first_page_text": None,
        }
        summary = build_book_summary(book)
        self.assertIn("no bookmarks or text available", summary)

    def test_truncates_first_page_text(self):
        book = {
            "id": 4, "filename": "long.pdf", "publisher": None,
            "collection": None, "pdf_title": None, "pdf_author": None,
            "bookmarks": [], "first_page_text": "x" * 5000,
        }
        summary = build_book_summary(book)
        # Should be truncated to 1500 chars
        self.assertLess(len(summary), 2000)


class TestBuildSeriesPrompt(unittest.TestCase):
    def test_format(self):
        books = [
            {"id": 1, "filename": "a.pdf", "collection": "Dungeon Dressing: Altars", "pdf_title": "Altars"},
            {"id": 2, "filename": "b.pdf", "collection": "Dungeon Dressing: Bridges", "pdf_title": "Bridges"},
        ]
        prompt = build_series_prompt("Raging Swan Press", books)
        self.assertIn("Raging Swan Press", prompt)
        self.assertIn("[Book 1]", prompt)
        self.assertIn("[Book 2]", prompt)


class TestParseJsonResponse(unittest.TestCase):
    def test_plain_json(self):
        result = parse_json_response('[{"book_id": 1, "game_system": "D&D 5e"}]')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["game_system"], "D&D 5e")

    def test_markdown_fenced(self):
        text = '```json\n[{"book_id": 1, "game_system": "D&D 5e"}]\n```'
        result = parse_json_response(text)
        self.assertEqual(len(result), 1)

    def test_markdown_fenced_no_lang(self):
        text = '```\n{"series": "Test"}\n```'
        result = parse_json_response(text)
        self.assertEqual(result["series"], "Test")

    def test_invalid_json_raises(self):
        with self.assertRaises(json.JSONDecodeError):
            parse_json_response("not json at all")

    def test_dict_response(self):
        result = parse_json_response('{"Dungeon Dressing": [1, 2, 3]}')
        self.assertIsInstance(result, dict)


class TestValidateEnrichment(unittest.TestCase):
    def test_valid_entry(self):
        entry = {
            "book_id": 1, "game_system": "D&D 5e", "product_type": "adventure",
            "tags": ["adventure", "5e"], "series": None,
            "description": "An adventure module.",
        }
        result = validate_enrichment(entry)
        self.assertIsNotNone(result)
        self.assertEqual(result["product_type"], "adventure")

    def test_missing_required_field(self):
        entry = {"book_id": 1, "game_system": "D&D 5e"}  # missing others
        result = validate_enrichment(entry)
        self.assertIsNone(result)

    def test_invalid_product_type_fuzzy_match(self):
        entry = {
            "book_id": 1, "game_system": "D&D 5e",
            "product_type": "magic items collection",
            "tags": ["magic_items"], "description": "Items.",
        }
        result = validate_enrichment(entry)
        self.assertEqual(result["product_type"], "magic_items")

    def test_invalid_product_type_fallback(self):
        entry = {
            "book_id": 1, "game_system": "D&D 5e",
            "product_type": "completely_unknown_type",
            "tags": ["stuff"], "description": "Something.",
        }
        result = validate_enrichment(entry)
        self.assertEqual(result["product_type"], "sourcebook")

    def test_tags_not_list_normalized(self):
        entry = {
            "book_id": 1, "game_system": "D&D 5e", "product_type": "adventure",
            "tags": "adventure", "description": "An adventure.",
        }
        result = validate_enrichment(entry)
        self.assertEqual(result["tags"], ["adventure"])

    def test_missing_series_defaults_none(self):
        entry = {
            "book_id": 1, "game_system": "D&D 5e", "product_type": "adventure",
            "tags": ["adventure"], "description": "An adventure.",
        }
        result = validate_enrichment(entry)
        self.assertIsNone(result["series"])

    def test_low_confidence_tagged(self):
        entry = {
            "book_id": 1, "game_system": "D&D 5e", "product_type": "map_pack",
            "tags": ["map_pack"], "description": "A map.",
        }
        result = validate_enrichment(entry, low_confidence_ids={1})
        self.assertIn("low_confidence", result["tags"])

    def test_low_confidence_not_tagged_when_not_in_set(self):
        entry = {
            "book_id": 1, "game_system": "D&D 5e", "product_type": "adventure",
            "tags": ["adventure"], "description": "An adventure.",
        }
        result = validate_enrichment(entry, low_confidence_ids={99})
        self.assertNotIn("low_confidence", result["tags"])

    def test_low_confidence_not_duplicated(self):
        entry = {
            "book_id": 1, "game_system": "D&D 5e", "product_type": "map_pack",
            "tags": ["map_pack", "low_confidence"], "description": "A map.",
        }
        result = validate_enrichment(entry, low_confidence_ids={1})
        self.assertEqual(result["tags"].count("low_confidence"), 1)


class TestSaveEnrichments(unittest.TestCase):
    def setUp(self):
        self.conn = make_test_db()
        migrate_enrichment_schema(self.conn)
        insert_book(self.conn, 1, "test.pdf", publisher="Pub")

    def test_saves_all_fields(self):
        enrichments = [{
            "book_id": 1, "game_system": "D&D 5e", "product_type": "adventure",
            "tags": ["adventure", "5e"], "series": "Test Series",
            "description": "A test adventure.",
        }]
        count = save_enrichments(self.conn, enrichments)
        self.assertEqual(count, 1)

        row = self.conn.execute(
            "SELECT game_system, product_type, tags, series, description, date_enriched "
            "FROM books WHERE id=1"
        ).fetchone()
        self.assertEqual(row[0], "D&D 5e")
        self.assertEqual(row[1], "adventure")
        self.assertEqual(json.loads(row[2]), ["adventure", "5e"])
        self.assertEqual(row[3], "Test Series")
        self.assertEqual(row[4], "A test adventure.")
        self.assertIsNotNone(row[5])  # date_enriched set

    def test_null_series(self):
        enrichments = [{
            "book_id": 1, "game_system": "OSR", "product_type": "sourcebook",
            "tags": ["sourcebook", "osr"], "series": None,
            "description": "A sourcebook.",
        }]
        save_enrichments(self.conn, enrichments)
        row = self.conn.execute("SELECT series FROM books WHERE id=1").fetchone()
        self.assertIsNone(row[0])


class TestSaveSeries(unittest.TestCase):
    def setUp(self):
        self.conn = make_test_db()
        migrate_enrichment_schema(self.conn)
        insert_book(self.conn, 1, "dd_altars.pdf", publisher="RSP")
        insert_book(self.conn, 2, "dd_bridges.pdf", publisher="RSP")
        insert_book(self.conn, 3, "vb_ashford.pdf", publisher="RSP")

    def test_saves_series(self):
        series_map = {
            "Dungeon Dressing": [1, 2],
            "Village Backdrop": [3],
        }
        count = save_series(self.conn, series_map)
        self.assertEqual(count, 3)

        row1 = self.conn.execute("SELECT series FROM books WHERE id=1").fetchone()
        row3 = self.conn.execute("SELECT series FROM books WHERE id=3").fetchone()
        self.assertEqual(row1[0], "Dungeon Dressing")
        self.assertEqual(row3[0], "Village Backdrop")

    def test_empty_series_map(self):
        count = save_series(self.conn, {})
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
