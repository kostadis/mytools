"""
pdf_utils.py — Shared PDF utility helpers for all pdf-to-5etools converters.

Kept separate from claude_api.py because these functions depend on PyMuPDF
(fitz), which is not required by the API layer.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("PyMuPDF is required.  Install with:  pip install pymupdf")


# ---------------------------------------------------------------------------
# PDF string decoding
# ---------------------------------------------------------------------------

# Characters in the 0x80–0x9F range that PDFs sometimes embed using
# Windows-1252 or Mac-Roman encodings rather than proper Unicode.
_PDF_CHAR_MAP: dict[str, str] = {
    '\x80': '€',    '\x82': '‚',    '\x83': 'ƒ',    '\x84': '„',
    '\x85': '…',    '\x86': '†',    '\x87': '‡',    '\x89': '‰',
    '\x8b': '‹',    '\x8c': 'Œ',    '\x95': '•',    '\x96': '–',
    '\x97': '—',    '\x99': '™',    '\x9b': '›',    '\x9c': 'œ',
    # Variants observed in DDEX modules:
    '\x8d': '\u2018',   # left single quotation mark
    '\x8e': '\u2019',   # right single quotation mark
    '\x90': '\u2019',   # right single quotation mark / apostrophe
    '\x91': '\u2018',   '\x92': '\u2019',
    '\x93': '\u201c',   '\x94': '\u201d',
}


def _decode_pdf_string(text: str) -> str:
    """Replace raw Windows-1252 bytes in a PDF string with proper Unicode."""
    for bad, good in _PDF_CHAR_MAP.items():
        text = text.replace(bad, good)
    return text.strip()


# ---------------------------------------------------------------------------
# PDF bookmark / TOC extraction
# ---------------------------------------------------------------------------

def extract_pdf_toc(pdf_path: Path | str, max_level: int = 3) -> str | None:
    """Extract the PDF bookmark outline and return a formatted text hint.

    Returns ``None`` when the PDF has no bookmarks.  The hint is prepended to
    each Claude chunk so Claude knows the authoritative section names and page
    numbers before it reads the text content.

    Only levels ≤ *max_level* are included (level 1 is almost always the
    document title; level 2 are top-level sections; level 3 are subsections).
    Level 4+ items (Treasure, XP Award, Development…) are omitted to keep the
    hint compact.
    """
    doc = fitz.open(str(pdf_path))
    try:
        raw: list[list] = doc.get_toc(simple=True)  # [[level, title, page], …]
    finally:
        doc.close()

    if not raw:
        return None

    # Skip entries deeper than max_level
    entries = [(lvl, _decode_pdf_string(title), page)
               for lvl, title, page in raw
               if lvl <= max_level]

    if not entries:
        return None

    # Normalise so the shallowest level present becomes level 1
    min_lvl = min(lvl for lvl, _, _ in entries)

    lines = [
        "=== PDF TABLE OF CONTENTS ===",
        "Use these exact names for section headings in the JSON output.",
        "",
    ]
    for lvl, title, page in entries:
        indent = "  " * (lvl - min_lvl)
        lines.append(f"{indent}p{page}: {title}")
    lines.append("")
    lines.append("=== END OF TABLE OF CONTENTS ===")

    return "\n".join(lines)
