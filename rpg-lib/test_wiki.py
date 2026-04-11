#!/usr/bin/env python3
"""
Tests for wiki features: wiki_setup, relation_builder, library_api/db (wiki
functions), and library_api/nlq.
"""

import json
import sqlite3
import sys
import unittest
from unittest.mock import patch, MagicMock

from wiki_setup import setup_fts, setup_topic_overviews, setup_book_relations
from relation_builder import load_books, build_relations, save_relations
from library_api.db import (
    get_books_by_ids,
    get_graph,
    get_related_books,
    get_topic,
    nlq_search,
    search_books,
    search_facets,
    _row_to_summary,
    _topic_stats,
    _topic_where,
)
from library_api.nlq import _fts_safe, parse_query


# ── Shared fixtures ───────────────────────────────────────────────────────────

def make_db(with_wiki_tables: bool = True) -> sqlite3.Connection:
    """In-memory DB with the full books/bookmarks schema plus optional wiki tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
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
    if with_wiki_tables:
        setup_topic_overviews(conn)
        setup_book_relations(conn)
    return conn


def add_book(conn, id, filename, *, display_title=None, publisher=None,
             game_system=None, product_type=None, series=None, tags=None,
             description=None, page_count=100, is_old_version=0,
             is_draft=0, is_duplicate=0, date_enriched=None):
    conn.execute(
        """INSERT INTO books
               (id, filename, display_title, publisher, game_system, product_type,
                series, tags, description, page_count, is_old_version, is_draft,
                is_duplicate, date_enriched)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (id, filename, display_title or filename.replace(".pdf", ""),
         publisher, game_system, product_type, series,
         json.dumps(tags) if tags is not None else None,
         description, page_count, is_old_version, is_draft, is_duplicate,
         date_enriched),
    )
    conn.commit()


def populate_fts(conn):
    """Manually populate books_fts from books (mirrors wiki_setup behaviour)."""
    conn.execute("""
        INSERT INTO books_fts(rowid, display_title, description, tags, series, game_system)
        SELECT id,
            COALESCE(display_title, ''), COALESCE(description, ''),
            COALESCE(tags, ''), COALESCE(series, ''), COALESCE(game_system, '')
        FROM books
        WHERE is_old_version = 0 AND is_draft = 0 AND is_duplicate = 0
    """)
    conn.commit()


# ── wiki_setup tests ──────────────────────────────────────────────────────────

class TestSetupFts(unittest.TestCase):
    def make_books_db(self):
        conn = make_db(with_wiki_tables=False)
        # Give each excluded book a unique keyword so we can verify it's NOT indexed
        add_book(conn, 1, "a.pdf", description="active uniqueword1")
        add_book(conn, 2, "b.pdf", description="oldver uniqueword2", is_old_version=1)
        add_book(conn, 3, "c.pdf", description="draft uniqueword3", is_draft=1)
        add_book(conn, 4, "d.pdf", description="dupl uniqueword4", is_duplicate=1)
        return conn

    def _fts_ids(self, conn, term):
        """Return rowids from books_fts matching term."""
        return [r[0] for r in conn.execute(
            "SELECT rowid FROM books_fts WHERE books_fts MATCH ?", (term,)
        ).fetchall()]

    def test_creates_fts_table(self):
        conn = self.make_books_db()
        setup_fts(conn)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        self.assertIn("books_fts", tables)

    def test_indexes_only_active_books(self):
        conn = self.make_books_db()
        setup_fts(conn)
        # Active book is findable
        self.assertEqual(self._fts_ids(conn, "uniqueword1"), [1])
        # Excluded books are not indexed
        self.assertEqual(self._fts_ids(conn, "uniqueword2"), [])
        self.assertEqual(self._fts_ids(conn, "uniqueword3"), [])
        self.assertEqual(self._fts_ids(conn, "uniqueword4"), [])

    def test_rebuild_drops_and_recreates(self):
        conn = self.make_books_db()
        setup_fts(conn)
        # Add another active book with a unique word, then rebuild
        add_book(conn, 5, "e.pdf", description="new uniqueword5")
        setup_fts(conn, rebuild=True)
        self.assertEqual(self._fts_ids(conn, "uniqueword5"), [5])
        self.assertEqual(self._fts_ids(conn, "uniqueword1"), [1])

    def test_idempotent_without_rebuild(self):
        conn = self.make_books_db()
        setup_fts(conn)
        setup_fts(conn, rebuild=False)  # should skip without re-inserting
        # Book 1 should match exactly once, not twice
        results = self._fts_ids(conn, "uniqueword1")
        self.assertEqual(results, [1])


class TestSetupTopicOverviews(unittest.TestCase):
    def test_creates_table(self):
        conn = make_db(with_wiki_tables=False)
        setup_topic_overviews(conn)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        self.assertIn("topic_overviews", tables)

    def test_idempotent(self):
        conn = make_db(with_wiki_tables=False)
        setup_topic_overviews(conn)
        setup_topic_overviews(conn)  # must not raise

    def test_unique_constraint(self):
        conn = make_db(with_wiki_tables=False)
        setup_topic_overviews(conn)
        conn.execute(
            "INSERT INTO topic_overviews(topic_type, topic_name) VALUES ('tag', 'horror')"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO topic_overviews(topic_type, topic_name) VALUES ('tag', 'horror')"
            )


class TestSetupBookRelations(unittest.TestCase):
    def test_creates_table_and_index(self):
        conn = make_db(with_wiki_tables=False)
        setup_book_relations(conn)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','index')"
        ).fetchall()}
        self.assertIn("book_relations", tables)
        self.assertIn("idx_relations_a", tables)

    def test_idempotent(self):
        conn = make_db(with_wiki_tables=False)
        setup_book_relations(conn)
        setup_book_relations(conn)  # must not raise


# ── relation_builder tests ────────────────────────────────────────────────────

class TestLoadBooks(unittest.TestCase):
    def setUp(self):
        self.conn = make_db(with_wiki_tables=False)

    def test_loads_tagged_books(self):
        add_book(self.conn, 1, "a.pdf", tags=["dungeon", "horror"])
        books = load_books(self.conn)
        self.assertEqual(len(books), 1)
        self.assertEqual(books[1], {"dungeon", "horror"})

    def test_skips_books_without_tags(self):
        add_book(self.conn, 1, "a.pdf", tags=[])
        add_book(self.conn, 2, "b.pdf")  # tags column NULL
        books = load_books(self.conn)
        self.assertEqual(len(books), 0)

    def test_skips_old_draft_duplicate(self):
        add_book(self.conn, 1, "a.pdf", tags=["dungeon"])
        add_book(self.conn, 2, "b.pdf", tags=["dungeon"], is_old_version=1)
        add_book(self.conn, 3, "c.pdf", tags=["dungeon"], is_draft=1)
        add_book(self.conn, 4, "d.pdf", tags=["dungeon"], is_duplicate=1)
        books = load_books(self.conn)
        self.assertEqual(list(books.keys()), [1])


class TestBuildRelations(unittest.TestCase):
    def _books(self, spec):
        """spec: {id: set_of_tags}"""
        return {k: set(v) for k, v in spec.items()}

    def test_jaccard_perfect_overlap(self):
        books = self._books({1: ["a", "b"], 2: ["a", "b"]})
        rels = build_relations(books, min_score=0.0, top_k=10)
        scores = {(r[0], r[1]): r[2] for r in rels}
        self.assertAlmostEqual(scores[(1, 2)], 1.0)
        self.assertAlmostEqual(scores[(2, 1)], 1.0)

    def test_jaccard_no_overlap(self):
        books = self._books({1: ["a"], 2: ["b"]})
        rels = build_relations(books, min_score=0.0, top_k=10)
        self.assertEqual(len(rels), 0)

    def test_jaccard_partial_overlap(self):
        # tags_A = {a, b, c}, tags_B = {b, c, d}
        # intersection = {b, c} = 2, union = {a, b, c, d} = 4 → 0.5
        books = self._books({1: ["a", "b", "c"], 2: ["b", "c", "d"]})
        rels = build_relations(books, min_score=0.0, top_k=10)
        scores = {(r[0], r[1]): r[2] for r in rels}
        self.assertAlmostEqual(scores[(1, 2)], 0.5)

    def test_min_score_filter(self):
        books = self._books({1: ["a", "b", "c"], 2: ["b", "c", "d"]})
        rels = build_relations(books, min_score=0.6, top_k=10)
        self.assertEqual(len(rels), 0)

    def test_top_k_per_book(self):
        # Book 1 is similar to books 2-11; only top 3 should be kept
        books = {i: {"tag_common", f"tag_{i}"} for i in range(1, 12)}
        rels = build_relations(books, min_score=0.0, top_k=3)
        # Check that book 1 has at most 3 relations
        book1_rels = [r for r in rels if r[0] == 1]
        self.assertLessEqual(len(book1_rels), 3)

    def test_high_frequency_tags_skipped(self):
        # Create a tag shared by MAX_TAG_BOOKS+1 books so it gets skipped
        from relation_builder import MAX_TAG_BOOKS
        n = MAX_TAG_BOOKS + 1
        books = {i: {"common_tag"} for i in range(1, n + 1)}
        books[1].add("unique_tag")
        books[2].add("unique_tag")
        rels = build_relations(books, min_score=0.0, top_k=10)
        # common_tag is skipped; unique_tag overlap should still produce a pair
        pairs = {(r[0], r[1]) for r in rels}
        self.assertIn((1, 2), pairs)
        self.assertIn((2, 1), pairs)

    def test_shared_tags_count_correct(self):
        books = self._books({1: ["a", "b", "c"], 2: ["b", "c", "d"]})
        rels = build_relations(books, min_score=0.0, top_k=10)
        counts = {(r[0], r[1]): r[3] for r in rels}
        self.assertEqual(counts[(1, 2)], 2)

    def test_both_directions_stored(self):
        books = self._books({1: ["a", "b"], 2: ["a", "b"]})
        rels = build_relations(books, min_score=0.0, top_k=10)
        pairs = {(r[0], r[1]) for r in rels}
        self.assertIn((1, 2), pairs)
        self.assertIn((2, 1), pairs)


class TestSaveRelations(unittest.TestCase):
    def setUp(self):
        self.conn = make_db(with_wiki_tables=True)

    def test_saves_relations(self):
        save_relations(self.conn, [(1, 2, 0.8, 4), (2, 1, 0.8, 4)])
        count = self.conn.execute("SELECT COUNT(*) FROM book_relations").fetchone()[0]
        self.assertEqual(count, 2)

    def test_clears_existing_before_save(self):
        save_relations(self.conn, [(1, 2, 0.8, 4)])
        save_relations(self.conn, [(3, 4, 0.5, 2)])
        count = self.conn.execute("SELECT COUNT(*) FROM book_relations").fetchone()[0]
        self.assertEqual(count, 1)

    def test_saves_score_correctly(self):
        save_relations(self.conn, [(1, 2, 0.75, 3)])
        row = self.conn.execute(
            "SELECT score, shared_tags_count FROM book_relations WHERE book_id_a=1"
        ).fetchone()
        self.assertAlmostEqual(row["score"], 0.75)
        self.assertEqual(row["shared_tags_count"], 3)


# ── library_api/db wiki function tests ───────────────────────────────────────

class TestTopicWhere(unittest.TestCase):
    def test_tag(self):
        where, params = _topic_where("tag", "horror")
        self.assertIn('tags LIKE ?', where)
        self.assertIn('%"horror"%', params[0])

    def test_game_system(self):
        where, params = _topic_where("game_system", "D&D 5e")
        self.assertIn("game_system = ?", where)
        self.assertEqual(params[0], "D&D 5e")

    def test_series(self):
        where, params = _topic_where("series", "Waterdeep")
        self.assertIn("series = ?", where)

    def test_publisher(self):
        where, params = _topic_where("publisher", "Kobold Press")
        self.assertIn("publisher = ?", where)


class TestTopicStats(unittest.TestCase):
    def setUp(self):
        self.conn = make_db()
        add_book(self.conn, 1, "a.pdf", game_system="D&D 5e",
                 product_type="Adventure", publisher="WotC",
                 series="Waterdeep", tags=["dungeon", "urban"],
                 date_enriched="2026-01-01")
        add_book(self.conn, 2, "b.pdf", game_system="D&D 5e",
                 product_type="Sourcebook", publisher="Kobold",
                 tags=["dungeon", "rules"])
        add_book(self.conn, 3, "c.pdf", game_system="OSR",
                 product_type="Adventure", publisher="WotC",
                 tags=["dungeon"])
        add_book(self.conn, 4, "d.pdf", game_system="D&D 5e",
                 is_old_version=1)  # excluded

    def _stats(self, topic_type, topic_name):
        where, params = _topic_where(topic_type, topic_name)
        return _topic_stats(self.conn, topic_type, where, params)

    def test_total_count(self):
        stats = self._stats("game_system", "D&D 5e")
        self.assertEqual(stats["total"], 2)

    def test_enriched_count(self):
        stats = self._stats("game_system", "D&D 5e")
        self.assertEqual(stats["enriched"], 1)

    def test_by_product_type(self):
        stats = self._stats("game_system", "D&D 5e")
        types = {x["value"]: x["count"] for x in stats["by_product_type"]}
        self.assertEqual(types.get("Adventure"), 1)
        self.assertEqual(types.get("Sourcebook"), 1)

    def test_top_publishers_absent_for_publisher_type(self):
        stats = self._stats("publisher", "WotC")
        self.assertEqual(stats["top_publishers"], [])

    def test_top_tags_absent_for_tag_type(self):
        stats = self._stats("tag", "dungeon")
        self.assertEqual(stats["top_tags"], [])

    def test_top_series_absent_for_series_type(self):
        stats = self._stats("series", "Waterdeep")
        self.assertEqual(stats["top_series"], [])

    def test_top_game_systems_absent_for_game_system_type(self):
        stats = self._stats("game_system", "D&D 5e")
        self.assertEqual(stats["top_game_systems"], [])

    def test_top_tags_computed_from_json(self):
        stats = self._stats("game_system", "D&D 5e")
        tags = {x["value"]: x["count"] for x in stats["top_tags"]}
        self.assertEqual(tags.get("dungeon"), 2)  # both 5e books have it
        self.assertEqual(tags.get("urban"), 1)

    def test_top_publishers_sorted_descending(self):
        # WotC appears for game_system OSR; Kobold for 5e
        stats = self._stats("tag", "dungeon")  # all 3 books
        pubs = [x["value"] for x in stats["top_publishers"]]
        # WotC (2) should come before Kobold (1)
        if "WotC" in pubs and "Kobold" in pubs:
            self.assertLess(pubs.index("WotC"), pubs.index("Kobold"))


class TestGetTopic(unittest.TestCase):
    def setUp(self):
        self.conn = make_db()
        add_book(self.conn, 1, "a.pdf", game_system="D&D 5e",
                 product_type="Adventure", publisher="WotC",
                 tags=["dungeon", "horror"], series="Curse of Strahd")
        add_book(self.conn, 2, "b.pdf", game_system="D&D 5e",
                 product_type="Sourcebook", tags=["rules"])
        add_book(self.conn, 3, "c.pdf", game_system="OSR",
                 tags=["dungeon"])

    def test_game_system(self):
        result = get_topic(self.conn, "game_system", "D&D 5e")
        self.assertIsNotNone(result)
        self.assertEqual(result["stats"]["total"], 2)
        self.assertEqual(len(result["books"]), 2)

    def test_tag(self):
        result = get_topic(self.conn, "tag", "dungeon")
        self.assertIsNotNone(result)
        self.assertEqual(result["stats"]["total"], 2)

    def test_series(self):
        result = get_topic(self.conn, "series", "Curse of Strahd")
        self.assertIsNotNone(result)
        self.assertEqual(result["stats"]["total"], 1)

    def test_publisher(self):
        result = get_topic(self.conn, "publisher", "WotC")
        self.assertIsNotNone(result)
        self.assertEqual(result["stats"]["total"], 1)

    def test_invalid_type_returns_none(self):
        result = get_topic(self.conn, "invalid", "whatever")
        self.assertIsNone(result)

    def test_missing_topic_returns_none(self):
        result = get_topic(self.conn, "game_system", "Nonexistent System")
        self.assertIsNone(result)

    def test_books_sorted_by_title(self):
        result = get_topic(self.conn, "game_system", "D&D 5e")
        titles = [b["display_title"] or b["filename"] for b in result["books"]]
        self.assertEqual(titles, sorted(titles))

    def test_response_shape(self):
        result = get_topic(self.conn, "game_system", "D&D 5e")
        self.assertIn("topic_type", result)
        self.assertIn("topic_name", result)
        self.assertIn("stats", result)
        self.assertIn("books", result)


class TestGetRelatedBooks(unittest.TestCase):
    def setUp(self):
        self.conn = make_db()
        add_book(self.conn, 1, "a.pdf", tags=["dungeon", "horror", "undead"])
        add_book(self.conn, 2, "b.pdf", tags=["dungeon", "horror"])
        add_book(self.conn, 3, "c.pdf", tags=["dungeon"])
        add_book(self.conn, 4, "d.pdf", tags=["horror", "undead"])
        add_book(self.conn, 5, "e.pdf", tags=["sci_fi"])

    def test_uses_book_relations_when_populated(self):
        self.conn.execute(
            "INSERT INTO book_relations VALUES (1, 2, 0.9, 2)"
        )
        self.conn.execute(
            "INSERT INTO book_relations VALUES (1, 4, 0.7, 2)"
        )
        self.conn.commit()
        results = get_related_books(self.conn, 1, limit=6)
        ids = [r["id"] for r in results]
        self.assertEqual(ids[0], 2)  # highest score first
        self.assertEqual(ids[1], 4)

    def test_fallback_tag_overlap(self):
        # No book_relations; should fall back to tag overlap
        results = get_related_books(self.conn, 1, limit=4)
        ids = {r["id"] for r in results}
        # Book 2 shares 2 tags (dungeon, horror), book 4 shares 2 (horror, undead)
        # Book 3 shares 1 tag (dungeon)
        self.assertIn(2, ids)
        self.assertIn(4, ids)
        # Book 5 shares nothing — should not appear
        self.assertNotIn(5, ids)

    def test_fallback_excludes_self(self):
        results = get_related_books(self.conn, 1, limit=10)
        ids = [r["id"] for r in results]
        self.assertNotIn(1, ids)

    def test_series_boost_in_fallback(self):
        add_book(self.conn, 6, "f.pdf", tags=["rules"], series="MySeries")
        add_book(self.conn, 7, "g.pdf", tags=["rules", "dungeon"], series="MySeries")
        results = get_related_books(self.conn, 6, limit=6)
        ids = [r["id"] for r in results]
        # Book 7 is in the same series — should appear first
        self.assertEqual(ids[0], 7)

    def test_respects_limit(self):
        results = get_related_books(self.conn, 1, limit=2)
        self.assertLessEqual(len(results), 2)

    def test_no_relations_no_tags_returns_empty(self):
        add_book(self.conn, 99, "empty.pdf")
        results = get_related_books(self.conn, 99, limit=6)
        self.assertEqual(results, [])


class TestGetGraph(unittest.TestCase):
    def setUp(self):
        self.conn = make_db()
        add_book(self.conn, 1, "a.pdf", game_system="D&D 5e")
        add_book(self.conn, 2, "b.pdf", game_system="D&D 5e")
        add_book(self.conn, 3, "c.pdf", game_system="OSR")
        # Relations (both directions)
        self.conn.executemany(
            "INSERT INTO book_relations VALUES (?, ?, ?, ?)",
            [(1, 2, 0.8, 4), (2, 1, 0.8, 4),
             (1, 3, 0.3, 2), (3, 1, 0.3, 2),
             (2, 3, 0.2, 1), (3, 2, 0.2, 1)],
        )
        self.conn.commit()

    def test_returns_nodes_and_edges(self):
        result = get_graph(self.conn, min_score=0.1, limit=300)
        self.assertIn("nodes", result)
        self.assertIn("edges", result)
        self.assertGreater(len(result["nodes"]), 0)
        self.assertGreater(len(result["edges"]), 0)

    def test_min_score_filters_edges(self):
        result = get_graph(self.conn, min_score=0.5, limit=300)
        for edge in result["edges"]:
            self.assertGreaterEqual(edge["score"], 0.5)

    def test_game_system_filter(self):
        result = get_graph(self.conn, min_score=0.0, limit=300,
                           game_system="D&D 5e")
        node_ids = {n["id"] for n in result["nodes"]}
        self.assertNotIn(3, node_ids)  # OSR book excluded

    def test_empty_when_no_relations(self):
        conn = make_db()
        add_book(conn, 1, "a.pdf")
        result = get_graph(conn, min_score=0.1, limit=300)
        self.assertEqual(result["nodes"], [])
        self.assertEqual(result["edges"], [])

    def test_nodes_have_required_fields(self):
        result = get_graph(self.conn, min_score=0.1, limit=300)
        for node in result["nodes"]:
            self.assertIn("id", node)
            self.assertIn("label", node)
            self.assertIn("group", node)

    def test_edges_deduplicated(self):
        # Edges should be stored as a < b (one direction) in the graph response
        result = get_graph(self.conn, min_score=0.1, limit=300)
        pairs = [(e["source"], e["target"]) for e in result["edges"]]
        reversed_pairs = [(e["target"], e["source"]) for e in result["edges"]]
        # No pair should appear alongside its reverse
        overlap = set(pairs) & set(reversed_pairs)
        self.assertEqual(len(overlap), 0)


class TestNlqSearch(unittest.TestCase):
    def setUp(self):
        self.conn = make_db()
        add_book(self.conn, 1, "horror.pdf", description="A terrifying horror dungeon",
                 game_system="D&D 5e", product_type="Adventure")
        add_book(self.conn, 2, "space.pdf", description="A space sci-fi adventure",
                 game_system="Mothership", product_type="Sourcebook")
        add_book(self.conn, 3, "old.pdf", is_old_version=1,
                 description="horror dungeon")
        # Set up FTS
        setup_fts(self.conn)
        populate_fts(self.conn)

    def test_fts_search_returns_match(self):
        results = nlq_search(self.conn, keywords="horror dungeon")
        ids = [r["id"] for r in results]
        self.assertIn(1, ids)
        self.assertNotIn(3, ids)  # old version excluded

    def test_fts_with_game_system_filter(self):
        # Book 1 has "horror dungeon" and game_system D&D 5e
        # Book 2 has "space sci-fi" and game_system Mothership
        results = nlq_search(self.conn, keywords="horror",
                             game_system="D&D 5e")
        ids = [r["id"] for r in results]
        self.assertIn(1, ids)
        self.assertNotIn(2, ids)

    def test_fts_with_product_type_filter(self):
        results = nlq_search(self.conn, keywords="adventure",
                             product_type="Sourcebook")
        ids = [r["id"] for r in results]
        self.assertIn(2, ids)
        self.assertNotIn(1, ids)

    def test_fts_with_tag_filter(self):
        add_book(self.conn, 4, "tagged.pdf", description="horror adventure",
                 tags=["dungeon", "horror"])
        # Rebuild FTS with new book
        self.conn.execute("DROP TABLE books_fts")
        setup_fts(self.conn)
        populate_fts(self.conn)
        results = nlq_search(self.conn, keywords="horror", tags=["dungeon"])
        ids = [r["id"] for r in results]
        self.assertIn(4, ids)
        self.assertNotIn(1, ids)  # book 1 has no tags

    def test_fallback_when_no_fts(self):
        # Drop FTS to force fallback path
        conn = make_db()
        add_book(conn, 1, "a.pdf", description="horror dungeon adventure")
        results = nlq_search(conn, keywords="horror")
        ids = [r["id"] for r in results]
        self.assertIn(1, ids)


# ── library_api/nlq tests ─────────────────────────────────────────────────────

class TestFtsSafe(unittest.TestCase):
    def test_strips_special_chars(self):
        result = _fts_safe('horror "undead" (dungeons)')
        self.assertNotIn('"', result)
        self.assertNotIn('(', result)
        self.assertNotIn(')', result)

    def test_keeps_alphanumeric(self):
        result = _fts_safe("horror dungeon adventure")
        self.assertIn("horror", result)
        self.assertIn("dungeon", result)

    def test_limits_to_12_words(self):
        long_input = " ".join(f"word{i}" for i in range(20))
        result = _fts_safe(long_input)
        self.assertLessEqual(len(result.split()), 12)

    def test_handles_empty_string(self):
        result = _fts_safe("")
        self.assertEqual(result, "")

    def test_handles_only_special_chars(self):
        result = _fts_safe("!@#$%^&*()")
        self.assertEqual(result.strip(), "")


class TestParseQuery(unittest.TestCase):
    MOCK_RESPONSE = json.dumps({
        "game_system": "D&D 5e",
        "product_type": "Adventure",
        "tags": ["horror", "undead"],
        "keywords": "horror undead dungeon",
    })

    def test_extracts_all_fields(self):
        with patch("library_api.nlq.call_api", return_value=self.MOCK_RESPONSE):
            with patch("library_api.nlq._get_client", return_value=MagicMock()):
                result = parse_query("horror adventures for D&D 5e with undead")
        self.assertEqual(result["game_system"], "D&D 5e")
        self.assertEqual(result["product_type"], "Adventure")
        self.assertIn("horror", result["tags"])
        self.assertEqual(result["keywords"], "horror undead dungeon")

    def test_handles_markdown_fenced_json(self):
        fenced = "```json\n" + self.MOCK_RESPONSE + "\n```"
        with patch("library_api.nlq.call_api", return_value=fenced):
            with patch("library_api.nlq._get_client", return_value=MagicMock()):
                result = parse_query("horror D&D 5e")
        self.assertEqual(result["game_system"], "D&D 5e")

    def test_null_fields_become_none(self):
        response = json.dumps({
            "game_system": None,
            "product_type": None,
            "tags": [],
            "keywords": "dungeon",
        })
        with patch("library_api.nlq.call_api", return_value=response):
            with patch("library_api.nlq._get_client", return_value=MagicMock()):
                result = parse_query("dungeon stuff")
        self.assertIsNone(result["game_system"])
        self.assertIsNone(result["product_type"])
        self.assertEqual(result["tags"], [])

    def test_fallback_on_invalid_json(self):
        with patch("library_api.nlq.call_api", return_value="not json at all"):
            with patch("library_api.nlq._get_client", return_value=MagicMock()):
                result = parse_query("horror dungeon")
        # Should fall back: no game_system, keywords from original query
        self.assertIsNone(result["game_system"])
        self.assertIn("horror", result["keywords"])

    def test_fallback_on_api_error(self):
        with patch("library_api.nlq.call_api", side_effect=Exception("API error")):
            with patch("library_api.nlq._get_client", return_value=MagicMock()):
                result = parse_query("horror dungeon")
        self.assertIsNone(result["game_system"])
        self.assertIsNone(result["product_type"])
        self.assertEqual(result["tags"], [])

    def test_tags_must_be_strings(self):
        response = json.dumps({
            "game_system": None, "product_type": None,
            "tags": ["horror", 42, None, "dungeon"],
            "keywords": "horror",
        })
        with patch("library_api.nlq.call_api", return_value=response):
            with patch("library_api.nlq._get_client", return_value=MagicMock()):
                result = parse_query("horror dungeon")
        # Non-string tags should be filtered out
        self.assertEqual(result["tags"], ["horror", "dungeon"])

    def test_keywords_sanitized(self):
        response = json.dumps({
            "game_system": None, "product_type": None,
            "tags": [],
            "keywords": 'horror "undead" (stuff)',
        })
        with patch("library_api.nlq.call_api", return_value=response):
            with patch("library_api.nlq._get_client", return_value=MagicMock()):
                result = parse_query("horror undead stuff")
        self.assertNotIn('"', result["keywords"])


# ── _row_to_summary contract tests ────────────────────────────────────────────
#
# Every function in library_api/db.py that returns summaries must project
# every column that _row_to_summary reads. This is enforced structurally: if
# a SELECT drops a column, sqlite3.Row[col] raises IndexError as soon as a
# non-empty result reaches _row_to_summary. These tests feed each call site
# at least one non-empty result and verify every expected key is present, so
# any future column added to _row_to_summary but forgotten in a SELECT gets
# caught here rather than in production.
#
# Regression: a previous change added min_level/max_level to _row_to_summary
# but only updated the grouped search_books path and the FTS nlq_search path.
# Six other call sites silently broke for any query that returned rows.

EXPECTED_SUMMARY_KEYS = {
    "id", "display_title", "filename", "publisher", "collection",
    "game_system", "product_type", "tags", "series", "source",
    "page_count", "has_bookmarks", "description", "min_level", "max_level",
}


class TestRowToSummaryContract(unittest.TestCase):
    """Each _row_to_summary call site must return rows with the full key set."""

    def _populated_db(self, with_fts: bool = True):
        """DB with three related horror books in the same series + book_relations."""
        conn = make_db(with_wiki_tables=True)
        add_book(conn, 1, "curse.pdf", display_title="Curse of Strahd",
                 publisher="WotC", game_system="D&D 5e", product_type="Adventure",
                 series="Ravenloft", tags=["horror", "undead"],
                 description="A gothic horror adventure in Barovia.",
                 date_enriched="2026-01-01")
        add_book(conn, 2, "ravenloft.pdf", display_title="Van Richten's Guide",
                 publisher="WotC", game_system="D&D 5e", product_type="Sourcebook",
                 series="Ravenloft", tags=["horror", "undead"],
                 description="A guide to the domains of dread.",
                 date_enriched="2026-01-01")
        add_book(conn, 3, "tyranny.pdf", display_title="Tyranny of Dragons",
                 publisher="WotC", game_system="D&D 5e", product_type="Adventure",
                 series="Tyranny", tags=["dragons"],
                 description="A five-part dragon campaign.",
                 date_enriched="2026-01-01")
        # min_level/max_level are NULL by default, which is a valid state —
        # the contract is "key present", not "value non-null".
        conn.execute("UPDATE books SET min_level=1, max_level=10 WHERE id=1")
        conn.commit()

        # Populate book_relations so get_related_books hits its primary path.
        conn.execute(
            "INSERT INTO book_relations (book_id_a, book_id_b, score) VALUES (?, ?, ?)",
            (1, 2, 0.9),
        )
        conn.commit()

        if with_fts:
            setup_fts(conn)
        return conn

    def _assert_summary_shape(self, summary: dict, where: str):
        missing = EXPECTED_SUMMARY_KEYS - set(summary.keys())
        self.assertFalse(
            missing,
            f"{where} returned summary missing keys: {sorted(missing)}",
        )

    def test_search_books_grouped(self):
        conn = self._populated_db()
        result = search_books(conn, q="horror", grouped=True)
        self.assertGreater(len(result["results"]), 0)
        for row in result["results"]:
            self._assert_summary_shape(row, "search_books(grouped=True)")

    def test_search_books_ungrouped(self):
        conn = self._populated_db()
        result = search_books(conn, q="horror", grouped=False)
        self.assertGreater(len(result["results"]), 0)
        for row in result["results"]:
            self._assert_summary_shape(row, "search_books(grouped=False)")

    def test_get_books_by_ids(self):
        conn = self._populated_db()
        rows = get_books_by_ids(conn, [1, 2, 3])
        self.assertEqual(len(rows), 3)
        for row in rows:
            self._assert_summary_shape(row, "get_books_by_ids")

    def test_get_topic_tag(self):
        conn = self._populated_db()
        result = get_topic(conn, "tag", "horror")
        self.assertIsNotNone(result)
        self.assertGreater(len(result["books"]), 0)
        for row in result["books"]:
            self._assert_summary_shape(row, "get_topic(tag)")

    def test_get_topic_game_system(self):
        conn = self._populated_db()
        result = get_topic(conn, "game_system", "D&D 5e")
        self.assertIsNotNone(result)
        for row in result["books"]:
            self._assert_summary_shape(row, "get_topic(game_system)")

    def test_get_topic_series(self):
        conn = self._populated_db()
        result = get_topic(conn, "series", "Ravenloft")
        self.assertIsNotNone(result)
        for row in result["books"]:
            self._assert_summary_shape(row, "get_topic(series)")

    def test_get_topic_publisher(self):
        conn = self._populated_db()
        result = get_topic(conn, "publisher", "WotC")
        self.assertIsNotNone(result)
        for row in result["books"]:
            self._assert_summary_shape(row, "get_topic(publisher)")

    def test_get_related_books_primary(self):
        """book_relations populated → primary path."""
        conn = self._populated_db()
        rows = get_related_books(conn, 1, limit=5)
        self.assertGreater(len(rows), 0)
        for row in rows:
            self._assert_summary_shape(row, "get_related_books(primary)")

    def test_get_related_books_fallback(self):
        """No book_relations row → tag-overlap fallback path."""
        conn = self._populated_db()
        conn.execute("DELETE FROM book_relations")
        conn.commit()
        rows = get_related_books(conn, 1, limit=5)
        self.assertGreater(len(rows), 0)
        for row in rows:
            self._assert_summary_shape(row, "get_related_books(fallback)")

    def test_nlq_search_fts(self):
        conn = self._populated_db(with_fts=True)
        rows = nlq_search(conn, "horror", limit=10)
        self.assertGreater(len(rows), 0)
        for row in rows:
            self._assert_summary_shape(row, "nlq_search(FTS)")

    def test_nlq_search_like_fallback(self):
        """No books_fts table → FTS path raises → LIKE fallback kicks in."""
        conn = self._populated_db(with_fts=False)
        rows = nlq_search(conn, "horror", limit=10)
        self.assertGreater(len(rows), 0)
        for row in rows:
            self._assert_summary_shape(row, "nlq_search(LIKE fallback)")


# ── search_facets contract tests ──────────────────────────────────────────────
#
# search_facets must reflect the SAME WHERE clause as search_books, so the
# counts in each bucket sum to the same set of books that the regular search
# would return. These tests verify both the basic aggregation and the
# search-context narrowing.

class TestSearchFacets(unittest.TestCase):
    def _populate(self, conn):
        # 6 horror books across multiple series, publishers, systems, tags
        add_book(conn, 1, "curse.pdf", display_title="Curse of Strahd",
                 publisher="WotC", game_system="D&D 5e", product_type="adventure",
                 series="Ravenloft", tags=["horror", "undead", "5e"],
                 description="Gothic horror in Barovia.",
                 date_enriched="2026-01-01")
        add_book(conn, 2, "vrgr.pdf", display_title="Van Richten's Guide",
                 publisher="WotC", game_system="D&D 5e", product_type="sourcebook",
                 series="Ravenloft", tags=["horror", "undead", "5e"],
                 description="Guide to the domains of dread.",
                 date_enriched="2026-01-01")
        add_book(conn, 3, "vathak.pdf", display_title="Shadows over Vathak",
                 publisher="Fat Goblin", game_system="Pathfinder 1e",
                 product_type="setting",
                 series="Vathak", tags=["horror", "dark_fantasy", "pf1e"],
                 description="Dark setting for PF.",
                 date_enriched="2026-01-01")
        add_book(conn, 4, "coc.pdf", display_title="Call of Cthulhu Quickstart",
                 publisher="Chaosium", game_system="Call of Cthulhu",
                 product_type="quickstart",
                 series="Cthulhu Quickstart", tags=["horror", "mystery", "coc"],
                 description="Investigating cosmic horror.",
                 date_enriched="2026-01-01")
        # Non-horror book in Ravenloft (proves filtering works)
        add_book(conn, 5, "tyranny.pdf", display_title="Tyranny of Dragons",
                 publisher="WotC", game_system="D&D 5e", product_type="adventure",
                 series="Tyranny", tags=["dragons", "5e"],
                 description="Dragon adventure.",
                 date_enriched="2026-01-01")
        # Old version that should be excluded by default
        add_book(conn, 6, "old_strahd.pdf", display_title="Old Strahd",
                 publisher="WotC", game_system="D&D 5e", product_type="adventure",
                 series="Ravenloft", tags=["horror", "5e"],
                 description="Older edition.",
                 is_old_version=1,
                 date_enriched="2026-01-01")

    def setUp(self):
        self.conn = make_db(with_wiki_tables=False)
        self._populate(self.conn)

    def test_response_shape(self):
        result = search_facets(self.conn)
        self.assertIn("total", result)
        for key in ("series", "publisher", "game_system", "tag"):
            self.assertIn(key, result)
            for entry in result[key]:
                self.assertIn("value", entry)
                self.assertIn("count", entry)

    def test_unfiltered_total_excludes_old_versions(self):
        result = search_facets(self.conn)
        # 5 live books (book 6 is is_old_version=1)
        self.assertEqual(result["total"], 5)

    def test_unfiltered_includes_old_versions_when_requested(self):
        result = search_facets(self.conn, include_old=True)
        self.assertEqual(result["total"], 6)

    def test_q_horror_filters_buckets(self):
        """Searching 'horror' must narrow every bucket to only horror books."""
        result = search_facets(self.conn, q="horror")
        self.assertEqual(result["total"], 4)  # books 1, 2, 3, 4

        # Check series facet — Ravenloft should have 2, Vathak 1, Cthulhu 1, Tyranny absent
        series_map = {e["value"]: e["count"] for e in result["series"]}
        self.assertEqual(series_map.get("Ravenloft"), 2)
        self.assertEqual(series_map.get("Vathak"), 1)
        self.assertEqual(series_map.get("Cthulhu Quickstart"), 1)
        self.assertNotIn("Tyranny", series_map)  # not a horror book

        # Publisher facet
        pub_map = {e["value"]: e["count"] for e in result["publisher"]}
        self.assertEqual(pub_map.get("WotC"), 2)
        self.assertEqual(pub_map.get("Fat Goblin"), 1)
        self.assertEqual(pub_map.get("Chaosium"), 1)

        # Game system facet
        gs_map = {e["value"]: e["count"] for e in result["game_system"]}
        self.assertEqual(gs_map.get("D&D 5e"), 2)
        self.assertEqual(gs_map.get("Pathfinder 1e"), 1)
        self.assertEqual(gs_map.get("Call of Cthulhu"), 1)

        # Tag facet — horror appears on all 4 matching books
        tag_map = {e["value"]: e["count"] for e in result["tag"]}
        self.assertEqual(tag_map.get("horror"), 4)
        self.assertEqual(tag_map.get("undead"), 2)  # books 1, 2
        self.assertEqual(tag_map.get("dark_fantasy"), 1)  # book 3
        self.assertEqual(tag_map.get("mystery"), 1)  # book 4
        self.assertNotIn("dragons", tag_map)  # only on the non-horror book

    def test_facet_counts_sum_to_total_for_required_columns(self):
        """For columns where every matching book has a value, counts must sum
        to the total. Tags can sum higher because a book has multiple tags."""
        result = search_facets(self.conn, q="horror")
        total = result["total"]
        for key in ("series", "publisher", "game_system"):
            facet_total = sum(e["count"] for e in result[key])
            self.assertEqual(facet_total, total,
                             f"{key} facet sums to {facet_total} but total is {total}")

    def test_facets_sorted_by_count_desc(self):
        result = search_facets(self.conn, q="horror")
        for key in ("series", "publisher", "game_system", "tag"):
            counts = [e["count"] for e in result[key]]
            self.assertEqual(counts, sorted(counts, reverse=True),
                             f"{key} not sorted by count desc")

    def test_filter_by_series_narrows_other_facets(self):
        """Filtering by series='Ravenloft' must narrow publisher/system/tag too."""
        result = search_facets(self.conn, series="Ravenloft")
        self.assertEqual(result["total"], 2)  # books 1, 2 (book 6 is old)
        # Series facet now contains only Ravenloft (the strict interpretation)
        series_map = {e["value"]: e["count"] for e in result["series"]}
        self.assertEqual(series_map, {"Ravenloft": 2})

    def test_tag_filter_intersection(self):
        """tags='horror,undead' must AND the conditions, not OR."""
        result = search_facets(self.conn, tags="horror,undead")
        self.assertEqual(result["total"], 2)  # only books 1 and 2 have BOTH

    def test_null_columns_excluded_from_facets(self):
        """A book with NULL series doesn't pollute the series facet."""
        add_book(self.conn, 7, "no_series.pdf",
                 publisher="Solo", game_system="System Neutral",
                 product_type="gm_aid",
                 series=None, tags=["gm_aid"],
                 description="A standalone GM tool.",
                 date_enriched="2026-01-01")
        result = search_facets(self.conn)
        # Series facet should NOT contain a NULL/empty entry
        for entry in result["series"]:
            self.assertTrue(entry["value"])
        # But publisher should include 'Solo'
        pub_map = {e["value"]: e["count"] for e in result["publisher"]}
        self.assertEqual(pub_map.get("Solo"), 1)

    def test_empty_search_returns_empty_facets(self):
        """A query that matches nothing returns total=0 and empty buckets."""
        result = search_facets(self.conn, q="ZZZNoMatchZZZ")
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["series"], [])
        self.assertEqual(result["publisher"], [])
        self.assertEqual(result["game_system"], [])
        self.assertEqual(result["tag"], [])

    def test_facets_match_search_books_total(self):
        """search_facets total must equal search_books total under the same params."""
        params = {"q": "horror"}
        f = search_facets(self.conn, **params)
        s = search_books(self.conn, grouped=False, per_page=500, **params)
        self.assertEqual(f["total"], s["total"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
