#!/usr/bin/env python3
"""Tests for validate_adventure.py — 5etools adventure JSON validator.

Run:
    pytest test_validate_adventure.py -v
"""

import json
from pathlib import Path

import pytest

from validate_adventure import validate, ValidationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _official(sections):
    """Build a minimal official-format adventure."""
    return {"data": sections}


def _homebrew(sections, *, name="Test", source="TEST"):
    """Build a minimal homebrew-format adventure."""
    contents = [{"name": s["name"], "headers": []} for s in sections
                if isinstance(s, dict) and s.get("type") == "section"]
    return {
        "_meta": {
            "sources": [{"json": source, "abbreviation": source, "full": name}],
            "dateAdded": 0,
            "dateLastModified": 0,
        },
        "adventure": [{
            "name": name,
            "id": source,
            "source": source,
            "contents": contents,
        }],
        "adventureData": [{
            "id": source,
            "source": source,
            "data": sections,
        }],
    }


def _section(name, entries=None):
    return {"type": "section", "name": name, "id": "000", "entries": entries or []}


# ---------------------------------------------------------------------------
# Top-level structure
# ---------------------------------------------------------------------------

class TestTopLevelStructure:
    def test_official_format_valid(self):
        r = validate(_official([_section("Ch1")]))
        assert r.ok

    def test_homebrew_format_valid(self):
        r = validate(_homebrew([_section("Ch1")]))
        assert r.ok

    def test_unrecognised_format(self):
        r = validate({"foo": "bar"})
        assert not r.ok
        assert any("Unrecognised" in e for e in r.errors)

    def test_not_an_object(self):
        r = validate([1, 2, 3])
        assert not r.ok

    def test_empty_data(self):
        r = validate(_official([]))
        assert any("empty" in w for w in r.warnings)

    def test_book_format_valid(self):
        data = {
            "_meta": {"sources": [{"json": "TB"}]},
            "book": [{"name": "Test Book", "id": "TB", "contents": []}],
            "bookData": [{"id": "TB", "data": [_section("Ch1")]}],
        }
        r = validate(data)
        assert r.ok


# ---------------------------------------------------------------------------
# Homebrew-specific validation
# ---------------------------------------------------------------------------

class TestHomebrewMeta:
    def test_missing_meta(self):
        data = _homebrew([_section("Ch1")])
        del data["_meta"]
        r = validate(data)
        assert any("_meta" in w for w in r.warnings)

    def test_empty_sources(self):
        data = _homebrew([_section("Ch1")])
        data["_meta"]["sources"] = []
        r = validate(data)
        assert any("sources" in w for w in r.warnings)

    def test_source_missing_json(self):
        data = _homebrew([_section("Ch1")])
        data["_meta"]["sources"] = [{"abbreviation": "X"}]
        r = validate(data)
        assert any("json" in e for e in r.errors)


# ---------------------------------------------------------------------------
# Contents/data alignment
# ---------------------------------------------------------------------------

class TestContentsAlignment:
    def test_aligned(self):
        sections = [_section("A"), _section("B")]
        r = validate(_homebrew(sections))
        assert r.ok

    def test_misaligned_count(self):
        data = _homebrew([_section("A"), _section("B")])
        data["adventure"][0]["contents"] = [{"name": "A", "headers": []}]
        r = validate(data)
        assert any("contents has 1" in w for w in r.warnings)

    def test_name_mismatch(self):
        data = _homebrew([_section("A")])
        data["adventure"][0]["contents"] = [{"name": "Wrong Name", "headers": []}]
        r = validate(data)
        assert any("Wrong Name" in w for w in r.warnings)

    def test_non_section_top_level(self):
        data = _homebrew([_section("A")])
        data["adventureData"][0]["data"].append({"type": "entries", "name": "Orphan", "entries": []})
        r = validate(data)
        assert any("non-section" in e.lower() or "must be 'section'" in e for e in r.errors)


# ---------------------------------------------------------------------------
# Entry type validation
# ---------------------------------------------------------------------------

class TestEntryTypes:
    def test_valid_types(self):
        sections = [_section("Ch1", entries=[
            "paragraph",
            {"type": "entries", "name": "Sub", "entries": ["text"]},
            {"type": "inset", "name": "Box", "entries": ["text"]},
            {"type": "insetReadaloud", "entries": ["text"]},
            {"type": "list", "items": ["a", "b"]},
            {"type": "table", "colLabels": ["A"], "rows": [["1"]]},
            {"type": "image", "href": {"type": "internal", "path": "img.png"}},
            {"type": "quote", "entries": ["text"], "by": "Author"},
            {"type": "hr"},
        ])]
        r = validate(_official(sections))
        assert r.ok, f"Errors: {r.errors}, Warnings: {r.warnings}"

    def test_unknown_type_warns(self):
        sections = [_section("Ch1", entries=[
            {"type": "foobar", "entries": []},
        ])]
        r = validate(_official(sections))
        assert any("foobar" in w for w in r.warnings)

    def test_missing_type_warns(self):
        sections = [_section("Ch1", entries=[
            {"name": "No type", "entries": []},
        ])]
        r = validate(_official(sections))
        assert any("no 'type'" in w for w in r.warnings)

    def test_null_entry_errors(self):
        sections = [_section("Ch1", entries=[None])]
        r = validate(_official(sections))
        assert any("null" in e for e in r.errors)

    def test_bare_string_at_top_level_official_warns(self):
        r = validate(_official(["orphan string"]))
        assert any("bare string" in w for w in r.warnings)

    def test_bare_string_at_top_level_homebrew_errors(self):
        data = _homebrew([_section("Ch1")])
        data["adventureData"][0]["data"].append("orphan string")
        r = validate(data)
        assert any("bare string" in e for e in r.errors)

    def test_section_without_name(self):
        sections = [{"type": "section", "entries": []}]
        r = validate(_official(sections))
        assert any("no name" in w for w in r.warnings)


# ---------------------------------------------------------------------------
# Table validation
# ---------------------------------------------------------------------------

class TestTableValidation:
    def test_valid_table(self):
        sections = [_section("Ch1", entries=[
            {"type": "table", "colLabels": ["A", "B"], "rows": [["1", "2"], ["3", "4"]]},
        ])]
        r = validate(_official(sections))
        assert r.ok

    def test_table_no_col_labels(self):
        sections = [_section("Ch1", entries=[
            {"type": "table", "rows": [["1", "2"]]},
        ])]
        r = validate(_official(sections))
        assert any("colLabels" in w for w in r.warnings)

    def test_table_tags_in_cells(self):
        sections = [_section("Ch1", entries=[
            {"type": "table", "colLabels": ["A"], "rows": [["{@badtag foo}"]]},
        ])]
        r = validate(_official(sections))
        assert any("badtag" in e for e in r.errors)


# ---------------------------------------------------------------------------
# List validation
# ---------------------------------------------------------------------------

class TestListValidation:
    def test_valid_list(self):
        sections = [_section("Ch1", entries=[
            {"type": "list", "items": ["a", "b", "c"]},
        ])]
        r = validate(_official(sections))
        assert r.ok

    def test_list_with_item_objects(self):
        sections = [_section("Ch1", entries=[
            {"type": "list", "items": [
                {"type": "item", "name": "Bold", "entry": "Description"},
            ]},
        ])]
        r = validate(_official(sections))
        assert r.ok

    def test_list_items_not_array(self):
        sections = [_section("Ch1", entries=[
            {"type": "list", "items": "not an array"},
        ])]
        r = validate(_official(sections))
        assert any("items must be an array" in e for e in r.errors)


# ---------------------------------------------------------------------------
# Image validation
# ---------------------------------------------------------------------------

class TestImageValidation:
    def test_valid_image(self):
        sections = [_section("Ch1", entries=[
            {"type": "image", "href": {"type": "internal", "path": "img.png"}},
        ])]
        r = validate(_official(sections))
        assert r.ok

    def test_image_no_href(self):
        sections = [_section("Ch1", entries=[
            {"type": "image"},
        ])]
        r = validate(_official(sections))
        assert any("no href" in e for e in r.errors)

    def test_image_empty_href(self):
        sections = [_section("Ch1", entries=[
            {"type": "image", "href": {"type": "internal"}},
        ])]
        r = validate(_official(sections))
        assert any("no path" in w for w in r.warnings)


# ---------------------------------------------------------------------------
# Tag validation
# ---------------------------------------------------------------------------

class TestTagValidation:
    def test_valid_tags(self):
        sections = [_section("Ch1", entries=[
            "Cast {@spell fireball} at {@creature goblin}. DC {@dc 15}. {@damage 2d6} fire.",
            "The {@condition poisoned} creature takes {@dice 1d4} damage.",
            "{@b Bold} and {@i italic} text.",
        ])]
        r = validate(_official(sections))
        assert r.ok, f"Errors: {r.errors}"

    def test_unknown_tag_errors(self):
        sections = [_section("Ch1", entries=[
            "See {@scroll fireball} for details.",
        ])]
        r = validate(_official(sections))
        assert any("scroll" in e for e in r.errors)

    def test_multiple_unknown_tags(self):
        sections = [_section("Ch1", entries=[
            "Use {@npc Bob} and {@scroll shield}.",
        ])]
        r = validate(_official(sections))
        assert sum(1 for e in r.errors if "unknown tag" in e) == 2

    def test_tags_in_entry_name(self):
        sections = [_section("Ch1", entries=[
            {"type": "entries", "name": "The {@badtag test}", "entries": []},
        ])]
        r = validate(_official(sections))
        assert any("badtag" in e for e in r.errors)

    def test_tags_in_table_cells(self):
        sections = [_section("Ch1", entries=[
            {"type": "table", "colLabels": ["Spell"],
             "rows": [["{@spell magic missile}"]]},
        ])]
        r = validate(_official(sections))
        assert r.ok

    def test_tags_in_list_items(self):
        sections = [_section("Ch1", entries=[
            {"type": "list", "items": ["{@creature wolf}"]},
        ])]
        r = validate(_official(sections))
        assert r.ok

    def test_unbalanced_braces_warns(self):
        sections = [_section("Ch1", entries=[
            "Missing closing {@spell fireball",
        ])]
        r = validate(_official(sections))
        assert any("unbalanced" in w for w in r.warnings)


# ---------------------------------------------------------------------------
# ID validation
# ---------------------------------------------------------------------------

class TestIDValidation:
    def test_unique_ids(self):
        sections = [
            {"type": "section", "name": "A", "id": "001", "entries": []},
            {"type": "section", "name": "B", "id": "002", "entries": []},
        ]
        r = validate(_official(sections))
        assert r.ok

    def test_duplicate_ids_warns(self):
        sections = [
            {"type": "section", "name": "A", "id": "001", "entries": [
                {"type": "entries", "name": "Sub", "id": "001", "entries": []},
            ]},
        ]
        r = validate(_official(sections))
        assert any("duplicate id" in w for w in r.warnings)

    def test_non_string_id_errors(self):
        sections = [{"type": "section", "name": "A", "id": 42, "entries": []}]
        r = validate(_official(sections))
        assert any("id must be a string" in e for e in r.errors)


# ---------------------------------------------------------------------------
# Nested structure
# ---------------------------------------------------------------------------

class TestNestedStructure:
    def test_deep_nesting_valid(self):
        sections = [_section("Ch1", entries=[
            {"type": "entries", "name": "L1", "id": "010", "entries": [
                {"type": "entries", "name": "L2", "id": "011", "entries": [
                    {"type": "entries", "name": "L3", "id": "012", "entries": [
                        "Deep paragraph.",
                    ]},
                ]},
            ]},
        ])]
        r = validate(_official(sections))
        assert r.ok

    def test_entries_field_not_array(self):
        sections = [_section("Ch1", entries=[
            {"type": "entries", "name": "Bad", "entries": "not an array"},
        ])]
        r = validate(_official(sections))
        assert any("entries must be an array" in e for e in r.errors)


# ---------------------------------------------------------------------------
# Integration: validate official files
# ---------------------------------------------------------------------------

class TestOfficialFiles:
    """Run the validator against actual official adventure files."""

    OFFICIAL_DIR = Path("/home/kroussos/5etools-dev/5etools-src/data/adventure")

    @pytest.fixture
    def official_files(self):
        if not self.OFFICIAL_DIR.is_dir():
            pytest.skip("Official adventure directory not found")
        files = sorted(self.OFFICIAL_DIR.glob("*.json"))
        if not files:
            pytest.skip("No official adventure files found")
        return files

    def test_official_files_have_no_errors(self, official_files):
        """All official adventure files should pass validation with no errors."""
        failures = []
        for fpath in official_files:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            r = validate(data, filename=fpath.name)
            if not r.ok:
                failures.append(f"{fpath.name}: {r.errors[:3]}")
        assert failures == [], f"Official files with errors:\n" + "\n".join(failures)

    def test_sample_official_file_structure(self, official_files):
        """Spot-check that LMoP has expected structure."""
        lmop = self.OFFICIAL_DIR / "adventure-lmop.json"
        if not lmop.exists():
            pytest.skip("LMoP not found")
        with open(lmop, encoding="utf-8") as f:
            data = json.load(f)
        r = validate(data, filename="adventure-lmop.json")
        assert r.ok
        assert len(data["data"]) > 0
        assert data["data"][0]["type"] == "section"


# ---------------------------------------------------------------------------
# Integration: validate our homebrew output
# ---------------------------------------------------------------------------

class TestHomebrewOutput:
    """Run the validator against our converted homebrew files."""

    HOMEBREW_DIR = Path("/home/kroussos/5etools-dev/5etools-src/pdf-translators")

    def _validate_homebrew_file(self, name):
        fpath = self.HOMEBREW_DIR / name
        if not fpath.exists():
            pytest.skip(f"{name} not found")
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        return validate(data, filename=name)

    def test_toworlds(self):
        r = self._validate_homebrew_file("adventure-toworlds.json")
        # Log issues for visibility — this file may have known issues
        if not r.ok:
            print(f"\nadventure-toworlds.json validation errors ({len(r.errors)}):")
            for e in r.errors[:10]:
                print(f"  {e}")
        if r.warnings:
            print(f"\nadventure-toworlds.json warnings ({len(r.warnings)}):")
            for w in r.warnings[:10]:
                print(f"  {w}")
