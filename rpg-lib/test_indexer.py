#!/usr/bin/env python3
"""Tests for pdf_indexer.py"""

import sqlite3
import unittest

from pdf_indexer import (
    DB_SCHEMA,
    flag_content_duplicates,
)


def _make_db():
    """Fresh in-memory DB matching the indexer schema."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(DB_SCHEMA)
    return conn


def _insert(conn, *, id, filename, filepath, page_count=100,
            pdf_title=None, pdf_author=None, is_old_version=0,
            is_draft=0, is_duplicate=0):
    conn.execute(
        """INSERT INTO books
               (id, filename, filepath, relative_path, page_count,
                pdf_title, pdf_author, is_old_version, is_draft, is_duplicate,
                date_indexed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-01-01')""",
        (id, filename, filepath, filepath, page_count,
         pdf_title, pdf_author, is_old_version, is_draft, is_duplicate),
    )
    conn.commit()


def _is_duplicate(conn, book_id):
    return conn.execute(
        "SELECT is_duplicate FROM books WHERE id = ?", (book_id,)
    ).fetchone()[0]


class TestFlagContentDuplicates(unittest.TestCase):
    def test_no_clusters_no_op(self):
        """A DB with no duplicates flags zero rows."""
        conn = _make_db()
        _insert(conn, id=1, filename="a.pdf", filepath="/x/a.pdf",
                page_count=10, pdf_title="A", pdf_author="X")
        _insert(conn, id=2, filename="b.pdf", filepath="/x/b.pdf",
                page_count=10, pdf_title="B", pdf_author="Y")
        n = flag_content_duplicates(conn)
        self.assertEqual(n, 0)
        self.assertEqual(_is_duplicate(conn, 1), 0)
        self.assertEqual(_is_duplicate(conn, 2), 0)

    def test_simple_filename_cluster_deduped(self):
        """3 rows with identical content fingerprint → 2 flagged."""
        conn = _make_db()
        _insert(conn, id=1, filename="treasury.pdf", filepath="/pub/x/treasury.pdf",
                page_count=115, pdf_title="Treasury", pdf_author="Castle")
        _insert(conn, id=2, filename="treasury.pdf", filepath="/pub/y/treasury.pdf",
                page_count=115, pdf_title="Treasury", pdf_author="Castle")
        _insert(conn, id=3, filename="treasury.pdf", filepath="/pub/z/treasury.pdf",
                page_count=115, pdf_title="Treasury", pdf_author="Castle")
        n = flag_content_duplicates(conn)
        self.assertEqual(n, 2)

    def test_lowest_id_kept(self):
        """The MIN(id) within a cluster is the keeper; higher ids are flagged."""
        conn = _make_db()
        _insert(conn, id=10, filename="x.pdf", filepath="/a/x.pdf",
                page_count=5, pdf_title="X", pdf_author="Y")
        _insert(conn, id=20, filename="x.pdf", filepath="/b/x.pdf",
                page_count=5, pdf_title="X", pdf_author="Y")
        _insert(conn, id=30, filename="x.pdf", filepath="/c/x.pdf",
                page_count=5, pdf_title="X", pdf_author="Y")
        flag_content_duplicates(conn)
        self.assertEqual(_is_duplicate(conn, 10), 0)
        self.assertEqual(_is_duplicate(conn, 20), 1)
        self.assertEqual(_is_duplicate(conn, 30), 1)

    def test_different_page_count_not_clustered(self):
        """Same filename + different page counts → genuine revisions, kept distinct."""
        conn = _make_db()
        _insert(conn, id=1, filename="trophy.pdf", filepath="/a/trophy.pdf",
                page_count=204, pdf_title="Trophy", pdf_author="Z")
        _insert(conn, id=2, filename="trophy.pdf", filepath="/b/trophy.pdf",
                page_count=201, pdf_title="Trophy", pdf_author="Z")
        n = flag_content_duplicates(conn)
        self.assertEqual(n, 0)

    def test_different_title_not_clustered(self):
        """Same filename, different pdf_title → not deduped."""
        conn = _make_db()
        _insert(conn, id=1, filename="adventure.pdf", filepath="/a/adventure.pdf",
                page_count=20, pdf_title="The Crypt", pdf_author="A")
        _insert(conn, id=2, filename="adventure.pdf", filepath="/b/adventure.pdf",
                page_count=20, pdf_title="The Tower", pdf_author="A")
        n = flag_content_duplicates(conn)
        self.assertEqual(n, 0)

    def test_different_author_not_clustered(self):
        """Same filename + page_count + title, different author → not deduped."""
        conn = _make_db()
        _insert(conn, id=1, filename="x.pdf", filepath="/a/x.pdf",
                page_count=10, pdf_title="T", pdf_author="Alice")
        _insert(conn, id=2, filename="x.pdf", filepath="/b/x.pdf",
                page_count=10, pdf_title="T", pdf_author="Bob")
        n = flag_content_duplicates(conn)
        self.assertEqual(n, 0)

    def test_null_title_treated_as_cluster(self):
        """NULL pdf_title rows still cluster via COALESCE-to-empty-string."""
        conn = _make_db()
        _insert(conn, id=1, filename="no_meta.pdf", filepath="/a/no_meta.pdf",
                page_count=8, pdf_title=None, pdf_author=None)
        _insert(conn, id=2, filename="no_meta.pdf", filepath="/b/no_meta.pdf",
                page_count=8, pdf_title=None, pdf_author=None)
        n = flag_content_duplicates(conn)
        self.assertEqual(n, 1)
        self.assertEqual(_is_duplicate(conn, 1), 0)
        self.assertEqual(_is_duplicate(conn, 2), 1)

    def test_existing_duplicates_skipped(self):
        """A row already flagged is_duplicate=1 is excluded from clustering.

        This means it's not considered for the keeper either — so a cluster of
        2 rows where one is already flagged stays at 1 flag (the cluster
        becomes a single non-duplicate row, no further action)."""
        conn = _make_db()
        _insert(conn, id=1, filename="x.pdf", filepath="/a/x.pdf",
                page_count=5, pdf_title="X", pdf_author="Y", is_duplicate=1)
        _insert(conn, id=2, filename="x.pdf", filepath="/b/x.pdf",
                page_count=5, pdf_title="X", pdf_author="Y")
        n = flag_content_duplicates(conn)
        self.assertEqual(n, 0)
        self.assertEqual(_is_duplicate(conn, 1), 1)  # untouched
        self.assertEqual(_is_duplicate(conn, 2), 0)  # the only live row in the cluster

    def test_idempotent(self):
        """Running twice flags zero additional rows on the second pass."""
        conn = _make_db()
        for i in (1, 2, 3, 4):
            _insert(conn, id=i, filename="x.pdf", filepath=f"/p{i}/x.pdf",
                    page_count=10, pdf_title="X", pdf_author="Y")
        first = flag_content_duplicates(conn)
        second = flag_content_duplicates(conn)
        self.assertEqual(first, 3)
        self.assertEqual(second, 0)

    def test_dry_run_does_not_write(self):
        """dry_run=True returns the count but does not UPDATE the rows."""
        conn = _make_db()
        for i in (1, 2, 3):
            _insert(conn, id=i, filename="x.pdf", filepath=f"/p{i}/x.pdf",
                    page_count=10, pdf_title="X", pdf_author="Y")
        n = flag_content_duplicates(conn, dry_run=True)
        self.assertEqual(n, 2)
        self.assertEqual(_is_duplicate(conn, 1), 0)
        self.assertEqual(_is_duplicate(conn, 2), 0)
        self.assertEqual(_is_duplicate(conn, 3), 0)

    def test_old_version_and_new_have_distinct_filenames(self):
        """Sanity: book.pdf and book.old.pdf are separate clusters because
        their filenames differ. is_old_version is irrelevant to clustering."""
        conn = _make_db()
        _insert(conn, id=1, filename="book.pdf", filepath="/a/book.pdf",
                page_count=10, pdf_title="T", pdf_author="A")
        _insert(conn, id=2, filename="book.old.pdf", filepath="/a/book.old.pdf",
                page_count=10, pdf_title="T", pdf_author="A", is_old_version=1)
        n = flag_content_duplicates(conn)
        self.assertEqual(n, 0)

    def test_multiple_independent_clusters(self):
        """Two separate clusters are flagged independently."""
        conn = _make_db()
        # Cluster A: 3 copies of treasury.pdf
        for i in (1, 2, 3):
            _insert(conn, id=i, filename="treasury.pdf",
                    filepath=f"/pubA/{i}/treasury.pdf",
                    page_count=115, pdf_title="Treasury", pdf_author="Castle")
        # Cluster B: 2 copies of catalog.pdf
        for i in (4, 5):
            _insert(conn, id=i, filename="catalog.pdf",
                    filepath=f"/pubB/{i}/catalog.pdf",
                    page_count=8, pdf_title="Catalog", pdf_author="Other")
        # Standalone (not duplicated)
        _insert(conn, id=6, filename="lone.pdf", filepath="/lone.pdf",
                page_count=20, pdf_title="Lone", pdf_author="Solo")
        n = flag_content_duplicates(conn)
        self.assertEqual(n, 3)  # 2 from cluster A + 1 from cluster B
        self.assertEqual(_is_duplicate(conn, 1), 0)
        self.assertEqual(_is_duplicate(conn, 2), 1)
        self.assertEqual(_is_duplicate(conn, 3), 1)
        self.assertEqual(_is_duplicate(conn, 4), 0)
        self.assertEqual(_is_duplicate(conn, 5), 1)
        self.assertEqual(_is_duplicate(conn, 6), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
