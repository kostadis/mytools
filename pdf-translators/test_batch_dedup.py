"""Tests for canonical-file selection (dedup) in batch_convert.py.

Covers the filename helpers and `select_canonical`'s two passes:
  A) reuse rpg-lib flags (old/draft/duplicate) + skip companion files
     (maps / Pathfinder -PF / preview),
  B) collapse same-title variants to one printer-friendly canonical.
"""
import batch_convert as bc


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------
def test_variant_title_key_collapses_format_and_version():
    keys = {
        bc._variant_title_key("1549348-Adaptable_NPCs_(v1.0).pdf"),
        bc._variant_title_key("1549348-Adaptable_NPCs_(v1.0_-_Optimized_PDF).pdf"),
        bc._variant_title_key("1549348-Adaptable_NPCs_(v1.0)_PrintFriendly.pdf"),
        bc._variant_title_key("1549348-Adaptable_NPCs_(full_res).pdf"),
    }
    assert len(keys) == 1, keys


def test_variant_title_key_collapses_version_variants():
    a = bc._variant_title_key("1802525-TOEE_Leadership-ver1.4.pdf")
    b = bc._variant_title_key("1802525-TOEE_Leadership-v_2.pdf")
    c = bc._variant_title_key("1802525-TOEE_Leadership-ver1_5.pdf")
    assert a == b == c


def test_variant_title_key_keeps_distinct_titles_apart():
    # Same product id, genuinely different chapters -> must NOT merge.
    one = bc._variant_title_key("1010432-1_Troll_Trouble.pdf")
    two = bc._variant_title_key("1010432-2_The_Five_Temples.pdf")
    assert one != two


def test_variant_title_key_collapses_bare_dotted_versions():
    # DriveThru stamps versions as BARE dotted numbers (no v/ver prefix). All
    # four below are one product (id 2327454) and must collapse to one key.
    keys = {
        bc._variant_title_key("2327454-Manual_of_the_Planes_1.0.1_printer_friendly.pdf"),
        bc._variant_title_key("2327454-Manual_of_the_Planes_1.0.2.pdf"),
        bc._variant_title_key("2327454-Manual_of_the_Planes_1.1.pdf"),
        bc._variant_title_key("2327454-Manual_of_the_Planes_1.1_(Quick_Load).pdf"),
    }
    assert len(keys) == 1, keys


def test_parse_version_handles_bare_dotted():
    # Bare dotted versions order correctly (1.1 > 1.0.2 > 1.0.1).
    assert bc._parse_version("Manual_1.0.1.pdf") == (1, 0, 1)
    assert bc._parse_version("Manual_1.1.pdf") == (1, 1)
    assert bc._parse_version("Manual_1.1.pdf") > bc._parse_version("Manual_1.0.2.pdf")
    assert bc._parse_version("Manual_1.0.2.pdf") > bc._parse_version("Manual_1.0.1.pdf")
    # A numeric product-ID prefix must NOT be read as a version.
    assert bc._parse_version("2327454-Manual_of_the_Planes_1.1.pdf") == (1, 1)


def test_single_bare_number_is_not_a_version():
    # The guard: a lone integer is real title content, not a version, so these
    # stay distinct products and parse to no version.
    assert bc._parse_version("100_NPCs.pdf") == (0,)
    assert bc._parse_version("5MWD_Adventures.pdf") == (0,)
    assert bc._parse_version("Tome_Volume_2.pdf") == (0,)
    assert (bc._variant_title_key("1010432-1_Troll_Trouble.pdf")
            != bc._variant_title_key("1010432-2_The_Five_Temples.pdf"))


def test_quick_load_is_a_disfavored_format():
    assert bc._format_rank("Manual_1.1_(Quick_Load).pdf") == 2
    assert bc._format_rank("Manual_QuickLoad.pdf") == 2


def test_select_canonical_new_world_db_owns_versions():
    """End-to-end of the rpg-lib-authority split: the library DB flags the old
    VERSIONS (is_old_version) and select_canonical drops them in Pass A; the
    remaining same-version FORMAT variants collapse in Pass B to the
    printer-friendly/plain winner. Mirrors what happens once rpg-lib's
    elect_latest_versions has run."""
    docs = {
        "MotP/2327454-Manual_of_the_Planes_1.0.1.pdf": _doc(),
        "MotP/2327454-Manual_of_the_Planes_1.0.2.pdf": _doc(),
        "MotP/2327454-Manual_of_the_Planes_1.1.pdf": _doc(),
        "MotP/2327454-Manual_of_the_Planes_1.1_(Quick_Load).pdf": _doc(),
    }
    # DB authority: 1.0.1 and 1.0.2 are superseded versions (is_old_version=1).
    flags = {
        "MotP/2327454-Manual_of_the_Planes_1.0.1.pdf": (1, 0, 0),
        "MotP/2327454-Manual_of_the_Planes_1.0.2.pdf": (1, 0, 0),
    }
    bc.select_canonical(docs, flags)
    survivors = [r for r, e in docs.items() if e["status"] == "pending"]
    assert survivors == ["MotP/2327454-Manual_of_the_Planes_1.1.pdf"], survivors
    assert (docs["MotP/2327454-Manual_of_the_Planes_1.0.1.pdf"]["reason"]
            == "library:old_version")
    assert (docs["MotP/2327454-Manual_of_the_Planes_1.1_(Quick_Load).pdf"]["reason"]
            == "variant:superseded")


def test_select_canonical_picks_newest_bare_version():
    # End-to-end: the four Manual of the Planes files reduce to the newest plain
    # edition (1.1), with printer-friendly 1.0.1 and the Quick Load both dropped.
    docs = {
        "MotP/2327454-Manual_of_the_Planes_1.0.1_printer_friendly.pdf": _doc(),
        "MotP/2327454-Manual_of_the_Planes_1.0.2.pdf": _doc(),
        "MotP/2327454-Manual_of_the_Planes_1.1.pdf": _doc(),
        "MotP/2327454-Manual_of_the_Planes_1.1_(Quick_Load).pdf": _doc(),
    }
    counts = bc.select_canonical(docs, {})
    survivors = [r for r, e in docs.items() if e["status"] == "pending"]
    assert survivors == ["MotP/2327454-Manual_of_the_Planes_1.1.pdf"], survivors
    assert counts["variant:superseded"] == 3


def test_parse_version_orders_correctly():
    assert bc._parse_version("x-ver1.4.pdf") == (1, 4)
    assert bc._parse_version("x-v_2.pdf") == (2,)
    assert bc._parse_version("x-ver1_5.pdf") == (1, 5)
    assert bc._parse_version("x-v2_7_1.pdf") == (2, 7, 1)
    assert bc._parse_version("no_version_here.pdf") == (0,)
    assert bc._parse_version("x-v_2.pdf") > bc._parse_version("x-ver1_5.pdf")
    assert bc._parse_version("x-ver1_5.pdf") > bc._parse_version("x-ver1.4.pdf")


def test_format_rank_prefers_printer_friendly():
    assert bc._format_rank("Book_PrintFriendly.pdf") == 0
    assert bc._format_rank("Book_Accessible_Version.pdf") == 0
    assert bc._format_rank("Book.pdf") == 1
    assert bc._format_rank("Book_Optimized.pdf") == 2
    assert bc._format_rank("Book_full_res.pdf") == 2


def test_companion_kind_detects_maps_pf_preview():
    assert bc._companion_kind("Realms_Maps_Booklet.pdf") == "maps"
    assert bc._companion_kind("Forests_of_the_Realms_Map-PF.pdf") == "maps"  # maps wins
    assert bc._companion_kind("Forests_of_the_Realms-PF.pdf") == "pathfinder"
    assert bc._companion_kind("326194-Preview.pdf") == "preview"
    assert bc._companion_kind("CaptainSnowmanes_Promo.pdf") == "preview"
    assert bc._companion_kind("193137-Feats.pdf") is None


# ---------------------------------------------------------------------------
# select_canonical
# ---------------------------------------------------------------------------
def _doc(status="pending", pages=10, text=1000, mtime=100):
    return {"status": status, "reason": "", "pages": pages,
            "text_chars": text, "mtime": mtime}


def test_select_canonical_full():
    docs = {
        # format variants, same version -> printer-friendly wins
        "NPCs/1549348-Adaptable_NPCs_(v1.0).pdf": _doc(text=5000),
        "NPCs/1549348-Adaptable_NPCs_(v1.0_-_Optimized_PDF).pdf": _doc(text=5200),
        "NPCs/1549348-Adaptable_NPCs_(v1.0)_PrintFriendly.pdf": _doc(text=4900),
        # version variants -> newest wins
        "TOEE/1802525-TOEE_Leadership-ver1.4.pdf": _doc(),
        "TOEE/1802525-TOEE_Leadership-v_2.pdf": _doc(),
        "TOEE/1802525-TOEE_Leadership-ver1_5.pdf": _doc(),
        # companions skipped; plain survivor stays
        "Almanac/1713687-Forests-PF.pdf": _doc(),
        "Almanac/1713687-Forests_Map-PF.pdf": _doc(),
        "Almanac/1713687-Forests.pdf": _doc(),
        "Promo/326194-Preview.pdf": _doc(),
        # library-flagged old version
        "Feats/193137-Feats.pdf": _doc(),
        "Feats/193137-Feats.old.pdf": _doc(),
        # single-file group untouched
        "Solo/999999-Unique_Adventure.pdf": _doc(),
    }
    flags = {"Feats/193137-Feats.old.pdf": (1, 0, 0)}

    counts = bc.select_canonical(docs, flags)

    def st(rel):
        return docs[rel]["status"]

    def rs(rel):
        return docs[rel]["reason"]

    # printer-friendly is the canonical of the format-variant group
    assert st("NPCs/1549348-Adaptable_NPCs_(v1.0)_PrintFriendly.pdf") == "pending"
    assert st("NPCs/1549348-Adaptable_NPCs_(v1.0).pdf") == "skipped"
    assert st("NPCs/1549348-Adaptable_NPCs_(v1.0_-_Optimized_PDF).pdf") == "skipped"
    assert rs("NPCs/1549348-Adaptable_NPCs_(v1.0).pdf") == "variant:superseded"

    # newest version wins
    assert st("TOEE/1802525-TOEE_Leadership-v_2.pdf") == "pending"
    assert st("TOEE/1802525-TOEE_Leadership-ver1.4.pdf") == "skipped"
    assert st("TOEE/1802525-TOEE_Leadership-ver1_5.pdf") == "skipped"

    # companions skipped, plain book survives
    assert st("Almanac/1713687-Forests.pdf") == "pending"
    assert rs("Almanac/1713687-Forests-PF.pdf") == "variant:pathfinder"
    assert rs("Almanac/1713687-Forests_Map-PF.pdf") == "variant:maps"
    assert rs("Promo/326194-Preview.pdf") == "variant:preview"

    # library old version skipped, canonical kept
    assert st("Feats/193137-Feats.pdf") == "pending"
    assert rs("Feats/193137-Feats.old.pdf") == "library:old_version"

    # single-file group untouched
    assert st("Solo/999999-Unique_Adventure.pdf") == "pending"

    # exactly one canonical survives per multi-file group
    survivors = [r for r, e in docs.items() if e["status"] == "pending"]
    assert sorted(survivors) == sorted([
        "NPCs/1549348-Adaptable_NPCs_(v1.0)_PrintFriendly.pdf",
        "TOEE/1802525-TOEE_Leadership-v_2.pdf",
        "Almanac/1713687-Forests.pdf",
        "Feats/193137-Feats.pdf",
        "Solo/999999-Unique_Adventure.pdf",
    ])
    assert counts["variant:superseded"] == 4
    assert counts["library:old_version"] == 1


def test_select_canonical_respects_existing_skips():
    docs = {
        "A/1-Book.pdf": _doc(status="skipped"),
        "A/1-Book_PrintFriendly.pdf": _doc(),
    }
    bc.select_canonical(docs, {})
    # already-skipped doc stays skipped; lone survivor stays pending
    assert docs["A/1-Book.pdf"]["status"] == "skipped"
    assert docs["A/1-Book_PrintFriendly.pdf"]["status"] == "pending"
