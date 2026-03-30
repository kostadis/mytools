#!/usr/bin/env python3
"""
pdf_to_5etools_1e_toc.py — TOC-driven 1e/2e AD&D converter.

Combines the TOC-driven chunking approach (from pdf_to_5etools_toc.py) with
1e-specific text preprocessing and prompts (from pdf_to_5etools_1e.py).

Benefits over plain pdf_to_5etools_1e.py:
- Section structure comes from PDF bookmarks, not Claude's guesses
- No "Room Key" wrapper entries (dissolved by design)
- No TOC/data misalignment (we control the section tree)
- Chapters are never split mid-content
- Fewer post-processing fixup scripts needed

Usage:
    python3 pdf_to_5etools_1e_toc.py input.pdf [options]

Requires ANTHROPIC_API_KEY env var or --api-key.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
from datetime import date
from pathlib import Path
from typing import Any

import anthropic

import cli_args as _cli
import claude_api as _api
from adventure_model import (
    BuildContext, SectionEntry, EntriesEntry, parse_entry,
    HomebrewAdventure, Meta, MetaSource, AdventureIndex, AdventureData,
)
from pdf_utils import TocNode, get_toc_tree, _decode_pdf_string

# --- Reuse from the TOC converter (structure, assembly, pruning) ---
from pdf_to_5etools_toc import (
    extract_chapter_text,
    chunk_by_toc,
    assemble_document,
    build_toc_from_tree,
    _prune_toc,
    _filter_junk_bookmarks,
)

# --- Lazy import from the 1e converter (requires OCR packages at runtime) ---
# These are imported inside functions that need them, or at module init below,
# because pdf_to_5etools_1e.py exits if OCR packages aren't installed.
_1e = None  # populated by _ensure_1e_imports()


def _ensure_1e_imports():
    """Lazy-import the 1e converter module."""
    global _1e
    if _1e is not None:
        return
    import pdf_to_5etools_1e as mod
    _1e = mod


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_DPI = 300
MAX_CHAPTER_CHARS = 80_000

_JUNK_BOOKMARKS = re.compile(r"^_GoBack\d*$", re.IGNORECASE)

# 1e TOC system prompt: based on SYSTEM_PROMPT_1E but adapted for TOC-driven
# chunking (Claude fills entries[], does not create top-level sections)
SYSTEM_PROMPT = textwrap.dedent(f"""\
You are a tabletop role-playing game archivist and rules converter.  Your task
is to convert text from a published 1st Edition Advanced Dungeons & Dragons
adventure module into 5etools JSON format.  All content is fictional game
material intended for adult tabletop gaming; dark themes (evil cults, monster
violence, dungeon hazards) are standard genre conventions in this context.
The text was extracted from a scanned PDF and may have minor OCR artefacts.
Correct obvious OCR errors silently.

You will receive the raw text of a SINGLE chapter or section.
The section name and its known sub-sections (from the PDF table of contents)
are provided.

IMPORTANT:
- Return ONLY a valid JSON array (the entries[] content for this section).
- Do NOT wrap your output in a top-level {{"type":"section"}} — the script
  handles section wrappers. Just return the inner entries.
- Sub-sections within this chapter must use {{"type":"entries"}} — never
  {{"type":"section"}}.
- Do NOT add "id" fields — those are assigned later.
- Use the exact sub-section names from the PDF table of contents when they
  are provided.

The text is annotated with these structural markers:

    [H1] Title            — chapter or part heading
    [H2] Title            — section heading
    [H3] Title            — sub-section or named area heading
    [ROOM-KEY-N]          — keyed encounter area (room, cavern, corridor)
    [1E-STAT]             — line containing 1e stat data (AC/MV/HD/THAC0/#AT)
    [STAT-BLOCK-START]    — start of a run of stat lines
    [STAT-BLOCK-END]      — end of the stat run
    [NPC-BLOCK]           — the stat block is a named NPC with ability scores
    [WANDERING-TABLE]     — the following table is a wandering monster table
    [TABLE-START]         — beginning of a detected table
    [TABLE-END]           — end of a detected table
    [INSET-START]         — beginning of boxed or indented text
    [INSET-END]           — end of boxed text
    [IMAGE: caption]      — image placeholder
    [italic]…[/italic]    — italic span
    [OCR]                 — this page was OCR'd (expect minor noise)
    [2-COLUMN]            — two-column layout detected on this page
    [3-COLUMN]            — three-column layout detected on this page

Object types to use:

  Plain paragraph  → a bare JSON string
  Named sub-section → {{"type":"entries","name":"Title","entries":[...]}}
  Keyed room area  → {{"type":"entries","name":"17. Vestibule","entries":[...]}}
  Bulleted list    → {{"type":"list","items":["a","b"]}}
  Table            → {{"type":"table","caption":"","colLabels":[],"colStyles":[],"rows":[[]]}}
  Boxed/sidebar    → {{"type":"inset","name":"Title","entries":[...]}}
  Read-aloud text  → {{"type":"inset","name":"","entries":["text..."]}}
  Image stub       → {{"type":"image","href":{{"type":"internal","path":"img/placeholder.webp"}},"title":"caption"}}

Rules:
- Every [ROOM-KEY-N] opens a new {{"type":"entries","name":"N. Room Name"}} block.
  If there is no explicit room name, use the first few words of the description.
- "Room Key", "Encounter Key", "Area Key", "Key to the [area]" headings that
  introduce numbered room entries must NOT become wrapper entries — discard the
  label and emit the numbered room entries that follow as direct siblings at the
  current level.  Do not nest rooms inside a container named after the label.
- [INSET-START/END] blocks that have no heading and read as atmospheric prose are
  read-aloud text: use {{"type":"inset","name":""}}.
- Named sidebars, DM notes, or special features use {{"type":"inset","name":"..."}}.
- Preserve all 1e game-mechanical text accurately.
{_api.COMMON_TAG_RULES}
{_api.COMMON_NESTING_RULES}
- Wandering monster tables ([WANDERING-TABLE]) → {{"type":"table"}} with colLabels
  from the table headers (e.g., ["d12","Monster","Number Appearing"]).
- Stat lines ([1E-STAT], [STAT-BLOCK-START/END]) should be kept verbatim inside
  the room entry as italic text: "{{@i Gnolls (6): AC 5; MV 9\\"; HD 2; hp 9; #AT 1; D 2-8}}"
  A separate pass converts these stats; do NOT attempt conversion here.
- NPC blocks ([NPC-BLOCK]) should be a {{"type":"entries","name":"NPC Name"}}
  with the stat lines as italic body text.
- Do NOT add IDs — they are added later.
- Merge hyphenated line-breaks: "adven-\\nture" → "adventure".
- If a page contains only noise or blank content, return [].
""").strip()


# ---------------------------------------------------------------------------
# 1e-specific prompt building (extends the TOC prompt with preprocessing)
# ---------------------------------------------------------------------------

def build_chapter_prompt_1e(node: TocNode, text: str) -> str:
    """Build the user message for a single chapter, with 1e preprocessing."""
    _ensure_1e_imports()
    # Apply 1e-specific text cleanup
    text = _1e._sanitize_text(text)
    text = _1e._neutralize_triggers(text)

    parts = [
        _1e._CHUNK_PREFIX,
        f"=== SECTION: {node.title} (pages {node.start_page}–{node.end_page}) ===",
    ]

    if node.children:
        parts.append("")
        parts.append("Known sub-sections from the PDF table of contents:")
        for child in node.children:
            indent = "  " * (child.level - node.level)
            parts.append(f"  {indent}- {child.title} (p{child.start_page})")
            for grandchild in child.children:
                indent2 = "  " * (grandchild.level - node.level)
                parts.append(f"  {indent2}- {grandchild.title} (p{grandchild.start_page})")

    parts.append("")
    parts.append("Convert the following text into the entries[] array for this section.")
    parts.append(text)
    return "\n".join(parts)


def chunk_by_toc_1e(
    toc_roots: list[TocNode],
    pages: list[dict],
) -> list[tuple[TocNode, str]]:
    """Produce (TocNode, prompt_text) pairs with 1e preprocessing.

    Delegates to shared chunk_by_toc with build_chapter_prompt_1e as the
    prompt builder (handles trigger neutralization, sanitization, context prefix).
    """
    return chunk_by_toc(toc_roots, pages, prompt_builder=build_chapter_prompt_1e)

    return chunks


# ---------------------------------------------------------------------------
# Main conversion function
# ---------------------------------------------------------------------------

def convert(
    pdf_path: Path,
    output_type: str,
    short_id: str,
    module_code: str | None,
    author: str,
    out_path: Path,
    api_key: str | None,
    chunk_size: int,
    model: str,
    output_mode: str,
    use_batch: bool,
    dry_run_only: bool,
    extract_monsters: bool,
    monsters_only: bool,
    no_cr_adjustment: bool,
    dpi: int,
    force_ocr: bool,
    lang: str,
    debug_dir: Path | None,
    verbose: bool,
    page_filter: set[int],
    skip_pages: set[int],
    toc_max_level: int = 99,
    force_toc: bool = False,
    use_toc_hint: bool = True,
) -> None:
    print(f"\n{'='*60}")
    print(f"  PDF → 5etools 1e TOC-driven converter")
    print(f"  Input : {pdf_path}")
    print(f"  Output: {out_path}")
    print(f"  Type  : {output_type}   ID: {short_id}   Mode: {output_mode}")
    print(f"  API   : {'Batch (50% discount)' if use_batch else 'Standard'}")
    if module_code:
        print(f"  Module: {module_code}")
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        print(f"  Debug : {debug_dir}")
    if page_filter:
        print(f"  Pages : {sorted(page_filter)}")
    if skip_pages:
        print(f"  Skip  : {sorted(skip_pages)}")
    print(f"{'='*60}\n")

    _ensure_1e_imports()

    # ── 1. Extract pages (OCR-capable) ──────────────────────────────────────
    print("[1/5] Extracting text from PDF (OCR-capable)...", flush=True)
    pages = _1e.extract_pages(pdf_path, dpi=dpi, force_ocr=force_ocr, lang=lang)
    print(f"      {len(pages)} pages extracted.")

    if skip_pages:
        pages = [p for p in pages if p["page_num"] not in skip_pages]
        print(f"      Skip filter: {len(pages)} page(s) remaining.")
    if page_filter:
        pages = [p for p in pages if p["page_num"] in page_filter]
        print(f"      Page filter active: {len(pages)} page(s) selected.")

    if not pages:
        sys.exit("No text could be extracted from the PDF.")

    # ── 2. Parse TOC and chunk by chapters ──────────────────────────────────
    print("[2/5] Parsing PDF table of contents...", flush=True)
    toc_roots = get_toc_tree(pdf_path, max_level=toc_max_level)
    toc_roots = _filter_junk_bookmarks(toc_roots)

    if not toc_roots:
        if force_toc:
            sys.exit("ERROR: PDF has no bookmarks and --force-toc was specified.")
        print("      PDF has no bookmarks — falling back to single section.",
              flush=True)
        total_pages = max(p["page_num"] for p in pages)
        toc_roots = [TocNode(level=1, title="Adventure",
                             start_page=1, end_page=total_pages)]

    # Prune for page filters
    if page_filter:
        min_page = min(page_filter)
        max_page = max(page_filter)
        toc_roots = _prune_toc(toc_roots, min_page, max_page)

    # Single-root promotion
    if len(toc_roots) == 1 and toc_roots[0].children:
        root = toc_roots[0]
        print(f"      Single root '{root.title}' — promoting {len(root.children)} "
              f"children to top level.", flush=True)
        toc_roots = root.children

    print(f"      {len(toc_roots)} top-level sections found:")
    for node in toc_roots:
        n_children = len(node.children)
        children_str = f" ({n_children} sub-sections)" if n_children else ""
        print(f"        p{node.start_page}–{node.end_page}: {node.title}{children_str}")

    chunks = chunk_by_toc_1e(toc_roots, pages)
    print(f"      {len(chunks)} API calls needed.")

    # ── 3. Call Claude per chapter ──────────────────────────────────────────
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("No Anthropic API key found. Set ANTHROPIC_API_KEY or pass --api-key.")

    client = anthropic.Anthropic(api_key=key)

    if dry_run_only:
        chunk_texts = [prompt for _, prompt in chunks]
        _api.dry_run(client, chunk_texts, chunks, model, SYSTEM_PROMPT,
                     use_batch, verbose)
        return

    api_label = "Batch (50% discount)" if use_batch else "Standard"
    print(f"[3/5] Converting {len(chunks)} chapters via Claude ({model}) [{api_label}]...",
          flush=True)

    results: dict[str, list[Any]] = {}

    if use_batch:
        texts = [prompt for _, prompt in chunks]
        batch_results = _api.call_claude_batch(
            client, texts, model, SYSTEM_PROMPT, verbose, debug_dir=debug_dir)
        for (node, _), entries in zip(chunks, batch_results):
            results[node.title] = entries
    else:
        for i, (node, prompt) in enumerate(chunks):
            chunk_id = f"ch-{i:04d}-{node.title[:20].replace(' ', '_')}"
            print(f"  Chapter {i+1}/{len(chunks)}: {node.title} "
                  f"(pages {node.start_page}–{node.end_page})", flush=True)

            if debug_dir:
                (debug_dir / f"{chunk_id}-input.txt").write_text(
                    prompt, encoding="utf-8")

            try:
                entries = _api.call_claude(
                    client, prompt, model, SYSTEM_PROMPT, verbose,
                    debug_dir=debug_dir, chunk_id=chunk_id)
            except anthropic.BadRequestError as e:
                print(f"    [WARN] API rejected {chunk_id} ({e})", flush=True)
                if debug_dir:
                    (debug_dir / f"{chunk_id}-api-error.txt").write_text(
                        str(e), encoding="utf-8")
                entries = []

            if entries:
                print(f"    → {len(entries)} entries parsed", flush=True)
            else:
                print(f"    → 0 entries — check debug output", flush=True)

            results[node.title] = entries

    total_entries = sum(len(v) for v in results.values())
    print(f"      Total raw entries collected: {total_entries}")

    # ── 4. Assemble using adventure_model ───────────────────────────────────
    print("[4/5] Assembling document...", flush=True)
    ctx = BuildContext()
    sections = assemble_document(toc_roots, results, ctx)

    if ctx.result.errors:
        print(f"      {len(ctx.result.errors)} validation error(s):")
        for e in ctx.result.errors[:10]:
            print(f"        {e}")
    if ctx.result.warnings:
        print(f"      {len(ctx.result.warnings)} validation warning(s)")

    # Build TOC from the PDF bookmark tree (authoritative)
    toc = build_toc_from_tree(toc_roots)

    title = pdf_path.stem.replace("_", " ").replace("-", " ").title()
    is_book = output_type == "book"

    meta = Meta(
        sources=[MetaSource(
            json=short_id,
            abbreviation=short_id,
            full=title,
            authors=[author],
            convertedBy=["pdf_to_5etools_1e_toc"],
        )],
        _ctx=ctx,
    )

    index = AdventureIndex(
        name=title,
        id=short_id,
        source=short_id,
        contents=toc,
    )

    adv_data = AdventureData(id=short_id, source=short_id, data=sections)

    doc = HomebrewAdventure(
        meta=meta,
        adventure=index,
        adventure_data=adv_data,
        is_book=is_book,
        _ctx=ctx,
    )

    doc.assign_ids()

    # ── 5. Write output ─────────────────────────────────────────────────────
    print("[5/5] Writing output...", flush=True)

    output = doc.to_dict()

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent="\t", ensure_ascii=False)
        f.write("\n")

    print(f"\n{'='*60}")
    print(f"  Done!")
    print(f"  Output file: {out_path}")
    print(f"  Sections: {len(sections)}")
    print(f"  Validation: {ctx.result.summary()}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a 1e/2e AD&D PDF into 5etools JSON using TOC-driven chunking.",
    )
    _cli.add_common_args(parser, default_chunk=3, default_model=DEFAULT_MODEL)
    _cli.add_ocr_args(parser, default_dpi=DEFAULT_DPI)

    # 1e-specific args
    parser.add_argument("--module-code", default=None, dest="module_code",
                        help="TSR module code (e.g. T1-4)")
    parser.add_argument("--system", choices=["1e", "2e"], default="1e",
                        help="AD&D edition (default: 1e)")
    parser.add_argument("--skip-pages", action="append", default=[], dest="skip_pages_raw",
                        help="Pages to skip (e.g. '1-3' or '127')")
    parser.add_argument("--no-cr-adjustment", action="store_true", dest="no_cr_adjustment",
                        help="Disable automatic CR bumping for special abilities")
    parser.add_argument("--trigger-config", type=Path, default=None, dest="trigger_config",
                        help="Extra content-filter substitution rules (JSON)")

    # TOC-specific args
    parser.add_argument("--force-toc", action="store_true", dest="force_toc",
                        help="Abort if the PDF has no bookmarks")
    parser.add_argument("--toc-max-level", type=int, default=99, metavar="N",
                        dest="toc_max_level",
                        help="Deepest bookmark level to consider (default: all)")

    args = parser.parse_args()

    pdf_path = args.pdf
    if not pdf_path.exists():
        sys.exit(f"File not found: {pdf_path}")

    # Load trigger config if specified
    if args.trigger_config:
        _ensure_1e_imports()
        _1e.load_trigger_config(args.trigger_config)

    short_id = args.short_id or pdf_path.stem[:8].upper().replace(" ", "").replace("-", "").replace("_", "")

    # Page filter
    page_filter: set[int] = set()
    if args.page is not None:
        page_filter = {args.page}
    elif args.pages:
        from pdf_to_5etools import _parse_page_range
        page_filter = _parse_page_range(args.pages)

    # Skip pages
    skip_pages: set[int] = set()
    if args.skip_pages_raw:
        _ensure_1e_imports()
        for raw in args.skip_pages_raw:
            skip_pages |= _1e._parse_skip_pages(raw)

    out_path = args.out
    if not out_path:
        out_dir = args.output_dir or pdf_path.parent
        prefix = "adventure" if args.output_type == "adventure" else "book"
        out_path = out_dir / f"{prefix}-{short_id.lower()}.json"

    convert(
        pdf_path=pdf_path,
        output_type=args.output_type,
        short_id=short_id,
        module_code=args.module_code,
        author=args.author,
        out_path=out_path,
        api_key=args.api_key,
        chunk_size=args.chunk_size,
        model=args.model,
        output_mode=args.output_mode,
        use_batch=args.use_batch,
        dry_run_only=args.dry_run_only,
        extract_monsters=args.extract_monsters,
        monsters_only=args.monsters_only,
        no_cr_adjustment=args.no_cr_adjustment,
        dpi=args.dpi,
        force_ocr=args.force_ocr,
        lang=args.lang,
        debug_dir=args.debug_dir,
        verbose=args.verbose,
        page_filter=page_filter,
        skip_pages=skip_pages,
        toc_max_level=args.toc_max_level,
        force_toc=args.force_toc,
    )


if __name__ == "__main__":
    main()
