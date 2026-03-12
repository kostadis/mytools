#!/usr/bin/env python3
"""
Unit tests for pdf_to_5etools.py and pdf_to_5etools_ocr.py.

Run with:
    cd pdf-translators
    pytest test_pdf_to_5etools.py -v
"""

from __future__ import annotations

import importlib
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers to import the modules under test without requiring fitz / anthropic
# ---------------------------------------------------------------------------

def _make_stub(name: str) -> types.ModuleType:
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


def _import_base():
    """Import pdf_to_5etools with fitz + anthropic stubbed out."""
    stub_fitz = _make_stub("fitz")
    stub_fitz.open = MagicMock()
    stub_fitz.TEXT_PRESERVE_WHITESPACE = 0

    stub_anthropic = _make_stub("anthropic")
    stub_anthropic.Anthropic = MagicMock()

    if "pdf_to_5etools" in sys.modules:
        del sys.modules["pdf_to_5etools"]

    import pdf_to_5etools as mod
    return mod


def _import_ocr():
    """Import pdf_to_5etools_ocr with all hard deps stubbed out."""
    stub_fitz = _make_stub("fitz")
    stub_fitz.open = MagicMock()
    stub_fitz.TEXT_PRESERVE_WHITESPACE = 0

    stub_anthropic = _make_stub("anthropic")
    stub_anthropic.Anthropic = MagicMock()

    stub_pyt = _make_stub("pytesseract")
    stub_pyt.image_to_data = MagicMock()
    stub_pyt.Output = MagicMock()
    stub_pyt.Output.DICT = "dict"

    # PIL needs individual sub-modules importable via `from PIL import X`
    stub_pil = _make_stub("PIL")
    stub_pil.Image = MagicMock()
    stub_pil.ImageFilter = MagicMock()
    stub_pil.ImageEnhance = MagicMock()
    _make_stub("PIL.Image").Image = MagicMock()
    _make_stub("PIL.ImageFilter").SHARPEN = MagicMock()
    _make_stub("PIL.ImageEnhance").Contrast = MagicMock()

    # pdf2image needs convert_from_path as an attribute
    stub_pdf2image = _make_stub("pdf2image")
    stub_pdf2image.convert_from_path = MagicMock()

    if "pdf_to_5etools_ocr" in sys.modules:
        del sys.modules["pdf_to_5etools_ocr"]

    import pdf_to_5etools_ocr as mod
    return mod


# ---------------------------------------------------------------------------
# Module-level import (done once to avoid repeated patching overhead)
# ---------------------------------------------------------------------------
BASE = _import_base()
OCR  = _import_ocr()


# ===========================================================================
# Tests for pdf_to_5etools.py (BASE)
# ===========================================================================

class TestNormalisePath(unittest.TestCase):
    """normalise_path handles Windows, WSL-mount, and Unix paths."""

    def _call(self, raw: str) -> Path:
        return BASE.normalise_path(raw)

    def test_windows_backslash(self):
        p = self._call(r"G:\My Drive\foo.pdf")
        self.assertEqual(str(p), "/mnt/g/My Drive/foo.pdf")

    def test_windows_forward_slash(self):
        p = self._call("C:/Users/Bob/bar.pdf")
        self.assertEqual(str(p), "/mnt/c/Users/Bob/bar.pdf")

    def test_linux_absolute(self):
        p = self._call("/tmp/test.pdf")
        self.assertEqual(str(p), "/tmp/test.pdf")

    def test_strips_quotes(self):
        p = self._call('"G:/foo/bar.pdf"')
        self.assertEqual(str(p), "/mnt/g/foo/bar.pdf")

    def test_strips_single_quotes(self):
        p = self._call("'G:/foo/bar.pdf'")
        self.assertEqual(str(p), "/mnt/g/foo/bar.pdf")

    def test_tilde_expansion(self):
        import os
        p = self._call("~/test.pdf")
        self.assertTrue(str(p).startswith(os.path.expanduser("~")))

    def test_uppercase_drive_lowercased(self):
        p = self._call("D:/docs/file.pdf")
        self.assertTrue(str(p).startswith("/mnt/d/"))


class TestMedian(unittest.TestCase):
    """_median returns the correct median (or 12.0 for empty input)."""

    def test_empty(self):
        self.assertEqual(BASE._median([]), 12.0)

    def test_single(self):
        self.assertEqual(BASE._median([7.0]), 7.0)

    def test_odd_count(self):
        self.assertEqual(BASE._median([1.0, 3.0, 5.0]), 3.0)

    def test_even_count(self):
        self.assertEqual(BASE._median([2.0, 4.0, 6.0, 8.0]), 5.0)

    def test_already_sorted(self):
        self.assertEqual(BASE._median([10.0, 12.0, 14.0]), 12.0)


class TestPageToAnnotatedText(unittest.TestCase):
    """page_to_annotated_text annotates headings and italic spans."""

    def _make_block(self, text, is_heading=False, heading_level=0,
                    bold=False, italic=False):
        return {
            "text": text,
            "is_heading": is_heading,
            "heading_level": heading_level,
            "bold": bold,
            "italic": italic,
        }

    def test_plain_text(self):
        page = {"blocks": [self._make_block("Hello world")]}
        self.assertEqual(BASE.page_to_annotated_text(page), "Hello world")

    def test_h1_heading(self):
        page = {"blocks": [self._make_block("Chapter One", True, 1)]}
        self.assertEqual(BASE.page_to_annotated_text(page), "[H1] Chapter One")

    def test_h2_heading(self):
        page = {"blocks": [self._make_block("Section A", True, 2)]}
        self.assertEqual(BASE.page_to_annotated_text(page), "[H2] Section A")

    def test_h3_heading(self):
        page = {"blocks": [self._make_block("Sub-section", True, 3)]}
        self.assertEqual(BASE.page_to_annotated_text(page), "[H3] Sub-section")

    def test_italic_text(self):
        page = {"blocks": [self._make_block("Read aloud", italic=True)]}
        self.assertEqual(BASE.page_to_annotated_text(page),
                         "[italic]Read aloud[/italic]")

    def test_bold_italic_not_wrapped(self):
        # Bold+italic should NOT be wrapped with [italic] tags
        page = {"blocks": [self._make_block("Bold italic", bold=True, italic=True)]}
        self.assertEqual(BASE.page_to_annotated_text(page), "Bold italic")

    def test_multiple_blocks(self):
        page = {
            "blocks": [
                self._make_block("Chapter", True, 1),
                self._make_block("Intro paragraph"),
            ]
        }
        result = BASE.page_to_annotated_text(page)
        self.assertIn("[H1] Chapter", result)
        self.assertIn("Intro paragraph", result)

    def test_empty_blocks(self):
        page = {"blocks": []}
        self.assertEqual(BASE.page_to_annotated_text(page), "")


class TestChunkPages(unittest.TestCase):
    """chunk_pages splits the list into equal-sized groups."""

    def _pages(self, n):
        return [{"page_num": i + 1, "blocks": []} for i in range(n)]

    def test_even_split(self):
        chunks = BASE.chunk_pages(self._pages(6), 2)
        self.assertEqual(len(chunks), 3)
        self.assertEqual(len(chunks[0]), 2)

    def test_remainder(self):
        chunks = BASE.chunk_pages(self._pages(7), 3)
        self.assertEqual(len(chunks), 3)
        self.assertEqual(len(chunks[-1]), 1)

    def test_chunk_larger_than_pages(self):
        chunks = BASE.chunk_pages(self._pages(3), 10)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(len(chunks[0]), 3)

    def test_empty_input(self):
        self.assertEqual(BASE.chunk_pages([], 5), [])

    def test_single_page(self):
        chunks = BASE.chunk_pages(self._pages(1), 6)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0][0]["page_num"], 1)


class TestParseClaudeResponse(unittest.TestCase):
    """_parse_claude_response handles valid JSON, markdown fences, and errors."""

    def _call(self, raw: str):
        return BASE._parse_claude_response(raw, verbose=False)

    def test_plain_json_array(self):
        raw = '[{"type":"section","name":"Intro"}]'
        result = self._call(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Intro")

    def test_json_fenced_json(self):
        raw = '```json\n[{"type":"section","name":"Test"}]\n```'
        result = self._call(raw)
        self.assertEqual(result[0]["name"], "Test")

    def test_plain_fenced(self):
        raw = '```\n["paragraph"]\n```'
        result = self._call(raw)
        self.assertEqual(result, ["paragraph"])

    def test_single_object_wrapped_in_list(self):
        raw = '{"type":"section","name":"X"}'
        result = self._call(raw)
        self.assertIsInstance(result, list)
        self.assertEqual(result[0]["name"], "X")

    def test_empty_array(self):
        self.assertEqual(self._call("[]"), [])

    def test_invalid_json_returns_empty(self):
        result = self._call("not json at all")
        self.assertEqual(result, [])

    def test_truncated_json_returns_empty(self):
        result = self._call('[{"type":"section","na')
        self.assertEqual(result, [])

    def test_whitespace_preserved_in_strings(self):
        raw = '[{"type":"list","items":["item one","item two"]}]'
        result = self._call(raw)
        self.assertEqual(result[0]["items"], ["item one", "item two"])


class TestAssignIds(unittest.TestCase):
    """assign_ids stamps sequential 3-digit IDs onto section/entries/inset objects."""

    def setUp(self):
        BASE.reset_ids()

    def test_section_gets_id(self):
        entries = [{"type": "section", "name": "Ch1", "entries": []}]
        BASE.assign_ids(entries)
        self.assertEqual(entries[0]["id"], "000")

    def test_entries_type_gets_id(self):
        entries = [{"type": "entries", "name": "Sub", "entries": []}]
        BASE.assign_ids(entries)
        self.assertEqual(entries[0]["id"], "000")

    def test_inset_gets_id(self):
        entries = [{"type": "inset", "name": "Box", "entries": []}]
        BASE.assign_ids(entries)
        self.assertEqual(entries[0]["id"], "000")

    def test_table_does_not_get_id(self):
        entries = [{"type": "table", "colLabels": [], "rows": []}]
        BASE.assign_ids(entries)
        self.assertNotIn("id", entries[0])

    def test_list_does_not_get_id(self):
        entries = [{"type": "list", "items": ["a"]}]
        BASE.assign_ids(entries)
        self.assertNotIn("id", entries[0])

    def test_sequential_ids(self):
        entries = [
            {"type": "section", "name": "A", "entries": []},
            {"type": "section", "name": "B", "entries": []},
            {"type": "section", "name": "C", "entries": []},
        ]
        BASE.assign_ids(entries)
        self.assertEqual([e["id"] for e in entries], ["000", "001", "002"])

    def test_nested_entries_get_ids(self):
        entries = [
            {
                "type": "section",
                "name": "Ch1",
                "entries": [
                    {"type": "entries", "name": "Sub1", "entries": []},
                    {"type": "entries", "name": "Sub2", "entries": []},
                ],
            }
        ]
        BASE.assign_ids(entries)
        self.assertEqual(entries[0]["id"], "000")
        self.assertEqual(entries[0]["entries"][0]["id"], "001")
        self.assertEqual(entries[0]["entries"][1]["id"], "002")

    def test_strings_skipped(self):
        entries = ["A plain paragraph", {"type": "section", "name": "X", "entries": []}]
        BASE.assign_ids(entries)
        self.assertEqual(entries[1]["id"], "000")

    def test_counter_starts_at_zero_after_reset(self):
        BASE.assign_ids([{"type": "section", "name": "X", "entries": []}])
        BASE.reset_ids()
        entries = [{"type": "section", "name": "Y", "entries": []}]
        BASE.assign_ids(entries)
        self.assertEqual(entries[0]["id"], "000")

    def test_id_format_three_digits(self):
        BASE.reset_ids()
        entries = [{"type": "section", "name": str(i), "entries": []}
                   for i in range(12)]
        BASE.assign_ids(entries)
        self.assertEqual(entries[10]["id"], "010")
        self.assertEqual(entries[11]["id"], "011")


class TestBuildToc(unittest.TestCase):
    """build_toc creates the contents array expected by 5etools index files."""

    def test_single_section_no_headers(self):
        data = [{"type": "section", "name": "Introduction", "entries": []}]
        toc = BASE.build_toc(data)
        self.assertEqual(len(toc), 1)
        self.assertEqual(toc[0]["name"], "Introduction")
        self.assertEqual(toc[0]["headers"], [])

    def test_section_with_subsections(self):
        data = [
            {
                "type": "section",
                "name": "Chapter 1",
                "entries": [
                    {"type": "entries", "name": "Section A", "entries": []},
                    {"type": "entries", "name": "Section B", "entries": []},
                ],
            }
        ]
        toc = BASE.build_toc(data)
        self.assertEqual(toc[0]["headers"], ["Section A", "Section B"])

    def test_non_section_entries_ignored(self):
        data = [
            "A plain string",
            {"type": "entries", "name": "Not a section", "entries": []},
            {"type": "section", "name": "Real Section", "entries": []},
        ]
        toc = BASE.build_toc(data)
        self.assertEqual(len(toc), 1)
        self.assertEqual(toc[0]["name"], "Real Section")

    def test_multiple_sections(self):
        data = [
            {"type": "section", "name": "Ch1", "entries": []},
            {"type": "section", "name": "Ch2", "entries": []},
        ]
        toc = BASE.build_toc(data)
        self.assertEqual([t["name"] for t in toc], ["Ch1", "Ch2"])

    def test_only_entries_subsections_included(self):
        # Tables and lists nested in a section should not appear in headers
        data = [
            {
                "type": "section",
                "name": "Ch1",
                "entries": [
                    {"type": "table", "colLabels": [], "rows": []},
                    {"type": "list", "items": []},
                    {"type": "entries", "name": "Valid Header", "entries": []},
                ],
            }
        ]
        toc = BASE.build_toc(data)
        self.assertEqual(toc[0]["headers"], ["Valid Header"])

    def test_empty_data(self):
        self.assertEqual(BASE.build_toc([]), [])


# ===========================================================================
# Tests for pdf_to_5etools_ocr.py (OCR)
# ===========================================================================

class TestOcrNormalisePath(unittest.TestCase):
    """OCR module's normalise_path should behave identically to the base module."""

    def _call(self, raw: str) -> Path:
        return OCR.normalise_path(raw)

    def test_windows_path(self):
        p = self._call(r"G:\books\dmg.pdf")
        self.assertEqual(str(p), "/mnt/g/books/dmg.pdf")

    def test_linux_path(self):
        p = self._call("/home/user/dmg.pdf")
        self.assertEqual(str(p), "/home/user/dmg.pdf")


class TestInjectTableMarkers(unittest.TestCase):
    """_inject_table_markers wraps table-like runs with [TABLE-START/END]."""

    def _call(self, lines):
        return OCR._inject_table_markers(lines)

    def test_no_tables(self):
        lines = ["This is a paragraph.", "Another sentence."]
        self.assertEqual(self._call(lines), lines)

    def test_table_detected(self):
        # 3+ lines each with 2+ whitespace-separated columns
        lines = [
            "Name  CR  HP",
            "Goblin  1/4  7",
            "Orc  1/2  15",
        ]
        result = self._call(lines)
        self.assertIn("[TABLE-START]", result)
        self.assertIn("[TABLE-END]", result)

    def test_table_requires_three_rows(self):
        # Only 2 rows: should NOT be wrapped
        lines = ["Name  CR", "Goblin  1/4"]
        result = self._call(lines)
        self.assertNotIn("[TABLE-START]", result)

    def test_annotated_lines_not_matched(self):
        # Lines starting with [ should pass through unchanged
        lines = ["[H1] Chapter", "Name  CR  HP", "Goblin  1/4  7", "Orc  1/2  15"]
        result = self._call(lines)
        # The annotated [H1] line should still be present
        self.assertIn("[H1] Chapter", result)
        # The table should be wrapped
        self.assertIn("[TABLE-START]", result)

    def test_tab_separated_table(self):
        lines = ["Name\tCR\tHP", "Goblin\t1/4\t7", "Orc\t1/2\t15"]
        result = self._call(lines)
        self.assertIn("[TABLE-START]", result)

    def test_table_content_preserved(self):
        lines = [
            "Name  CR  HP",
            "Goblin  1/4  7",
            "Orc  1/2  15",
        ]
        result = self._call(lines)
        for row in lines:
            self.assertIn(row, result)

    def test_mixed_content(self):
        lines = [
            "Here is some intro text.",
            "Name  CR  HP",
            "Goblin  1/4  7",
            "Orc  1/2  15",
            "More narrative text follows.",
        ]
        result = self._call(lines)
        self.assertIn("[TABLE-START]", result)
        self.assertIn("[TABLE-END]", result)
        self.assertIn("Here is some intro text.", result)
        self.assertIn("More narrative text follows.", result)

    def test_single_column_lines_not_table(self):
        lines = ["Word1", "Word2", "Word3", "Word4"]
        result = self._call(lines)
        self.assertNotIn("[TABLE-START]", result)


class TestOcrAssignIds(unittest.TestCase):
    """OCR module's assign_ids matches base module behaviour."""

    def setUp(self):
        OCR.reset_ids()

    def test_section_id(self):
        entries = [{"type": "section", "name": "X", "entries": []}]
        OCR.assign_ids(entries)
        self.assertEqual(entries[0]["id"], "000")

    def test_inset_id(self):
        entries = [{"type": "inset", "name": "Box", "entries": []}]
        OCR.assign_ids(entries)
        self.assertEqual(entries[0]["id"], "000")

    def test_table_no_id(self):
        entries = [{"type": "table", "rows": []}]
        OCR.assign_ids(entries)
        self.assertNotIn("id", entries[0])

    def test_nested(self):
        entries = [
            {
                "type": "section",
                "name": "Ch",
                "entries": [{"type": "entries", "name": "S", "entries": []}],
            }
        ]
        OCR.assign_ids(entries)
        self.assertEqual(entries[0]["id"], "000")
        self.assertEqual(entries[0]["entries"][0]["id"], "001")


class TestOcrBuildToc(unittest.TestCase):
    """OCR module's build_toc matches base module behaviour."""

    def test_basic(self):
        data = [
            {
                "type": "section",
                "name": "Ch1",
                "entries": [
                    {"type": "entries", "name": "Sec A", "entries": []},
                ],
            }
        ]
        toc = OCR.build_toc(data)
        self.assertEqual(toc[0]["name"], "Ch1")
        self.assertEqual(toc[0]["headers"], ["Sec A"])


if __name__ == "__main__":
    unittest.main()
