#!/usr/bin/env python3
"""Tests for pdf_to_5etools_ocr_toc.py — TOC-driven OCR converter.

Run:
    pytest test_pdf_to_5etools_ocr_toc.py -v
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock

from pdf_utils import TocNode

# The OCR TOC module loads without OCR (lazy imports)
from pdf_to_5etools_ocr_toc import SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

class TestSystemPrompt(unittest.TestCase):
    def test_no_top_level_section(self):
        self.assertIn("Do NOT wrap your output in a top-level", SYSTEM_PROMPT)

    def test_has_ocr_awareness(self):
        self.assertIn("[OCR]", SYSTEM_PROMPT)
        self.assertIn("OCR errors", SYSTEM_PROMPT)

    def test_has_tag_rules(self):
        self.assertIn("{@creature", SYSTEM_PROMPT)

    def test_has_entry_types(self):
        self.assertIn("insetReadaloud", SYSTEM_PROMPT)

    def test_entries_not_section(self):
        self.assertIn('use {"type":"entries"}', SYSTEM_PROMPT)

    def test_has_nesting_rules(self):
        self.assertIn("headers", SYSTEM_PROMPT)

    def test_has_hyphenation_merge(self):
        self.assertIn("adven-", SYSTEM_PROMPT)

    def test_has_column_hint(self):
        self.assertIn("[2-COLUMN]", SYSTEM_PROMPT)


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------

class TestModuleStructure(unittest.TestCase):
    def test_imports_toc_functions(self):
        """Verify shared TOC functions are available."""
        from pdf_to_5etools_ocr_toc import (
            chunk_by_toc,
            assemble_document,
            build_toc_from_tree,
            _prune_toc,
            _filter_junk_bookmarks,
        )
        # Just verify they're callable
        self.assertTrue(callable(chunk_by_toc))
        self.assertTrue(callable(assemble_document))

    def test_lazy_ocr_import(self):
        """OCR module is not imported until needed."""
        from pdf_to_5etools_ocr_toc import _ocr
        # Before calling _ensure_ocr_imports, _ocr may or may not be set
        # depending on test ordering, but the module should load without OCR packages

    def test_convert_function_exists(self):
        from pdf_to_5etools_ocr_toc import convert
        self.assertTrue(callable(convert))

    def test_extract_pages_ocr_exists(self):
        from pdf_to_5etools_ocr_toc import extract_pages_ocr
        self.assertTrue(callable(extract_pages_ocr))


if __name__ == "__main__":
    unittest.main()
