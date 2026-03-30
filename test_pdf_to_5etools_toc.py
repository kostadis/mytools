#!/usr/bin/env python3
"""Tests for pdf_to_5etools_toc.py — TOC-driven converter.

Run:
    pytest test_pdf_to_5etools_toc.py -v
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pdf_utils import TocNode, parse_toc_tree

# Import converter functions (fitz/anthropic already available in this env,
# but we mock API calls in tests that need them)
from pdf_to_5etools_toc import (
    extract_chapter_text,
    build_chapter_prompt,
    chunk_by_toc,
    assemble_document,
    build_toc_from_tree,
    _prune_toc,
    SYSTEM_PROMPT,
)
from adventure_model import BuildContext, SectionEntry, EntriesEntry


# ---------------------------------------------------------------------------
# TocNode and parse_toc_tree
# ---------------------------------------------------------------------------

class TestTocNode(unittest.TestCase):
    def test_page_count(self):
        n = TocNode(level=1, title="Ch1", start_page=5, end_page=10)
        self.assertEqual(n.page_count, 6)

    def test_page_count_single_page(self):
        n = TocNode(level=1, title="Ch1", start_page=5, end_page=5)
        self.assertEqual(n.page_count, 1)

    def test_walk_flat(self):
        n = TocNode(level=1, title="Ch1", start_page=1, end_page=10)
        self.assertEqual(len(n.walk()), 1)

    def test_walk_nested(self):
        child = TocNode(level=2, title="Sub", start_page=3, end_page=5)
        parent = TocNode(level=1, title="Ch1", start_page=1, end_page=10,
                         children=[child])
        self.assertEqual(len(parent.walk()), 2)


class TestParseTocTree(unittest.TestCase):
    def test_simple_flat(self):
        """Three level-1 entries become three roots."""
        raw = [
            [1, "Chapter 1", 1],
            [1, "Chapter 2", 10],
            [1, "Chapter 3", 20],
        ]
        roots = parse_toc_tree(raw, total_pages=30)
        self.assertEqual(len(roots), 3)
        self.assertEqual(roots[0].title, "Chapter 1")
        self.assertEqual(roots[0].start_page, 1)
        self.assertEqual(roots[0].end_page, 9)
        self.assertEqual(roots[1].end_page, 19)
        self.assertEqual(roots[2].end_page, 30)

    def test_nested_levels(self):
        """Level-2 entries become children of preceding level-1."""
        raw = [
            [1, "Chapter 1", 1],
            [2, "Section A", 3],
            [2, "Section B", 7],
            [1, "Chapter 2", 10],
        ]
        roots = parse_toc_tree(raw, total_pages=20)
        self.assertEqual(len(roots), 2)
        self.assertEqual(len(roots[0].children), 2)
        self.assertEqual(roots[0].children[0].title, "Section A")
        self.assertEqual(roots[0].children[0].end_page, 6)
        self.assertEqual(roots[0].children[1].title, "Section B")
        self.assertEqual(roots[0].children[1].end_page, 9)
        self.assertEqual(len(roots[1].children), 0)

    def test_three_level_nesting(self):
        """Level-3 entries become children of preceding level-2."""
        raw = [
            [1, "Chapter 1", 1],
            [2, "Section A", 3],
            [3, "Room A1", 4],
            [3, "Room A2", 6],
            [2, "Section B", 8],
            [1, "Chapter 2", 15],
        ]
        roots = parse_toc_tree(raw, total_pages=20)
        self.assertEqual(len(roots), 2)
        ch1 = roots[0]
        self.assertEqual(len(ch1.children), 2)
        sec_a = ch1.children[0]
        self.assertEqual(len(sec_a.children), 2)
        self.assertEqual(sec_a.children[0].title, "Room A1")
        self.assertEqual(sec_a.children[1].title, "Room A2")

    def test_empty_toc(self):
        self.assertEqual(parse_toc_tree([], total_pages=10), [])

    def test_max_level_filter(self):
        raw = [
            [1, "Chapter 1", 1],
            [2, "Section A", 3],
            [3, "Deep Sub", 5],
        ]
        roots = parse_toc_tree(raw, total_pages=10, max_level=2)
        self.assertEqual(len(roots), 1)
        self.assertEqual(len(roots[0].children), 1)
        # Level-3 should be filtered out
        self.assertEqual(len(roots[0].children[0].children), 0)

    def test_level_normalisation(self):
        """If min level is 2 (no level 1), levels are shifted down."""
        raw = [
            [2, "Section A", 1],
            [2, "Section B", 5],
            [3, "Sub B1", 7],
        ]
        roots = parse_toc_tree(raw, total_pages=10)
        # Levels normalised: 2→1, 3→2
        self.assertEqual(len(roots), 2)
        self.assertEqual(roots[0].level, 1)
        self.assertEqual(len(roots[1].children), 1)
        self.assertEqual(roots[1].children[0].level, 2)

    def test_page_0_clamped_to_1(self):
        """Pages reported as 0 are clamped to 1."""
        raw = [[1, "Intro", 0], [1, "Ch1", 5]]
        roots = parse_toc_tree(raw, total_pages=10)
        self.assertEqual(roots[0].start_page, 1)

    def test_end_page_never_less_than_start(self):
        """Adjacent entries on the same page: end_page >= start_page."""
        raw = [[1, "A", 5], [1, "B", 5], [1, "C", 10]]
        roots = parse_toc_tree(raw, total_pages=15)
        for r in roots:
            self.assertGreaterEqual(r.end_page, r.start_page)


# ---------------------------------------------------------------------------
# Chapter text extraction
# ---------------------------------------------------------------------------

class TestExtractChapterText(unittest.TestCase):
    def _make_pages(self):
        return [
            {"page_num": 1, "blocks": [{"text": "Page 1", "is_heading": False,
                                         "heading_level": 0, "bold": False, "italic": False}]},
            {"page_num": 2, "blocks": [{"text": "Page 2", "is_heading": True,
                                         "heading_level": 1, "bold": True, "italic": False}]},
            {"page_num": 3, "blocks": [{"text": "Page 3", "is_heading": False,
                                         "heading_level": 0, "bold": False, "italic": False}]},
        ]

    def test_filters_by_page_range(self):
        pages = self._make_pages()
        text = extract_chapter_text(pages, 2, 3)
        self.assertIn("Page 2", text)
        self.assertIn("Page 3", text)
        self.assertNotIn("Page 1", text)

    def test_single_page(self):
        pages = self._make_pages()
        text = extract_chapter_text(pages, 1, 1)
        self.assertIn("Page 1", text)
        self.assertNotIn("Page 2", text)

    def test_empty_range(self):
        pages = self._make_pages()
        text = extract_chapter_text(pages, 10, 20)
        self.assertEqual(text.strip(), "")


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

class TestBuildChapterPrompt(unittest.TestCase):
    def test_includes_section_name(self):
        node = TocNode(level=1, title="Chapter 1", start_page=1, end_page=10)
        prompt = build_chapter_prompt(node, "Some text")
        self.assertIn("Chapter 1", prompt)
        self.assertIn("pages 1–10", prompt)

    def test_includes_sub_sections(self):
        child = TocNode(level=2, title="Room A1", start_page=3, end_page=5)
        node = TocNode(level=1, title="Chapter 1", start_page=1, end_page=10,
                       children=[child])
        prompt = build_chapter_prompt(node, "Some text")
        self.assertIn("Room A1", prompt)
        self.assertIn("Known sub-sections", prompt)

    def test_includes_grandchildren(self):
        grandchild = TocNode(level=3, title="Trap", start_page=4, end_page=4)
        child = TocNode(level=2, title="Room A1", start_page=3, end_page=5,
                        children=[grandchild])
        node = TocNode(level=1, title="Ch1", start_page=1, end_page=10,
                       children=[child])
        prompt = build_chapter_prompt(node, "text")
        self.assertIn("Trap", prompt)

    def test_no_children_no_sub_section_header(self):
        node = TocNode(level=1, title="Ch1", start_page=1, end_page=5)
        prompt = build_chapter_prompt(node, "text")
        self.assertNotIn("Known sub-sections", prompt)


# ---------------------------------------------------------------------------
# TOC chunking
# ---------------------------------------------------------------------------

class TestChunkByToc(unittest.TestCase):
    def _make_pages(self, n):
        return [
            {"page_num": i + 1, "blocks": [
                {"text": f"Content page {i+1}", "is_heading": False,
                 "heading_level": 0, "bold": False, "italic": False}
            ]}
            for i in range(n)
        ]

    def test_one_chunk_per_root(self):
        roots = [
            TocNode(level=1, title="Ch1", start_page=1, end_page=5),
            TocNode(level=1, title="Ch2", start_page=6, end_page=10),
        ]
        pages = self._make_pages(10)
        chunks = chunk_by_toc(roots, pages)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0][0].title, "Ch1")
        self.assertEqual(chunks[1][0].title, "Ch2")

    def test_oversized_leaf_splits_by_page(self):
        """A chapter exceeding MAX_CHAPTER_CHARS with no children splits by page."""
        import pdf_to_5etools_toc as mod
        old_max = mod.MAX_CHAPTER_CHARS
        mod.MAX_CHAPTER_CHARS = 200  # tiny limit to force splitting
        try:
            roots = [TocNode(level=1, title="Big Chapter", start_page=1, end_page=5)]
            pages = self._make_pages(5)
            chunks = chunk_by_toc(roots, pages)
            # Should have been split into multiple sub-chunks
            self.assertGreater(len(chunks), 1)
            # All chunks should have synthetic titles starting with "Big Chapter (p"
            for node, prompt in chunks:
                self.assertTrue(node.title.startswith("Big Chapter"))
        finally:
            mod.MAX_CHAPTER_CHARS = old_max

    def test_oversized_with_children_splits_by_toc(self):
        """A chapter exceeding MAX_CHAPTER_CHARS with children splits by TOC."""
        import pdf_to_5etools_toc as mod
        old_max = mod.MAX_CHAPTER_CHARS
        mod.MAX_CHAPTER_CHARS = 200
        try:
            child1 = TocNode(level=2, title="Part A", start_page=1, end_page=3)
            child2 = TocNode(level=2, title="Part B", start_page=4, end_page=5)
            root = TocNode(level=1, title="Big Chapter", start_page=1, end_page=5,
                           children=[child1, child2])
            pages = self._make_pages(5)
            chunks = chunk_by_toc([root], pages)
            titles = [n.title for n, _ in chunks]
            self.assertIn("Part A", titles)
            self.assertIn("Part B", titles)
        finally:
            mod.MAX_CHAPTER_CHARS = old_max

    def test_empty_chapter_skipped(self):
        """Chapters with no page content are skipped."""
        roots = [
            TocNode(level=1, title="Ch1", start_page=100, end_page=100),
        ]
        pages = self._make_pages(10)
        chunks = chunk_by_toc(roots, pages)
        self.assertEqual(len(chunks), 0)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

class TestAssembleDocument(unittest.TestCase):
    def test_direct_results(self):
        """Each root has a direct Claude result."""
        roots = [
            TocNode(level=1, title="Chapter 1", start_page=1, end_page=10),
            TocNode(level=1, title="Chapter 2", start_page=11, end_page=20),
        ]
        results = {
            "Chapter 1": ["Paragraph 1.", {"type": "entries", "name": "Sub", "entries": ["inner"]}],
            "Chapter 2": ["Paragraph 2."],
        }
        ctx = BuildContext()
        sections = assemble_document(roots, results, ctx)
        self.assertEqual(len(sections), 2)
        self.assertIsInstance(sections[0], SectionEntry)
        self.assertEqual(sections[0].name, "Chapter 1")
        self.assertEqual(len(sections[0].entries), 2)
        self.assertEqual(sections[1].name, "Chapter 2")

    def test_sub_chunked_assembly(self):
        """Root was split into children — assembles children as nested entries."""
        child1 = TocNode(level=2, title="Section A", start_page=1, end_page=5)
        child2 = TocNode(level=2, title="Section B", start_page=6, end_page=10)
        root = TocNode(level=1, title="Chapter 1", start_page=1, end_page=10,
                       children=[child1, child2])

        results = {
            # No direct result for "Chapter 1" — sub-chunked
            "Section A": ["Content A."],
            "Section B": ["Content B."],
        }
        ctx = BuildContext()
        sections = assemble_document([root], results, ctx)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].name, "Chapter 1")
        self.assertEqual(len(sections[0].entries), 2)
        self.assertIsInstance(sections[0].entries[0], EntriesEntry)
        self.assertEqual(sections[0].entries[0].name, "Section A")

    def test_validates_entries(self):
        """Unknown tags in Claude output are caught during assembly."""
        roots = [TocNode(level=1, title="Ch1", start_page=1, end_page=10)]
        results = {"Ch1": ["See {@scroll fireball}."]}
        ctx = BuildContext()
        assemble_document(roots, results, ctx)
        self.assertTrue(any("scroll" in e for e in ctx.result.errors))

    def test_page_split_assembly(self):
        """Page-split results are concatenated flat into the section."""
        root = TocNode(level=1, title="Big Chapter", start_page=1, end_page=20)
        results = {
            "Big Chapter (p1–10)": ["Part one content."],
            "Big Chapter (p11–20)": ["Part two content."],
        }
        ctx = BuildContext()
        sections = assemble_document([root], results, ctx)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].name, "Big Chapter")
        self.assertEqual(len(sections[0].entries), 2)
        self.assertEqual(sections[0].entries[0], "Part one content.")
        self.assertEqual(sections[0].entries[1], "Part two content.")

    def test_child_page_split_assembly(self):
        """TOC child that was page-split gets its entries concatenated."""
        child = TocNode(level=2, title="Part 1", start_page=1, end_page=20)
        root = TocNode(level=1, title="Chapter 1", start_page=1, end_page=20,
                       children=[child])
        results = {
            "Part 1 (p1–10)": ["First half."],
            "Part 1 (p11–20)": ["Second half."],
        }
        ctx = BuildContext()
        sections = assemble_document([root], results, ctx)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].name, "Chapter 1")
        # Part 1 should be an EntriesEntry with both halves
        self.assertEqual(len(sections[0].entries), 1)
        part1 = sections[0].entries[0]
        self.assertIsInstance(part1, EntriesEntry)
        self.assertEqual(part1.name, "Part 1")
        self.assertEqual(len(part1.entries), 2)


# ---------------------------------------------------------------------------
# TOC from tree
# ---------------------------------------------------------------------------

class TestBuildTocFromTree(unittest.TestCase):
    def test_basic(self):
        child1 = TocNode(level=2, title="Section A", start_page=3, end_page=5)
        child2 = TocNode(level=2, title="Section B", start_page=6, end_page=9)
        root = TocNode(level=1, title="Chapter 1", start_page=1, end_page=10,
                       children=[child1, child2])
        toc = build_toc_from_tree([root])
        self.assertEqual(len(toc), 1)
        self.assertEqual(toc[0].name, "Chapter 1")
        self.assertEqual(len(toc[0].headers), 2)
        self.assertEqual(toc[0].headers[0].header, "Section A")

    def test_grandchildren_as_depth_1(self):
        grandchild = TocNode(level=3, title="Room A1", start_page=4, end_page=4)
        child = TocNode(level=2, title="Section A", start_page=3, end_page=5,
                        children=[grandchild])
        root = TocNode(level=1, title="Ch1", start_page=1, end_page=10,
                       children=[child])
        toc = build_toc_from_tree([root])
        self.assertEqual(len(toc[0].headers), 2)
        self.assertEqual(toc[0].headers[1].header, "Room A1")
        self.assertEqual(toc[0].headers[1].depth, 1)

    def test_empty_children(self):
        root = TocNode(level=1, title="Ch1", start_page=1, end_page=10)
        toc = build_toc_from_tree([root])
        self.assertEqual(len(toc[0].headers), 0)


# ---------------------------------------------------------------------------
# TOC pruning
# ---------------------------------------------------------------------------

class TestPruneToc(unittest.TestCase):
    def test_prune_out_of_range(self):
        roots = [
            TocNode(level=1, title="Ch1", start_page=1, end_page=10),
            TocNode(level=1, title="Ch2", start_page=11, end_page=20),
            TocNode(level=1, title="Ch3", start_page=21, end_page=30),
        ]
        pruned = _prune_toc(roots, 11, 20)
        self.assertEqual(len(pruned), 1)
        self.assertEqual(pruned[0].title, "Ch2")

    def test_prune_clamps_page_range(self):
        roots = [
            TocNode(level=1, title="Ch1", start_page=1, end_page=20),
        ]
        pruned = _prune_toc(roots, 5, 15)
        self.assertEqual(pruned[0].start_page, 5)
        self.assertEqual(pruned[0].end_page, 15)

    def test_prune_children(self):
        child = TocNode(level=2, title="Sub", start_page=15, end_page=20)
        root = TocNode(level=1, title="Ch1", start_page=1, end_page=20,
                       children=[child])
        pruned = _prune_toc([root], 1, 10)
        # Root survives but child is out of range
        self.assertEqual(len(pruned), 1)
        self.assertEqual(len(pruned[0].children), 0)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

class TestSystemPrompt(unittest.TestCase):
    def test_no_section_instruction(self):
        self.assertIn("Do NOT wrap your output in a top-level", SYSTEM_PROMPT)

    def test_has_tag_rules(self):
        self.assertIn("{@creature", SYSTEM_PROMPT)

    def test_has_entry_types(self):
        self.assertIn("insetReadaloud", SYSTEM_PROMPT)


# ---------------------------------------------------------------------------
# Integration: real PDF TOC parsing (requires PyMuPDF + actual PDF)
# ---------------------------------------------------------------------------

class TestRealPdfToc(unittest.TestCase):
    PDF_PATH = Path("/home/kroussos/5etools-dev/5etools-src/pdf-translators/"
                    "To_Worlds_Unknown_5e_(revised).pdf")

    def test_to_worlds_toc_structure(self):
        if not self.PDF_PATH.exists():
            self.skipTest("To Worlds Unknown PDF not found")
        from pdf_utils import get_toc_tree
        roots = get_toc_tree(self.PDF_PATH)
        self.assertGreater(len(roots), 0)
        # All nodes should have valid page ranges
        for root in roots:
            for node in root.walk():
                self.assertGreaterEqual(node.end_page, node.start_page,
                                        f"{node.title}: end < start")
                self.assertGreater(node.start_page, 0,
                                   f"{node.title}: start_page <= 0")


if __name__ == "__main__":
    unittest.main()
