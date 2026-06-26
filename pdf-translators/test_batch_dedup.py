"""Tests for canonical-file selection (dedup) in batch_convert.py.

rpg-lib is the authority (reached via /api/library/resolve): it flags
old/duplicate/draft and which file is printer-friendly. select_canonical:
  A) drops old/draft/duplicate + companion files (maps / Pathfinder -PF / preview),
  B) when several current files remain for one product (same-version FORMAT
     variants), keeps the printer-friendly one (rpg-lib's is_printer_friendly flag).
Version dedup and the format tiebreak are NOT computed here.
"""
import io
import json
import urllib.error

import pytest

import batch_convert as bc


def _doc(status="pending", pages=10, text=1000, mtime=100):
    return {"status": status, "reason": "", "pages": pages,
            "text_chars": text, "mtime": mtime}


# ---------------------------------------------------------------------------
# Grouping key (unchanged: still strips version + format tokens)
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


def test_variant_title_key_collapses_bare_dotted_versions():
    keys = {
        bc._variant_title_key("2327454-Manual_of_the_Planes_1.0.1_printer_friendly.pdf"),
        bc._variant_title_key("2327454-Manual_of_the_Planes_1.0.2.pdf"),
        bc._variant_title_key("2327454-Manual_of_the_Planes_1.1.pdf"),
        bc._variant_title_key("2327454-Manual_of_the_Planes_1.1_(Quick_Load).pdf"),
    }
    assert len(keys) == 1, keys


def test_variant_title_key_keeps_distinct_titles_apart():
    # Same product id, genuinely different chapters -> must NOT merge.
    assert (bc._variant_title_key("1010432-1_Troll_Trouble.pdf")
            != bc._variant_title_key("1010432-2_The_Five_Temples.pdf"))


def test_companion_kind_detects_maps_pf_preview():
    assert bc._companion_kind("Realms_Maps_Booklet.pdf") == "maps"
    assert bc._companion_kind("Forests_of_the_Realms_Map-PF.pdf") == "maps"  # maps wins
    assert bc._companion_kind("Forests_of_the_Realms-PF.pdf") == "pathfinder"
    assert bc._companion_kind("326194-Preview.pdf") == "preview"
    assert bc._companion_kind("CaptainSnowmanes_Promo.pdf") == "preview"
    assert bc._companion_kind("193137-Feats.pdf") is None


# ---------------------------------------------------------------------------
# select_canonical — rpg-lib flags (dicts) drive everything
# ---------------------------------------------------------------------------
def _flags(**by_rel):
    """by_rel: rel -> dict of flag overrides (missing keys default False)."""
    return by_rel


def test_pass_a_drops_old_duplicate_draft():
    docs = {"a.pdf": _doc(), "b.pdf": _doc(), "c.pdf": _doc(), "d.pdf": _doc()}
    flags = {
        "a.pdf": {"is_old_version": True},
        "b.pdf": {"is_duplicate": True},
        "c.pdf": {"is_draft": True},
    }
    bc.select_canonical(docs, flags)
    assert docs["a.pdf"]["reason"] == "library:old_version"
    assert docs["b.pdf"]["reason"] == "library:duplicate"
    assert docs["c.pdf"]["reason"] == "library:draft"
    assert docs["d.pdf"]["status"] == "pending"


def test_pass_b_printer_friendly_flag_wins():
    # Two current same-version format variants; rpg-lib marks one printer-friendly.
    docs = {
        "MotP/2327454-Manual_of_the_Planes_1.1.pdf": _doc(text=9000),
        "MotP/2327454-Manual_of_the_Planes_1.1_printer_friendly.pdf": _doc(text=100),
    }
    # PF wins on the flag even though the plain edition has far more text.
    flags = {"MotP/2327454-Manual_of_the_Planes_1.1_printer_friendly.pdf":
             {"is_printer_friendly": True}}
    counts = bc.select_canonical(docs, flags)
    survivors = [r for r, e in docs.items() if e["status"] == "pending"]
    assert survivors == ["MotP/2327454-Manual_of_the_Planes_1.1_printer_friendly.pdf"]
    assert counts["variant:superseded"] == 1


def test_select_canonical_new_world_db_owns_versions():
    """Library flags the old VERSIONS; Pass A drops them; the remaining
    same-version FORMAT variants collapse in Pass B (no PF flag here -> the
    plain edition wins on the shorter-name tiebreak over Quick Load)."""
    docs = {
        "MotP/2327454-Manual_of_the_Planes_1.0.1.pdf": _doc(),
        "MotP/2327454-Manual_of_the_Planes_1.0.2.pdf": _doc(),
        "MotP/2327454-Manual_of_the_Planes_1.1.pdf": _doc(),
        "MotP/2327454-Manual_of_the_Planes_1.1_(Quick_Load).pdf": _doc(),
    }
    flags = {
        "MotP/2327454-Manual_of_the_Planes_1.0.1.pdf": {"is_old_version": True},
        "MotP/2327454-Manual_of_the_Planes_1.0.2.pdf": {"is_old_version": True},
    }
    bc.select_canonical(docs, flags)
    survivors = [r for r, e in docs.items() if e["status"] == "pending"]
    assert survivors == ["MotP/2327454-Manual_of_the_Planes_1.1.pdf"], survivors
    assert (docs["MotP/2327454-Manual_of_the_Planes_1.0.1.pdf"]["reason"]
            == "library:old_version")
    assert (docs["MotP/2327454-Manual_of_the_Planes_1.1_(Quick_Load).pdf"]["reason"]
            == "variant:superseded")


def test_select_canonical_full():
    docs = {
        # format variants, same version -> printer-friendly (flagged) wins
        "NPCs/1549348-Adaptable_NPCs_(v1.0).pdf": _doc(text=5000),
        "NPCs/1549348-Adaptable_NPCs_(v1.0_-_Optimized_PDF).pdf": _doc(text=5200),
        "NPCs/1549348-Adaptable_NPCs_(v1.0)_PrintFriendly.pdf": _doc(text=4900),
        # version variants -> rpg-lib flags the old ones, newest survives
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
    flags = {
        "NPCs/1549348-Adaptable_NPCs_(v1.0)_PrintFriendly.pdf": {"is_printer_friendly": True},
        "TOEE/1802525-TOEE_Leadership-ver1.4.pdf": {"is_old_version": True},
        "TOEE/1802525-TOEE_Leadership-ver1_5.pdf": {"is_old_version": True},
        "Feats/193137-Feats.old.pdf": {"is_old_version": True},
    }
    counts = bc.select_canonical(docs, flags)

    def st(rel): return docs[rel]["status"]
    def rs(rel): return docs[rel]["reason"]

    # printer-friendly (flagged) is the canonical of the format-variant group
    assert st("NPCs/1549348-Adaptable_NPCs_(v1.0)_PrintFriendly.pdf") == "pending"
    assert rs("NPCs/1549348-Adaptable_NPCs_(v1.0).pdf") == "variant:superseded"
    assert rs("NPCs/1549348-Adaptable_NPCs_(v1.0_-_Optimized_PDF).pdf") == "variant:superseded"

    # rpg-lib-flagged old versions dropped, newest survives
    assert st("TOEE/1802525-TOEE_Leadership-v_2.pdf") == "pending"
    assert rs("TOEE/1802525-TOEE_Leadership-ver1.4.pdf") == "library:old_version"
    assert rs("TOEE/1802525-TOEE_Leadership-ver1_5.pdf") == "library:old_version"

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

    survivors = sorted(r for r, e in docs.items() if e["status"] == "pending")
    assert survivors == sorted([
        "NPCs/1549348-Adaptable_NPCs_(v1.0)_PrintFriendly.pdf",
        "TOEE/1802525-TOEE_Leadership-v_2.pdf",
        "Almanac/1713687-Forests.pdf",
        "Feats/193137-Feats.pdf",
        "Solo/999999-Unique_Adventure.pdf",
    ])
    assert counts["variant:superseded"] == 2
    assert counts["library:old_version"] == 3


def test_select_canonical_respects_existing_skips():
    docs = {
        "A/1-Book.pdf": _doc(status="skipped"),
        "A/1-Book_PrintFriendly.pdf": _doc(),
    }
    bc.select_canonical(docs, {})
    assert docs["A/1-Book.pdf"]["status"] == "skipped"
    assert docs["A/1-Book_PrintFriendly.pdf"]["status"] == "pending"


# ---------------------------------------------------------------------------
# resolve_flags_via_api — HTTP client (mocked transport)
# ---------------------------------------------------------------------------
class _FakeResp:
    def __init__(self, body, status=200):
        self.status = status
        self._body = body.encode()
    def read(self): return self._body
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_resolve_flags_via_api_maps_back_to_rel(monkeypatch):
    from pathlib import Path
    root = Path("/mnt/lib")
    docs = {"sub/a.pdf": {}, "sub/b.pdf": {}}
    captured = {}

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        # server keys by absolute filepath
        return _FakeResp(json.dumps({
            "/mnt/lib/sub/a.pdf": {"is_old_version": True, "is_duplicate": False,
                                   "is_draft": False, "is_printer_friendly": False},
        }))

    monkeypatch.setattr(bc.urllib.request, "urlopen", fake_urlopen)
    flags = bc.resolve_flags_via_api("http://h:8000", root, docs)
    assert captured["url"] == "http://h:8000/api/library/resolve"
    assert set(captured["body"]["filepaths"]) == {"/mnt/lib/sub/a.pdf", "/mnt/lib/sub/b.pdf"}
    assert flags["sub/a.pdf"]["is_old_version"] is True
    assert "sub/b.pdf" not in flags  # unmatched omitted


def test_resolve_flags_via_api_errors_out_when_down(monkeypatch):
    from pathlib import Path
    def boom(req, timeout=0):
        raise urllib.error.URLError("connection refused")
    monkeypatch.setattr(bc.urllib.request, "urlopen", boom)
    with pytest.raises(bc.LibraryAPIError):
        bc.resolve_flags_via_api("http://h:8000", Path("/mnt/lib"), {"a.pdf": {}})


def test_resolve_flags_via_api_errors_on_non_200(monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(bc.urllib.request, "urlopen",
                        lambda req, timeout=0: _FakeResp("{}", status=503))
    with pytest.raises(bc.LibraryAPIError):
        bc.resolve_flags_via_api("http://h:8000", Path("/mnt/lib"), {"a.pdf": {}})
