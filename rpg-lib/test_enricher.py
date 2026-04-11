#!/usr/bin/env python3
"""Tests for pdf_enricher.py"""

import json
import sqlite3
import unittest

from pdf_enricher import (
    PATHFINDER_CONVERSION_FILENAME_RE,
    SERIES_ALIASES,
    UNQUALIFIED_AL_SERIES,
    al_season_canonical_series,
    al_season_from_filename,
    apply_pathfinder_conversion_rule,
    apply_series_implied_tags,
    build_book_summary,
    build_series_prompt,
    migrate_enrichment_schema,
    normalize_series_in_db,
    normalize_series_value,
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

    def test_series_implied_tag_applied_via_validate(self):
        """validate_enrichment adds organized_play when book_meta matches AL."""
        entry = {
            "book_id": 1, "game_system": "D&D 5e", "product_type": "adventure",
            "tags": ["adventure", "5e"],
            "description": "A tier-1 adventure in Neverwinter.",
        }
        book_meta = {
            "id": 1,
            "filename": "DDAL05-01 Treasure of the Broken Hoard.pdf",
            "collection": "D&D Adventurers League - Storm King's Thunder",
        }
        result = validate_enrichment(entry, book_meta=book_meta)
        self.assertIn("organized_play", result["tags"])


class TestSeriesImpliedTags(unittest.TestCase):
    """Deterministic post-LLM tag rules keyed on filename/collection/series."""

    def _entry(self, tags=None, series=None):
        return {
            "book_id": 1, "game_system": "D&D 5e", "product_type": "adventure",
            "tags": list(tags) if tags is not None else ["adventure", "5e"],
            "series": series,
            "description": "An adventure.",
        }

    def test_ddal_filename_implies_organized_play(self):
        """DDAL filename prefix → organized_play, even if LLM missed it."""
        entry = self._entry()
        apply_series_implied_tags(entry, {
            "filename": "DDAL05-01 Treasure of the Broken Hoard.pdf",
            "collection": "Season 5",
        })
        self.assertIn("organized_play", entry["tags"])

    def test_ddex_filename_implies_organized_play(self):
        entry = self._entry()
        apply_series_implied_tags(entry, {
            "filename": "DDEX1-01 Defiance in Phlan.pdf",
            "collection": "Tyranny of Dragons",
        })
        self.assertIn("organized_play", entry["tags"])

    def test_adventurers_league_collection_implies_organized_play(self):
        """Collection substring alone is enough (handles CCC-* files etc)."""
        entry = self._entry()
        apply_series_implied_tags(entry, {
            "filename": "CCC-AE-01 Frozen Sick.pdf",
            "collection": "D&D Adventurers League: CCC-AE",
        })
        self.assertIn("organized_play", entry["tags"])

    def test_match_is_case_insensitive(self):
        entry = self._entry()
        apply_series_implied_tags(entry, {
            "filename": "ddal05-01.pdf",
            "collection": "d&d adventurers league - storm king",
        })
        self.assertIn("organized_play", entry["tags"])

    def test_non_al_book_unaffected(self):
        """Tight-radius rule: regular books must not pick up organized_play."""
        entry = self._entry()
        apply_series_implied_tags(entry, {
            "filename": "Curse of Strahd.pdf",
            "collection": "Ravenloft",
        })
        self.assertNotIn("organized_play", entry["tags"])

    def test_basic_dnd_not_matched_by_ddal_false_positive(self):
        """Sanity check: B10 Night's Dark Terror (Basic D&D) must not match."""
        entry = self._entry()
        apply_series_implied_tags(entry, {
            "filename": "B10 Night's Dark Terror.pdf",
            "collection": "B10 Night's Dark Terror (Basic)",
        })
        self.assertNotIn("organized_play", entry["tags"])

    def test_idempotent_when_tag_already_present(self):
        """Don't duplicate organized_play if the LLM already produced it."""
        entry = self._entry(tags=["adventure", "5e", "organized_play"])
        apply_series_implied_tags(entry, {
            "filename": "DDAL05-01.pdf",
            "collection": "D&D Adventurers League - Storm King",
        })
        self.assertEqual(entry["tags"].count("organized_play"), 1)

    def test_no_book_meta_is_noop(self):
        """Callers without DB context (tests, dry runs) should not crash."""
        entry = self._entry()
        apply_series_implied_tags(entry, None)
        self.assertNotIn("organized_play", entry["tags"])

    def test_llm_series_is_bonus_signal(self):
        """Even if filename/collection miss, LLM-extracted series can trigger."""
        entry = self._entry(series="D&D Adventurers League - Season 3")
        apply_series_implied_tags(entry, {
            "filename": "unknown.pdf",
            "collection": "",
        })
        self.assertIn("organized_play", entry["tags"])

    def test_ddexp_prefix_is_not_ddex(self):
        """Regression: DDEXP_B10_NightsDarkTerror.pdf is an old Basic D&D
        module (book 13041 in the live DB) whose filename starts with 'DDEXP'
        — a scanner artifact, not the AL DDEX code. The regex must reject it."""
        entry = self._entry()
        apply_series_implied_tags(entry, {
            "filename": "DDEXP_B10_NightsDarkTerror.pdf",
            "collection": "B10 Night's Dark Terror (Basic)",
        })
        self.assertNotIn("organized_play", entry["tags"])

    def test_ddal_letter_suffix_is_not_match(self):
        """Synthetic guardrail: any DDAL followed by a letter is rejected."""
        entry = self._entry()
        apply_series_implied_tags(entry, {
            "filename": "DDALOSAURUS_something.pdf",
            "collection": "",
        })
        self.assertNotIn("organized_play", entry["tags"])

    def test_ddal_drw_dash_suffix_still_matches(self):
        """Dreams of the Red Wizards files use DDAL-DRW##; the dash is not a
        letter, so these legitimate AL-affiliated DMsGuild books still match."""
        entry = self._entry()
        apply_series_implied_tags(entry, {
            "filename": "DDAL-DRW06_Thimblerigging.pdf",
            "collection": "DDAL-DRW-06 Thimblerigging",
        })
        self.assertIn("organized_play", entry["tags"])

    def test_ddal_eb_dash_suffix_still_matches(self):
        """Eberron / Oracle of War (Season 9) uses DDAL-EB-##; same rationale."""
        entry = self._entry()
        apply_series_implied_tags(entry, {
            "filename": "925821-DDAL-EB-01_The_Night_Land.pdf",
            "collection": "EB-01 The Night Land",
        })
        self.assertIn("organized_play", entry["tags"])


class TestPathfinderConversionFilenameRegex(unittest.TestCase):
    """Pure-regex coverage for the PF-suffix detector."""

    def _matches(self, filename: str) -> bool:
        return bool(PATHFINDER_CONVERSION_FILENAME_RE.search(filename))

    # Positive cases — must match
    def test_dash_pf_pdf(self):
        self.assertTrue(self._matches("925821-DDAL-DRW06_Thimblerigging-PF.pdf"))

    def test_underscore_pf_pdf(self):
        self.assertTrue(self._matches(
            "1315435-Bloodied__Bruised_-_Volos_Guide_to_Monsters_PF.pdf"))

    def test_dash_pf_versioned(self):
        self.assertTrue(self._matches("925821-DDAL-DRW05_Uncertain_Scrutiny-PF_v1.2.pdf"))

    def test_underscore_pf_versioned(self):
        self.assertTrue(self._matches(
            "1315435-Bloodied__Bruised_-_Strixhaven_v1_PF_v2.pdf"))

    def test_lowercase_pf(self):
        """Some filenames use lowercase _pf — case-insensitive match."""
        self.assertTrue(self._matches("2133295-Lost_Dragon_Egg_pf.pdf"))

    # Negative cases — must NOT match
    def test_print_friendly_does_not_match(self):
        """'_PrintFriendly.pdf' is a different convention (B&W layout, not PF)."""
        self.assertFalse(self._matches(
            "193137-Icewind_Dale_Travel_Cheatsheet_(printer_friendly).pdf"))
        self.assertFalse(self._matches(
            "Icewind_Dale_Rime_of_the_Frostmaiden_PrintFriendly.pdf"))

    def test_bare_pf_no_separator_does_not_match(self):
        """'APGDMG002PF.pdf' has no separator before PF — too risky to auto-match."""
        self.assertFalse(self._matches("APGDMG002PF.pdf"))

    def test_unrelated_filename(self):
        self.assertFalse(self._matches("Curse_of_Strahd.pdf"))
        self.assertFalse(self._matches("DDAL05-08_Durlags_Tower_v1.0.pdf"))

    def test_player_guide_pg_does_not_match(self):
        """'_PG' must not be confused with '_PF'."""
        self.assertFalse(self._matches("Oracle_of_War_PG_v1.3.pdf"))


class TestApplyPathfinderConversionRule(unittest.TestCase):
    """End-to-end behaviour of the post-LLM PF override."""

    def _entry(self, *, game_system="D&D 5e", tags=None):
        return {
            "book_id": 1, "game_system": game_system, "product_type": "adventure",
            "tags": list(tags) if tags is not None else ["adventure", "5e", "horror"],
            "description": "An adventure.",
        }

    def test_dnd_5e_with_pf_filename_overrides(self):
        entry = self._entry()
        apply_pathfinder_conversion_rule(entry, {
            "filename": "925821-DDAL-DRW06_Thimblerigging-PF.pdf",
        })
        self.assertEqual(entry["game_system"], "Pathfinder 1e")

    def test_drops_5e_tag_and_adds_pf1e(self):
        entry = self._entry(tags=["adventure", "5e", "horror"])
        apply_pathfinder_conversion_rule(entry, {
            "filename": "1315435-Monster_Loot_-_Out_of_the_Abyss_PF.pdf",
        })
        self.assertNotIn("5e", entry["tags"])
        self.assertIn("pf1e", entry["tags"])
        self.assertIn("adventure", entry["tags"])
        self.assertIn("horror", entry["tags"])

    def test_drops_all_dnd_system_tags(self):
        """If multiple D&D system tags slipped in, all are removed."""
        entry = self._entry(tags=["5e", "5e_2024", "3_5e", "ad_d", "adventure"])
        apply_pathfinder_conversion_rule(entry, {"filename": "foo-PF.pdf"})
        self.assertEqual(set(entry["tags"]), {"adventure", "pf1e"})

    def test_idempotent_on_already_pf1e(self):
        entry = self._entry(game_system="Pathfinder 1e", tags=["pf1e", "adventure"])
        apply_pathfinder_conversion_rule(entry, {"filename": "foo-PF.pdf"})
        self.assertEqual(entry["game_system"], "Pathfinder 1e")
        self.assertEqual(entry["tags"].count("pf1e"), 1)

    def test_does_not_touch_pf2e(self):
        """A book the LLM correctly classified as PF2e is left alone."""
        entry = self._entry(game_system="Pathfinder 2e", tags=["pf2e", "adventure"])
        apply_pathfinder_conversion_rule(entry, {"filename": "foo-PF.pdf"})
        self.assertEqual(entry["game_system"], "Pathfinder 2e")
        self.assertNotIn("pf1e", entry["tags"])

    def test_does_not_touch_dune(self):
        """Dune RPG uses '_pf_' as a version marker — must not override."""
        entry = self._entry(
            game_system="Other: Dune Adventures in the Imperium",
            tags=["adventure"],
        )
        apply_pathfinder_conversion_rule(entry, {
            "filename": "dune_digital_pf_20-1-22.pdf",
        })
        self.assertEqual(entry["game_system"],
                         "Other: Dune Adventures in the Imperium")

    def test_does_not_touch_vampire(self):
        """Vampire: The Masquerade product code uses _PF for version, not Pathfinder."""
        entry = self._entry(
            game_system="Other: Vampire: The Masquerade",
            tags=["adventure"],
        )
        apply_pathfinder_conversion_rule(entry, {
            "filename": "387228-VoS-SQ-SunderedSisters_PF_V1.0.pdf",
        })
        self.assertEqual(entry["game_system"], "Other: Vampire: The Masquerade")

    def test_does_not_touch_savage_worlds(self):
        entry = self._entry(game_system="Savage Worlds", tags=["adventure"])
        apply_pathfinder_conversion_rule(entry, {"filename": "MIS7092-PF.pdf"})
        self.assertEqual(entry["game_system"], "Savage Worlds")

    def test_no_change_when_filename_does_not_match(self):
        entry = self._entry()
        apply_pathfinder_conversion_rule(entry, {
            "filename": "Curse_of_Strahd.pdf",
        })
        self.assertEqual(entry["game_system"], "D&D 5e")
        self.assertIn("5e", entry["tags"])

    def test_no_book_meta_is_noop(self):
        entry = self._entry()
        apply_pathfinder_conversion_rule(entry, None)
        self.assertEqual(entry["game_system"], "D&D 5e")

    def test_preserves_unrelated_tags(self):
        entry = self._entry(tags=["adventure", "5e", "horror", "dungeon", "undead"])
        apply_pathfinder_conversion_rule(entry, {"filename": "foo-PF.pdf"})
        self.assertEqual(set(entry["tags"]),
                         {"adventure", "horror", "dungeon", "undead", "pf1e"})

    def test_validate_enrichment_applies_rule(self):
        """Integration: validate_enrichment runs the PF rule when book_meta is present."""
        entry = {
            "book_id": 1, "game_system": "D&D 5e", "product_type": "adventure",
            "tags": ["adventure", "5e"],
            "description": "...",
        }
        result = validate_enrichment(entry, book_meta={
            "filename": "925821-DDAL-DRW06_Thimblerigging-PF.pdf",
            "collection": "DDAL-DRW-06 Thimblerigging",
        })
        self.assertEqual(result["game_system"], "Pathfinder 1e")
        self.assertIn("pf1e", result["tags"])
        self.assertNotIn("5e", result["tags"])
        # And the AL series-implied-tags rule still fires after the override
        self.assertIn("organized_play", result["tags"])


class TestSeriesAliasesMapShape(unittest.TestCase):
    """Structural invariants of the SERIES_ALIASES constant."""

    def test_no_chains(self):
        """No value is also a key — every entry is one-hop."""
        overlap = set(SERIES_ALIASES.keys()) & set(SERIES_ALIASES.values())
        self.assertFalse(overlap, f"Chained aliases: {overlap}")

    def test_values_are_stable_under_renormalization(self):
        """Every target already matches its own structurally-normalized form."""
        for target in SERIES_ALIASES.values():
            self.assertEqual(normalize_series_value(target), target,
                             f"Target not self-stable: {target!r}")


class TestNormalizeSeriesValue(unittest.TestCase):
    def test_none_passes_through(self):
        self.assertIsNone(normalize_series_value(None))

    def test_empty_string_becomes_none(self):
        self.assertIsNone(normalize_series_value(""))
        self.assertIsNone(normalize_series_value("   "))

    def test_strips_whitespace(self):
        self.assertEqual(normalize_series_value("  Ravenloft  "), "Ravenloft")

    def test_collapses_internal_whitespace(self):
        self.assertEqual(normalize_series_value("Rage   of  Demons"),
                         "Rage of Demons")

    def test_normalizes_em_dash(self):
        self.assertEqual(normalize_series_value("Foo \u2014 Bar"), "Foo - Bar")

    def test_normalizes_en_dash(self):
        self.assertEqual(normalize_series_value("Foo \u2013 Bar"), "Foo - Bar")

    def test_strips_trailing_colon(self):
        self.assertEqual(normalize_series_value("Ravenloft:"), "Ravenloft")

    def test_strips_trailing_dash(self):
        self.assertEqual(normalize_series_value("Ravenloft -"), "Ravenloft")

    def test_strips_trailing_comma(self):
        self.assertEqual(normalize_series_value("Ravenloft,"), "Ravenloft")

    def test_applies_alias_colon_variant(self):
        self.assertEqual(
            normalize_series_value("D&D Adventurers League: Rage of Demons"),
            "D&D Adventurers League - Season 3 (Rage of Demons)",
        )

    def test_applies_alias_no_colon_variant(self):
        self.assertEqual(
            normalize_series_value("D&D Adventurers League Rage of Demons"),
            "D&D Adventurers League - Season 3 (Rage of Demons)",
        )

    def test_applies_alias_ddex3_shorthand(self):
        self.assertEqual(
            normalize_series_value("D&D Adventurers League DDEX3"),
            "D&D Adventurers League - Season 3 (Rage of Demons)",
        )

    def test_corrects_wrong_season_3_subtitle(self):
        """DDEX3 was Rage of Demons, not Elemental Evil — the DB's wrong label is fixed."""
        self.assertEqual(
            normalize_series_value("D&D Adventurers League - Season 3 (Elemental Evil)"),
            "D&D Adventurers League - Season 3 (Rage of Demons)",
        )

    def test_applies_alias_season_5_variants(self):
        for variant in ("D&D Adventurers League - Season 5",
                        "D&D Adventurers League - Storm King's Thunder"):
            with self.subTest(variant=variant):
                self.assertEqual(
                    normalize_series_value(variant),
                    "D&D Adventurers League - Season 5 (Storm King's Thunder)",
                )

    def test_applies_alias_frostmaiden_plural(self):
        self.assertEqual(
            normalize_series_value("Icewind Dale: Rime of the Frostmaiden DM's Resources"),
            "Icewind Dale: Rime of the Frostmaiden DM's Resource",
        )

    def test_untouched_series_passes_through(self):
        """Series outside the alias map are only structurally normalized."""
        self.assertEqual(
            normalize_series_value("Dungeon Crawl Classics"),
            "Dungeon Crawl Classics",
        )


class TestAlSeasonFromFilename(unittest.TestCase):
    def test_none_and_empty(self):
        self.assertIsNone(al_season_from_filename(None))
        self.assertIsNone(al_season_from_filename(""))

    def test_ddal_with_separator(self):
        self.assertEqual(al_season_from_filename("DDAL05-08 Durlags Tower.pdf"), 5)
        self.assertEqual(al_season_from_filename("DDAL_08-13_Vampire.pdf"), 8)
        self.assertEqual(al_season_from_filename("DDAL04-01_Curse.pdf"), 4)

    def test_ddal_compressed(self):
        """No separator: DDAL0508 = Season 5."""
        self.assertEqual(al_season_from_filename("DDAL0508.pdf"), 5)

    def test_ddal_triple_segment_certificate(self):
        """CERT filenames use DDAL{SS}{AA}{NN} with no separators."""
        self.assertEqual(al_season_from_filename("CERT - DDAL050801.pdf"), 5)

    def test_ddex_one_digit_season(self):
        self.assertEqual(al_season_from_filename("DDEX1-10_TyrannyinPhlan.pdf"), 1)
        self.assertEqual(al_season_from_filename("DDEX3-1_HarriedInHillsfar.pdf"), 3)

    def test_ddex_compressed(self):
        """No separator: DDEX110 = Season 1 adventure 10."""
        self.assertEqual(al_season_from_filename("DDEX110_TyrannyinPhlan.pdf"), 1)
        self.assertEqual(al_season_from_filename("DDEX19_OutlawsIronRoute.pdf"), 1)

    def test_ddex_leading_zero(self):
        """DDEX03-10 = Season 3 (leading-zero form)."""
        self.assertEqual(al_season_from_filename("DDEX03-10_Quelling.pdf"), 3)

    def test_ddal_below_season_4_rejected(self):
        """DDAL was only used Season 4+; DDAL03 is out of range."""
        self.assertIsNone(al_season_from_filename("DDAL03-01_fake.pdf"))

    def test_ddex_above_season_3_rejected(self):
        """DDEX was only used Seasons 1-3; DDEX5 is out of range."""
        self.assertIsNone(al_season_from_filename("DDEX5-01_fake.pdf"))

    def test_non_al_filename(self):
        self.assertIsNone(al_season_from_filename("Curse_of_Strahd.pdf"))
        # Basic D&D false positive sanity check from TODO #5
        self.assertIsNone(al_season_from_filename("B10 Night's Dark Terror.pdf"))

    def test_case_insensitive(self):
        self.assertEqual(al_season_from_filename("ddal05-08.pdf"), 5)
        self.assertEqual(al_season_from_filename("ddex1-10.pdf"), 1)


class TestAlSeasonCanonicalSeries(unittest.TestCase):
    def test_known_season_includes_name(self):
        self.assertEqual(
            al_season_canonical_series(3),
            "D&D Adventurers League - Season 3 (Rage of Demons)",
        )
        self.assertEqual(
            al_season_canonical_series(5),
            "D&D Adventurers League - Season 5 (Storm King's Thunder)",
        )

    def test_unknown_season_bare_label(self):
        """Unknown seasons get 'Season N' with no subtitle — still canonical."""
        self.assertEqual(
            al_season_canonical_series(7),
            "D&D Adventurers League - Season 7",
        )


class TestNormalizeSeriesInDb(unittest.TestCase):
    def setUp(self):
        self.conn = make_test_db()
        migrate_enrichment_schema(self.conn)

    def _insert(self, book_id, filename, series):
        insert_book(self.conn, book_id, filename)
        self.conn.execute("UPDATE books SET series = ? WHERE id = ?",
                          (series, book_id))
        self.conn.commit()

    def _series_of(self, book_id):
        return self.conn.execute(
            "SELECT series FROM books WHERE id = ?", (book_id,)
        ).fetchone()[0]

    def test_alias_rewrites_db_row(self):
        self._insert(1, "DDEX32_ShacklesBlood.pdf",
                     "D&D Adventurers League: Rage of Demons")
        normalize_series_in_db(self.conn)
        self.assertEqual(
            self._series_of(1),
            "D&D Adventurers League - Season 3 (Rage of Demons)",
        )

    def test_unqualified_al_reassigned_by_filename(self):
        """Book in the unqualified AL bucket gets promoted to its specific season."""
        self._insert(1, "DDAL05-08 Durlags Tower v1.0.pdf",
                     "D&D Adventurers League")
        normalize_series_in_db(self.conn)
        self.assertEqual(
            self._series_of(1),
            "D&D Adventurers League - Season 5 (Storm King's Thunder)",
        )

    def test_unqualified_al_without_code_untouched(self):
        """Generic AL program material stays unqualified."""
        self._insert(1, "925821-AL_DM_Guide_v9.1.pdf",
                     "D&D Adventurers League")
        normalize_series_in_db(self.conn)
        self.assertEqual(self._series_of(1), "D&D Adventurers League")

    def test_qualified_al_not_touched_by_filename_pass(self):
        """A book already in a specific season is not overridden by the filename pass,
        because its series isn't in UNQUALIFIED_AL_SERIES."""
        # Deliberately mismatched: series says Season 5, filename has DDEX3 code
        self._insert(1, "DDEX32_ShacklesBlood.pdf",
                     "D&D Adventurers League - Season 5 (Storm King's Thunder)")
        normalize_series_in_db(self.conn)
        self.assertEqual(
            self._series_of(1),
            "D&D Adventurers League - Season 5 (Storm King's Thunder)",
        )

    def test_non_al_book_unaffected(self):
        self._insert(1, "curse_of_strahd.pdf", "Ravenloft")
        normalize_series_in_db(self.conn)
        self.assertEqual(self._series_of(1), "Ravenloft")

    def test_null_series_unaffected(self):
        insert_book(self.conn, 1, "some.pdf")  # series stays NULL
        normalize_series_in_db(self.conn)
        row = self.conn.execute("SELECT series FROM books WHERE id=1").fetchone()
        self.assertIsNone(row[0])

    def test_dry_run_does_not_write(self):
        self._insert(1, "DDEX32_ShacklesBlood.pdf",
                     "D&D Adventurers League: Rage of Demons")
        normalize_series_in_db(self.conn, dry_run=True)
        self.assertEqual(
            self._series_of(1),
            "D&D Adventurers League: Rage of Demons",
        )

    def test_frostmaiden_plural_merged(self):
        self._insert(1, "resource.pdf",
                     "Icewind Dale: Rime of the Frostmaiden DM's Resources")
        normalize_series_in_db(self.conn)
        self.assertEqual(
            self._series_of(1),
            "Icewind Dale: Rime of the Frostmaiden DM's Resource",
        )

    def test_structural_normalization_without_alias(self):
        """Series not in the alias map still gets structural cleanup."""
        self._insert(1, "book.pdf", "Dolmenwood  ")  # trailing whitespace
        normalize_series_in_db(self.conn)
        self.assertEqual(self._series_of(1), "Dolmenwood")


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
