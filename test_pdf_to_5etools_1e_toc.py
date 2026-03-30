#!/usr/bin/env python3
"""Tests for pdf_to_5etools_1e_toc.py — TOC-driven 1e converter.

Run:
    pytest test_pdf_to_5etools_1e_toc.py -v

Tests the 1e-specific layers (preprocessing, prompt, system prompt) that sit
on top of the shared TOC infrastructure. The TOC parsing and assembly tests
are in test_pdf_to_5etools_toc.py.
"""

from __future__ import annotations

import re
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pdf_utils import TocNode

# The 1e TOC module itself loads without OCR (lazy imports)
from pdf_to_5etools_1e_toc import (
    SYSTEM_PROMPT,
    build_chapter_prompt_1e,
    chunk_by_toc_1e,
    _ensure_1e_imports,
)


# ---------------------------------------------------------------------------
# Stub the 1e module's OCR dependencies so we can test preprocessing
# ---------------------------------------------------------------------------

def _stub_ocr_packages():
    """Install stubs for pytesseract/PIL/pdf2image so pdf_to_5etools_1e imports."""
    for name in ("pytesseract", "PIL", "PIL.Image", "PIL.ImageFilter",
                 "PIL.ImageEnhance", "pdf2image"):
        if name not in sys.modules:
            m = types.ModuleType(name)
            sys.modules[name] = m
            if name == "pytesseract":
                m.image_to_data = MagicMock()
                m.Output = MagicMock()
                m.Output.DICT = "dict"
            elif name == "PIL":
                m.Image = MagicMock()
                m.ImageFilter = MagicMock()
                m.ImageEnhance = MagicMock()
            elif name == "PIL.Image":
                m.Image = MagicMock()
            elif name == "PIL.ImageFilter":
                m.SHARPEN = MagicMock()
            elif name == "PIL.ImageEnhance":
                m.Contrast = MagicMock()
            elif name == "pdf2image":
                m.convert_from_path = MagicMock()

_stub_ocr_packages()

# Now safe to ensure 1e imports
_ensure_1e_imports()
from pdf_to_5etools_1e_toc import _1e


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

class TestSystemPrompt(unittest.TestCase):
    def test_no_top_level_section(self):
        """Prompt tells Claude NOT to create top-level sections."""
        self.assertIn("Do NOT wrap your output in a top-level", SYSTEM_PROMPT)

    def test_has_room_key_rules(self):
        self.assertIn("[ROOM-KEY-N]", SYSTEM_PROMPT)

    def test_has_1e_stat_rules(self):
        self.assertIn("[1E-STAT]", SYSTEM_PROMPT)

    def test_has_room_key_discard_rule(self):
        """Room Key/Encounter Key labels should be discarded, not wrapped."""
        self.assertIn("Room Key", SYSTEM_PROMPT)
        self.assertIn("NOT become wrapper entries", SYSTEM_PROMPT)

    def test_has_tag_rules(self):
        self.assertIn("{@creature", SYSTEM_PROMPT)

    def test_has_nesting_rules(self):
        self.assertIn("headers", SYSTEM_PROMPT)

    def test_entries_not_section(self):
        """Sub-sections must use entries, not section."""
        self.assertIn('use {"type":"entries"}', SYSTEM_PROMPT)


# ---------------------------------------------------------------------------
# 1e prompt building (preprocessing integration)
# ---------------------------------------------------------------------------

class TestBuildChapterPrompt1e(unittest.TestCase):
    def test_has_context_prefix(self):
        node = TocNode(level=1, title="Dungeon Level One", start_page=1, end_page=10)
        prompt = build_chapter_prompt_1e(node, "Some text")
        self.assertIn("[CONTEXT:", prompt)

    def test_has_section_name(self):
        node = TocNode(level=1, title="Dungeon Level One", start_page=1, end_page=10)
        prompt = build_chapter_prompt_1e(node, "Some text")
        self.assertIn("Dungeon Level One", prompt)

    def test_has_sub_sections(self):
        child = TocNode(level=2, title="Room A1", start_page=3, end_page=5)
        node = TocNode(level=1, title="Ch1", start_page=1, end_page=10,
                       children=[child])
        prompt = build_chapter_prompt_1e(node, "Some text")
        self.assertIn("Room A1", prompt)
        self.assertIn("Known sub-sections", prompt)

    def test_trigger_neutralization(self):
        """TSR-era trigger words are replaced in the prompt."""
        node = TocNode(level=1, title="Ch1", start_page=1, end_page=5)
        prompt = build_chapter_prompt_1e(node, "The demons enslaved the wenches.")
        # "demons" → "fiend", "enslaved" → "captured", "wenches" → "barmaid"
        self.assertNotIn("demons", prompt)
        self.assertNotIn("enslaved", prompt)
        self.assertNotIn("wenches", prompt)

    def test_sanitization(self):
        """Control characters are stripped."""
        node = TocNode(level=1, title="Ch1", start_page=1, end_page=5)
        prompt = build_chapter_prompt_1e(node, "Text with\x00null\x01bytes")
        self.assertNotIn("\x00", prompt)
        self.assertNotIn("\x01", prompt)


# ---------------------------------------------------------------------------
# 1e chunking
# ---------------------------------------------------------------------------

class TestChunkByToc1e(unittest.TestCase):
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
        chunks = chunk_by_toc_1e(roots, pages)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0][0].title, "Ch1")
        self.assertEqual(chunks[1][0].title, "Ch2")

    def test_prompts_have_context_prefix(self):
        roots = [TocNode(level=1, title="Ch1", start_page=1, end_page=3)]
        pages = self._make_pages(3)
        chunks = chunk_by_toc_1e(roots, pages)
        self.assertTrue(chunks[0][1].startswith("[CONTEXT:"))

    def test_trigger_words_neutralized_in_chunks(self):
        pages = [
            {"page_num": 1, "blocks": [
                {"text": "The demons enslaved villagers", "is_heading": False,
                 "heading_level": 0, "bold": False, "italic": False}
            ]}
        ]
        roots = [TocNode(level=1, title="Ch1", start_page=1, end_page=1)]
        chunks = chunk_by_toc_1e(roots, pages)
        self.assertNotIn("demons", chunks[0][1])
        self.assertNotIn("enslaved", chunks[0][1])


# ---------------------------------------------------------------------------
# 1e preprocessing functions (via lazy import)
# ---------------------------------------------------------------------------

class TestPreprocessing(unittest.TestCase):
    def test_sanitize_text(self):
        result = _1e._sanitize_text("Hello\x00World\x01Test")
        self.assertNotIn("\x00", result)
        self.assertNotIn("\x01", result)

    def test_neutralize_triggers(self):
        result = _1e._neutralize_triggers("The demons and wenches")
        self.assertNotIn("demons", result)
        self.assertNotIn("wenches", result)

    def test_strip_noise_lines(self):
        text = "Good content here\nxy\nAnother good line"
        result = _1e._strip_noise_lines(text)
        self.assertIn("Good content here", result)
        self.assertIn("Another good line", result)
        # "xy" is noise (no word >= 4 chars)
        self.assertNotIn("\nxy\n", result)

    def test_deinterleave_columns_passthrough(self):
        """Normal text without column artifacts passes through unchanged."""
        text = "Line 1\nLine 2\nLine 3"
        result = _1e._deinterleave_columns(text)
        self.assertEqual(result, text)


if __name__ == "__main__":
    unittest.main()
