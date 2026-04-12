"""Tests for campaign and location tag inference (PR #13).

Covers:
- SERIES_IMPLIED_TAGS pattern matching for each campaign/location
- CAMPAIGN_IMPLIED_LOCATIONS dual-tag logic
- apply_series_implied_tags() idempotency
- backfill_campaign_tags() against a real DB fixture
"""

import json
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pdf_enricher import (
    CAMPAIGN_IMPLIED_LOCATIONS,
    CANONICAL_TAGS,
    SERIES_IMPLIED_TAGS,
    apply_series_implied_tags,
    backfill_campaign_tags,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_entry(tags=None, series=None, display_title=None):
    return {"tags": list(tags or []), "series": series, "display_title": display_title}


def _book_meta(filename="", collection=""):
    return {"filename": filename, "collection": collection}


def _applied_tags(filename="", collection="", series=None, display_title=None,
                  existing_tags=None):
    """Return the tag list after applying series-implied rules."""
    entry = _make_entry(tags=existing_tags, series=series, display_title=display_title)
    apply_series_implied_tags(entry, _book_meta(filename, collection))
    return entry["tags"]


# ── Vocabulary ─────────────────────────────────────────────────────────────────

class TestVocabulary(unittest.TestCase):

    def test_campaign_tags_in_canonical(self):
        expected = {
            "curse_of_strahd", "rime_of_the_frostmaiden", "descent_into_avernus",
            "waterdeep_adventures", "out_of_the_abyss", "tyranny_of_dragons",
            "tomb_of_annihilation",
        }
        for tag in expected:
            self.assertIn(tag, CANONICAL_TAGS, f"{tag!r} missing from CANONICAL_TAGS")

    def test_location_tags_in_canonical(self):
        expected = {"ravenloft", "icewind_dale", "underdark", "waterdeep", "avernus"}
        for tag in expected:
            self.assertIn(tag, CANONICAL_TAGS, f"{tag!r} missing from CANONICAL_TAGS")

    def test_campaign_implied_locations_values_are_canonical(self):
        for campaign, location in CAMPAIGN_IMPLIED_LOCATIONS.items():
            self.assertIn(campaign, CANONICAL_TAGS)
            self.assertIn(location, CANONICAL_TAGS)


# ── Pattern matching ───────────────────────────────────────────────────────────

def _patterns_for(tag):
    return [p for p, t in SERIES_IMPLIED_TAGS if t == tag]


class TestCampaignPatterns(unittest.TestCase):

    # tyranny_of_dragons
    def test_tyranny_matches_core_title(self):
        self.assertIn("tyranny_of_dragons",
                      _applied_tags(series="Tyranny of Dragons"))

    def test_tyranny_matches_hoard(self):
        self.assertIn("tyranny_of_dragons",
                      _applied_tags(series="Hoard of the Dragon Queen"))

    def test_tyranny_matches_rise_of_tiamat(self):
        self.assertIn("tyranny_of_dragons",
                      _applied_tags(series="Rise of Tiamat"))

    def test_tyranny_matches_ddex1(self):
        self.assertIn("tyranny_of_dragons",
                      _applied_tags(filename="DDEX1-01_EleventhHour.pdf"))

    def test_tyranny_matches_ddal01(self):
        self.assertIn("tyranny_of_dragons",
                      _applied_tags(filename="DDAL01-01.pdf"))

    def test_tyranny_no_false_positive_ddex3(self):
        self.assertNotIn("tyranny_of_dragons",
                         _applied_tags(filename="DDEX3-01_RageOfDemons.pdf"))

    # out_of_the_abyss
    def test_ota_matches_core_title(self):
        self.assertIn("out_of_the_abyss",
                      _applied_tags(series="Out of the Abyss"))

    def test_ota_matches_rage_of_demons(self):
        self.assertIn("out_of_the_abyss",
                      _applied_tags(collection="D&D Adventurers League - Season 3 (Rage of Demons)"))

    def test_ota_matches_ddex3(self):
        self.assertIn("out_of_the_abyss",
                      _applied_tags(filename="DDEX3-05_VaultOfTheUndying.pdf"))

    def test_ota_matches_ddal03(self):
        self.assertIn("out_of_the_abyss",
                      _applied_tags(filename="DDAL03-12.pdf"))

    # curse_of_strahd
    def test_cos_matches_title(self):
        self.assertIn("curse_of_strahd",
                      _applied_tags(series="Curse of Strahd"))

    def test_cos_matches_ddal04(self):
        self.assertIn("curse_of_strahd",
                      _applied_tags(filename="DDAL04-01_WalksInDarkness.pdf"))

    def test_cos_no_match_strahd_alone(self):
        # "Strahd" alone should not trigger curse_of_strahd — only the full phrase
        self.assertNotIn("curse_of_strahd",
                         _applied_tags(filename="StrahdsMonsters.pdf"))

    # rime_of_the_frostmaiden
    def test_rotf_matches_full_title(self):
        self.assertIn("rime_of_the_frostmaiden",
                      _applied_tags(series="Icewind Dale: Rime of the Frostmaiden"))

    def test_rotf_matches_frostmaiden_alone(self):
        self.assertIn("rime_of_the_frostmaiden",
                      _applied_tags(collection="Caves of Hunger - an Icewind Dale: "
                                               "Rime of the Frostmaiden DM's resource"))

    # descent_into_avernus
    def test_dia_matches_full_title(self):
        self.assertIn("descent_into_avernus",
                      _applied_tags(series="Baldur's Gate: Descent into Avernus"))

    def test_dia_matches_descent_alone(self):
        self.assertIn("descent_into_avernus",
                      _applied_tags(series="Descent into Avernus Supplement"))

    # waterdeep_adventures
    def test_wda_matches_dragon_heist(self):
        self.assertIn("waterdeep_adventures",
                      _applied_tags(series="Waterdeep: Dragon Heist"))

    def test_wda_matches_mad_mage(self):
        self.assertIn("waterdeep_adventures",
                      _applied_tags(series="Dungeon of the Mad Mage"))

    # tomb_of_annihilation
    def test_toa_matches(self):
        self.assertIn("tomb_of_annihilation",
                      _applied_tags(series="Tomb of Annihilation"))


class TestLocationPatterns(unittest.TestCase):

    def test_ravenloft_matches_name(self):
        self.assertIn("ravenloft",
                      _applied_tags(series="Van Richten's Guide to Ravenloft"))

    def test_ravenloft_matches_barovia(self):
        # "Barovian" (adjective form) should also match
        self.assertIn("ravenloft",
                      _applied_tags(series="Barovian Encounters"))

    def test_icewind_dale_matches(self):
        self.assertIn("icewind_dale",
                      _applied_tags(series="Icewind Dale Campaign Guide"))

    def test_underdark_matches(self):
        self.assertIn("underdark",
                      _applied_tags(series="Underdark Encounter Tables"))

    def test_waterdeep_location_matches(self):
        self.assertIn("waterdeep",
                      _applied_tags(series="Waterdeep: City Encounters"))

    def test_avernus_matches(self):
        self.assertIn("avernus",
                      _applied_tags(series="Avernus Encounters"))


# ── Dual-tag (CAMPAIGN_IMPLIED_LOCATIONS) ─────────────────────────────────────

class TestDualTagging(unittest.TestCase):

    def test_curse_of_strahd_implies_ravenloft(self):
        tags = _applied_tags(series="Curse of Strahd")
        self.assertIn("curse_of_strahd", tags)
        self.assertIn("ravenloft", tags)

    def test_rime_implies_icewind_dale(self):
        tags = _applied_tags(series="Icewind Dale: Rime of the Frostmaiden")
        self.assertIn("rime_of_the_frostmaiden", tags)
        self.assertIn("icewind_dale", tags)

    def test_descent_implies_avernus(self):
        tags = _applied_tags(series="Baldur's Gate: Descent into Avernus")
        self.assertIn("descent_into_avernus", tags)
        self.assertIn("avernus", tags)

    def test_waterdeep_adventures_implies_waterdeep(self):
        tags = _applied_tags(series="Waterdeep: Dragon Heist")
        self.assertIn("waterdeep_adventures", tags)
        self.assertIn("waterdeep", tags)

    def test_out_of_the_abyss_implies_underdark(self):
        tags = _applied_tags(series="Out of the Abyss")
        self.assertIn("out_of_the_abyss", tags)
        self.assertIn("underdark", tags)

    def test_tyranny_no_implied_location(self):
        # tyranny_of_dragons has no location parent in CAMPAIGN_IMPLIED_LOCATIONS
        tags = _applied_tags(series="Tyranny of Dragons")
        self.assertIn("tyranny_of_dragons", tags)
        self.assertNotIn("forgotten_realms", tags)

    def test_existing_campaign_tag_still_gets_location(self):
        # If a book already has curse_of_strahd (from LLM), ravenloft gets added
        tags = _applied_tags(existing_tags=["curse_of_strahd"])
        self.assertIn("ravenloft", tags)

    def test_existing_location_not_duplicated(self):
        # If ravenloft is already present, it isn't added twice
        tags = _applied_tags(series="Curse of Strahd",
                             existing_tags=["ravenloft"])
        self.assertEqual(tags.count("ravenloft"), 1)


# ── Idempotency ────────────────────────────────────────────────────────────────

class TestIdempotency(unittest.TestCase):

    def test_double_application_no_duplicates(self):
        entry = _make_entry(series="Curse of Strahd")
        meta = _book_meta(filename="DDAL04-01.pdf")
        apply_series_implied_tags(entry, meta)
        first_pass = list(entry["tags"])
        apply_series_implied_tags(entry, meta)
        self.assertEqual(entry["tags"], first_pass)

    def test_no_book_meta_is_noop(self):
        entry = _make_entry(tags=["adventure"])
        apply_series_implied_tags(entry, None)
        self.assertEqual(entry["tags"], ["adventure"])


# ── Backfill ───────────────────────────────────────────────────────────────────

def _make_db():
    """In-memory DB with a handful of representative books."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE books (
            id INTEGER PRIMARY KEY,
            filename TEXT,
            collection TEXT,
            series TEXT,
            display_title TEXT,
            tags TEXT,
            date_enriched TEXT,
            is_old_version INTEGER DEFAULT 0,
            is_draft INTEGER DEFAULT 0,
            is_duplicate INTEGER DEFAULT 0
        )
    """)
    books = [
        # should get tyranny_of_dragons
        (1, "DDAL01-01_EleventhHour.pdf",  "D&D Adventurers League - Season 1",
         "D&D Adventurers League - Season 1 (Tyranny of Dragons)", None,
         '["adventure","organized_play"]', "2024-01-01"),
        # should get curse_of_strahd + ravenloft
        (2, "CurseOfStrahd_DMs_Resource.pdf",
         "Curse of Strahd DM Resources", "Curse of Strahd", None,
         '["adventure","horror"]', "2024-01-01"),
        # should get ravenloft (standalone, not campaign)
        (3, "VanRichtensGuide.pdf", "Van Richten's Guide to Ravenloft",
         "Van Richten's Guide to Ravenloft", None,
         '["sourcebook"]', "2024-01-01"),
        # should get rime_of_the_frostmaiden + icewind_dale
        (4, "TenTowns_DMNotes.pdf",
         "Ten-Towns - an Icewind Dale: Rime of the Frostmaiden DM's resource",
         "Rime of the Frostmaiden DM's Resource", None,
         '["gm_aid"]', "2024-01-01"),
        # should get nothing new (no match)
        (5, "RandomDungeon.pdf", "Generic Dungeon Collection", None, None,
         '["dungeon","maps"]', "2024-01-01"),
        # not enriched — should be skipped by backfill
        (6, "DDEX3-01_RageOfDemons.pdf", "Rage of Demons", None, None,
         '["adventure"]', None),
    ]
    conn.executemany(
        "INSERT INTO books VALUES (?,?,?,?,?,?,?,0,0,0)", books
    )
    conn.commit()
    return conn


class TestBackfillCampaignTags(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()

    def tearDown(self):
        self.conn.close()

    def _tags(self, book_id):
        row = self.conn.execute(
            "SELECT tags FROM books WHERE id=?", (book_id,)
        ).fetchone()
        return json.loads(row[0])

    def test_tyranny_tagged(self):
        backfill_campaign_tags(self.conn)
        self.assertIn("tyranny_of_dragons", self._tags(1))

    def test_curse_strahd_and_ravenloft_tagged(self):
        backfill_campaign_tags(self.conn)
        tags = self._tags(2)
        self.assertIn("curse_of_strahd", tags)
        self.assertIn("ravenloft", tags)

    def test_standalone_ravenloft_tagged(self):
        backfill_campaign_tags(self.conn)
        self.assertIn("ravenloft", self._tags(3))
        self.assertNotIn("curse_of_strahd", self._tags(3))

    def test_rime_and_icewind_dale_tagged(self):
        backfill_campaign_tags(self.conn)
        tags = self._tags(4)
        self.assertIn("rime_of_the_frostmaiden", tags)
        self.assertIn("icewind_dale", tags)

    def test_unmatched_book_unchanged(self):
        backfill_campaign_tags(self.conn)
        self.assertEqual(self._tags(5), ["dungeon", "maps"])

    def test_unenriched_book_skipped(self):
        backfill_campaign_tags(self.conn)
        # book 6 has date_enriched=NULL, should not be touched
        self.assertEqual(self._tags(6), ["adventure"])

    def test_dry_run_makes_no_changes(self):
        backfill_campaign_tags(self.conn, dry_run=True)
        # cos book should still have original tags
        self.assertNotIn("curse_of_strahd", self._tags(2))

    def test_idempotent(self):
        backfill_campaign_tags(self.conn)
        after_first = {i: self._tags(i) for i in range(1, 6)}
        backfill_campaign_tags(self.conn)
        after_second = {i: self._tags(i) for i in range(1, 6)}
        self.assertEqual(after_first, after_second)


if __name__ == "__main__":
    unittest.main()
