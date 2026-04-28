#!/usr/bin/env python3
"""
pdf_to_5etools_v2.py — unified PDF-to-5etools converter.

Replaces the six heuristic v1 converters (see tag v1.0 for the historical
snapshot). Routes PDFs through one of two front-ends:

  1. PyMuPDF fast path — selectable text + PDF bookmarks present.
     Cheapest; uses the PDF's own table of contents as section structure.

  2. Marker path — scans, un-bookmarked PDFs, or image-heavy layouts.
     Runs Marker (Surya OCR + ML layout) to produce markdown with
     authoritative `#`/`##`/`###` headings. Synthesises a TocNode tree
     from those headings and chunks the same way as the fast path.

Downstream of chunking everything is shared: the same system prompt,
the same `claude_api.call_claude`, the same `adventure_model` validation,
the same `fix_adventure_json` post-processing.

Default model: claude-haiku-4-5-20251001. Marker removes the structure-
inference burden that previously required Sonnet for 1e content.

Usage:
    python3 pdf_to_5etools_v2.py input.pdf [options]

Requires ANTHROPIC_API_KEY env var or --api-key. The Marker path also
requires marker-pdf installed in `marker-env/` (see README/CLAUDE.md).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import anthropic
import fitz  # PyMuPDF

import cli_args as _cli
import claude_api as _api
import extract_monsters as _mon
from adventure_model import (
    BuildContext, SectionEntry, EntriesEntry, parse_entry,
    HomebrewAdventure,
)
from pdf_utils import (
    TocNode, get_toc_tree, extract_pdf_toc, _decode_pdf_string,
    detect_printed_toc, build_toc_from_printed,
)


DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_CHUNK = 1  # one chapter per Claude call; Marker/TOC defines boundaries

# Treat a PDF as "has selectable text" if sampled pages yield >= this many chars.
SELECTABLE_TEXT_MIN_CHARS = 100

# Hard cap per chunk body sent to Claude. Above this we split by child
# TocNodes (or, if the node is a leaf, pass through and let Claude's own
# max_tokens / retry handling deal with it). 150 KB corresponds to roughly
# 38k input tokens for English prose, leaving ample headroom inside the
# 200k-token context window. Output of a 150 KB chunk is roughly 50k
# tokens of structured JSON, which Haiku 4.5 handles inside the raised
# MAX_OUTPUT_TOKENS ceiling (see claude_api.py).
MAX_CHUNK_CHARS = 150_000

MARKER_ENV = Path(__file__).parent / "marker-env"
MARKER_BIN = MARKER_ENV / "bin" / "marker_single"


# ---------------------------------------------------------------------------
# Slim v2 system prompt: markdown headings are authoritative structure.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = textwrap.dedent(f"""\
You are a tabletop RPG archivist converting a published adventure module
into 5etools JSON format. All content is fictional game material intended
for adult tabletop gaming; dark themes (evil cults, monster violence,
dungeon hazards) are standard genre conventions.

You will receive a SINGLE chapter. Its name and known sub-section names
are provided as a hint. The body text is either clean digital text or
Marker-extracted markdown with `#`/`##`/`###`/`####` headings; treat any
heading that appears in the body as an authoritative sub-section name.

Return ONLY a JSON array: the entries[] content for this chapter. Do NOT
wrap the output in a {{"type":"section"}} — the caller handles section
wrappers. Do NOT add "id" fields.

Mapping rules:
- Every named sub-section becomes an {{"type":"entries","name":"...","entries":[...]}}.
  Strip any leading `**` bold markers, trailing whitespace, and all-caps
  formatting from heading names (normalise to title case).
- Numbered keyed rooms (e.g. "101. Armory", "17. Barracks") keep the
  "N. Room Name" form in the entries "name".
- Plain paragraphs under a heading become bare JSON strings inside its entries[].
- Stat lines ("Ghasts (2): AC 4, MV 15\\", HD 4, ...") stay as italic strings:
  "{{@i Ghasts (2): AC 4, MV 15\\"; HD 4; ...}}". Do NOT convert 1e stats to 5e
  here — a separate pass handles that.
- Markdown bullet lists ("- item") become {{"type":"list","items":["...","..."]}}.
- Read-aloud / boxed prose (visually set off, sometimes in a quote/blockquote
  in the markdown) becomes {{"type":"inset","name":"","entries":["..."]}}.
- Named sidebars / DM notes become {{"type":"inset","name":"Title","entries":[...]}}.
- Merge hyphenated line breaks: "adven-\\nture" -> "adventure".
- Fix obvious OCR typos silently (e.g. "HANDING FROM CHAINS" -> "HANGING FROM CHAINS",
  "IMPOS-ING" -> "IMPOSING"). Do not editorialise beyond OCR correction.
{_api.COMMON_TAG_RULES}
{_api.COMMON_NESTING_RULES}

If the chapter body is empty or pure noise, return [].
""").strip()


# ---------------------------------------------------------------------------
# Input routing: choose PyMuPDF fast path vs Marker path
# ---------------------------------------------------------------------------

@dataclass
class InputProfile:
    has_bookmarks: bool
    has_selectable_text: bool
    page_count: int
    printed_toc_entries: list = None
    printed_toc_pages: list = None

    def __post_init__(self):
        if self.printed_toc_entries is None:
            self.printed_toc_entries = []
        if self.printed_toc_pages is None:
            self.printed_toc_pages = []

    @property
    def use_fast_path(self) -> bool:
        return self.has_bookmarks and self.has_selectable_text

    @property
    def use_printed_toc_path(self) -> bool:
        """Bookmark-less PDF with enough text and a printed ToC we parsed."""
        return (not self.has_bookmarks
                and self.has_selectable_text
                and len(self.printed_toc_entries) >= 5)


def profile_pdf(pdf_path: Path) -> InputProfile:
    """Inspect a PDF to decide the pipeline.

    Order of preference:
      1. Embedded bookmarks → PyMuPDF fast path (cheapest, most accurate)
      2. Printed ToC page + selectable text → PyMuPDF + printed-ToC path
         (near-free, author-provided structure)
      3. Everything else → Marker path (GPU, slower, more expensive)
    """
    doc = fitz.open(str(pdf_path))
    try:
        pages = doc.page_count
        has_bookmarks = bool(doc.get_toc())

        # Sample up to 10 pages; if most yield real text, it's digital.
        sample_ixs = [i * max(1, pages // 10) for i in range(min(10, pages))]
        chars_found = 0
        for ix in sample_ixs:
            try:
                chars_found += len(doc.load_page(ix).get_text("text"))
            except Exception:
                pass
        avg_chars = chars_found / max(1, len(sample_ixs))
        has_selectable_text = avg_chars >= SELECTABLE_TEXT_MIN_CHARS
    finally:
        doc.close()

    # Only scan for a printed ToC when we'd actually use it (no embedded
    # bookmarks, text is selectable). Saves a few hundred ms on PDFs that
    # already have bookmarks.
    printed_entries: list = []
    printed_pages: list = []
    if not has_bookmarks and has_selectable_text:
        printed_entries, printed_pages = detect_printed_toc(pdf_path)

    return InputProfile(
        has_bookmarks=has_bookmarks,
        has_selectable_text=has_selectable_text,
        page_count=pages,
        printed_toc_entries=printed_entries,
        printed_toc_pages=printed_pages,
    )


# ---------------------------------------------------------------------------
# PyMuPDF fast path: bookmarked digital PDFs
# ---------------------------------------------------------------------------

def extract_page_text(doc: fitz.Document, page_num: int) -> str:
    """Plain text for page_num (1-indexed). Merges hyphenated line breaks."""
    text = doc.load_page(page_num - 1).get_text("text")
    # Merge hyphenated line breaks: "adven-\nture" -> "adventure"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    return text


def _node_body_pymupdf(node: TocNode, doc: fitz.Document) -> str:
    """Join all page texts for a node's page range."""
    pages_text = []
    for p in range(node.start_page, node.end_page + 1):
        if 1 <= p <= doc.page_count:
            pages_text.append(f"=== page {p} ===\n{extract_page_text(doc, p)}")
    return "\n\n".join(pages_text)


def _node_body_markdown(node: TocNode, lines: list[str]) -> str:
    """Slice markdown lines covered by a node's (line-number) range."""
    start = max(0, node.start_page - 1)
    end = min(len(lines), node.end_page)
    return "\n".join(lines[start:end])


@dataclass
class ChunkSpec:
    """Descriptor for one chunk emitted by :func:`split_oversized`.

    Attributes
    ----------
    root:
        The top-level ``TocNode`` (from the input ``toc_roots``) this chunk
        descends from. All chunks sharing a ``root`` are assembled into a
        single ``SectionEntry`` downstream.
    target_node:
        The TocNode whose content this chunk provides. Always an instance
        from the original tree (never synthesised) so downstream code can
        walk the tree and match chunks back to their positions.
    is_prose_stub:
        When True, ``body`` contains ONLY ``target_node``'s own prose
        (the text between its heading and its first child's heading).
        Used when a container node was split because it exceeded
        ``max_chars``; its prose would otherwise be lost.

        When False, ``body`` covers the full range of ``target_node``
        (including descendant content). For unsplit subtrees Claude
        renders the entire hierarchy in a single response, and the
        assembly step uses that response as-is.
    body:
        The text payload sent to Claude.
    """
    root: TocNode
    target_node: TocNode
    is_prose_stub: bool
    body: str


def split_oversized(
    nodes: list[TocNode],
    body_fn,
    max_chars: int = MAX_CHUNK_CHARS,
) -> list[ChunkSpec]:
    """Emit :class:`ChunkSpec` entries, splitting by children when a node's
    body exceeds ``max_chars``.

    When a node exceeds ``max_chars`` and has children, we:
      1. Emit the PARENT'S OWN PROSE (the text between the parent heading
         and the first child heading) as a chunk with
         ``is_prose_stub=True`` — previously this was silently dropped.
         ``target_node`` still points at the original TocNode so the
         assembly step can merge the prose back into the right section.
      2. Recurse into children, which may themselves get split.

    Leaves exceeding the budget are passed through as-is — Claude's own
    retry/split logic handles them if they truncate.

    Each top-level input ``node`` becomes the ``root`` of all chunks it
    (and its descendants) emit, so grouping chunks by ``.root`` recovers
    the one-section-per-top-level-root invariant the adventure model
    requires.
    """
    chunks: list[ChunkSpec] = []
    for root in nodes:
        chunks.extend(_split_into_chunks(root, root, body_fn, max_chars))
    return chunks


def _split_into_chunks(
    root: TocNode,
    node: TocNode,
    body_fn,
    max_chars: int,
) -> list[ChunkSpec]:
    """Recursive helper: emit chunks for ``node`` (descendant of ``root``)."""
    body = body_fn(node)
    if len(body) <= max_chars or not node.children:
        return [ChunkSpec(root=root, target_node=node,
                          is_prose_stub=False, body=body)]

    chunks: list[ChunkSpec] = []
    # Parent's own prose: text between node start and first child start.
    first_child = min(node.children, key=lambda c: c.start_page)
    prose_end = first_child.start_page - 1
    if prose_end >= node.start_page:
        prose_stub = TocNode(
            level=node.level,
            title=node.title,
            start_page=node.start_page,
            end_page=prose_end,
            children=[],
        )
        prose_body = body_fn(prose_stub)
        if prose_body.strip():
            chunks.append(ChunkSpec(root=root, target_node=node,
                                    is_prose_stub=True, body=prose_body))

    for child in node.children:
        chunks.extend(_split_into_chunks(root, child, body_fn, max_chars))
    return chunks


def build_chunks_from_toc(
    toc_roots: list[TocNode],
    doc: fitz.Document,
) -> list[ChunkSpec]:
    """One chunk per top-level section; oversized sections split by children."""
    return split_oversized(toc_roots, lambda n: _node_body_pymupdf(n, doc))


# ---------------------------------------------------------------------------
# Marker path: scanned / un-bookmarked PDFs
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#+)\s+(.+?)\s*$")
_NUMBERED_ROOM_RE = re.compile(r"^\s*\**\s*(\d+)[.,]\s+[A-Za-z]")


def run_marker(pdf_path: Path, out_dir: Path, verbose: bool = False) -> Path:
    """Invoke marker_single via subprocess. Returns path to the .md file."""
    if not MARKER_BIN.exists():
        raise RuntimeError(
            f"Marker not found at {MARKER_BIN}. Set up the venv:\n"
            f"  python3 -m venv {MARKER_ENV} && source {MARKER_ENV}/bin/activate "
            f"&& pip install marker-pdf pymupdf"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(MARKER_BIN), str(pdf_path),
        "--output_dir", str(out_dir),
        "--output_format", "markdown",
        "--disable_image_extraction",
    ]
    if verbose:
        print(f"  running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=not verbose, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"marker failed: {result.stderr}")

    # Marker writes to <out_dir>/<stem>/<stem>.md
    stem = pdf_path.stem
    md_path = out_dir / stem / f"{stem}.md"
    if not md_path.exists():
        # Some marker versions drop the subdir; fall back to flat layout.
        md_path = out_dir / f"{stem}.md"
    if not md_path.exists():
        raise RuntimeError(f"marker did not produce expected markdown at {md_path}")
    return md_path


def clean_heading(title: str) -> str:
    """Strip markdown bold markers and surrounding whitespace."""
    return re.sub(r"\*+", "", title).strip()


@dataclass
class MdHeading:
    level: int      # 1-based, from `#` count
    title: str
    line_no: int    # 0-based line index where the heading appeared


def parse_markdown_headings(md_text: str) -> tuple[list[MdHeading], list[str]]:
    """Return (headings, body_lines). Body lines are the raw markdown."""
    lines = md_text.splitlines()
    headings: list[MdHeading] = []
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m:
            headings.append(MdHeading(
                level=len(m.group(1)),
                title=clean_heading(m.group(2)),
                line_no=i,
            ))
    return headings, lines


def normalise_numbered_rooms(headings: list[MdHeading]) -> list[MdHeading]:
    """Flatten numbered-room headings (e.g. "101. ARMORY") to a common level.

    Marker's heading-level assignment is noisy on keyed-room dungeons — it
    spreads rooms across multiple `#` levels based on visual font metrics.
    We detect the pattern and collapse to the most common level.

    Importantly, a modern adventure PDF contains MANY numbered sequences
    (the keyed-room list, numbered patron types inside a tavern, numbered
    quest hooks inside a quest section, …). We only want to flatten the
    ONE series that represents top-level locations. Heuristic:

    - Find the most common level among numbered headings.
    - Only the numbered headings already at (or within ±1 of) that level
      count as "real" keyed rooms. Numbered items much deeper than the
      majority are sub-list items (patrons, hooks) and stay put.
    - After flattening, run :func:`nest_between_keyed_rooms` so generic
      sub-headings get tucked under the preceding room.
    """
    numbered = [h for h in headings if _NUMBERED_ROOM_RE.match(h.title)]
    if len(numbered) < 5:
        return headings  # not a keyed dungeon; leave levels alone

    from collections import Counter
    common_level = Counter(h.level for h in numbered).most_common(1)[0][0]

    # Tolerance: accept outliers within ±1 of the majority level. Beyond
    # that (e.g. a "1. Foo" at level 5 when rooms are at level 2) the item
    # is almost certainly part of an inner numbered list, not a room.
    def is_keyed_room(h: MdHeading) -> bool:
        return (_NUMBERED_ROOM_RE.match(h.title) is not None
                and abs(h.level - common_level) <= 1)

    # Need at least 5 numbered items in the tight cluster to trust the
    # pattern; otherwise leave everything alone.
    keyed = [h for h in numbered if is_keyed_room(h)]
    if len(keyed) < 5:
        return headings

    for h in keyed:
        h.level = common_level

    nest_between_keyed_rooms(headings, room_level=common_level,
                             keyed_predicate=is_keyed_room)
    return headings


def nest_between_keyed_rooms(
    headings: list[MdHeading],
    *,
    room_level: int,
    keyed_predicate=None,
) -> list[MdHeading]:
    """Demote non-keyed-room headings that appear between keyed rooms so
    they become children of the preceding keyed room.

    ``keyed_predicate(h) -> bool`` identifies which headings are real
    keyed rooms (default: any ``_NUMBERED_ROOM_RE`` match). Pass a tighter
    predicate when the PDF contains multiple numbered sequences and only
    one of them represents top-level locations.

    Context: a published adventure's natural structure is
        keyed_room
            Background
            Creatures
            Treasure
            Development
        next_keyed_room
            Background
            Treasure
            …

    Marker's heading-level assignment is driven by visual font metrics, so
    these generic sub-headings often land at the same level as — or
    shallower than — the keyed room itself. That makes them top-level
    siblings under :func:`parse_toc_tree`, producing an over-fragmented
    TOC with the room's own sections scattered alongside the rooms.

    This pass walks the heading list and, for every stretch of headings
    that follows a keyed room, demotes any heading whose level is at or
    above ``room_level`` to ``room_level + 1`` so it nests inside the
    preceding keyed room. Headings strictly deeper than ``room_level``
    (e.g. Marker's own genuine sub-sub-headings, or inner numbered lists
    rejected by ``keyed_predicate``) are left untouched so existing
    hierarchy is preserved.

    Headings BEFORE the first keyed room are intro/matter content and are
    left at their original level. They become proper top-level siblings
    alongside the keyed rooms.
    """
    if keyed_predicate is None:
        keyed_predicate = lambda h: bool(_NUMBERED_ROOM_RE.match(h.title))

    child_level = room_level + 1
    inside_run = False
    for h in headings:
        if keyed_predicate(h):
            inside_run = True
            continue
        if not inside_run:
            continue
        if h.level <= room_level:
            h.level = child_level
    return headings


def build_synthetic_toc(
    headings: list[MdHeading],
    total_lines: int,
) -> list[TocNode]:
    """Build a TocNode tree from markdown headings, using line numbers as
    stand-ins for page numbers. start_page = line_no + 1."""
    if not headings:
        return []

    # Re-use parse_toc_tree's approach but with line numbers.
    from pdf_utils import parse_toc_tree
    raw = [[h.level, h.title, h.line_no + 1] for h in headings]
    return parse_toc_tree(raw, total_pages=total_lines, max_level=99)


def build_chunks_from_markdown(
    toc_roots: list[TocNode],
    lines: list[str],
) -> list[ChunkSpec]:
    """One chunk per top-level heading; oversized sections split by children."""
    return split_oversized(toc_roots, lambda n: _node_body_markdown(n, lines))


# ---------------------------------------------------------------------------
# Shared: build the Claude user prompt for one chunk
# ---------------------------------------------------------------------------

def build_prompt(node: TocNode, body: str) -> str:
    parts = [f"=== SECTION: {node.title} ==="]
    if node.children:
        parts.append("")
        parts.append("Known sub-sections (treat as authoritative structure hints):")
        for child in node.children:
            parts.append(f"  - {child.title}")
            for grand in child.children:
                parts.append(f"    - {grand.title}")
    parts.append("")
    parts.append("Convert the following text into the entries[] array for this section.")
    parts.append(body)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Claude loop + assembly
# ---------------------------------------------------------------------------

def call_claude_for_chunk(
    client: anthropic.Anthropic,
    chunk_text: str,
    model: str,
    verbose: bool,
    debug_dir: Path | None,
    chunk_id: str,
) -> list | None:
    """Thin wrapper delegating to claude_api.call_claude."""
    return _api.call_claude(
        client,
        chunk_text,
        model=model,
        system_prompt=SYSTEM_PROMPT,
        verbose=verbose,
        debug_dir=debug_dir,
        chunk_id=chunk_id,
    )


def _unwrap_self_named_wrapper(entries: list, section_name: str) -> list:
    """If ``entries`` is a single ``{"type":"entries","name":...}`` block whose
    name matches ``section_name``, return the inner entries instead.

    Claude often wraps its output for a section in one top-level entries
    block re-stating the section title, which would render as a duplicate
    visible heading and populate the mini-ToC headers with the chapter's
    own name.
    """
    if len(entries) != 1:
        return entries
    outer = entries[0]
    if not isinstance(outer, dict):
        return entries
    if outer.get("type") not in ("entries", "section"):
        return entries
    outer_name = (outer.get("name") or "").strip().casefold()
    if not outer_name or outer_name != (section_name or "").strip().casefold():
        return entries
    inner = outer.get("entries")
    if not isinstance(inner, list):
        return entries
    return inner


def _has_any_content(node: TocNode, node_ids_with_entries: set[int]) -> bool:
    """True if ``node`` or any descendant has a chunk with entries."""
    if id(node) in node_ids_with_entries:
        return True
    return any(_has_any_content(c, node_ids_with_entries) for c in node.children)


def _build_raw_section_entries(
    root: TocNode,
    entries_by_target: dict[int, list],
) -> list:
    """Walk the TocNode subtree under ``root`` and build a nested
    raw-JSON entries[] list (dicts + strings only — no parsed Entry
    objects).

    ``entries_by_target[id(node)]`` holds the raw JSON entries that Claude
    produced for chunks whose ``target_node`` was ``node``.

    Returning raw JSON (rather than parsed Entry objects) is critical:
    ``parse_entry`` expects its input to be pure JSON and recurses into
    nested ``entries`` arrays as JSON. Handing it already-parsed Entry
    objects leads to ``TypeError: Object of type EntriesEntry is not
    JSON serializable`` when the top-level document is later written out.

    The caller is responsible for running ``parse_entry`` on each item
    of the returned list exactly once, at the section boundary.
    """
    node_ids_with_entries = set(entries_by_target.keys())

    def walk(node: TocNode) -> list:
        result: list = list(entries_by_target.get(id(node), []))
        for child in node.children:
            if not _has_any_content(child, node_ids_with_entries):
                continue
            result.append({
                "type": "entries",
                "name": child.title,
                "entries": walk(child),
            })
        return result

    return walk(root)


def assemble_adventure(
    name: str,
    source: str,
    chunk_results: list[tuple[ChunkSpec, list | None]],
    author: str,
    is_book: bool,
) -> HomebrewAdventure:
    """Group chunks by their ``root`` and build one ``SectionEntry`` per
    top-level TocNode, preserving the tree structure when a root was split.

    For unsplit roots (single chunk, ``is_prose_stub=False``) Claude's output
    is used as-is — the system prompt asks Claude to emit the whole
    subtree structure inside its entries[].

    For split roots (multiple chunks, or any prose stub) the tree is
    rebuilt by walking the TocNode hierarchy and placing each chunk's
    entries at the correct depth.
    """
    ctx = BuildContext()
    sections: list[SectionEntry] = []

    # Group chunk_results by root
    by_root: dict[int, tuple[TocNode, list[tuple[ChunkSpec, list | None]]]] = {}
    for spec, entries in chunk_results:
        key = id(spec.root)
        if key not in by_root:
            by_root[key] = (spec.root, [])
        by_root[key][1].append((spec, entries))

    for root, group in by_root.values():
        # Skip roots where every chunk returned None (all Claude calls failed)
        if all(entries is None for _, entries in group):
            print(f"  [skip] {root.title}: all chunks returned None")
            continue

        # Filter Nones to detect unsplit-vs-split case
        non_none = [(s, e) for s, e in group if e is not None]

        if (len(group) == 1
                and not group[0][0].is_prose_stub
                and non_none):
            # Unsplit: Claude output covers the whole subtree. Use as-is.
            spec, entries = non_none[0]

            # Unwrap single-entry wrappers that duplicate the section name.
            # Claude sometimes emits:
            #   [{"type": "entries", "name": "1. Waterside Hostel",
            #     "entries": [actual content]}]
            # If we keep that, the section name appears both as the
            # SectionEntry's own name AND as an inner entries-block title,
            # which 5etools renders as a visible title + a mirror of it
            # inside the chapter's own mini-ToC.
            entries = _unwrap_self_named_wrapper(entries, root.title)

            parsed_entries: list = []
            for i, raw in enumerate(entries):
                try:
                    parsed_entries.append(
                        parse_entry(raw, ctx, f"section[{root.title}].entries[{i}]")
                    )
                except Exception as e:
                    print(f"  [warn] {root.title}[{i}]: {e}")
                    if isinstance(raw, str):
                        parsed_entries.append(raw)
        else:
            # Split: rebuild the tree from per-node entries.
            entries_by_target: dict[int, list] = {}
            for spec, entries in non_none:
                entries_by_target.setdefault(
                    id(spec.target_node), []
                ).extend(entries)
            raw_entries = _build_raw_section_entries(root, entries_by_target)
            parsed_entries = []
            for i, raw in enumerate(raw_entries):
                try:
                    parsed_entries.append(
                        parse_entry(raw, ctx, f"section[{root.title}].entries[{i}]")
                    )
                except Exception as e:
                    print(f"  [warn] {root.title}[{i}]: {e}")
                    if isinstance(raw, str):
                        parsed_entries.append(raw)

        sections.append(SectionEntry(
            name=root.title,
            entries=parsed_entries,
            _ctx=ctx,
        ))

    return HomebrewAdventure.build(
        name=name, source=source, sections=sections,
        ctx=ctx, is_book=is_book,
        authors=[author] if author and author != "Unknown" else [],
    )


# ---------------------------------------------------------------------------
# Main conversion entry point
# ---------------------------------------------------------------------------

def _bestiary_path(out: Path) -> Path:
    """`foo.json` -> `foo-bestiary.json`."""
    return out.with_name(f"{out.stem}-bestiary.json")


def write_bestiary(
    client: anthropic.Anthropic,
    statblocks: list[dict],
    *,
    adventure_name: str,
    adventure_source: str,
    author: str,
    out_path: Path,
    model: str,
    use_batch: bool,
    debug_dir: Path | None,
    verbose: bool,
) -> Path:
    """Run the monster Claude pass and write the bestiary JSON."""
    bestiary_source, source_meta = _mon.make_bestiary_source_meta(
        adventure_source, adventure_name, author=author,
    )
    print(f"[monsters] extracting {len(statblocks)} stat block(s) → {out_path.name}")
    if not statblocks:
        print("[monsters] nothing to extract; skipping bestiary write")
        return out_path
    bestiary = _mon.build_bestiary(
        client, statblocks,
        source_id=bestiary_source,
        source_meta=source_meta,
        model=model,
        use_batch=use_batch,
        debug_dir=debug_dir,
        verbose=verbose,
    )
    out_path.write_text(
        json.dumps(bestiary, indent="\t", ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[wrote] {out_path} ({len(bestiary['monster'])} monsters)")
    return out_path


def convert_monsters_only(
    pdf_path: Path,
    short_id: str,
    name: str,
    author: str,
    out_path: Path | None,
    output_dir: Path | None,
    client: anthropic.Anthropic,
    model: str,
    use_batch: bool,
    debug_dir: Path | None,
    dry_run_only: bool,
    verbose: bool,
) -> Path:
    """Bestiary-only pipeline: Marker → stat-block slices → Claude.

    Always uses Marker (per decision), ignoring the PyMuPDF fast path, so
    stat-block detection is uniform across digital and scanned PDFs.
    """
    print("[monsters-only] running Marker (no adventure pass)")
    with tempfile.TemporaryDirectory(prefix="marker-") as tmp:
        md_path = run_marker(pdf_path, Path(tmp), verbose=verbose)
        md_text = md_path.read_text()

    statblocks = _mon.extract_markdown_statblocks(md_text)
    print(f"[monsters-only] found {len(statblocks)} stat-block section(s)")
    if verbose or dry_run_only:
        for sb in statblocks[:30]:
            print(f"  - {sb['name'][:60]}")
        if len(statblocks) > 30:
            print(f"  ... and {len(statblocks) - 30} more")

    if dry_run_only:
        chunks = [(_synth_node(sb["name"]), sb["text"]) for sb in statblocks]
        _api.dry_run(client, [sb["text"] for sb in statblocks], chunks,
                     model, _mon.SYSTEM_PROMPT, use_batch, verbose)
        return pdf_path

    # Output path: <stem>-bestiary.json next to the PDF unless overridden
    if out_path is not None:
        bestiary_out = out_path
    else:
        target_dir = output_dir or pdf_path.parent
        target_dir.mkdir(parents=True, exist_ok=True)
        bestiary_out = target_dir / f"{pdf_path.stem}-bestiary.json"

    return write_bestiary(
        client, statblocks,
        adventure_name=name, adventure_source=short_id, author=author,
        out_path=bestiary_out, model=model, use_batch=use_batch,
        debug_dir=debug_dir, verbose=verbose,
    )


def _synth_node(title: str) -> TocNode:
    """Placeholder TocNode for dry-run bookkeeping in monsters-only mode."""
    return TocNode(level=1, title=title, start_page=1, end_page=1)


def convert(
    pdf_path: Path,
    output_type: str,
    short_id: str | None,
    author: str,
    out_path: Path | None,
    output_dir: Path | None,
    api_key: str | None,
    model: str,
    use_batch: bool,
    debug_dir: Path | None,
    dry_run_only: bool,
    verbose: bool,
    force_marker: bool = False,
    extract_monsters: bool = False,
    monsters_only: bool = False,
    resume_batch: str | None = None,
) -> Path:
    """Drive the end-to-end v2 conversion. Returns the output JSON path."""
    client = anthropic.Anthropic(api_key=api_key) if api_key \
        else anthropic.Anthropic()

    # Default source/name derivation
    if short_id is None:
        short_id = re.sub(r"[^A-Z0-9]", "", pdf_path.stem.upper())[:8] or "HOMEBREW"
    name = pdf_path.stem.replace("_", " ")

    # Always persist raw Claude responses alongside the output so a crash
    # in later steps (assembly, write, monster pass) doesn't lose the API
    # work. Default location: <out_stem>-responses/. Respects --debug-dir
    # if the user passed one.
    if not dry_run_only and debug_dir is None and not monsters_only:
        target_dir_for_log = output_dir or (out_path.parent if out_path
                                             else pdf_path.parent)
        stem = out_path.stem if out_path else pdf_path.stem
        debug_dir = target_dir_for_log / f"{stem}-responses"
    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        if not dry_run_only:
            print(f"[responses] saving raw Claude I/O to {debug_dir}")

    # ---- Bestiary-only fast exit ----
    if monsters_only:
        return convert_monsters_only(
            pdf_path=pdf_path, short_id=short_id, name=name, author=author,
            out_path=out_path, output_dir=output_dir,
            client=client, model=model, use_batch=use_batch,
            debug_dir=debug_dir, dry_run_only=dry_run_only, verbose=verbose,
        )

    # ---- 1. Route ----
    profile = profile_pdf(pdf_path)
    use_fast = profile.use_fast_path and not force_marker
    use_printed_toc = (
        not use_fast
        and profile.use_printed_toc_path
        and not force_marker
    )
    if use_fast:
        route_label = "fast-path (PyMuPDF + bookmarks)"
    elif use_printed_toc:
        route_label = (f"printed-ToC path (PyMuPDF, "
                       f"{len(profile.printed_toc_entries)} ToC entries from "
                       f"pages {profile.printed_toc_pages})")
    else:
        route_label = "Marker path"
    print(f"[profile] pages={profile.page_count} "
          f"bookmarks={'yes' if profile.has_bookmarks else 'no'} "
          f"digital={'yes' if profile.has_selectable_text else 'no'} "
          f"printed_toc={len(profile.printed_toc_entries) or 'none'} "
          f"-> {route_label}")

    # ---- 2. Build chunks ----
    if use_fast:
        doc = fitz.open(str(pdf_path))
        try:
            toc_roots = get_toc_tree(pdf_path, max_level=3)
            if not toc_roots:
                raise RuntimeError("fast path selected but get_toc_tree returned no roots")
            chunks = build_chunks_from_toc(toc_roots, doc)
        finally:
            doc.close()
    elif use_printed_toc:
        doc = fitz.open(str(pdf_path))
        try:
            toc_roots = build_toc_from_printed(
                profile.printed_toc_entries,
                total_pages=profile.page_count,
            )
            if not toc_roots:
                raise RuntimeError(
                    "printed-ToC path selected but no TocNode tree produced"
                )
            chunks = build_chunks_from_toc(toc_roots, doc)
        finally:
            doc.close()
    else:
        with tempfile.TemporaryDirectory(prefix="marker-") as tmp:
            md_path = run_marker(pdf_path, Path(tmp), verbose=verbose)
            md_text = md_path.read_text()
        headings, lines = parse_markdown_headings(md_text)
        headings = normalise_numbered_rooms(headings)
        toc_roots = build_synthetic_toc(headings, total_lines=len(lines))
        chunks = build_chunks_from_markdown(toc_roots, lines)

    # Count distinct top-level roots for user-visible reporting
    distinct_roots = {id(c.root) for c in chunks}
    print(f"[chunks] {len(chunks)} API calls across "
          f"{len(distinct_roots)} top-level sections")
    for spec in chunks:
        tag = " [prose-only]" if spec.is_prose_stub else ""
        print(f"  - {spec.target_node.title} "
              f"({len(spec.body)} chars, "
              f"{len(spec.target_node.children)} children){tag}")

    if not chunks:
        raise RuntimeError("no chunks produced; cannot convert")

    # ---- 3. Dry run ----
    if dry_run_only:
        chunk_texts = [build_prompt(c.target_node, c.body) for c in chunks]
        _api.dry_run(client, chunk_texts, chunks, model,
                     SYSTEM_PROMPT, use_batch, verbose)
        return pdf_path  # nothing written

    # ---- 4. Claude pass ----
    chunk_results: list[tuple[ChunkSpec, list | None]] = []
    if resume_batch:
        print(f"[resume] skipping Claude submission — fetching batch "
              f"{resume_batch}")
        batch = _api.fetch_claude_batch_results(
            client, resume_batch, len(chunks),
            verbose=verbose, debug_dir=debug_dir,
        )
        for spec, entries in zip(chunks, batch):
            chunk_results.append((spec, entries))
    elif use_batch:
        prompts = [build_prompt(c.target_node, c.body) for c in chunks]
        batch = _api.call_claude_batch(
            client, prompts, model, SYSTEM_PROMPT, verbose, debug_dir=debug_dir,
        )
        for spec, entries in zip(chunks, batch):
            chunk_results.append((spec, entries))
    else:
        for i, spec in enumerate(chunks):
            cid = f"{i+1:03d}-{re.sub(r'[^a-z0-9]+', '-', spec.target_node.title.lower())[:30]}"
            if verbose:
                print(f"[chunk {cid}] calling Claude ({len(spec.body)} chars)")
            prompt = build_prompt(spec.target_node, spec.body)
            entries = call_claude_for_chunk(
                client, prompt, model, verbose, debug_dir, cid,
            )
            chunk_results.append((spec, entries))

    # ---- 5. Assemble ----
    doc = assemble_adventure(
        name=name, source=short_id,
        chunk_results=chunk_results,
        author=author,
        is_book=(output_type == "book"),
    )

    # ---- 6. Write adventure ----
    out = out_path
    if out is None:
        target_dir = output_dir or pdf_path.parent
        target_dir.mkdir(parents=True, exist_ok=True)
        out = target_dir / f"{pdf_path.stem}.json"
    out.write_text(doc.to_json())
    print(f"[wrote] {out}")

    # ---- 7. Optional monster extraction pass ----
    if extract_monsters:
        adv_dict = doc.to_dict() if hasattr(doc, "to_dict") else json.loads(out.read_text())
        italic_blocks = _mon.extract_italic_statblocks(adv_dict)
        # Also scan for the legacy table format in case a future prompt
        # emits structured tables.
        table_entries = _mon.extract_statblock_entries(adv_dict)
        table_blocks = [
            {"name": e.get("name", "Unknown"),
             "text": _mon.statblock_to_text(e)}
            for e in table_entries
        ]
        all_blocks = italic_blocks + table_blocks
        if verbose:
            print(f"[monsters] found italic={len(italic_blocks)} "
                  f"table={len(table_blocks)}")
        write_bestiary(
            client, all_blocks,
            adventure_name=name, adventure_source=short_id, author=author,
            out_path=_bestiary_path(out),
            model=model, use_batch=use_batch,
            debug_dir=debug_dir, verbose=verbose,
        )

    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert a PDF into a 5etools homebrew adventure/book JSON (v2).",
    )
    _cli.add_common_args(parser, default_chunk=DEFAULT_CHUNK, default_model=DEFAULT_MODEL)
    parser.add_argument(
        "--force-marker", action="store_true", dest="force_marker",
        help="Bypass the PyMuPDF fast path; always use Marker. Useful when "
             "the PDF has bookmarks but the text layer is unreliable.",
    )
    parser.add_argument(
        "--resume-batch", metavar="BATCH_ID", dest="resume_batch", default=None,
        help="Fetch results from an already-completed Anthropic Batch API run "
             "(e.g. 'msgbatch_01ABC...') instead of submitting a new batch. "
             "Skips all Claude billing for the recovered chunks. Still runs "
             "Marker + chunking to map custom_ids back to chunks; chunking "
             "must be deterministic for the mapping to be correct.",
    )
    args = parser.parse_args(argv)

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("error: ANTHROPIC_API_KEY not set and --api-key not provided")
        return 1
    if not args.pdf.exists():
        print(f"error: {args.pdf} does not exist")
        return 1

    try:
        convert(
            pdf_path=args.pdf,
            output_type=args.output_type,
            short_id=args.short_id,
            author=args.author,
            out_path=args.out,
            output_dir=args.output_dir,
            api_key=api_key,
            model=args.model,
            use_batch=args.use_batch,
            debug_dir=args.debug_dir,
            dry_run_only=args.dry_run_only,
            verbose=args.verbose,
            force_marker=args.force_marker,
            extract_monsters=args.extract_monsters,
            monsters_only=args.monsters_only,
            resume_batch=args.resume_batch,
        )
    except RuntimeError as e:
        print(f"error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
