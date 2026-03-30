"""
pdf_utils.py — Shared PDF utility helpers for all pdf-to-5etools converters.

Kept separate from claude_api.py because these functions depend on PyMuPDF
(fitz), which is not required by the API layer.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
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


# ---------------------------------------------------------------------------
# Structured TOC tree with page ranges
# ---------------------------------------------------------------------------

@dataclass
class TocNode:
    """A node in the PDF bookmark tree with computed page ranges."""
    level: int           # 1-based depth from get_toc()
    title: str           # decoded bookmark title
    start_page: int      # 1-based, inclusive
    end_page: int = 0    # 1-based, inclusive (computed by parse_toc_tree)
    children: list[TocNode] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return max(0, self.end_page - self.start_page + 1)

    def walk(self) -> list[TocNode]:
        """Return this node and all descendants in pre-order."""
        result = [self]
        for child in self.children:
            result.extend(child.walk())
        return result

    def __repr__(self) -> str:
        return (f"TocNode(level={self.level}, title={self.title!r}, "
                f"pages={self.start_page}-{self.end_page}, "
                f"children={len(self.children)})")


def parse_toc_tree(raw_toc: list[list], total_pages: int,
                   max_level: int = 99) -> list[TocNode]:
    """Parse PyMuPDF get_toc() output into a tree of TocNode objects.

    Parameters
    ----------
    raw_toc : list of [level, title, page] triples from ``doc.get_toc(simple=True)``
    total_pages : total number of pages in the PDF
    max_level : ignore bookmarks deeper than this level

    Returns a list of top-level TocNode objects (the roots of the tree).
    Each node has computed ``end_page`` values and nested ``children``.
    """
    if not raw_toc:
        return []

    # Build flat list of nodes, filtering by max_level
    flat: list[TocNode] = []
    for lvl, title, page in raw_toc:
        if lvl > max_level:
            continue
        flat.append(TocNode(
            level=lvl,
            title=_decode_pdf_string(title),
            start_page=max(1, page),  # some PDFs have page=0
        ))

    if not flat:
        return []

    # Normalise levels so the shallowest becomes 1
    min_lvl = min(n.level for n in flat)
    if min_lvl > 1:
        for n in flat:
            n.level -= (min_lvl - 1)

    # Compute end_page: each node runs until the next node at same or
    # shallower level starts (or end of document)
    for i, node in enumerate(flat):
        # Look ahead for the next node at same or shallower level
        node.end_page = total_pages  # default: runs to end
        for j in range(i + 1, len(flat)):
            if flat[j].level <= node.level:
                node.end_page = max(node.start_page, flat[j].start_page - 1)
                break

    # Build tree: stack-based, attaching each node as child of nearest
    # ancestor at a shallower level
    roots: list[TocNode] = []
    stack: list[TocNode] = []

    for node in flat:
        # Pop until we find a parent at a shallower level
        while stack and stack[-1].level >= node.level:
            stack.pop()

        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)

        stack.append(node)

    return roots


def get_toc_tree(pdf_path: Path | str, max_level: int = 99) -> list[TocNode]:
    """Extract PDF bookmarks as a structured tree with page ranges.

    Convenience wrapper combining ``doc.get_toc()`` + ``parse_toc_tree()``.
    Returns an empty list if the PDF has no bookmarks.
    """
    doc = fitz.open(str(pdf_path))
    try:
        raw = doc.get_toc(simple=True)
        total = doc.page_count
    finally:
        doc.close()

    return parse_toc_tree(raw, total, max_level=max_level)
