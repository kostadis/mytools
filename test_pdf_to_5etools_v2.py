"""Tests for pdf_to_5etools_v2 and the pdf_utils filter additions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import pdf_to_5etools_v2 as v2
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

    def test_flattens_rooms_to_common_level(self):
        # 6 numbered rooms: one at L2, four at L4, one at L3 → common = L4
        heads = self._mk([
            (1, "Dungeon Level One"),
            (2, "101. ARMORY"),
            (4, "102. ARMORY"),
            (4, "103. PILLARED HALL"),
            (4, "104. ROOM"),
            (3, "105. ROOM"),
            (4, "106. ROOM"),
        ])
        out = v2.normalise_numbered_rooms(heads)
        numbered = [h for h in out if h.title[0].isdigit()]
        assert {h.level for h in numbered} == {4}

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
        heads = self._mk([
            (2, "101, ARMORY"),
            (4, "102, ARMORY"),
            (4, "103, PILLARED HALL"),
            (3, "104, ROOM"),
            (4, "105, ROOM"),
            (4, "106, ROOM"),
        ])
        out = v2.normalise_numbered_rooms(heads)
        # Common level among the 6 numbered rooms should be applied
        assert len({h.level for h in out}) == 1


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
        assert out == [(node, "x" * 100)]

    def test_oversized_section_splits_by_children(self):
        child_a = self._node("A")
        child_b = self._node("B")
        parent = self._node("Parent", [child_a, child_b])

        # Parent body is huge; each child body is small
        def body(n):
            return "x" * 10_000 if n is parent else "small"

        out = v2.split_oversized([parent], body, max_chars=1000)
        names = [n.title for n, _ in out]
        assert names == ["A", "B"]

    def test_oversized_leaf_passes_through(self):
        """A leaf with no children can't be split; pass through as one chunk."""
        leaf = self._node("Big Leaf")
        out = v2.split_oversized([leaf], lambda n: "x" * 10_000, max_chars=1000)
        assert out == [(leaf, "x" * 10_000)]

    def test_recurses_when_children_also_oversized(self):
        grandchild = self._node("Grandchild")
        child = self._node("Child", [grandchild])
        parent = self._node("Parent", [child])

        # Both parent and child are oversized; grandchild is fine
        def body(n):
            return "small" if n is grandchild else "x" * 10_000

        out = v2.split_oversized([parent], body, max_chars=1000)
        assert [n.title for n, _ in out] == ["Grandchild"]


# ---------------------------------------------------------------------------
# v2 prompt assembly
# ---------------------------------------------------------------------------

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
