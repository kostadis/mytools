"""Tests for pdf_to_5etools_v2 and the pdf_utils filter additions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import pdf_to_5etools_v2 as v2
import extract_monsters as _mon
from pdf_utils import (
    TocNode, is_anchor_bookmark, parse_toc_tree,
)


# ---------------------------------------------------------------------------
# pdf_utils: anchor bookmark filter
# ---------------------------------------------------------------------------

class TestAnchorBookmarkFilter:
    """Microsoft-Word-generated anchor bookmarks should be dropped by default."""

    @pytest.mark.parametrize("title,expected", [
        ("_GoBack", True),
        ("_GoBack1", True),
        ("_Toc123456789", True),
        ("_Ref987654321", True),
        ("_Hlk12345", True),
        ("  _GoBack", True),                      # leading whitespace
        ("Chapter 1", False),
        ("", False),
        ("_", True),
        ("A_real_title", False),                  # underscore in middle is fine
        ("Area 1_GoBack", False),                 # only filter when it LEADS
    ])
    def test_is_anchor_bookmark(self, title, expected):
        assert is_anchor_bookmark(title) is expected

    def test_parse_toc_tree_filters_goback_by_default(self):
        raw = [
            [1, "Introduction", 1],
            [1, "_GoBack", 5],
            [1, "_GoBack1", 7],
            [1, "Chapter 1", 10],
            [1, "_Toc12345", 12],
            [1, "Appendix", 20],
        ]
        roots = parse_toc_tree(raw, total_pages=30)
        titles = [r.title for r in roots]
        assert titles == ["Introduction", "Chapter 1", "Appendix"]

    def test_parse_toc_tree_can_keep_anchors(self):
        raw = [
            [1, "Intro", 1],
            [1, "_GoBack", 5],
            [1, "Chapter 1", 10],
        ]
        roots = parse_toc_tree(raw, total_pages=15,
                               skip_anchor_bookmarks=False)
        titles = [r.title for r in roots]
        assert "_GoBack" in titles

    def test_end_page_computed_over_anchor_gaps(self):
        """Dropping anchor bookmarks should not create gaps in the tree."""
        raw = [
            [1, "Intro", 1],
            [1, "_GoBack", 5],
            [1, "Chapter 1", 10],
        ]
        roots = parse_toc_tree(raw, total_pages=30)
        # Intro should run until Chapter 1 starts, not until _GoBack
        intro = roots[0]
        assert intro.title == "Intro"
        assert intro.end_page == 9


# ---------------------------------------------------------------------------
# v2 markdown heading extraction and TOC synthesis
# ---------------------------------------------------------------------------

class TestMarkdownHeadings:
    def test_parses_all_heading_levels(self):
        md = "\n".join([
            "# H1",
            "body",
            "## H2",
            "### H3",
            "#### H4",
            "##### H5",
        ])
        headings, lines = v2.parse_markdown_headings(md)
        assert [h.level for h in headings] == [1, 2, 3, 4, 5]
        assert [h.title for h in headings] == ["H1", "H2", "H3", "H4", "H5"]
        assert len(lines) == 6

    def test_strips_bold_markers_from_titles(self):
        md = "# **Dungeon Level One**\n## *Italic Title*\n### 101. **ARMORY**"
        headings, _ = v2.parse_markdown_headings(md)
        assert headings[0].title == "Dungeon Level One"
        # v2.clean_heading strips all * markers, so mixed bold/italic also cleans
        assert headings[1].title == "Italic Title"
        assert headings[2].title == "101. ARMORY"

    def test_records_line_numbers(self):
        md = "intro\n# First\nbody\n# Second"
        headings, _ = v2.parse_markdown_headings(md)
        assert headings[0].line_no == 1
        assert headings[1].line_no == 3

    def test_ignores_non_heading_hash_lines(self):
        """A `#` not followed by a space (e.g. a C preprocessor directive in a
        code block) should not be treated as a heading."""
        md = "```\n#include <stdio.h>\n```\n# Real Heading"
        headings, _ = v2.parse_markdown_headings(md)
        assert len(headings) == 1
        assert headings[0].title == "Real Heading"


class TestNumberedRoomNormalization:
    def _mk(self, items):
        return [v2.MdHeading(level=lvl, title=t, line_no=i)
                for i, (lvl, t) in enumerate(items)]

    def test_flattens_rooms_within_tolerance_of_common_level(self):
        # 6 numbered rooms: four at L4 (majority), one at L3 (within ±1
        # tolerance → flattened), one at L2 (outside tolerance → left alone,
        # treated as an inner-list item rather than a keyed room).
        heads = self._mk([
            (1, "Dungeon Level One"),
            (2, "101. ARMORY"),        # too far from common → NOT flattened
            (4, "102. ARMORY"),
            (4, "103. PILLARED HALL"),
            (4, "104. ROOM"),
            (3, "105. ROOM"),           # within ±1 → flattened to 4
            (4, "106. ROOM"),
        ])
        out = v2.normalise_numbered_rooms(heads)
        title_to_level = {h.title: h.level for h in out}
        # L4 rooms stay at 4; L3 room flattens to 4; L2 room stays at 2
        assert title_to_level["101. ARMORY"] == 2       # outlier preserved
        assert title_to_level["102. ARMORY"] == 4
        assert title_to_level["105. ROOM"] == 4          # flattened from 3

    def test_rejects_inner_numbered_lists(self):
        """The Nulb problem: a PDF with real rooms 1-N at one level AND an
        inner numbered list (patron types, quest hooks) at a much deeper
        level. Only the room series should be flattened; inner list items
        stay put so they don't become spurious keyed-room boundaries."""
        heads = self._mk([
            (2, "1. Waterside Hostel"),
            (2, "2. Manor"),
            (2, "3. Cottage"),
            (2, "4. Mill"),
            (5, "1. Villagers"),        # patron type inside a section
            (5, "2. Bargefolk"),         # patron type, deep
            (5, "3. Bandits"),           # patron type, deep
            (2, "5. Grove"),
        ])
        out = v2.normalise_numbered_rooms(heads)
        title_to_level = {h.title: h.level for h in out}
        # Real rooms stay at 2
        assert title_to_level["1. Waterside Hostel"] == 2
        assert title_to_level["5. Grove"] == 2
        # Patron list items at L5 are far outside tolerance → preserved
        assert title_to_level["1. Villagers"] == 5
        assert title_to_level["3. Bandits"] == 5

    def test_leaves_structure_alone_when_no_keyed_rooms(self):
        heads = self._mk([
            (1, "Intro"),
            (2, "Background"),
            (3, "Setting"),
        ])
        out = v2.normalise_numbered_rooms(heads)
        assert [h.level for h in out] == [1, 2, 3]

    def test_leaves_structure_alone_when_few_rooms(self):
        # Only 3 numbered rooms → below the 5-room threshold → no normalization
        heads = self._mk([
            (1, "Chapter"),
            (2, "1. Foo"),
            (4, "2. Bar"),
            (3, "3. Baz"),
        ])
        out = v2.normalise_numbered_rooms(heads)
        # Levels preserved
        assert [h.level for h in out] == [1, 2, 4, 3]

    def test_recognises_comma_delimited_room_numbers(self):
        # Some Marker outputs use "101, ARMORY" instead of "101. ARMORY"
        # Keep all rooms within ±1 of the majority level so the tight-
        # cluster heuristic fires.
        heads = self._mk([
            (4, "101, ARMORY"),
            (4, "102, ARMORY"),
            (4, "103, PILLARED HALL"),
            (3, "104, ROOM"),
            (4, "105, ROOM"),
            (4, "106, ROOM"),
        ])
        out = v2.normalise_numbered_rooms(heads)
        # All six are within tolerance — flatten to the common level 4
        numbered = [h for h in out if h.title.startswith("1")]
        assert {h.level for h in numbered} == {4}


class TestNestBetweenKeyedRooms:
    """Second-pass normalization: sub-headings between keyed rooms become
    children of the preceding keyed room."""

    def _mk(self, items):
        return [v2.MdHeading(level=lvl, title=t, line_no=i)
                for i, (lvl, t) in enumerate(items)]

    def test_sibling_subheadings_get_demoted_to_children(self):
        """The Nulb pattern: Marker put 'Background' at level 2 (shallower
        than the keyed room at level 3), making it a sibling. After
        normalization it should be level 4 — a child of the room."""
        heads = self._mk([
            (3, "1. Waterside Hostel"),
            (2, "Background"),          # should become 4
            (2, "Current Use"),          # should become 4
            (3, "2. Fishermen's Shack"),
            (2, "Treasure"),             # should become 4
            (3, "3. Manor"),
            (3, "4. Farm"),
            (3, "5. Cottage"),
            (3, "6. Mill"),
        ])
        v2.normalise_numbered_rooms(heads)
        titles_to_levels = {h.title: h.level for h in heads}
        assert titles_to_levels["Background"] == 4
        assert titles_to_levels["Current Use"] == 4
        assert titles_to_levels["Treasure"] == 4
        # Keyed rooms stay at their common level
        assert titles_to_levels["1. Waterside Hostel"] == 3

    def test_headings_before_first_keyed_room_are_untouched(self):
        """Intro / preface content should stay at whatever level it was."""
        heads = self._mk([
            (1, "Introduction"),         # before any keyed room, leave alone
            (2, "Using This Book"),      # ditto
            (3, "1. Waterside Hostel"),
            (3, "2. Manor"),
            (3, "3. Cottage"),
            (3, "4. Mill"),
            (3, "5. Grove"),
            (2, "Background"),           # after keyed rooms — demote
        ])
        v2.normalise_numbered_rooms(heads)
        # Intro untouched
        intro = next(h for h in heads if h.title == "Introduction")
        using = next(h for h in heads if h.title == "Using This Book")
        assert intro.level == 1
        assert using.level == 2
        # But the trailing "Background" should be demoted
        bg = next(h for h in heads if h.title == "Background")
        assert bg.level == 4

    def test_deeper_subheadings_preserved(self):
        """Headings already deeper than the keyed room (genuine sub-sub-
        sections) should NOT be demoted further."""
        heads = self._mk([
            (3, "1. Room"),
            (4, "Background"),           # already at child level
            (5, "Historical Note"),       # grandchild — preserve
            (3, "2. Room"),
            (3, "3. Room"),
            (3, "4. Room"),
            (3, "5. Room"),
        ])
        v2.normalise_numbered_rooms(heads)
        hist = next(h for h in heads if h.title == "Historical Note")
        assert hist.level == 5   # unchanged

    def test_noop_without_keyed_rooms(self):
        """Documents without numbered rooms should pass through untouched."""
        heads = self._mk([
            (1, "Part One"),
            (2, "Chapter 1"),
            (3, "Section A"),
            (2, "Chapter 2"),
        ])
        levels_before = [h.level for h in heads]
        v2.normalise_numbered_rooms(heads)
        assert [h.level for h in heads] == levels_before

    def test_trailing_subheadings_after_last_keyed_room_get_demoted(self):
        heads = self._mk([
            (3, "1. Room"),
            (3, "2. Room"),
            (3, "3. Room"),
            (3, "4. Room"),
            (3, "5. Room"),
            (2, "Appendix Notes"),       # after last keyed room — demote
            (3, "Another Section"),       # ditto
        ])
        v2.normalise_numbered_rooms(heads)
        app = next(h for h in heads if h.title == "Appendix Notes")
        another = next(h for h in heads if h.title == "Another Section")
        assert app.level == 4
        assert another.level == 4


class TestSyntheticToc:
    def test_line_numbers_stand_in_as_pages(self):
        heads = [
            v2.MdHeading(level=1, title="Chapter", line_no=0),
            v2.MdHeading(level=2, title="Section", line_no=10),
            v2.MdHeading(level=2, title="Section 2", line_no=20),
        ]
        roots = v2.build_synthetic_toc(heads, total_lines=30)
        assert len(roots) == 1
        chapter = roots[0]
        assert chapter.start_page == 1
        assert chapter.end_page == 30
        assert len(chapter.children) == 2


# ---------------------------------------------------------------------------
# v2 chunk building with oversize splitting
# ---------------------------------------------------------------------------

class TestSplitOversized:
    def _node(self, title, children=None):
        n = TocNode(level=1, title=title, start_page=1, end_page=1)
        n.children = children or []
        return n

    def test_under_threshold_emits_single_chunk(self):
        node = self._node("Small")
        out = v2.split_oversized([node], lambda n: "x" * 100, max_chars=1000)
        assert len(out) == 1
        assert out[0].root is node
        assert out[0].target_node is node
        assert out[0].is_prose_stub is False
        assert out[0].body == "x" * 100

    def test_oversized_section_splits_by_children(self):
        child_a = self._node("A")
        child_b = self._node("B")
        parent = self._node("Parent", [child_a, child_b])

        # Parent body is huge; each child body is small
        def body(n):
            return "x" * 10_000 if n is parent else "small"

        out = v2.split_oversized([parent], body, max_chars=1000)
        # Every chunk's root is the parent (top-level input node)
        assert all(c.root is parent for c in out)
        # Children still emitted
        target_titles = [c.target_node.title for c in out]
        assert "A" in target_titles
        assert "B" in target_titles

    def test_oversized_leaf_passes_through(self):
        """A leaf with no children can't be split; pass through as one chunk."""
        leaf = self._node("Big Leaf")
        out = v2.split_oversized([leaf], lambda n: "x" * 10_000, max_chars=1000)
        assert len(out) == 1
        assert out[0].target_node is leaf
        assert out[0].is_prose_stub is False

    def test_recurses_when_children_also_oversized(self):
        grandchild = self._node("Grandchild")
        child = self._node("Child", [grandchild])
        parent = self._node("Parent", [child])

        # Both parent and child are oversized; grandchild is fine
        def body(n):
            return "small" if n is grandchild else "x" * 10_000

        out = v2.split_oversized([parent], body, max_chars=1000)
        titles = [c.target_node.title for c in out]
        assert "Grandchild" in titles
        # Root tracking survives recursion
        assert all(c.root is parent for c in out)

    def test_oversized_parent_preserves_own_prose(self):
        """Regression: when a parent is split by children, the prose between
        the parent heading and its first child must still be emitted as a
        chunk. Previously this text was silently dropped."""
        child_a = TocNode(level=2, title="A", start_page=50, end_page=75,
                          children=[])
        child_b = TocNode(level=2, title="B", start_page=76, end_page=100,
                          children=[])
        parent = TocNode(level=1, title="Parent", start_page=1, end_page=100,
                         children=[child_a, child_b])

        def body(n):
            if n is parent:
                return "x" * 50_000            # oversized
            if n.title == "A":
                return "small A body"
            if n.title == "B":
                return "small B body"
            # Called with a synthesized prose-only node: parent intro text
            if n.title == "Parent" and n.end_page == 49:
                return "parent intro prose"
            raise AssertionError(f"unexpected body call for {n!r}")

        chunks = v2.split_oversized([parent], body, max_chars=1000)
        texts = [c.body for c in chunks]
        # Parent's own prose must appear
        assert "parent intro prose" in texts
        # Children still emitted
        assert "small A body" in texts
        assert "small B body" in texts
        # The prose chunk's target_node is the original parent (not a synth)
        # and its is_prose_stub flag is set
        prose_specs = [c for c in chunks if c.is_prose_stub]
        assert len(prose_specs) == 1
        assert prose_specs[0].target_node is parent

    def test_oversized_parent_with_no_prose_gap_skips_prose_chunk(self):
        """If a parent's first child starts at the parent's start_page (no
        gap), there is no prose to preserve — don't emit an empty chunk."""
        child = TocNode(level=2, title="Child", start_page=1, end_page=10,
                        children=[])
        parent = TocNode(level=1, title="Parent", start_page=1, end_page=10,
                         children=[child])

        def body(n):
            if n is parent:
                return "x" * 50_000
            if n is child:
                return "child body"
            raise AssertionError(f"unexpected body call for {n!r}")

        chunks = v2.split_oversized([parent], body, max_chars=1000)
        # Should only contain the child, no phantom parent-prose chunk
        assert len(chunks) == 1
        assert chunks[0].target_node.title == "Child"


# ---------------------------------------------------------------------------
# v2 prompt assembly
# ---------------------------------------------------------------------------

class TestAssembleAdventure:
    """Tree-preserving assembly: split roots get their chunks re-nested."""

    def _spec(self, *, root, target=None, is_stub=False, body="body"):
        return v2.ChunkSpec(
            root=root,
            target_node=target if target is not None else root,
            is_prose_stub=is_stub,
            body=body,
        )

    def test_unsplit_root_uses_claude_entries_as_is(self):
        """Single chunk for a root that wasn't split: the entries array
        Claude returned is placed directly inside the SectionEntry."""
        root = TocNode(level=1, title="Chapter 1",
                       start_page=1, end_page=10, children=[])
        spec = self._spec(root=root)
        entries = [
            "Opening paragraph.",
            {"type": "entries", "name": "Sub-section",
             "entries": ["nested paragraph"]},
        ]
        doc = v2.assemble_adventure(
            name="Test", source="TST",
            chunk_results=[(spec, entries)],
            author="Me", is_book=False,
        )
        # Top-level section is Chapter 1 with its two entries
        d = doc.to_dict()
        adv_data = d["adventureData"][0]["data"]
        assert len(adv_data) == 1
        assert adv_data[0]["name"] == "Chapter 1"
        # Claude's entries are preserved, no double-wrapping
        assert len(adv_data[0]["entries"]) == 2
        assert adv_data[0]["entries"][0] == "Opening paragraph."

    def test_split_root_rebuilds_tree_from_chunks(self):
        """A root that was split into prose-stub + child chunks should
        produce a SectionEntry with the prose at the top and the child
        wrapped in its own entries block."""
        child = TocNode(level=2, title="Hidden Cache",
                        start_page=4, end_page=10, children=[])
        root = TocNode(level=1, title="Waterside Hostel",
                       start_page=1, end_page=10, children=[child])
        prose_spec = self._spec(root=root, target=root, is_stub=True)
        child_spec = self._spec(root=root, target=child)

        prose_entries = ["The hostel smells of old ale."]
        child_entries = ["A loose floorboard hides 50 gp."]

        doc = v2.assemble_adventure(
            name="Test", source="TST",
            chunk_results=[(prose_spec, prose_entries),
                           (child_spec, child_entries)],
            author="Me", is_book=False,
        )
        d = doc.to_dict()
        adv_data = d["adventureData"][0]["data"]
        assert len(adv_data) == 1
        section = adv_data[0]
        assert section["name"] == "Waterside Hostel"
        # Prose at top
        assert section["entries"][0] == "The hostel smells of old ale."
        # Child wrapped
        wrapped = section["entries"][1]
        assert wrapped["type"] == "entries"
        assert wrapped["name"] == "Hidden Cache"
        assert wrapped["entries"] == ["A loose floorboard hides 50 gp."]

    def test_one_section_per_root_even_with_many_chunks(self):
        """Multiple chunks for one root produce ONE SectionEntry, not many."""
        root = TocNode(level=1, title="Big Section",
                       start_page=1, end_page=100, children=[
                           TocNode(level=2, title="A", start_page=5, end_page=50, children=[]),
                           TocNode(level=2, title="B", start_page=51, end_page=100, children=[]),
                       ])
        prose = self._spec(root=root, target=root, is_stub=True)
        spec_a = self._spec(root=root, target=root.children[0])
        spec_b = self._spec(root=root, target=root.children[1])
        doc = v2.assemble_adventure(
            name="T", source="TST",
            chunk_results=[
                (prose, ["intro"]),
                (spec_a, ["A content"]),
                (spec_b, ["B content"]),
            ],
            author="Me", is_book=False,
        )
        adv_data = doc.to_dict()["adventureData"][0]["data"]
        # ONE section, not three
        assert len(adv_data) == 1
        assert adv_data[0]["name"] == "Big Section"
        # 3 entries: intro + A wrapped + B wrapped
        assert len(adv_data[0]["entries"]) == 3
        assert adv_data[0]["entries"][0] == "intro"
        assert adv_data[0]["entries"][1]["name"] == "A"
        assert adv_data[0]["entries"][2]["name"] == "B"

    def test_chunk_with_none_entries_is_skipped(self):
        root = TocNode(level=1, title="A", start_page=1, end_page=5, children=[])
        other = TocNode(level=1, title="B", start_page=6, end_page=10, children=[])
        spec_a = self._spec(root=root)
        spec_b = self._spec(root=other)
        doc = v2.assemble_adventure(
            name="T", source="TST",
            chunk_results=[(spec_a, None), (spec_b, ["B ok"])],
            author="Me", is_book=False,
        )
        adv_data = doc.to_dict()["adventureData"][0]["data"]
        # Only B survives
        assert [s["name"] for s in adv_data] == ["B"]


class TestPromptBuilding:
    def test_includes_section_name(self):
        node = TocNode(level=1, title="Dungeon Level One", start_page=1, end_page=5)
        prompt = v2.build_prompt(node, "body text")
        assert "=== SECTION: Dungeon Level One ===" in prompt
        assert "body text" in prompt

    def test_lists_children_as_hints_when_present(self):
        parent = TocNode(level=1, title="Parent", start_page=1, end_page=5)
        parent.children = [
            TocNode(level=2, title="101. Armory", start_page=1, end_page=2),
            TocNode(level=2, title="102. Kitchen", start_page=3, end_page=5),
        ]
        prompt = v2.build_prompt(parent, "body")
        assert "101. Armory" in prompt
        assert "102. Kitchen" in prompt
        assert "sub-sections" in prompt.lower()

    def test_omits_hint_block_when_no_children(self):
        node = TocNode(level=1, title="Flat", start_page=1, end_page=2)
        prompt = v2.build_prompt(node, "body")
        assert "sub-sections" not in prompt.lower()


# ---------------------------------------------------------------------------
# v2 PDF profile routing
# ---------------------------------------------------------------------------

class TestProfilePdf:
    def _mock_doc(self, *, page_count, has_toc, chars_per_page):
        doc = MagicMock()
        doc.page_count = page_count
        doc.get_toc.return_value = [[1, "Ch 1", 1]] if has_toc else []
        page = MagicMock()
        page.get_text.return_value = "x" * chars_per_page
        doc.load_page.return_value = page
        return doc

    def test_digital_with_bookmarks_uses_fast_path(self):
        doc = self._mock_doc(page_count=100, has_toc=True, chars_per_page=5000)
        with patch("pdf_to_5etools_v2.fitz.open", return_value=doc):
            profile = v2.profile_pdf("fake.pdf")
        assert profile.has_bookmarks
        assert profile.has_selectable_text
        assert profile.use_fast_path

    def test_scan_with_no_bookmarks_uses_marker(self):
        doc = self._mock_doc(page_count=100, has_toc=False, chars_per_page=2)
        with patch("pdf_to_5etools_v2.fitz.open", return_value=doc):
            profile = v2.profile_pdf("fake.pdf")
        assert not profile.has_bookmarks
        assert not profile.has_selectable_text
        assert not profile.use_fast_path

    def test_bookmarked_but_image_only_pdf_uses_marker(self):
        """Bookmarks alone are not enough; need selectable text too."""
        doc = self._mock_doc(page_count=100, has_toc=True, chars_per_page=2)
        with patch("pdf_to_5etools_v2.fitz.open", return_value=doc):
            profile = v2.profile_pdf("fake.pdf")
        assert profile.has_bookmarks
        assert not profile.has_selectable_text
        assert not profile.use_fast_path

    def test_digital_without_bookmarks_uses_marker(self):
        """Text-only with no bookmarks has no structure — Marker extracts it."""
        doc = self._mock_doc(page_count=100, has_toc=False, chars_per_page=5000)
        with patch("pdf_to_5etools_v2.fitz.open", return_value=doc):
            profile = v2.profile_pdf("fake.pdf")
        assert not profile.use_fast_path


# ---------------------------------------------------------------------------
# v2 markdown body slicing
# ---------------------------------------------------------------------------

class TestMarkdownBodySlicing:
    def test_slices_by_line_range(self):
        lines = [f"line {i}" for i in range(20)]
        node = TocNode(level=1, title="Sec", start_page=5, end_page=10)
        body = v2._node_body_markdown(node, lines)
        assert "line 4" in body
        assert "line 9" in body
        assert "line 3" not in body
        assert "line 10" not in body


# ---------------------------------------------------------------------------
# extract_monsters — italic-string stat blocks in v2 adventure JSON
# ---------------------------------------------------------------------------

class TestItalicStatblocks:
    def _wrap(self, *statlines):
        """Build an adventure-shaped dict where each statline sits inside an
        entries[] as a bare string."""
        return {
            "adventureData": [{
                "data": [{
                    "type": "section",
                    "name": "Chapter",
                    "entries": [
                        {"type": "entries", "name": "101. Armory",
                         "entries": list(statlines)},
                    ],
                }],
            }],
        }

    def test_finds_single_statblock(self):
        doc = self._wrap(
            "This plain chamber contains racks for weapons.",
            "{@i Ghasts (2): AC 4, MV 15\", HD 4, hp 23, 20, #AT 3, D 1-4/1-4/1-8}",
        )
        blocks = _mon.extract_italic_statblocks(doc)
        assert len(blocks) == 1
        assert blocks[0]["name"] == "Ghasts (2)"
        assert "AC 4" in blocks[0]["text"]

    def test_finds_multiple_deeply_nested(self):
        doc = {
            "adventureData": [{
                "data": [{
                    "type": "section", "name": "Dungeon",
                    "entries": [
                        {"type": "entries", "name": "Room",
                         "entries": [
                             {"type": "entries", "name": "Sub",
                              "entries": [
                                  "{@i Brigands (6): AC 8, MV 12\", Level 0}",
                                  "prose",
                                  "{@i Gnolls (4): AC 5, MV 9\", HD 2, hp 10}",
                              ]},
                         ]},
                    ],
                }],
            }],
        }
        blocks = _mon.extract_italic_statblocks(doc)
        names = [b["name"] for b in blocks]
        assert "Brigands (6)" in names
        assert "Gnolls (4)" in names

    def test_ignores_non_statblock_italic(self):
        """Italic strings without the `NAME: AC N` shape are atmospheric, not stats."""
        doc = self._wrap(
            "{@i A cold wind blows through the chamber.}",
            "{@i You hear scratching noises from below.}",
        )
        assert _mon.extract_italic_statblocks(doc) == []

    def test_ignores_numbered_room_headings(self):
        """A string that happens to start with a number shouldn't be matched
        as a stat block even if it has `: AC` later."""
        doc = self._wrap(
            "{@i 101. Armory: AC ruined, full of broken racks}",
        )
        # The leading-digit guard in the regex should reject this
        blocks = _mon.extract_italic_statblocks(doc)
        names = [b["name"] for b in blocks]
        assert not any(n.startswith("101") for n in names)

    def test_deduplicates_repeated_statblocks(self):
        """The same stat line appearing in multiple rooms should be emitted once."""
        doc = {
            "adventureData": [{
                "data": [{
                    "type": "section", "name": "C",
                    "entries": [
                        {"type": "entries", "name": "R1",
                         "entries": ["{@i Ghouls (2): AC 6, MV 9\", HD 2, hp 10, 9}"]},
                        {"type": "entries", "name": "R2",
                         "entries": ["{@i Ghouls (2): AC 6, MV 9\", HD 2, hp 10, 9}"]},
                    ],
                }],
            }],
        }
        blocks = _mon.extract_italic_statblocks(doc)
        assert len(blocks) == 1

    def test_italic_statblock_to_text_formats_for_prompt(self):
        block = {"name": "Ghasts (2)",
                 "text": "Ghasts (2): AC 4, MV 15\", HD 4, hp 23"}
        text = _mon.italic_statblock_to_text(block)
        assert text.startswith("=== Ghasts (2) ===")
        assert "AC 4" in text


# ---------------------------------------------------------------------------
# extract_monsters — Marker markdown scanning for --monsters-only
# ---------------------------------------------------------------------------

class TestMarkdownStatblocks:
    def test_extracts_1e_stat_line_from_inside_room(self):
        """The whole point of the rewrite: a room description that merely
        contains a stat line should NOT be classified as a monster. Only
        the stat line itself is the monster."""
        md = "\n".join([
            "## 101. Armory",
            "Two ghouls guard this room.",
            "Ghouls (2): AC 6, MV 9\", HD 2, hp 10, #AT 3, D 1-3/1-3/1-6",
            "",
            "## 102. Kitchen",
            "This room smells of old meat. No exits visible.",
        ])
        blocks = _mon.extract_markdown_statblocks(md)
        assert len(blocks) == 1
        assert blocks[0]["name"] == "Ghouls (2)"
        # Context should include the stat line
        assert "AC 6" in blocks[0]["text"]
        # The room heading is NOT the monster name
        assert "101. Armory" not in blocks[0]["name"]

    def test_keeps_section_with_5e_stat_block_header(self):
        """5e bestiary-style: one creature per heading, Armor Class/Hit Points labels."""
        md = "\n".join([
            "## Ancient Red Dragon",
            "**Armor Class** 22 (natural armor)",
            "**Hit Points** 546 (28d20 + 252)",
            "**Speed** 40 ft., climb 40 ft., fly 80 ft.",
        ])
        blocks = _mon.extract_markdown_statblocks(md)
        assert len(blocks) == 1
        assert blocks[0]["name"] == "Ancient Red Dragon"
        assert "Armor Class" in blocks[0]["text"]

    def test_keeps_section_whose_first_body_line_is_1e_stat(self):
        """Bestiary-style 1e PDFs sometimes put the stat line right under the heading."""
        md = "\n".join([
            "## Giant Rat",
            "Giant Rat: AC 7, MV 12\", HD 1/2, hp 3, #AT 1, D 1-3",
            "Usually found in groups of 2d8.",
        ])
        blocks = _mon.extract_markdown_statblocks(md)
        assert len(blocks) == 1
        assert blocks[0]["name"] == "Giant Rat"

    def test_drops_prose_with_isolated_AC_mention(self):
        """'AC' appearing in prose text (e.g. 'the dog's AC is quite poor')
        should not trigger stat-block detection — there must be other stat tokens."""
        md = "\n".join([
            "## Description",
            "The armored knight has very good AC against ranged attacks.",
            "He uses a longsword.",
        ])
        assert _mon.extract_markdown_statblocks(md) == []

    def test_drops_section_without_stats(self):
        md = "\n".join([
            "## Backstory",
            "Long ago, the temple fell to darkness.",
            "Adventurers have explored it ever since.",
        ])
        assert _mon.extract_markdown_statblocks(md) == []

    def test_ignores_numbered_room_heading_as_stat_name(self):
        """The pattern '101. Armory: AC ruined' should not be a stat block
        because the name starts with a digit."""
        md = "101. Armory: AC ruined, MV 0\", HD 0"
        blocks = _mon.extract_markdown_statblocks(md)
        assert blocks == []

    def test_deduplicates_repeated_stat_lines(self):
        """Same stat line appearing in multiple rooms -> one result.

        Uses a prose first-body-line so section-level detection does NOT
        fire (otherwise each section is kept wholesale under its heading
        and they wouldn't dedupe against each other)."""
        md = "\n".join([
            "## Room A",
            "Monsters lurk here.",
            "Gnolls (2): AC 5, MV 9\", HD 2, hp 10, #AT 1, D 2-8",
            "## Room B",
            "More foes.",
            "Gnolls (2): AC 5, MV 9\", HD 2, hp 10, #AT 1, D 2-8",
        ])
        blocks = _mon.extract_markdown_statblocks(md)
        assert len(blocks) == 1
        assert blocks[0]["name"] == "Gnolls (2)"

    def test_strips_bold_markers_from_headings_and_names(self):
        md = "\n".join([
            "## **Boss Monster**",
            "**Boss Monster**: AC 18, MV 9\", HD 5, #AT 1, D 1-8",
        ])
        blocks = _mon.extract_markdown_statblocks(md)
        assert len(blocks) == 1
        assert "Boss Monster" in blocks[0]["name"]


# ---------------------------------------------------------------------------
# Bestiary source-meta helper + output path
# ---------------------------------------------------------------------------

class TestBestiaryMeta:
    def test_make_bestiary_source_meta_appends_b(self):
        src_id, meta = _mon.make_bestiary_source_meta(
            "TOWORLDS", "To Worlds Unknown", author="Legendary Games",
        )
        assert src_id == "TOWORLDSb"
        assert meta["json"] == "TOWORLDSb"
        assert "(Bestiary)" in meta["full"]
        assert meta["authors"] == ["Legendary Games"]

    def test_bestiary_path_sibling_of_adventure(self):
        assert v2._bestiary_path(Path("/tmp/module.json")) \
            == Path("/tmp/module-bestiary.json")
        assert v2._bestiary_path(Path("./foo.json")) \
            == Path("./foo-bestiary.json")


# ---------------------------------------------------------------------------
# build_bestiary: shape of the output dict, no-op on empty input
# ---------------------------------------------------------------------------

class TestBuildBestiary:
    def test_empty_input_returns_empty_bestiary(self):
        out = _mon.build_bestiary(
            client=MagicMock(), statblocks=[],
            source_id="TESTb",
            source_meta={"json": "TESTb", "abbreviation": "TESTb",
                         "full": "Test (Bestiary)", "version": "1.0.0",
                         "authors": [], "convertedBy": []},
            model="claude-haiku-4-5-20251001",
        )
        assert out["monster"] == []
        assert out["_meta"]["sources"][0]["json"] == "TESTb"

    def test_sets_source_on_each_monster(self):
        statblocks = [{"name": "A", "text": "A: AC 10"}]
        with patch("extract_monsters._api.call_claude") as mock_call:
            mock_call.return_value = [
                {"name": "A", "source": "PLACEHOLDER", "cr": "1"},
            ]
            out = _mon.build_bestiary(
                client=MagicMock(), statblocks=statblocks,
                source_id="TESTb",
                source_meta={"json": "TESTb"},
                model="claude-haiku-4-5-20251001",
            )
        assert out["monster"][0]["source"] == "TESTb"

    def test_deduplicates_monsters_by_name(self):
        statblocks = [
            {"name": "A", "text": "A: AC 10"},
            {"name": "A", "text": "A: AC 10"},
        ]
        with patch("extract_monsters._api.call_claude") as mock_call:
            # Claude returns two different A's; dedup keeps the last one
            mock_call.side_effect = [
                [{"name": "A", "cr": "1"}],
                [{"name": "A", "cr": "2"}],
            ]
            out = _mon.build_bestiary(
                client=MagicMock(), statblocks=statblocks,
                source_id="TESTb",
                source_meta={"json": "TESTb"},
                model="claude-haiku-4-5-20251001",
                batch_size=1,
            )
        assert len(out["monster"]) == 1
        assert out["monster"][0]["cr"] == "2"
