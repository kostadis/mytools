"""
pdf_utils.py — Shared PDF utility helpers for all pdf-to-5etools converters.

Kept separate from claude_api.py because these functions depend on PyMuPDF
(fitz), which is not required by the API layer.
"""

from __future__ import annotations

import re
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


def is_anchor_bookmark(title: str) -> bool:
    """Return True for Microsoft Word / Adobe internal anchor bookmarks.

    Word emits entries like ``_GoBack``, ``_GoBack1``, ``_Toc123456789``,
    ``_Ref123456789``, ``_Hlk123456789`` when it saves a docx as PDF.
    These are hyperlink targets, not real sections — convention is that
    any bookmark whose decoded title starts with ``_`` is a tool-generated
    anchor.
    """
    return title.lstrip().startswith("_")


def parse_toc_tree(raw_toc: list[list], total_pages: int,
                   max_level: int = 99,
                   *,
                   skip_anchor_bookmarks: bool = True) -> list[TocNode]:
    """Parse PyMuPDF get_toc() output into a tree of TocNode objects.

    Parameters
    ----------
    raw_toc : list of [level, title, page] triples from ``doc.get_toc(simple=True)``
    total_pages : total number of pages in the PDF
    max_level : ignore bookmarks deeper than this level
    skip_anchor_bookmarks : drop entries whose title matches
        :func:`is_anchor_bookmark` (default True). Set False to keep
        Word-generated ``_GoBack`` / ``_Toc…`` anchors in the tree.

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
        decoded = _decode_pdf_string(title)
        if skip_anchor_bookmarks and is_anchor_bookmark(decoded):
            continue
        flat.append(TocNode(
            level=lvl,
            title=decoded,
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


def get_toc_tree(pdf_path: Path | str, max_level: int = 99,
                 *, skip_anchor_bookmarks: bool = True) -> list[TocNode]:
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

    return parse_toc_tree(raw, total, max_level=max_level,
                          skip_anchor_bookmarks=skip_anchor_bookmarks)


# ---------------------------------------------------------------------------
# Printed Table of Contents extraction
# ---------------------------------------------------------------------------
# Many PDFs from DriveThruRPG / DMsGuild / Legendary Games ship without
# embedded bookmarks but DO have a printed Contents page listing every
# section with its page number. That listing is authoritative author-
# written structure — bookmark-equivalent — and lets us skip Marker
# entirely for these PDFs.

# Leader-dot style:    "Chapter 1 ........... 5"
# Numbered w/ period:  "1. Waterside Hostel ........... 8"
# Unicode ellipsis:    "Chapter 1 …… 5"   or "Chapter 1 ……… 5"
# Spaced columnar:     "Chapter 1      5"
#
# Leader pattern alternatives: 3+ consecutive dots, OR 2+ ellipsis chars,
# OR 3+ space-dot pairs. All strong enough to distinguish from an in-
# title period like "1. Waterside" where `.+?` can extend past it.
_TOC_LEADER = r"(?:\.{3,}|[…]{2,}|(?:\s\.){3,})"
_TOC_LINE_DOTS_RE = re.compile(
    rf"^\s*(?P<title>.+?){_TOC_LEADER}\s*(?P<page>\d{{1,4}})\s*$"
)
_TOC_LINE_SPACED_RE = re.compile(
    r"^\s*(?P<title>.+?\S)\s{3,}(?P<page>\d{1,4})\s*$"
)
# Numbered-inline style: the line starts with a chapter number marker
# like "4:" / "5." / "12." / "GT 1." and the page number follows at the
# end after any whitespace. The leading marker is strong enough evidence
# that this is a ToC line that we can accept even a single-space
# separator before the page number.
#   "4: Boatman's Tavern and Nulb Market 15"    -> ("4: Boatman's Tavern and Nulb Market", 15)
#   "5. Nulb Guardhouse 16"                     -> ("5. Nulb Guardhouse", 16)
# Does NOT match prose like "Chapter 5 has 7 pages" (no leading digit+punct).
_TOC_LINE_NUMBERED_INLINE_RE = re.compile(
    r"^\s*(?P<title>\d+[.:;]\s+\S.*?\S)\s+(?P<page>\d{1,4})\s*$"
)


def _match_toc_line(line: str) -> tuple[str, int] | None:
    """Try to parse one text line as a ToC entry. Returns (title, page) or None."""
    for pattern in (_TOC_LINE_DOTS_RE, _TOC_LINE_SPACED_RE,
                    _TOC_LINE_NUMBERED_INLINE_RE):
        m = pattern.match(line)
        if m:
            title = m.group("title").strip(" .…-–—")
            if not title:
                return None
            try:
                page = int(m.group("page"))
            except ValueError:
                return None
            return title, page
    return None


def _extract_paired_toc_entries(
    lines: list[str],
    total_pages: int,
    *,
    min_title_len: int = 3,
) -> list[tuple[str, int]]:
    """Fallback for PDFs whose ToC renders each entry across two adjacent
    lines — a title line followed by a bare page-number line. This is
    what PyMuPDF produces for two-column / right-aligned printed ToCs.

    Example input:
        "1. Waterside Hostel of Nulb"
        "6"
        "2. Otis's Smithy and Stable"
        "11"
        ...

    Skips the "Contents" header line itself (no number follows it) and
    reject pairs where the "title" is another number or implausibly short.
    """
    entries: list[tuple[str, int]] = []
    i = 0
    while i < len(lines) - 1:
        title = lines[i].strip()
        next_line = lines[i + 1].strip()
        if (title
                and len(title) >= min_title_len
                and not title.isdigit()
                and next_line.isdigit()):
            try:
                page = int(next_line)
            except ValueError:
                i += 1
                continue
            if 1 <= page <= total_pages:
                entries.append((title, page))
                i += 2
                continue
        i += 1
    return entries


def detect_printed_toc(
    pdf_path: Path | str,
    *,
    max_scan_pages: int = 20,
    min_entries_per_page: int = 5,
) -> tuple[list[tuple[str, int]], list[int]]:
    """Scan the front of the PDF for a printed Table of Contents.

    Walks the first ``max_scan_pages`` pages, trying to parse each line as
    a ``<title> ... <page_number>`` entry. A page contributes its matches
    if it yields at least ``min_entries_per_page`` such lines — this
    filters out pages that happen to contain one or two numeric references
    in prose.

    Returns ``(entries, toc_page_numbers)`` where ``entries`` is a
    deduplicated, page-sorted list of ``(title, page_number)`` and
    ``toc_page_numbers`` is the 1-indexed list of pages recognised as
    ToC pages (useful for excluding them from the converted output).

    Returns ``([], [])`` if no printed ToC was detected.
    """
    doc = fitz.open(str(pdf_path))
    try:
        all_entries: list[tuple[str, int]] = []
        toc_pages: list[int] = []
        limit = min(max_scan_pages, doc.page_count)

        for page_idx in range(limit):
            try:
                text = doc.load_page(page_idx).get_text("text")
            except Exception:
                continue

            lines = text.splitlines()

            # Strategy 1: single-line entries like "Chapter 1 ...... 5"
            # or "4: Title 15" (the numbered-inline form).
            single_line: list[tuple[str, int]] = []
            for line in lines:
                parsed = _match_toc_line(line)
                if parsed is None:
                    continue
                title, page = parsed
                if 1 <= page <= doc.page_count:
                    single_line.append((title, page))

            # Strategy 2: paired lines — "<title>\n<page>\n..." layout
            # PyMuPDF produces for right-aligned / two-column ToCs.
            paired = _extract_paired_toc_entries(lines, doc.page_count)

            # Merge both strategies. A ToC page often has ONE stray single-
            # line entry that uses a different format from the rest (e.g.
            # Nulb's "4: Boatman's Tavern and Nulb Market 15" where every
            # other entry is paired). Previously strategy 2 replaced
            # strategy 1, dropping the single-line outlier. Dedupe
            # downstream collapses any true duplicates.
            page_entries = single_line + paired

            if len(page_entries) >= min_entries_per_page:
                toc_pages.append(page_idx + 1)
                all_entries.extend(page_entries)

        entries = _dedupe_toc_entries(all_entries)
        return entries, toc_pages
    finally:
        doc.close()


_XREF_SUFFIX_RE = re.compile(r"\s*\(\d+\)\s*$")
_LEADING_NUMBER_RE = re.compile(r"^\s*\d+[.,:]?\s+")


def _canonical_toc_title(title: str) -> str:
    """Normalise a ToC title for duplicate-detection.

    Handles both back-reference suffixes like ``"Valegrave Manor (26)"``
    and leading chapter numbers like ``"26. Valegrave Manor"`` so that
    both forms collapse to the same canonical key ``"valegrave manor"``.
    """
    t = _XREF_SUFFIX_RE.sub("", title).strip()
    t = _LEADING_NUMBER_RE.sub("", t).strip()
    return t.lower()


def _dedupe_toc_entries(
    raw_entries: list[tuple[str, int]],
) -> list[tuple[str, int]]:
    """Collapse duplicate ToC entries produced by secondary cross-reference
    indexes (e.g. a "Local Quests" page that lists ``Nulb Constable (47)``
    at p74 alongside ``Carpenter's Shop (11)`` at p74 as back-references
    to earlier-indexed locations).

    Rules, applied in order:

    1. Exact dedupe on ``(lowercased title, page)``.
    2. Cross-reference dedupe: if a title matches ``<name> (<digits>)`` and
       we've already seen an entry whose title equals or starts with
       ``<name>``, drop the cross-reference. The suffix is the tell — a
       real chapter wouldn't normally print its own number in parentheses
       after its name in the ToC.
    3. Same-page clustering: when ≥3 entries share the same start_page in
       the raw input, keep only the first — the remaining ones are
       almost certainly cross-references into shared content rather than
       distinct sections beginning on the same page.
    """
    # Step 1: exact dedupe
    seen: dict[tuple[str, int], tuple[str, int]] = {}
    for title, page in raw_entries:
        key = (title.lower(), page)
        if key not in seen:
            seen[key] = (title, page)
    entries = list(seen.values())

    # Step 3 (applied before step 2 so cross-reference dedupe uses the
    # first-entry-per-page as the canonical name). Count raw-order
    # occurrences by page using the pre-dedupe list so we pick up
    # clustering correctly.
    from collections import Counter
    page_counts: Counter[int] = Counter(p for _, p in raw_entries)

    # Preserve the first entry per page when clustered
    clustered_pages = {p for p, c in page_counts.items() if c >= 3}
    kept: list[tuple[str, int]] = []
    seen_pages: set[int] = set()
    for title, page in entries:
        if page in clustered_pages and page in seen_pages:
            continue
        seen_pages.add(page)
        kept.append((title, page))

    # Step 2: cross-reference dedupe — drop "<name> (<digits>)" entries
    # when a previously-seen entry names the same location (possibly via
    # a leading "N. Name" form).
    canonical_names: set[str] = set()
    final: list[tuple[str, int]] = []
    for title, page in kept:
        canonical = _canonical_toc_title(title)
        is_xref = bool(_XREF_SUFFIX_RE.search(title))
        if is_xref and canonical in canonical_names:
            continue
        canonical_names.add(canonical)
        final.append((title, page))

    final.sort(key=lambda e: e[1])
    return final


def build_toc_from_printed(
    entries: list[tuple[str, int]],
    total_pages: int,
) -> list[TocNode]:
    """Convert printed-ToC ``(title, page)`` entries into a TocNode tree.

    All entries are emitted at level 1 (flat top-level list). Level
    refinement — inferring hierarchy from indent, numbering patterns,
    or font metrics — can layer on top later; the current output is
    already enough to chunk correctly, which is the main goal.
    """
    if not entries:
        return []
    raw = [[1, title, page] for title, page in entries]
    return parse_toc_tree(raw, total_pages=total_pages, max_level=99,
                          skip_anchor_bookmarks=False)
