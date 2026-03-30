#!/usr/bin/env python3
"""Tests for adventure_model.py — typed data model for 5etools adventure JSON.

Run:
    pytest test_adventure_model.py -v
"""

import json
from pathlib import Path

import pytest

from adventure_model import (
    BuildContext, ValidationMode, ValidationError, ValidationResult,
    validate_tags,
    SectionEntry, EntriesEntry, InsetEntry, InsetReadaloudEntry,
    QuoteEntry, VariantInnerEntry,
    ListEntry, ItemEntry, ItemSubEntry,
    TableEntry, TableGroupEntry,
    ImageEntry, ImageHref, GalleryEntry,
    HrEntry, InlineEntry, InlineBlockEntry,
    FlowchartEntry, FlowBlockEntry,
    StatblockEntry, SpellcastingEntry, GenericEntry,
    Meta, MetaSource, TocEntry, TocHeader,
    AdventureIndex, AdventureData,
    HomebrewAdventure, OfficialAdventureData,
    parse_entry, parse_document,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(mode=ValidationMode.WARN):
    return BuildContext(mode=mode)


def _strict():
    return BuildContext(mode=ValidationMode.STRICT)


# ---------------------------------------------------------------------------
# Entry construction
# ---------------------------------------------------------------------------

class TestEntryConstruction:
    def test_section_basic(self):
        ctx = _ctx()
        s = SectionEntry(name="Chapter 1", entries=["Hello."], _ctx=ctx, _path="data[0]")
        assert s.type == "section"
        assert s.name == "Chapter 1"
        assert ctx.result.ok

    def test_entries_basic(self):
        ctx = _ctx()
        e = EntriesEntry(name="Room A1", entries=["Text."], _ctx=ctx, _path="x")
        assert e.type == "entries"
        assert ctx.result.ok

    def test_inset_basic(self):
        ctx = _ctx()
        e = InsetEntry(name="Sidebar", entries=["Info."], _ctx=ctx, _path="x")
        assert e.type == "inset"
        assert ctx.result.ok

    def test_inset_readaloud_basic(self):
        ctx = _ctx()
        e = InsetReadaloudEntry(entries=["Read this aloud."], _ctx=ctx, _path="x")
        assert e.type == "insetReadaloud"
        assert ctx.result.ok

    def test_quote_basic(self):
        ctx = _ctx()
        q = QuoteEntry(entries=["Wise words."], by="Author", from_="Book", _ctx=ctx, _path="x")
        assert q.type == "quote"
        assert ctx.result.ok

    def test_list_basic(self):
        ctx = _ctx()
        l = ListEntry(items=["a", "b", "c"], _ctx=ctx, _path="x")
        assert l.type == "list"
        assert ctx.result.ok

    def test_table_basic(self):
        ctx = _ctx()
        t = TableEntry(colLabels=["A", "B"], rows=[["1", "2"]], _ctx=ctx, _path="x")
        assert t.type == "table"
        assert ctx.result.ok

    def test_image_basic(self):
        ctx = _ctx()
        img = ImageEntry(href=ImageHref(type="internal", path="img.png"), _ctx=ctx, _path="x")
        assert img.type == "image"
        assert ctx.result.ok

    def test_hr_basic(self):
        ctx = _ctx()
        hr = HrEntry(_ctx=ctx, _path="x")
        assert hr.type == "hr"
        assert hr.to_dict() == {"type": "hr"}

    def test_item_basic(self):
        ctx = _ctx()
        item = ItemEntry(name="Bold", entry="Description", _ctx=ctx, _path="x")
        assert item.type == "item"
        assert ctx.result.ok

    def test_nested_entries(self):
        ctx = _ctx()
        inner = EntriesEntry(name="Sub", entries=["Deep."], _ctx=ctx, _path="x.entries[0]")
        outer = SectionEntry(name="Ch1", entries=[inner, "Text."], _ctx=ctx, _path="x")
        assert ctx.result.ok
        d = outer.to_dict()
        assert d["entries"][0]["type"] == "entries"
        assert d["entries"][0]["name"] == "Sub"
        assert d["entries"][1] == "Text."


# ---------------------------------------------------------------------------
# Validation — WARN mode
# ---------------------------------------------------------------------------

class TestValidationWarn:
    def test_section_no_name_warns(self):
        ctx = _ctx()
        SectionEntry(entries=["Text."], _ctx=ctx, _path="x")
        assert any("no name" in w for w in ctx.result.warnings)
        assert ctx.result.ok  # warnings don't make it not-ok

    def test_entries_no_name_warns(self):
        ctx = _ctx()
        EntriesEntry(entries=["Text."], _ctx=ctx, _path="x")
        assert any("no name" in w for w in ctx.result.warnings)

    def test_table_no_col_labels_warns(self):
        ctx = _ctx()
        TableEntry(rows=[["1", "2"]], _ctx=ctx, _path="x")
        assert any("colLabels" in w for w in ctx.result.warnings)

    def test_image_no_path_warns(self):
        ctx = _ctx()
        ImageEntry(href=ImageHref(type="internal"), _ctx=ctx, _path="x")
        assert any("no path" in w for w in ctx.result.warnings)

    def test_image_no_href_errors(self):
        ctx = _ctx()
        ImageEntry(href=None, _ctx=ctx, _path="x")
        assert any("no href" in e for e in ctx.result.errors)

    def test_unknown_tag_errors(self):
        ctx = _ctx()
        SectionEntry(name="Ch1", entries=["{@badtag foo}"], _ctx=ctx, _path="x")
        assert any("badtag" in e for e in ctx.result.errors)

    def test_valid_tags_ok(self):
        ctx = _ctx()
        SectionEntry(name="Ch1", entries=[
            "Cast {@spell fireball} at {@creature goblin}. DC {@dc 15}.",
        ], _ctx=ctx, _path="x")
        assert ctx.result.ok

    def test_unbalanced_braces_warns(self):
        ctx = _ctx()
        SectionEntry(name="Ch1", entries=[
            "Missing closing {@spell fireball",
        ], _ctx=ctx, _path="x")
        assert any("unbalanced" in w for w in ctx.result.warnings)

    def test_duplicate_ids_warns(self):
        ctx = _ctx()
        SectionEntry(name="A", id="001", entries=[], _ctx=ctx, _path="data[0]")
        EntriesEntry(name="B", id="001", entries=[], _ctx=ctx, _path="data[0].entries[0]")
        assert any("duplicate id" in w for w in ctx.result.warnings)

    def test_list_items_not_array_errors(self):
        ctx = _ctx()
        ListEntry(items="not a list", _ctx=ctx, _path="x")
        assert any("items must be an array" in e for e in ctx.result.errors)

    def test_entries_not_array_errors(self):
        ctx = _ctx()
        SectionEntry(name="Ch1", entries="not a list", _ctx=ctx, _path="x")
        assert any("entries must be an array" in e for e in ctx.result.errors)

    def test_null_entry_errors(self):
        ctx = _ctx()
        parsed = parse_entry(None, ctx, "data[0]")
        assert any("null" in e for e in ctx.result.errors)

    def test_tag_in_name_errors(self):
        ctx = _ctx()
        EntriesEntry(name="The {@badtag test}", entries=[], _ctx=ctx, _path="x")
        assert any("badtag" in e for e in ctx.result.errors)

    def test_tag_in_table_cells_errors(self):
        ctx = _ctx()
        TableEntry(colLabels=["A"], rows=[["{@badtag foo}"]], _ctx=ctx, _path="x")
        assert any("badtag" in e for e in ctx.result.errors)

    def test_tag_in_quote_by(self):
        ctx = _ctx()
        QuoteEntry(entries=["text"], by="{@badtag X}", _ctx=ctx, _path="x")
        assert any("badtag" in e for e in ctx.result.errors)


# ---------------------------------------------------------------------------
# Validation — STRICT mode
# ---------------------------------------------------------------------------

class TestValidationStrict:
    def test_unknown_tag_raises(self):
        ctx = _strict()
        with pytest.raises(ValidationError, match="badtag"):
            SectionEntry(name="Ch1", entries=["{@badtag foo}"], _ctx=ctx, _path="x")

    def test_image_no_href_raises(self):
        ctx = _strict()
        with pytest.raises(ValidationError, match="no href"):
            ImageEntry(href=None, _ctx=ctx, _path="x")

    def test_valid_does_not_raise(self):
        ctx = _strict()
        s = SectionEntry(name="Ch1", entries=["Hello."], _ctx=ctx, _path="x")
        assert s.name == "Ch1"

    def test_list_items_not_array_raises(self):
        ctx = _strict()
        with pytest.raises(ValidationError, match="items must be an array"):
            ListEntry(items="bad", _ctx=ctx, _path="x")


# ---------------------------------------------------------------------------
# Serialization (to_dict)
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_section_to_dict(self):
        ctx = _ctx()
        s = SectionEntry(name="Ch1", id="000", entries=["Text."], page=5, _ctx=ctx, _path="x")
        d = s.to_dict()
        assert d == {"type": "section", "name": "Ch1", "id": "000", "page": 5, "entries": ["Text."]}

    def test_none_fields_omitted(self):
        ctx = _ctx()
        s = SectionEntry(name="Ch1", entries=["Text."], _ctx=ctx, _path="x")
        d = s.to_dict()
        assert "id" not in d
        assert "page" not in d

    def test_quote_from_serializes_as_from(self):
        ctx = _ctx()
        q = QuoteEntry(entries=["Wise."], by="Author", from_="Source", _ctx=ctx, _path="x")
        d = q.to_dict()
        assert d["from"] == "Source"
        assert "from_" not in d

    def test_list_with_style(self):
        ctx = _ctx()
        l = ListEntry(items=["a"], style="list-hang-notitle", _ctx=ctx, _path="x")
        d = l.to_dict()
        assert d["style"] == "list-hang-notitle"

    def test_table_with_caption(self):
        ctx = _ctx()
        t = TableEntry(caption="My Table", colLabels=["A"], rows=[["1"]], _ctx=ctx, _path="x")
        d = t.to_dict()
        assert d["caption"] == "My Table"

    def test_image_to_dict(self):
        ctx = _ctx()
        img = ImageEntry(href=ImageHref(type="internal", path="img.png"),
                         title="A map", _ctx=ctx, _path="x")
        d = img.to_dict()
        assert d["href"] == {"type": "internal", "path": "img.png"}
        assert d["title"] == "A map"

    def test_hr_minimal(self):
        ctx = _ctx()
        assert HrEntry(_ctx=ctx, _path="x").to_dict() == {"type": "hr"}

    def test_homebrew_to_dict_keys(self):
        ctx = _ctx()
        doc = HomebrewAdventure.build(name="Test", source="TEST",
                                       sections=[SectionEntry(name="Ch1", entries=["Hi."], _ctx=ctx, _path="data[0]")],
                                       ctx=ctx)
        d = doc.to_dict()
        assert "_meta" in d
        assert "adventure" in d
        assert "adventureData" in d
        assert "book" not in d

    def test_book_to_dict_keys(self):
        ctx = _ctx()
        doc = HomebrewAdventure.build(name="Test Book", source="TB",
                                       sections=[SectionEntry(name="Ch1", entries=["Hi."], _ctx=ctx, _path="data[0]")],
                                       ctx=ctx, is_book=True)
        d = doc.to_dict()
        assert "book" in d
        assert "bookData" in d
        assert "adventure" not in d

    def test_official_to_dict(self):
        ctx = _ctx()
        s = SectionEntry(name="Ch1", entries=["Text."], _ctx=ctx, _path="data[0]")
        doc = OfficialAdventureData(data=[s], _ctx=ctx)
        d = doc.to_dict()
        assert "data" in d
        assert d["data"][0]["type"] == "section"

    def test_to_json_uses_tabs(self):
        ctx = _ctx()
        doc = HomebrewAdventure.build(name="Test", source="TEST",
                                       sections=[SectionEntry(name="Ch1", entries=["Hi."], _ctx=ctx, _path="data[0]")],
                                       ctx=ctx)
        j = doc.to_json()
        assert "\t" in j
        assert j.endswith("\n")


# ---------------------------------------------------------------------------
# Deserialization (from_dict / parse_entry)
# ---------------------------------------------------------------------------

class TestDeserialization:
    def test_parse_string(self):
        ctx = _ctx()
        result = parse_entry("Hello.", ctx, "x")
        assert result == "Hello."

    def test_parse_section(self):
        ctx = _ctx()
        result = parse_entry({"type": "section", "name": "Ch1", "id": "000",
                               "entries": ["Text."]}, ctx, "data[0]")
        assert isinstance(result, SectionEntry)
        assert result.name == "Ch1"

    def test_parse_entries(self):
        ctx = _ctx()
        result = parse_entry({"type": "entries", "name": "Sub", "entries": ["Text."]}, ctx, "x")
        assert isinstance(result, EntriesEntry)

    def test_parse_inset(self):
        ctx = _ctx()
        result = parse_entry({"type": "inset", "name": "Box", "entries": ["Text."]}, ctx, "x")
        assert isinstance(result, InsetEntry)

    def test_parse_list(self):
        ctx = _ctx()
        result = parse_entry({"type": "list", "items": ["a", "b"]}, ctx, "x")
        assert isinstance(result, ListEntry)
        assert len(result.items) == 2

    def test_parse_table(self):
        ctx = _ctx()
        result = parse_entry({"type": "table", "colLabels": ["A"], "rows": [["1"]]}, ctx, "x")
        assert isinstance(result, TableEntry)

    def test_parse_image(self):
        ctx = _ctx()
        result = parse_entry({"type": "image", "href": {"type": "internal", "path": "img.png"}}, ctx, "x")
        assert isinstance(result, ImageEntry)
        assert result.href.path == "img.png"

    def test_parse_hr(self):
        ctx = _ctx()
        result = parse_entry({"type": "hr"}, ctx, "x")
        assert isinstance(result, HrEntry)

    def test_parse_quote_with_from(self):
        ctx = _ctx()
        result = parse_entry({"type": "quote", "entries": ["Wise."],
                               "by": "Author", "from": "Source"}, ctx, "x")
        assert isinstance(result, QuoteEntry)
        assert result.from_ == "Source"

    def test_parse_item(self):
        ctx = _ctx()
        result = parse_entry({"type": "item", "name": "Bold", "entry": "Desc"}, ctx, "x")
        assert isinstance(result, ItemEntry)
        assert result.entry == "Desc"

    def test_parse_unknown_type_warns(self):
        ctx = _ctx()
        result = parse_entry({"type": "foobar", "entries": []}, ctx, "x")
        assert isinstance(result, GenericEntry)
        assert any("foobar" in w for w in ctx.result.warnings)

    def test_parse_missing_type_warns(self):
        ctx = _ctx()
        result = parse_entry({"name": "No type", "entries": []}, ctx, "x")
        assert isinstance(result, GenericEntry)
        assert any("no 'type'" in w for w in ctx.result.warnings)

    def test_parse_null_errors(self):
        ctx = _ctx()
        parse_entry(None, ctx, "x")
        assert any("null" in e for e in ctx.result.errors)

    def test_parse_nested_round_trip(self):
        ctx = _ctx()
        raw = {
            "type": "section", "name": "Ch1", "id": "000",
            "entries": [
                "A paragraph.",
                {"type": "entries", "name": "Sub", "id": "001", "entries": [
                    "Inner text.",
                    {"type": "list", "items": ["a", "b"]},
                ]},
                {"type": "inset", "name": "Box", "entries": ["Info."]},
                {"type": "hr"},
            ],
        }
        parsed = parse_entry(raw, ctx, "data[0]")
        assert isinstance(parsed, SectionEntry)
        d = parsed.to_dict()
        assert d["name"] == "Ch1"
        assert d["entries"][0] == "A paragraph."
        assert d["entries"][1]["type"] == "entries"
        assert d["entries"][1]["entries"][1]["type"] == "list"
        assert d["entries"][2]["type"] == "inset"
        assert d["entries"][3] == {"type": "hr"}


# ---------------------------------------------------------------------------
# Document deserialization
# ---------------------------------------------------------------------------

class TestDocumentDeserialization:
    def test_parse_official(self):
        raw = {"data": [
            {"type": "section", "name": "Ch1", "id": "000", "entries": ["Hello."]},
        ]}
        ctx = _ctx()
        doc = parse_document(raw, ctx)
        assert isinstance(doc, OfficialAdventureData)
        assert len(doc.data) == 1
        assert ctx.result.ok

    def test_parse_homebrew(self):
        raw = {
            "_meta": {"sources": [{"json": "TEST", "abbreviation": "TEST", "full": "Test"}]},
            "adventure": [{"name": "Test", "id": "TEST", "source": "TEST",
                           "contents": [{"name": "Ch1", "headers": []}]}],
            "adventureData": [{"id": "TEST", "source": "TEST",
                               "data": [{"type": "section", "name": "Ch1", "id": "000",
                                         "entries": ["Hello."]}]}],
        }
        ctx = _ctx()
        doc = parse_document(raw, ctx)
        assert isinstance(doc, HomebrewAdventure)
        assert len(doc.adventure_data.data) == 1
        assert ctx.result.ok

    def test_parse_book(self):
        raw = {
            "_meta": {"sources": [{"json": "TB"}]},
            "book": [{"name": "Test Book", "id": "TB", "source": "TB", "contents": []}],
            "bookData": [{"id": "TB", "source": "TB",
                          "data": [{"type": "section", "name": "Ch1", "entries": ["Hi."]}]}],
        }
        ctx = _ctx()
        doc = parse_document(raw, ctx)
        assert isinstance(doc, HomebrewAdventure)
        assert doc.is_book

    def test_parse_unrecognised(self):
        ctx = _ctx()
        doc = parse_document({"foo": "bar"}, ctx)
        assert any("Unrecognised" in e for e in ctx.result.errors)

    def test_parse_not_dict(self):
        ctx = _ctx()
        doc = parse_document([1, 2, 3], ctx)
        assert any("object" in e for e in ctx.result.errors)


# ---------------------------------------------------------------------------
# Contents / data alignment
# ---------------------------------------------------------------------------

class TestContentsAlignment:
    def test_aligned(self):
        ctx = _ctx()
        doc = HomebrewAdventure.build(name="Test", source="TEST",
                                       sections=[
                                           SectionEntry(name="A", entries=[], _ctx=ctx, _path="data[0]"),
                                           SectionEntry(name="B", entries=[], _ctx=ctx, _path="data[1]"),
                                       ], ctx=ctx)
        assert ctx.result.ok

    def test_misaligned_count_warns(self):
        ctx = _ctx()
        s1 = SectionEntry(name="A", entries=[], _ctx=ctx, _path="data[0]")
        s2 = SectionEntry(name="B", entries=[], _ctx=ctx, _path="data[1]")
        # Manually set mismatched contents
        doc = HomebrewAdventure(
            meta=Meta(sources=[MetaSource(json="T")], _ctx=ctx),
            adventure=AdventureIndex(name="Test", id="T", source="T",
                                     contents=[TocEntry(name="A")]),
            adventure_data=AdventureData(id="T", source="T", data=[s1, s2]),
            _ctx=ctx,
        )
        assert any("contents has 1" in w for w in ctx.result.warnings)

    def test_name_mismatch_warns(self):
        ctx = _ctx()
        s1 = SectionEntry(name="A", entries=[], _ctx=ctx, _path="data[0]")
        doc = HomebrewAdventure(
            meta=Meta(sources=[MetaSource(json="T")], _ctx=ctx),
            adventure=AdventureIndex(name="Test", id="T", source="T",
                                     contents=[TocEntry(name="Wrong Name")]),
            adventure_data=AdventureData(id="T", source="T", data=[s1]),
            _ctx=ctx,
        )
        assert any("Wrong Name" in w for w in ctx.result.warnings)


# ---------------------------------------------------------------------------
# ID assignment
# ---------------------------------------------------------------------------

class TestAssignIds:
    def test_sequential_ids(self):
        ctx = _ctx()
        s = SectionEntry(name="Ch1", entries=[
            EntriesEntry(name="Sub", entries=["Text."], _ctx=ctx, _path="x.entries[0]"),
            InsetEntry(name="Box", entries=["Info."], _ctx=ctx, _path="x.entries[1]"),
        ], _ctx=ctx, _path="data[0]")
        doc = OfficialAdventureData(data=[s], _ctx=ctx)
        doc.assign_ids()
        assert s.id == "000"
        assert s.entries[0].id == "001"
        assert s.entries[1].id == "002"

    def test_only_section_entries_inset_get_ids(self):
        ctx = _ctx()
        s = SectionEntry(name="Ch1", entries=[
            ListEntry(items=["a"], _ctx=ctx, _path="x.entries[0]"),
            "A string.",
        ], _ctx=ctx, _path="data[0]")
        doc = OfficialAdventureData(data=[s], _ctx=ctx)
        doc.assign_ids()
        assert s.id == "000"
        assert s.entries[0].id is None  # ListEntry doesn't get an ID


# ---------------------------------------------------------------------------
# TOC building
# ---------------------------------------------------------------------------

class TestBuildToc:
    def test_basic_toc(self):
        ctx = _ctx()
        doc = HomebrewAdventure.build(
            name="Test", source="TEST",
            sections=[
                SectionEntry(name="Intro", entries=[
                    EntriesEntry(name="Setup", entries=["Text."], _ctx=ctx, _path="x"),
                    EntriesEntry(name="Background", entries=["Text."], _ctx=ctx, _path="x"),
                ], _ctx=ctx, _path="data[0]"),
                SectionEntry(name="Chapter 1", entries=[], _ctx=ctx, _path="data[1]"),
            ],
            ctx=ctx,
        )
        toc = doc.adventure.contents
        assert len(toc) == 2
        assert toc[0].name == "Intro"
        assert len(toc[0].headers) == 2
        assert toc[0].headers[0].header == "Setup"
        assert toc[1].name == "Chapter 1"
        assert len(toc[1].headers) == 0


# ---------------------------------------------------------------------------
# Meta validation
# ---------------------------------------------------------------------------

class TestMetaValidation:
    def test_empty_sources_warns(self):
        ctx = _ctx()
        Meta(sources=[], _ctx=ctx)
        assert any("sources is empty" in w for w in ctx.result.warnings)

    def test_missing_json_errors(self):
        ctx = _ctx()
        Meta(sources=[MetaSource(json="", abbreviation="X")], _ctx=ctx)
        assert any("json is required" in e for e in ctx.result.errors)

    def test_valid_meta(self):
        ctx = _ctx()
        Meta(sources=[MetaSource(json="TEST", abbreviation="TEST", full="Test")], _ctx=ctx)
        assert ctx.result.ok


# ---------------------------------------------------------------------------
# HomebrewAdventure.build convenience
# ---------------------------------------------------------------------------

class TestBuild:
    def test_build_assigns_ids(self):
        ctx = _ctx()
        doc = HomebrewAdventure.build(
            name="My Adv", source="MYADV",
            sections=[SectionEntry(name="Ch1", entries=["Hi."], _ctx=ctx, _path="data[0]")],
            ctx=ctx,
        )
        assert doc.adventure_data.data[0].id == "000"

    def test_build_creates_toc(self):
        ctx = _ctx()
        doc = HomebrewAdventure.build(
            name="My Adv", source="MYADV",
            sections=[SectionEntry(name="Ch1", entries=["Hi."], _ctx=ctx, _path="data[0]")],
            ctx=ctx,
        )
        assert len(doc.adventure.contents) == 1
        assert doc.adventure.contents[0].name == "Ch1"

    def test_build_sets_meta(self):
        ctx = _ctx()
        doc = HomebrewAdventure.build(
            name="My Adv", source="MYADV",
            sections=[SectionEntry(name="Ch1", entries=["Hi."], _ctx=ctx, _path="data[0]")],
            ctx=ctx, authors=["Author"], convertedBy=["Claude"],
        )
        assert doc.meta.sources[0].json == "MYADV"
        assert doc.meta.sources[0].authors == ["Author"]

    def test_build_round_trip(self):
        ctx = _ctx()
        doc = HomebrewAdventure.build(
            name="Test", source="TEST",
            sections=[
                SectionEntry(name="Ch1", entries=[
                    "A paragraph.",
                    EntriesEntry(name="Sub", entries=["Inner."], _ctx=ctx, _path="x"),
                ], _ctx=ctx, _path="data[0]"),
            ],
            ctx=ctx,
        )
        j = doc.to_json()
        raw = json.loads(j)

        # Reload
        ctx2 = _ctx()
        doc2 = parse_document(raw, ctx2)
        assert isinstance(doc2, HomebrewAdventure)
        assert ctx2.result.ok
        assert doc2.adventure_data.data[0].name == "Ch1"


# ---------------------------------------------------------------------------
# Non-section top-level handling
# ---------------------------------------------------------------------------

class TestNonSectionTopLevel:
    def test_homebrew_non_section_errors(self):
        raw = {
            "_meta": {"sources": [{"json": "T"}]},
            "adventure": [{"name": "T", "id": "T", "source": "T", "contents": []}],
            "adventureData": [{"id": "T", "source": "T", "data": [
                {"type": "section", "name": "Ch1", "entries": []},
                {"type": "entries", "name": "Orphan", "entries": []},
            ]}],
        }
        ctx = _ctx()
        doc = parse_document(raw, ctx)
        assert any("must be 'section'" in e for e in ctx.result.errors)

    def test_homebrew_bare_string_errors(self):
        raw = {
            "_meta": {"sources": [{"json": "T"}]},
            "adventure": [{"name": "T", "id": "T", "source": "T", "contents": []}],
            "adventureData": [{"id": "T", "source": "T", "data": [
                "orphan string",
            ]}],
        }
        ctx = _ctx()
        doc = parse_document(raw, ctx)
        assert any("bare string" in e for e in ctx.result.errors)

    def test_official_non_section_warns(self):
        raw = {"data": [
            {"type": "entries", "name": "Orphan", "entries": []},
        ]}
        ctx = _ctx()
        doc = parse_document(raw, ctx)
        assert any("section" in w for w in ctx.result.warnings)


# ---------------------------------------------------------------------------
# GenericEntry pass-through
# ---------------------------------------------------------------------------

class TestGenericEntry:
    def test_round_trip(self):
        ctx = _ctx()
        raw = {"type": "foobar", "data": [1, 2, 3], "extra": "field"}
        parsed = parse_entry(raw, ctx, "x")
        assert isinstance(parsed, GenericEntry)
        d = parsed.to_dict()
        assert d["type"] == "foobar"
        assert d["data"] == [1, 2, 3]
        assert d["extra"] == "field"


# ---------------------------------------------------------------------------
# TocHeader / TocEntry
# ---------------------------------------------------------------------------

class TestTocEntry:
    def test_flat_header(self):
        h = TocHeader(header="Room A1", depth=0)
        assert h.to_dict() == "Room A1"

    def test_depth_header(self):
        h = TocHeader(header="Sub room", depth=1)
        assert h.to_dict() == {"header": "Sub room", "depth": 1}

    def test_from_raw_string(self):
        h = TocHeader.from_raw("Room A1")
        assert h.header == "Room A1"
        assert h.depth == 0

    def test_from_raw_dict(self):
        h = TocHeader.from_raw({"header": "Sub", "depth": 1})
        assert h.header == "Sub"
        assert h.depth == 1

    def test_toc_entry_round_trip(self):
        te = TocEntry(name="Ch1", headers=[
            TocHeader(header="Setup"),
            TocHeader(header="Detail", depth=1),
        ])
        d = te.to_dict()
        assert d["name"] == "Ch1"
        assert d["headers"] == ["Setup", {"header": "Detail", "depth": 1}]

        te2 = TocEntry.from_dict(d)
        assert te2.name == "Ch1"
        assert len(te2.headers) == 2


# ---------------------------------------------------------------------------
# Integration: official adventure files
# ---------------------------------------------------------------------------

class TestOfficialFiles:
    """Load official adventure files through the model and verify no errors."""

    OFFICIAL_DIR = Path("/home/kroussos/5etools-dev/5etools-src/data/adventure")

    @pytest.fixture
    def official_files(self):
        if not self.OFFICIAL_DIR.is_dir():
            pytest.skip("Official adventure directory not found")
        files = sorted(self.OFFICIAL_DIR.glob("*.json"))
        if not files:
            pytest.skip("No official adventure files found")
        return files

    def test_official_files_parse_no_errors(self, official_files):
        """All official adventure files should parse through the model with no errors."""
        failures = []
        for fpath in official_files:
            with open(fpath, encoding="utf-8") as f:
                raw = json.load(f)
            ctx = _ctx()
            doc = parse_document(raw, ctx)
            if not ctx.result.ok:
                failures.append(f"{fpath.name}: {ctx.result.errors[:3]}")
        assert failures == [], f"Official files with errors:\n" + "\n".join(failures)

    def test_lmop_structure(self, official_files):
        """Spot-check LMoP through the model."""
        lmop = self.OFFICIAL_DIR / "adventure-lmop.json"
        if not lmop.exists():
            pytest.skip("LMoP not found")
        with open(lmop, encoding="utf-8") as f:
            raw = json.load(f)
        ctx = _ctx()
        doc = parse_document(raw, ctx)
        assert isinstance(doc, OfficialAdventureData)
        assert ctx.result.ok
        assert len(doc.data) > 0
        assert doc.data[0].name == "Introduction"


# ---------------------------------------------------------------------------
# Integration: homebrew output files
# ---------------------------------------------------------------------------

class TestHomebrewOutput:
    HOMEBREW_DIR = Path("/home/kroussos/5etools-dev/5etools-src/pdf-translators")

    def test_toworlds(self):
        fpath = self.HOMEBREW_DIR / "adventure-toworlds.json"
        if not fpath.exists():
            pytest.skip("adventure-toworlds.json not found")
        with open(fpath, encoding="utf-8") as f:
            raw = json.load(f)
        ctx = _ctx()
        doc = parse_document(raw, ctx)
        assert isinstance(doc, HomebrewAdventure)
        if not ctx.result.ok:
            print(f"\nadventure-toworlds.json errors ({len(ctx.result.errors)}):")
            for e in ctx.result.errors[:10]:
                print(f"  {e}")
