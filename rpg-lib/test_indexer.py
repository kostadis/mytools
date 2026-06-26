#!/usr/bin/env python3
"""Tests for pdf_indexer.py"""

import sqlite3
import unittest

from pdf_indexer import (
    DB_SCHEMA,
    elect_latest_versions,
    flag_content_duplicates,
    normalize_title_key,
    parse_filename_metadata,
    parse_printer_friendly,
    parse_version_tuple,
)


def _make_db():
    """Fresh in-memory DB matching the indexer schema."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(DB_SCHEMA)
    return conn


def _insert(conn, *, id, filename, filepath, page_count=100,
            pdf_title=None, pdf_author=None, is_old_version=0,
            is_draft=0, is_duplicate=0, product_id=None, collection=None):
    pid, pver = parse_filename_metadata(filename)
    conn.execute(
        """INSERT INTO books
               (id, filename, filepath, relative_path, page_count,
                pdf_title, pdf_author, is_old_version, is_draft, is_duplicate,
                product_id, product_version, collection, date_indexed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-01-01')""",
        (id, filename, filepath, filepath, page_count,
         pdf_title, pdf_author, is_old_version, is_draft, is_duplicate,
         product_id if product_id is not None else pid, pver, collection),
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


class TestParseVersionTuple(unittest.TestCase):
    def test_bare_dotted(self):
        self.assertEqual(parse_version_tuple("Manual_1.0.2.pdf"), (1, 0, 2))
        self.assertEqual(parse_version_tuple("Manual_1.1.pdf"), (1, 1))

    def test_v_prefixed(self):
        self.assertEqual(parse_version_tuple("Foo_v1.4.pdf"), (1, 4))
        self.assertEqual(parse_version_tuple("Foo_ver2_7_1.pdf"), (2, 7, 1))

    def test_product_id_not_eaten(self):
        # The numeric DriveThru product-ID prefix must not be read as a version.
        self.assertEqual(
            parse_version_tuple("2327454-Manual_of_the_Planes_1.0.2.pdf"), (1, 0, 2))

    def test_update_and_date(self):
        self.assertEqual(parse_version_tuple("BeneBads_update6(Final).pdf"), (6,))
        self.assertEqual(parse_version_tuple("GreatDale-20191023-hi.pdf"),
                         (2019, 10, 23))

    def test_single_integer_is_not_a_version(self):
        self.assertEqual(parse_version_tuple("100_NPCs.pdf"), ())
        self.assertEqual(parse_version_tuple("Tome_Volume_2.pdf"), ())
        self.assertEqual(parse_version_tuple("plain_book.pdf"), ())

    def test_ordering(self):
        self.assertGreater(parse_version_tuple("x_1.1.pdf"),
                           parse_version_tuple("x_1.0.2.pdf"))
        self.assertGreater(parse_version_tuple("x_update6.pdf"),
                           parse_version_tuple("x_update2.pdf"))


class TestPrinterFriendly(unittest.TestCase):
    def test_matches_printer_friendly(self):
        self.assertEqual(parse_printer_friendly("x_printer_friendly.pdf"), 1)
        self.assertEqual(parse_printer_friendly("x_PrintFriendly.pdf"), 1)
        self.assertEqual(parse_printer_friendly("x_(screen-reader_friendly).pdf"), 1)
        self.assertEqual(parse_printer_friendly("x_accessible.pdf"), 1)

    def test_does_not_match_pathfinder_or_plain(self):
        # "-PF" is a Pathfinder conversion (pdf_enricher's concern), NOT printer-friendly.
        self.assertEqual(parse_printer_friendly("925821-DDAL-DRW06-PF.pdf"), 0)
        self.assertEqual(parse_printer_friendly("plain_book.pdf"), 0)


def _old(conn, book_id):
    return conn.execute(
        "SELECT is_old_version FROM books WHERE id = ?", (book_id,)
    ).fetchone()[0]


class TestElectLatestVersions(unittest.TestCase):
    def _manual_db(self):
        conn = _make_db()
        # product 2327454, one title — version + format variants
        _insert(conn, id=1, filename="2327454-Manual_of_the_Planes_1.0.1.pdf",
                filepath="/x/1.pdf", product_id="2327454", collection="MotP")
        _insert(conn, id=2,
                filename="2327454-Manual_of_the_Planes_1.0.1_printer_friendly.pdf",
                filepath="/x/2.pdf", product_id="2327454", collection="MotP")
        _insert(conn, id=3, filename="2327454-Manual_of_the_Planes_1.0.2.pdf",
                filepath="/x/3.pdf", product_id="2327454", collection="MotP")
        _insert(conn, id=4, filename="2327454-Manual_of_the_Planes_1.1.pdf",
                filepath="/x/4.pdf", product_id="2327454", collection="MotP")
        _insert(conn, id=5,
                filename="2327454-Manual_of_the_Planes_1.1_(Quick_Load).pdf",
                filepath="/x/5.pdf", product_id="2327454", collection="MotP")
        return conn

    def test_manual_case_collapses_to_latest(self):
        conn = self._manual_db()
        elect_latest_versions(conn)
        # 1.0.1 / 1.0.1-pf / 1.0.2 are superseded by 1.1
        self.assertEqual(_old(conn, 1), 1)
        self.assertEqual(_old(conn, 2), 1)
        self.assertEqual(_old(conn, 3), 1)
        # 1.1 and 1.1 Quick Load are the SAME version (format variants) — both stay
        self.assertEqual(_old(conn, 4), 0)
        self.assertEqual(_old(conn, 5), 0)

    def test_bundle_safety_distinct_titles_under_one_product(self):
        # A DriveThru product_id is often a bundle of DISTINCT works; election must
        # not mark one title old because a different title has a higher version.
        conn = self._manual_db()
        _insert(conn, id=10, filename="2327454-Tashas_Crucible_v1.1.1.pdf",
                filepath="/x/10.pdf", product_id="2327454", collection="MotP")
        _insert(conn, id=11, filename="2327454-Tashas_Crucible_v2.0.1.pdf",
                filepath="/x/11.pdf", product_id="2327454", collection="MotP")
        _insert(conn, id=12, filename="2327454-Expanded_Options.pdf",
                filepath="/x/12.pdf", product_id="2327454", collection="MotP")
        elect_latest_versions(conn)
        self.assertEqual(_old(conn, 10), 1)  # Tashas v1.1.1 superseded by v2.0.1
        self.assertEqual(_old(conn, 11), 0)  # Tashas v2.0.1 current
        self.assertEqual(_old(conn, 12), 0)  # Expanded_Options: lone, no version
        # Manual group unaffected by the bundle siblings
        self.assertEqual(_old(conn, 4), 0)

    def test_dry_run_writes_nothing(self):
        conn = self._manual_db()
        preview = elect_latest_versions(conn, dry_run=True)
        self.assertEqual(len(preview), 3)
        for bid in (1, 2, 3, 4, 5):
            self.assertEqual(_old(conn, bid), 0)

    def test_idempotent(self):
        conn = self._manual_db()
        elect_latest_versions(conn)
        self.assertEqual(len(elect_latest_versions(conn)), 0)

    def test_old_rename_rows_untouched(self):
        # .old files are already flagged by parse_version and must be left alone.
        conn = _make_db()
        _insert(conn, id=1, filename="Book_1.1.pdf", filepath="/x/1.pdf",
                collection="C")
        _insert(conn, id=2, filename="Book_1.0.old-001.pdf", filepath="/x/2.pdf",
                is_old_version=1, collection="C")
        elect_latest_versions(conn)
        self.assertEqual(_old(conn, 1), 0)
        self.assertEqual(_old(conn, 2), 1)  # unchanged

    def test_collection_fallback_when_no_product_id(self):
        # No product_id → group by collection; same title collapses, different
        # collections stay independent.
        conn = _make_db()
        _insert(conn, id=1, filename="Hoard_1.0.pdf", filepath="/a/1.pdf",
                collection="A")
        _insert(conn, id=2, filename="Hoard_2.0.pdf", filepath="/a/2.pdf",
                collection="A")
        _insert(conn, id=3, filename="Hoard_1.0.pdf", filepath="/b/3.pdf",
                collection="B")
        elect_latest_versions(conn)
        self.assertEqual(_old(conn, 1), 1)  # superseded within collection A
        self.assertEqual(_old(conn, 2), 0)
        self.assertEqual(_old(conn, 3), 0)  # different collection, untouched

    def test_title_key_groups_manual_variants(self):
        keys = {normalize_title_key(f) for f in [
            "2327454-Manual_of_the_Planes_1.0.1_printer_friendly.pdf",
            "2327454-Manual_of_the_Planes_1.0.2.pdf",
            "2327454-Manual_of_the_Planes_1.1_(Quick_Load).pdf",
        ]}
        self.assertEqual(len(keys), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
