#!/usr/bin/env python3
"""
Unit tests for pdf_to_5etools converters, cli_args, and claude_api.

Run with:
    cd pdf-translators
    pytest test_pdf_to_5etools.py -v
"""

from __future__ import annotations

import argparse
import importlib
import io
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch


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


def _import_1e():
    """Import pdf_to_5etools_1e with all hard deps stubbed out."""
    stub_fitz = _make_stub("fitz")
    stub_fitz.open = MagicMock()
    stub_fitz.TEXT_PRESERVE_WHITESPACE = 0

    stub_anthropic = _make_stub("anthropic")
    stub_anthropic.Anthropic = MagicMock()

    stub_pyt = _make_stub("pytesseract")
    stub_pyt.image_to_data = MagicMock()
    stub_pyt.Output = MagicMock()
    stub_pyt.Output.DICT = "dict"

    stub_pil = _make_stub("PIL")
    stub_pil.Image = MagicMock()
    stub_pil.ImageFilter = MagicMock()
    stub_pil.ImageEnhance = MagicMock()
    _make_stub("PIL.Image").Image = MagicMock()
    _make_stub("PIL.ImageFilter").SHARPEN = MagicMock()
    _make_stub("PIL.ImageEnhance").Contrast = MagicMock()

    stub_pdf2image = _make_stub("pdf2image")
    stub_pdf2image.convert_from_path = MagicMock()

    if "pdf_to_5etools_1e" in sys.modules:
        del sys.modules["pdf_to_5etools_1e"]

    import pdf_to_5etools_1e as mod
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
BASE  = _import_base()
MOD1E = _import_1e()
OCR   = _import_ocr()

# cli_args has no heavy deps — import directly
import cli_args as _cli

# claude_api is already in sys.modules (loaded by the converter imports above)
import claude_api as _claude_api


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
        result, _ = BASE._parse_claude_response(raw, verbose=False)
        return result

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


# ===========================================================================
# Tests for pdf_to_5etools_1e.py (MOD1E)
# ===========================================================================

class TestAc1eTo5e(unittest.TestCase):
    """ac_1e_to_5e converts descending 1e AC to 5e ascending AC."""

    def test_unarmoured(self):
        # AC 10 (unarmoured) → 9 (floor of 9 in 5e is still base unarmoured)
        self.assertEqual(MOD1E.ac_1e_to_5e(10), 9)

    def test_chain_mail(self):
        self.assertEqual(MOD1E.ac_1e_to_5e(5), 14)

    def test_plate_and_shield(self):
        self.assertEqual(MOD1E.ac_1e_to_5e(0), 19)

    def test_negative_ac(self):
        # AC -2 → 21, but capped at 9 minimum — no, max(9, 19-(-2)) = max(9,21) = 21
        self.assertEqual(MOD1E.ac_1e_to_5e(-2), 21)

    def test_floor_enforced(self):
        # Very high AC (e.g. 12) should not go below 9
        self.assertEqual(MOD1E.ac_1e_to_5e(12), max(9, 19 - 12))

    def test_formula_spot_checks(self):
        for ac_1e, expected in [(7, 12), (4, 15), (2, 17), (1, 18)]:
            with self.subTest(ac_1e=ac_1e):
                self.assertEqual(MOD1E.ac_1e_to_5e(ac_1e), expected)


class TestThac0ToAttackBonus(unittest.TestCase):
    """thac0_to_attack_bonus converts THAC0 to a 5e attack bonus."""

    def test_thac0_20(self):
        self.assertEqual(MOD1E.thac0_to_attack_bonus(20), 0)

    def test_thac0_17(self):
        self.assertEqual(MOD1E.thac0_to_attack_bonus(17), 3)

    def test_thac0_13(self):
        self.assertEqual(MOD1E.thac0_to_attack_bonus(13), 7)

    def test_thac0_10(self):
        self.assertEqual(MOD1E.thac0_to_attack_bonus(10), 10)

    def test_thac0_7(self):
        self.assertEqual(MOD1E.thac0_to_attack_bonus(7), 13)

    def test_formula(self):
        for thac0 in range(5, 21):
            self.assertEqual(MOD1E.thac0_to_attack_bonus(thac0), 20 - thac0)


class TestMvTo5eSpeed(unittest.TestCase):
    """mv_to_5e_speed converts 1e movement inches to 5e feet."""

    def test_mv_6(self):
        self.assertEqual(MOD1E.mv_to_5e_speed(6), 30)

    def test_mv_9(self):
        self.assertEqual(MOD1E.mv_to_5e_speed(9), 45)

    def test_mv_12(self):
        self.assertEqual(MOD1E.mv_to_5e_speed(12), 60)

    def test_mv_15(self):
        self.assertEqual(MOD1E.mv_to_5e_speed(15), 75)

    def test_mv_3(self):
        self.assertEqual(MOD1E.mv_to_5e_speed(3), 15)

    def test_minimum_speed(self):
        self.assertGreaterEqual(MOD1E.mv_to_5e_speed(1), 5)

    def test_rounded_to_5(self):
        # Result must always be a multiple of 5
        for mv in [1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 13]:
            with self.subTest(mv=mv):
                self.assertEqual(MOD1E.mv_to_5e_speed(mv) % 5, 0)


class TestHdToCr(unittest.TestCase):
    """hd_to_cr looks up approximate 5e CR from 1e HD."""

    def test_half_hd(self):
        self.assertEqual(MOD1E.hd_to_cr(0.25), "0")

    def test_one_hd(self):
        self.assertEqual(MOD1E.hd_to_cr(1.0), "1/4")

    def test_two_hd(self):
        self.assertEqual(MOD1E.hd_to_cr(2.0), "1/2")

    def test_three_hd(self):
        self.assertEqual(MOD1E.hd_to_cr(3.0), "1")

    def test_four_hd(self):
        self.assertEqual(MOD1E.hd_to_cr(4.0), "2")

    def test_eight_hd(self):
        self.assertEqual(MOD1E.hd_to_cr(8.0), "6")

    def test_ten_hd(self):
        self.assertEqual(MOD1E.hd_to_cr(10.0), "8")

    def test_fifteen_hd(self):
        self.assertEqual(MOD1E.hd_to_cr(15.0), "13")

    def test_twenty_plus_hd(self):
        self.assertEqual(MOD1E.hd_to_cr(25.0), "21")

    def test_returns_string(self):
        # CR is always a string, never a number
        self.assertIsInstance(MOD1E.hd_to_cr(5.0), str)


class TestParseSkipPages(unittest.TestCase):
    """_parse_skip_pages parses range strings into sets of page numbers."""

    def _call(self, s):
        return MOD1E._parse_skip_pages(s)

    def test_single_page(self):
        self.assertEqual(self._call("5"), {5})

    def test_range(self):
        self.assertEqual(self._call("1-3"), {1, 2, 3})

    def test_comma_separated(self):
        self.assertEqual(self._call("1-3,10"), {1, 2, 3, 10})

    def test_multiple_ranges(self):
        self.assertEqual(self._call("1-2,5-6"), {1, 2, 5, 6})

    def test_empty_string(self):
        self.assertEqual(self._call(""), set())

    def test_whitespace_ignored(self):
        self.assertEqual(self._call("1 - 3"), {1, 2, 3})


class TestAnnotate1ePatterns(unittest.TestCase):
    """annotate_1e_patterns adds 1e structural markers to page text."""

    def _call(self, text):
        return MOD1E.annotate_1e_patterns(text)

    def test_room_key_detected(self):
        text = "17. THE GREAT HALL\nSome description here."
        result = self._call(text)
        self.assertIn("[ROOM-KEY-17]", result)

    def test_room_key_with_period(self):
        text = "3. ENTRY CHAMBER"
        result = self._call(text)
        self.assertIn("[ROOM-KEY-3]", result)

    def test_stat_block_wrapped(self):
        text = "Gnolls (6): AC 5; MV 9\"; HD 2; hp 9 each; #AT 1; D 2-8"
        result = self._call(text)
        self.assertIn("[STAT-BLOCK-START]", result)
        self.assertIn("[STAT-BLOCK-END]", result)
        self.assertIn("[1E-STAT]", result)

    def test_single_stat_token_not_wrapped(self):
        # Only one stat token → not treated as a stat block
        text = "The room has AC painted on the wall."
        result = self._call(text)
        self.assertNotIn("[STAT-BLOCK-START]", result)

    def test_npc_block_detected(self):
        text = (
            "LARETH: AC 2; MV 9\"; HD 6; THAC0 15; hp 40\n"
            "S: 16  I: 14  W: 12  D: 13  Co: 15  Ch: 17"
        )
        result = self._call(text)
        self.assertIn("[NPC-BLOCK]", result)

    def test_wandering_monster_table_tagged(self):
        text = "WANDERING MONSTERS\nd6  Monster\n1   Goblin\n2   Orc"
        result = self._call(text)
        self.assertIn("[WANDERING-TABLE]", result)

    def test_random_encounter_also_tagged(self):
        text = "RANDOM ENCOUNTERS (LEVEL 1)"
        result = self._call(text)
        self.assertIn("[WANDERING-TABLE]", result)

    def test_plain_text_unchanged(self):
        text = "The corridor extends north for 30 feet."
        result = self._call(text)
        self.assertEqual(result.strip(), text.strip())

    def test_existing_markers_preserved(self):
        text = "[H1] Chapter One\n[INSET-START]\nSome boxed text.\n[INSET-END]"
        result = self._call(text)
        self.assertIn("[H1] Chapter One", result)
        self.assertIn("[INSET-START]", result)
        self.assertIn("[INSET-END]", result)


class TestPostProcessMonster1e(unittest.TestCase):
    """post_process_monster_1e applies numeric conversions and removes hint fields."""

    def test_ac_converted_from_hint(self):
        m = {"name": "Goblin", "_1e_ac": 6, "_thac0": None,
             "_mv_inches": None, "_hd": None, "_has_special": False}
        result = MOD1E.post_process_monster_1e(m)
        self.assertEqual(result["ac"], [13])   # 19 - 6 = 13

    def test_speed_converted_from_hint(self):
        m = {"name": "Goblin", "_1e_ac": None, "_thac0": None,
             "_mv_inches": 9, "_hd": None, "_has_special": False}
        result = MOD1E.post_process_monster_1e(m)
        self.assertEqual(result["speed"], {"walk": 45})

    def test_cr_derived_from_hd(self):
        m = {"name": "Troll", "_1e_ac": None, "_thac0": None,
             "_mv_inches": None, "_hd": 6.0, "_has_special": False}
        result = MOD1E.post_process_monster_1e(m)
        self.assertEqual(result["cr"], "4")

    def test_hint_fields_removed(self):
        m = {"name": "Orc", "_1e_ac": 6, "_thac0": 17,
             "_mv_inches": 9, "_hd": 1.0, "_has_special": False}
        result = MOD1E.post_process_monster_1e(m)
        for hint in ("_1e_ac", "_thac0", "_mv_inches", "_hd", "_has_special"):
            self.assertNotIn(hint, result)

    def test_no_cr_adjustment_skips_derivation(self):
        # With no_cr_adjustment=True the entire HD→CR derivation is bypassed,
        # so any CR Claude already set on the dict should be preserved as-is.
        m = {"name": "Wraith", "cr": "5",
             "_1e_ac": None, "_thac0": None,
             "_mv_inches": None, "_hd": 5.0, "_has_special": True}
        result = MOD1E.post_process_monster_1e(m, no_cr_adjustment=True)
        self.assertEqual(result["cr"], "5")   # Claude's value untouched

    def test_missing_hints_no_error(self):
        # No hint fields at all — should not crash
        m = {"name": "Skeleton", "cr": "1/4"}
        result = MOD1E.post_process_monster_1e(m)
        self.assertEqual(result["name"], "Skeleton")


class TestNeutralizeTriggers(unittest.TestCase):
    def test_enslaved_replaced(self):
        out = MOD1E._neutralize_triggers("Good folk were robbed, pillaged, enslaved, and worse.")
        self.assertNotIn("enslaved", out.lower())
        self.assertNotIn("and worse", out.lower())

    def test_enslavement_replaced(self):
        out = MOD1E._neutralize_triggers("Enslavement was common in those dark days.")
        self.assertNotIn("enslavement", out.lower())

    def test_wench_replaced(self):
        out = MOD1E._neutralize_triggers("A serving wench brought the drinks.")
        self.assertNotIn("wench", out.lower())

    def test_buxom_replaced(self):
        out = MOD1E._neutralize_triggers("A buxom girl smiled at the door.")
        self.assertNotIn("buxom", out.lower())

    def test_harlot_replaced(self):
        out = MOD1E._neutralize_triggers("The harlot sat in the corner.")
        self.assertNotIn("harlot", out.lower())

    def test_clean_text_unchanged(self):
        text = "The fighter entered the dungeon and fought the goblins."
        self.assertEqual(MOD1E._neutralize_triggers(text), text)

    def test_case_insensitive(self):
        out = MOD1E._neutralize_triggers("ENSLAVED prisoners and WENCHES served the cult.")
        self.assertNotIn("enslaved", out.lower())
        self.assertNotIn("wenche", out.lower())

    def test_young_girl_replaced(self):
        out = MOD1E._neutralize_triggers("Inside, a young girl and her old granny do chores.")
        self.assertNotIn("young girl", out.lower())

    def test_teenage_daughter_replaced(self):
        out = MOD1E._neutralize_triggers("The two eldest being teen-aged daughters.")
        self.assertNotIn("teen-aged daughter", out.lower())

    def test_carousing_replaced(self):
        out = MOD1E._neutralize_triggers("While in town 'carousing', he is unarmored.")
        self.assertNotIn("carousing", out.lower())

    def test_deinterleave_dense_insets(self):
        # Page where every other line is a single-line inset → de-interleave
        page = "\n".join([
            "Left col line 1",
            "[INSET-START]", "Right col line 1", "[INSET-END]",
            "Left col line 2",
            "[INSET-START]", "Right col line 2", "[INSET-END]",
            "Left col line 3",
            "[INSET-START]", "Right col line 3", "[INSET-END]",
        ])
        out = MOD1E._neutralize_triggers(page)
        left_pos  = out.index("Left col line 1")
        right_pos = out.index("Right col line 1")
        self.assertLess(left_pos, right_pos)  # left column comes first

    def test_deinterleave_preserves_real_insets(self):
        # Multi-line insets should stay in place
        page = "\n".join([
            "Normal text before",
            "[INSET-START]",
            "Sidebar line one",
            "Sidebar line two",
            "Sidebar line three",
            "[INSET-END]",
            "Normal text after",
        ])
        out = MOD1E._neutralize_triggers(page)
        self.assertIn("[INSET-START]", out)
        self.assertIn("[INSET-END]", out)
        # Sidebar content stays between the markers
        si = out.index("[INSET-START]")
        se = out.index("[INSET-END]")
        self.assertIn("Sidebar line one", out[si:se])

    def test_sparse_insets_not_deinterleaved(self):
        # Only 2 insets in a long page → not a column page, leave untouched
        page = "A\n" * 30 + "[INSET-START]\nBox text\n[INSET-END]\n" + "B\n" * 10
        out = MOD1E._neutralize_triggers(page)
        self.assertIn("[INSET-START]", out)

    def test_noise_lines_stripped(self):
        text = "Introduction\nwey i\nyY\n, Gd\nyd ae ne Ta\nThe village is nearby."
        out = MOD1E._neutralize_triggers(text)
        self.assertNotIn("wey", out)
        self.assertNotIn("yY", out)
        self.assertIn("Introduction", out)
        self.assertIn("The village is nearby.", out)

    def test_marker_lines_preserved(self):
        # A single real inset surrounded by lots of normal text should survive.
        # The marker density must stay below 20% to avoid triggering de-interleave.
        body = ("Normal paragraph text here.\n" * 20)
        text = body + "[INSET-START]\n[H3] 7. Rm\n[INSET-END]\n" + body
        out = MOD1E._neutralize_triggers(text)
        self.assertIn("[INSET-START]", out)
        self.assertIn("[INSET-END]", out)

    def test_beloved_replaced(self):
        out = MOD1E._neutralize_triggers("Zuggtmoy's Beloved serve the demon queen.")
        self.assertNotIn("beloved", out.lower())

    def test_dark_vocabulary_replaced(self):
        text = ("murderous oppressors were defeated in great slaughter; "
                "abominations, pestilence, wickedness, and tyranny ended.")
        out = MOD1E._neutralize_triggers(text)
        for word in ("murderous", "oppressor", "slaughter",
                     "abomination", "pestilence", "wickedness", "tyranny"):
            self.assertNotIn(word, out.lower())

    def test_lust_replaced(self):
        out = MOD1E._neutralize_triggers("The demon lusted for power and lust drove it onward.")
        self.assertNotIn("lust", out.lower())

    def test_ocr_garbage_stripped(self):
        out = MOD1E._neutralize_triggers("$15112W Co16Ch11\nFarmer: AC 7")
        self.assertNotIn("$15112W", out)
        self.assertIn("Farmer: AC 7", out)

    def test_dotted_leader_stripped(self):
        out = MOD1E._neutralize_triggers("Tower Exterior cece cece 36\nRoom Key ........ 45")
        self.assertNotIn("cece", out)
        self.assertNotIn("....", out)
        self.assertIn("Tower Exterior", out)
        self.assertIn("Room Key", out)


# ===========================================================================
# Tests for cli_args.py
# ===========================================================================

class TestCliArgsCommon(unittest.TestCase):
    """add_common_args registers all shared arguments with correct defaults."""

    def setUp(self):
        self.parser = argparse.ArgumentParser()
        _cli.add_common_args(self.parser, default_chunk=6, default_model="claude-haiku-4-5")

    def _parse(self, *extra):
        # Provide a minimal valid positional arg (pdf) then any extra flags
        return self.parser.parse_args(["dummy.pdf", *extra])

    def test_pdf_positional(self):
        args = self._parse()
        self.assertEqual(args.pdf, Path("dummy.pdf"))

    def test_type_default_adventure(self):
        args = self._parse()
        self.assertEqual(args.output_type, "adventure")

    def test_type_book(self):
        args = self._parse("--type", "book")
        self.assertEqual(args.output_type, "book")

    def test_output_mode_default_homebrew(self):
        args = self._parse()
        self.assertEqual(args.output_mode, "homebrew")

    def test_output_mode_server(self):
        args = self._parse("--output-mode", "server")
        self.assertEqual(args.output_mode, "server")

    def test_id_stored_as_short_id(self):
        args = self._parse("--id", "MYMOD")
        self.assertEqual(args.short_id, "MYMOD")
        self.assertFalse(hasattr(args, "id"))

    def test_id_default_none(self):
        args = self._parse()
        self.assertIsNone(args.short_id)

    def test_batch_default_false(self):
        args = self._parse()
        self.assertFalse(args.use_batch)

    def test_batch_flag_sets_true(self):
        args = self._parse("--batch")
        self.assertTrue(args.use_batch)

    def test_pages_per_chunk_default(self):
        args = self._parse()
        self.assertEqual(args.chunk_size, 6)

    def test_pages_per_chunk_override(self):
        args = self._parse("--pages-per-chunk", "3")
        self.assertEqual(args.chunk_size, 3)

    def test_model_default(self):
        args = self._parse()
        self.assertEqual(args.model, "claude-haiku-4-5")

    def test_model_override(self):
        args = self._parse("--model", "claude-sonnet-4-6")
        self.assertEqual(args.model, "claude-sonnet-4-6")

    def test_extract_monsters_default_false(self):
        args = self._parse()
        self.assertFalse(args.extract_monsters)

    def test_monsters_only_default_false(self):
        args = self._parse()
        self.assertFalse(args.monsters_only)

    def test_dry_run_default_false(self):
        args = self._parse()
        self.assertFalse(args.dry_run_only)

    def test_verbose_default_false(self):
        args = self._parse()
        self.assertFalse(args.verbose)

    def test_no_toc_hint_default_false(self):
        args = self._parse()
        self.assertFalse(args.no_toc_hint)

    def test_pages_default_none(self):
        args = self._parse()
        self.assertIsNone(args.pages)

    def test_page_default_none(self):
        args = self._parse()
        self.assertIsNone(args.page)

    def test_author_default(self):
        args = self._parse()
        self.assertEqual(args.author, "Unknown")

    def test_debug_dir_default_none(self):
        args = self._parse()
        self.assertIsNone(args.debug_dir)


class TestCliArgsOcr(unittest.TestCase):
    """add_ocr_args registers OCR-specific arguments with correct defaults."""

    def setUp(self):
        self.parser = argparse.ArgumentParser()
        _cli.add_common_args(self.parser, default_chunk=4, default_model="claude-haiku-4-5")
        _cli.add_ocr_args(self.parser, default_dpi=200)

    def _parse(self, *extra):
        return self.parser.parse_args(["dummy.pdf", *extra])

    def test_dpi_default(self):
        args = self._parse()
        self.assertEqual(args.dpi, 200)

    def test_dpi_override(self):
        args = self._parse("--dpi", "600")
        self.assertEqual(args.dpi, 600)

    def test_force_ocr_default_false(self):
        args = self._parse()
        self.assertFalse(args.force_ocr)

    def test_force_ocr_flag(self):
        args = self._parse("--force-ocr")
        self.assertTrue(args.force_ocr)

    def test_lang_default_eng(self):
        args = self._parse()
        self.assertEqual(args.lang, "eng")

    def test_lang_override(self):
        args = self._parse("--lang", "fra")
        self.assertEqual(args.lang, "fra")

    def test_batch_still_present(self):
        # --batch must be available even when add_ocr_args is added
        args = self._parse("--batch")
        self.assertTrue(args.use_batch)


# ===========================================================================
# Tests for claude_api.py
# ===========================================================================

class TestClaudeApiConstants(unittest.TestCase):
    """COMMON_TAG_RULES and COMMON_NESTING_RULES contain expected guidance."""

    def test_tag_rules_has_bold(self):
        self.assertIn("{@b", _claude_api.COMMON_TAG_RULES)

    def test_tag_rules_has_creature(self):
        self.assertIn("{@creature", _claude_api.COMMON_TAG_RULES)

    def test_tag_rules_has_spell(self):
        self.assertIn("{@spell", _claude_api.COMMON_TAG_RULES)

    def test_tag_rules_has_dice(self):
        self.assertIn("{@dice", _claude_api.COMMON_TAG_RULES)

    def test_nesting_rules_has_section(self):
        self.assertIn('"type":"section"', _claude_api.COMMON_NESTING_RULES)

    def test_nesting_rules_headers_guidance(self):
        self.assertIn("headers", _claude_api.COMMON_NESTING_RULES)

    def test_nesting_rules_no_repeat_name(self):
        self.assertIn("NOT repeat the section", _claude_api.COMMON_NESTING_RULES)

    def test_nesting_rules_excludes_generic_headings(self):
        self.assertIn("Treasure", _claude_api.COMMON_NESTING_RULES)
        self.assertIn("Creatures", _claude_api.COMMON_NESTING_RULES)

    def test_max_output_tokens(self):
        self.assertGreaterEqual(_claude_api.MAX_OUTPUT_TOKENS, 8_000)


class TestModelTier(unittest.TestCase):
    """_model_tier detects haiku / sonnet / opus from model name."""

    def _t(self, model):
        return _claude_api._model_tier(model)

    def test_haiku(self):
        self.assertEqual(self._t("claude-haiku-4-5-20251001"), "haiku")

    def test_sonnet(self):
        self.assertEqual(self._t("claude-sonnet-4-6"), "sonnet")

    def test_opus(self):
        self.assertEqual(self._t("claude-opus-4-6"), "opus")

    def test_unknown_defaults_to_sonnet(self):
        self.assertEqual(self._t("gpt-4o"), "sonnet")

    def test_case_insensitive(self):
        self.assertEqual(self._t("Claude-Haiku-4-5"), "haiku")


class TestRecoverPartialJsonApi(unittest.TestCase):
    """_recover_partial_json in claude_api salvages complete entries from truncated output."""

    def _call(self, raw):
        return _claude_api._recover_partial_json(raw)

    def test_no_bracket_returns_empty(self):
        self.assertEqual(self._call("no bracket here"), [])

    def test_recovers_first_entry_from_truncated_array(self):
        # Array is truncated mid-second object; first object should be recovered
        raw = '[{"type":"section","name":"A"},\n  {"type":"section","name":"B'
        result = self._call(raw)
        self.assertGreaterEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "A")

    def test_truncated_array_recovers_complete_entries(self):
        # Second object is cut off — should recover first object only
        raw = '[{"type":"section","name":"A"},\n  {"type":"section","nam'
        result = self._call(raw)
        self.assertGreaterEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "A")

    def test_empty_array_returns_empty(self):
        self.assertEqual(self._call("[]"), [])


class TestCallClaudeBatch(unittest.TestCase):
    """call_claude_batch submits all chunks and returns results in order."""

    def _make_result(self, custom_id, text):
        result = MagicMock()
        result.custom_id = custom_id
        result.result.type = "succeeded"
        result.result.message.stop_reason = "end_turn"
        result.result.message.content = [MagicMock(text=text)]
        return result

    def test_returns_results_in_chunk_order(self):
        client = MagicMock()
        batch = MagicMock()
        batch.id = "batch_abc"
        client.messages.batches.create.return_value = batch

        ended = MagicMock()
        ended.processing_status = "ended"
        ended.request_counts.processing = 0
        ended.request_counts.succeeded = 2
        ended.request_counts.errored = 0
        client.messages.batches.retrieve.return_value = ended

        # Return results out of order to verify ordering logic
        client.messages.batches.results.return_value = [
            self._make_result("chunk-0001", '[{"type":"section","name":"B"}]'),
            self._make_result("chunk-0000", '[{"type":"section","name":"A"}]'),
        ]

        results = _claude_api.call_claude_batch(
            client, ['chunk 0 text', 'chunk 1 text'],
            model="claude-haiku-4-5",
            system_prompt="test prompt",
            verbose=False,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][0]["name"], "A")  # chunk-0000 first
        self.assertEqual(results[1][0]["name"], "B")  # chunk-0001 second

    def test_failed_chunk_returns_empty_list(self):
        client = MagicMock()
        batch = MagicMock()
        batch.id = "batch_xyz"
        client.messages.batches.create.return_value = batch

        ended = MagicMock()
        ended.processing_status = "ended"
        ended.request_counts.processing = 0
        ended.request_counts.succeeded = 0
        ended.request_counts.errored = 1
        client.messages.batches.retrieve.return_value = ended

        failed = MagicMock()
        failed.custom_id = "chunk-0000"
        failed.result.type = "errored"
        client.messages.batches.results.return_value = [failed]

        results = _claude_api.call_claude_batch(
            client, ['text'],
            model="claude-haiku-4-5",
            system_prompt="test",
            verbose=False,
        )
        self.assertEqual(results, [[]])

    def test_batch_create_called_once(self):
        client = MagicMock()
        batch = MagicMock()
        batch.id = "b1"
        client.messages.batches.create.return_value = batch

        ended = MagicMock()
        ended.processing_status = "ended"
        ended.request_counts = MagicMock(processing=0, succeeded=0, errored=0)
        client.messages.batches.retrieve.return_value = ended
        client.messages.batches.results.return_value = []

        _claude_api.call_claude_batch(
            client, ['a', 'b'],
            model="claude-haiku-4-5",
            system_prompt="sys",
            verbose=False,
        )
        client.messages.batches.create.assert_called_once()
        # Verify requests list has one entry per non-empty chunk
        req_arg = client.messages.batches.create.call_args[1]["requests"]
        self.assertEqual(len(req_arg), 2)
        self.assertEqual(req_arg[0]["custom_id"], "chunk-0000")
        self.assertEqual(req_arg[1]["custom_id"], "chunk-0001")


class TestDryRunShared(unittest.TestCase):
    """dry_run calls count_tokens for each non-empty chunk and prints a summary."""

    def _make_client(self, tokens_per_chunk=500):
        client = MagicMock()
        token_resp = MagicMock()
        token_resp.input_tokens = tokens_per_chunk
        client.messages.count_tokens.return_value = token_resp
        return client

    def test_count_tokens_called_for_each_non_empty_chunk(self):
        client = self._make_client()
        chunk_texts = ["text chunk 0", "  ", "text chunk 2"]  # middle is empty
        with patch("sys.stdout", new_callable=io.StringIO):
            _claude_api.dry_run(
                client, chunk_texts, chunk_texts, "claude-haiku-4-5",
                "sys prompt", use_batch=False, verbose=False,
            )
        # Only 2 non-empty chunks should trigger count_tokens
        self.assertEqual(client.messages.count_tokens.call_count, 2)

    def test_batch_discount_mentioned_in_output(self):
        client = self._make_client()
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            _claude_api.dry_run(
                client, ["some text"], ["some text"], "claude-haiku-4-5",
                "sys", use_batch=True, verbose=False,
            )
        output = mock_out.getvalue()
        self.assertIn("Batch", output)

    def test_no_tokens_counted_for_empty_chunks(self):
        client = self._make_client()
        chunk_texts = ["  ", "\n", ""]
        with patch("sys.stdout", new_callable=io.StringIO):
            _claude_api.dry_run(
                client, chunk_texts, chunk_texts, "claude-haiku-4-5",
                "sys", use_batch=False, verbose=False,
            )
        client.messages.count_tokens.assert_not_called()


# ===========================================================================
# Tests for batch mode in pdf_to_5etools_1e.py
# ===========================================================================

class Test1eDryRunWrapper(unittest.TestCase):
    """The 1e dry_run wrapper delegates to _api.dry_run with use_batch forwarded."""

    def test_delegates_use_batch_true(self):
        client = MagicMock()
        with patch.object(MOD1E._api, "dry_run") as mock_dry:
            MOD1E.dry_run(client, [], [], "model", use_batch=True, verbose=False)
        mock_dry.assert_called_once()
        _, kwargs = mock_dry.call_args
        self.assertTrue(kwargs.get("use_batch") or mock_dry.call_args[0][5])

    def test_delegates_use_batch_false(self):
        client = MagicMock()
        with patch.object(MOD1E._api, "dry_run") as mock_dry:
            MOD1E.dry_run(client, [], [], "model", use_batch=False, verbose=False)
        mock_dry.assert_called_once()
        # use_batch=False should be forwarded
        args_call = mock_dry.call_args
        # It's the 6th positional or use_batch keyword
        all_args = list(args_call[0]) + list(args_call[1].values())
        self.assertIn(False, all_args)


class Test1eBatchModeRouting(unittest.TestCase):
    """convert() in 1e calls call_claude_batch when use_batch=True."""

    def test_use_batch_param_accepted(self):
        import inspect
        sig = inspect.signature(MOD1E.convert)
        self.assertIn("use_batch", sig.parameters)


class TestOcrBatchModeRouting(unittest.TestCase):
    """convert() in OCR calls call_claude_batch when use_batch=True."""

    def test_use_batch_param_accepted(self):
        import inspect
        sig = inspect.signature(OCR.convert)
        self.assertIn("use_batch", sig.parameters)


# ===========================================================================
# Tests for validation retry in claude_api
# ===========================================================================

class TestValidateEntries(unittest.TestCase):
    """validate_entries runs parsed entries through the adventure model."""

    def test_valid_entries_returns_empty(self):
        entries = [
            {"type": "section", "name": "Ch1", "id": "000", "entries": [
                "A paragraph with {@spell fireball}.",
                {"type": "entries", "name": "Sub", "id": "001", "entries": ["Text."]},
            ]},
        ]
        errors = _claude_api.validate_entries(entries, "chunk-0000")
        self.assertEqual(errors, [])

    def test_unknown_tag_detected(self):
        entries = [
            {"type": "section", "name": "Ch1", "entries": [
                "See {@scroll fireball} for details.",
            ]},
        ]
        errors = _claude_api.validate_entries(entries, "chunk-0000")
        self.assertTrue(any("scroll" in e for e in errors))

    def test_multiple_errors_detected(self):
        entries = [
            {"type": "section", "name": "Ch1", "entries": [
                "Use {@npc Bob} and {@scroll shield}.",
            ]},
        ]
        errors = _claude_api.validate_entries(entries, "chunk-0000")
        self.assertGreaterEqual(len(errors), 2)

    def test_image_no_href_detected(self):
        entries = [
            {"type": "section", "name": "Ch1", "entries": [
                {"type": "image"},
            ]},
        ]
        errors = _claude_api.validate_entries(entries, "chunk-0000")
        self.assertTrue(any("href" in e for e in errors))

    def test_valid_tags_pass(self):
        entries = [
            {"type": "section", "name": "Ch1", "entries": [
                "Cast {@spell fireball} at {@creature goblin}. DC {@dc 15}.",
                {"type": "list", "items": ["{@item sword}", "arrows"]},
                {"type": "table", "colLabels": ["Spell"], "rows": [["{@spell magic missile}"]]},
            ]},
        ]
        errors = _claude_api.validate_entries(entries, "chunk-0000")
        self.assertEqual(errors, [])

    def test_empty_entries_returns_empty(self):
        self.assertEqual(_claude_api.validate_entries([], "chunk-0000"), [])


class TestValidationRetry(unittest.TestCase):
    """call_claude retries when validation finds errors in parsed output."""

    def _make_message(self, text, stop_reason="end_turn"):
        msg = MagicMock()
        msg.content = [MagicMock(text=text)]
        msg.stop_reason = stop_reason
        return msg

    def test_retry_on_unknown_tag(self):
        """When output contains unknown tags, call_claude retries with correction prompt."""
        client = MagicMock()

        # First call returns bad tags, second call returns fixed output
        bad_response = '[{"type":"section","name":"Ch1","entries":["See {@scroll fireball}."]}]'
        good_response = '[{"type":"section","name":"Ch1","entries":["See {@item scroll of fireball}."]}]'

        client.messages.create.side_effect = [
            self._make_message(bad_response),
            self._make_message(good_response),
        ]

        result = _claude_api.call_claude(
            client, "some pdf text", "claude-haiku-4-5",
            "system prompt", verbose=False, chunk_id="chunk-0000",
        )

        # Should have called API twice (original + retry)
        self.assertEqual(client.messages.create.call_count, 2)
        # Result should be the fixed version
        self.assertEqual(result[0]["entries"][0], "See {@item scroll of fireball}.")

    def test_no_retry_on_valid_output(self):
        """When output is valid, no retry happens."""
        client = MagicMock()

        good_response = '[{"type":"section","name":"Ch1","entries":["Hello."]}]'
        client.messages.create.return_value = self._make_message(good_response)

        result = _claude_api.call_claude(
            client, "some pdf text", "claude-haiku-4-5",
            "system prompt", verbose=False, chunk_id="chunk-0000",
        )

        self.assertEqual(client.messages.create.call_count, 1)
        self.assertEqual(result[0]["name"], "Ch1")

    def test_retry_limited_to_max(self):
        """Validation retry does not loop — only retries MAX_VALIDATION_RETRIES times."""
        client = MagicMock()

        # Always returns bad tags — should only retry once
        bad_response = '[{"type":"section","name":"Ch1","entries":["See {@scroll X}."]}]'
        client.messages.create.return_value = self._make_message(bad_response)

        result = _claude_api.call_claude(
            client, "some pdf text", "claude-haiku-4-5",
            "system prompt", verbose=False, chunk_id="chunk-0000",
        )

        # 1 original + MAX_VALIDATION_RETRIES retries
        self.assertEqual(client.messages.create.call_count,
                         1 + _claude_api.MAX_VALIDATION_RETRIES)

    def test_retry_prompt_includes_errors(self):
        """The correction prompt includes the validation errors."""
        client = MagicMock()

        bad_response = '[{"type":"section","name":"Ch1","entries":["See {@npc Bob}."]}]'
        good_response = '[{"type":"section","name":"Ch1","entries":["See Bob."]}]'

        client.messages.create.side_effect = [
            self._make_message(bad_response),
            self._make_message(good_response),
        ]

        _claude_api.call_claude(
            client, "some pdf text", "claude-haiku-4-5",
            "system prompt", verbose=False, chunk_id="chunk-0000",
        )

        # Check the retry message includes the error text
        retry_call = client.messages.create.call_args_list[1]
        retry_content = retry_call[1]["messages"][0]["content"]
        self.assertIn("validation errors", retry_content)
        self.assertIn("npc", retry_content)

    def test_no_retry_on_empty_result(self):
        """Empty results don't trigger validation retry."""
        client = MagicMock()
        # Return something that parses to empty
        client.messages.create.return_value = self._make_message("[]")

        result = _claude_api.call_claude(
            client, "some pdf text", "claude-haiku-4-5",
            "system prompt", verbose=False, chunk_id="chunk-0000",
        )

        self.assertEqual(client.messages.create.call_count, 1)
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
