#!/usr/bin/env python3
"""
pdf_to_5etools_toc.py — TOC-driven PDF to 5etools JSON converter.

Uses the PDF's bookmark/TOC structure to drive chunking and construction.
Each top-level bookmark becomes a SectionEntry (created by this script, not
Claude). Claude only fills the entries[] content for each section.

This eliminates:
- Non-section top-level entries (the script creates all sections)
- TOC/data misalignment (structure comes from bookmarks, not Claude)
- Name mismatches (names come from PDF, not Claude)
- "Room Key" wrapper entries (Claude sees the authoritative sub-section list)
- Chapters split mid-content (chunks follow the TOC, not page counts)

Usage:
    python3 pdf_to_5etools_toc.py input.pdf [options]

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
    HomebrewAdventure, OfficialAdventureData, TocEntry, TocHeader,
    Meta, MetaSource, AdventureIndex, AdventureData,
)
from pdf_utils import TocNode, get_toc_tree, parse_toc_tree, _decode_pdf_string

# Import text extraction utilities from the standard converter
from pdf_to_5etools import extract_pages, page_to_annotated_text, _parse_page_range


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_CHAPTER_CHARS = 80_000

# PDF bookmark names that are navigation artifacts, not real sections
_JUNK_BOOKMARKS = re.compile(r"^_GoBack\d*$", re.IGNORECASE)


# System prompt — simpler than the standard converter since we control structure
SYSTEM_PROMPT = textwrap.dedent(f"""\
You are an expert at converting RPG sourcebook text into 5etools JSON entries.

You will receive the raw text of a SINGLE chapter or section from a PDF.
The section name and its known sub-sections (from the PDF table of contents)
are provided. Your job is to convert the text content into a JSON array of
5etools entry objects.

IMPORTANT:
- Return ONLY a valid JSON array (the entries[] content for this section).
- Do NOT wrap your output in a top-level {{"type":"section"}} — the script
  handles section wrappers. Just return the inner entries.
- Sub-sections within this chapter must use {{"type":"entries"}} — never
  {{"type":"section"}}.
- Do NOT add "id" fields — those are assigned later.
- Use the exact sub-section names from the PDF table of contents when they
  are provided.

{_api.COMMON_TAG_RULES}

Entry types:
- Plain paragraph → bare JSON string
- Named sub-section → {{"type":"entries","name":"Title","entries":[...]}}
- Bulleted/numbered list → {{"type":"list","items":["a","b"]}}
- Table → {{"type":"table","colLabels":["A","B"],"rows":[["1","2"]]}}
- Boxed/sidebar → {{"type":"inset","name":"Title","entries":[...]}}
- Read-aloud text → {{"type":"insetReadaloud","entries":["text..."]}}
- Quote → {{"type":"quote","entries":["text..."],"by":"Author"}}
- Horizontal rule → {{"type":"hr"}}
- Image reference → {{"type":"image","href":{{"type":"internal","path":"img.png"}}}}

{_api.COMMON_NESTING_RULES}
""")


# ---------------------------------------------------------------------------
# Chapter text extraction
# ---------------------------------------------------------------------------

def extract_chapter_text(pages: list[dict], start_page: int, end_page: int) -> str:
    """Extract annotated text for a page range (1-based, inclusive)."""
    lines: list[str] = []
    for page in pages:
        pnum = page["page_num"]
        if pnum < start_page or pnum > end_page:
            continue
        annotated = page_to_annotated_text(page)
        if annotated.strip():
            lines.append(f"\n--- Page {pnum} ---\n{annotated}")
    return "\n".join(lines)


def build_chapter_prompt(node: TocNode, text: str) -> str:
    """Build the user message for a single chapter/section API call."""
    parts = [f"=== SECTION: {node.title} (pages {node.start_page}–{node.end_page}) ==="]

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


# ---------------------------------------------------------------------------
# Chunking by TOC
# ---------------------------------------------------------------------------

def _split_by_pages(
    node: TocNode,
    pages: list[dict],
    prompt_builder=None,
) -> list[tuple[TocNode, str]]:
    """Split an oversized leaf node into page-boundary sub-chunks.

    Creates synthetic TocNode children, each covering a range of pages
    sized to stay under MAX_CHAPTER_CHARS.
    """
    if prompt_builder is None:
        prompt_builder = build_chapter_prompt

    # Collect pages in this node's range
    node_pages = [p for p in pages
                  if node.start_page <= p["page_num"] <= node.end_page]
    if not node_pages:
        return []

    chunks: list[tuple[TocNode, str]] = []
    batch: list[dict] = []
    batch_start = node_pages[0]["page_num"]

    for page in node_pages:
        batch.append(page)
        # Check accumulated size
        text = extract_chapter_text(batch, batch[0]["page_num"], page["page_num"])
        test_node = TocNode(level=node.level + 1,
                            title=f"{node.title} (p{batch_start}–{page['page_num']})",
                            start_page=batch_start, end_page=page["page_num"])
        prompt = prompt_builder(test_node, text)

        if len(prompt) > MAX_CHAPTER_CHARS and len(batch) > 1:
            # Emit everything except the last page
            batch.pop()
            end_page = batch[-1]["page_num"]
            sub_node = TocNode(
                level=node.level + 1,
                title=f"{node.title} (p{batch_start}–{end_page})",
                start_page=batch_start, end_page=end_page,
            )
            sub_text = extract_chapter_text(batch, batch_start, end_page)
            chunks.append((sub_node, prompt_builder(sub_node, sub_text)))
            # Start new batch with current page
            batch = [page]
            batch_start = page["page_num"]

    # Emit remaining batch
    if batch:
        end_page = batch[-1]["page_num"]
        sub_node = TocNode(
            level=node.level + 1,
            title=f"{node.title} (p{batch_start}–{end_page})",
            start_page=batch_start, end_page=end_page,
        )
        sub_text = extract_chapter_text(batch, batch_start, end_page)
        chunks.append((sub_node, prompt_builder(sub_node, sub_text)))

    return chunks


def chunk_by_toc(
    toc_roots: list[TocNode],
    pages: list[dict],
    prompt_builder=None,
) -> list[tuple[TocNode, str]]:
    """Produce (TocNode, prompt_text) pairs, one per API call.

    If a chapter exceeds MAX_CHAPTER_CHARS:
    1. Split by TOC children if available
    2. Otherwise split by page boundaries

    ``prompt_builder`` can be overridden by 1e/OCR converters to inject
    their own preprocessing (default: ``build_chapter_prompt``).
    """
    if prompt_builder is None:
        prompt_builder = build_chapter_prompt

    chunks: list[tuple[TocNode, str]] = []

    for node in toc_roots:
        text = extract_chapter_text(pages, node.start_page, node.end_page)
        if not text.strip():
            continue

        prompt = prompt_builder(node, text)

        if len(prompt) <= MAX_CHAPTER_CHARS:
            chunks.append((node, prompt))
        elif node.children:
            # Split by TOC children
            print(f"    [SPLIT] '{node.title}' ({len(prompt):,} chars) — "
                  f"splitting into {len(node.children)} sub-chunks by TOC",
                  flush=True)
            # Recursively chunk children (they may also be oversized)
            chunks.extend(chunk_by_toc(node.children, pages, prompt_builder))
        else:
            # No children — split by page boundaries
            page_chunks = _split_by_pages(node, pages, prompt_builder)
            print(f"    [SPLIT] '{node.title}' ({len(prompt):,} chars) — "
                  f"splitting into {len(page_chunks)} sub-chunks by page",
                  flush=True)
            chunks.extend(page_chunks)

    return chunks


# ---------------------------------------------------------------------------
# Assembly: build the adventure model from Claude results
# ---------------------------------------------------------------------------

def _page_split_sort_key(key: str) -> int:
    """Extract the starting page number from a page-split key for sorting."""
    m = re.search(r'\(p(\d+)', key)
    return int(m.group(1)) if m else 0


def _collect_entries_for(title: str, results: dict[str, list[Any]]) -> list[Any]:
    """Collect all result entries for a given title, including page-split keys."""
    if title in results:
        return list(results[title])
    # Check for page-split keys: "Title (pN–M)"
    page_keys = sorted(
        [k for k in results if k.startswith(title + " (p")],
        key=_page_split_sort_key,
    )
    if page_keys:
        flat: list[Any] = []
        for pk in page_keys:
            flat.extend(results[pk])
        return flat
    return []


def _assemble_sub_chunks(
    node: TocNode,
    results: dict[str, list[Any]],
    ctx: BuildContext,
    path: str,
) -> list:
    """Assemble entries for a node that was sub-chunked (by TOC or pages)."""
    # First check: was this node itself page-split (no children in TOC)?
    if not node.children:
        entries = _collect_entries_for(node.title, results)
        return [parse_entry(e, ctx, f"{path}.entries[{j}]")
                for j, e in enumerate(entries)]

    # Node has TOC children — each child may have direct results or page-split results
    parsed = []
    for child in node.children:
        child_entries = _collect_entries_for(child.title, results)
        if not child_entries:
            continue
        child_parsed = [
            parse_entry(e, ctx, f"{path}.entries[{len(parsed)}].entries[{j}]")
            for j, e in enumerate(child_entries)
        ]
        entry = EntriesEntry(
            name=child.title,
            entries=child_parsed,
            page=child.start_page,
            _ctx=ctx,
            _path=f"{path}.entries[{len(parsed)}]",
        )
        parsed.append(entry)
    return parsed


def assemble_document(
    toc_roots: list[TocNode],
    results: dict[str, list[Any]],
    ctx: BuildContext,
) -> list[SectionEntry]:
    """Build SectionEntry objects from TOC + Claude results.

    ``results`` maps TocNode title to the parsed entries from Claude.

    Three cases per top-level node:
    1. Direct result (title in results) — use as-is
    2. Split by TOC children — each child becomes a nested EntriesEntry
    3. Split by page boundaries — all sub-chunk entries concatenated flat
    """
    sections: list[SectionEntry] = []

    for i, node in enumerate(toc_roots):
        path = f"data[{i}]"

        if node.title in results:
            # Case 1: direct result for this chapter
            raw_entries = results[node.title]
            parsed = [parse_entry(e, ctx, f"{path}.entries[{j}]")
                      for j, e in enumerate(raw_entries)]
        else:
            parsed = _assemble_sub_chunks(node, results, ctx, path)

        section = SectionEntry(
            name=node.title,
            entries=parsed,
            page=node.start_page,
            _ctx=ctx,
            _path=path,
        )
        sections.append(section)

    return sections


def build_toc_from_tree(toc_roots: list[TocNode]) -> list[TocEntry]:
    """Build the contents[] TOC directly from the PDF bookmark tree."""
    toc: list[TocEntry] = []
    for node in toc_roots:
        headers: list[TocHeader] = []
        for child in node.children:
            headers.append(TocHeader(header=child.title, depth=0))
            for grandchild in child.children:
                headers.append(TocHeader(header=grandchild.title, depth=1))
        toc.append(TocEntry(name=node.title, headers=headers))
    return toc


# ---------------------------------------------------------------------------
# Main conversion function
# ---------------------------------------------------------------------------

def convert(
    pdf_path: Path,
    output_type: str,
    short_id: str,
    author: str,
    out_path: Path,
    api_key: str | None,
    chunk_size: int,
    model: str,
    output_mode: str,
    use_batch: bool,
    dry_run_only: bool,
    debug_dir: Path | None,
    verbose: bool,
    page_filter: set[int],
    toc_max_level: int = 99,
    force_toc: bool = False,
) -> None:
    print(f"\n{'='*60}")
    print(f"  PDF → 5etools TOC-driven converter")
    print(f"  Input : {pdf_path}")
    print(f"  Output: {out_path}")
    print(f"  Type  : {output_type}   ID: {short_id}   Mode: {output_mode}")
    print(f"  API   : {'Batch (50% discount)' if use_batch else 'Standard'}")
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        print(f"  Debug : {debug_dir}")
    if page_filter:
        print(f"  Pages : {sorted(page_filter)}")
    print(f"{'='*60}\n")

    # ── 1. Extract pages ────────────────────────────────────────────────────
    print("[1/5] Extracting text from PDF...", flush=True)
    pages = extract_pages(pdf_path)
    print(f"      {len(pages)} pages extracted.")
    if page_filter:
        pages = [p for p in pages if p["page_num"] in page_filter]
        print(f"      Page filter active: {len(pages)} page(s) selected.")

    if not pages:
        sys.exit("No text could be extracted from the PDF.")

    # ── 2. Parse TOC and chunk by chapters ──────────────────────────────────
    print("[2/5] Parsing PDF table of contents...", flush=True)
    toc_roots = get_toc_tree(pdf_path, max_level=toc_max_level)

    # Filter junk bookmarks (_GoBack etc.)
    toc_roots = _filter_junk_bookmarks(toc_roots)

    if not toc_roots:
        if force_toc:
            sys.exit("ERROR: PDF has no bookmarks and --force-toc was specified.")
        print("      PDF has no bookmarks — falling back to page-count chunking.",
              flush=True)
        # Fall back: treat the whole document as one section
        total_pages = max(p["page_num"] for p in pages)
        toc_roots = [TocNode(level=1, title="Adventure",
                             start_page=1, end_page=total_pages)]

    # If page_filter is active, prune TOC nodes outside the range
    if page_filter:
        min_page = min(page_filter)
        max_page = max(page_filter)
        toc_roots = _prune_toc(toc_roots, min_page, max_page)

    # Handle single-root TOC: if there's one root with children, promote children
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

    chunks = chunk_by_toc(toc_roots, pages)
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

            entries = _api.call_claude(
                client, prompt, model, SYSTEM_PROMPT, verbose,
                debug_dir=debug_dir, chunk_id=chunk_id)

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
            convertedBy=["pdf_to_5etools_toc"],
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

    # Assign IDs
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
# TOC filtering and pruning
# ---------------------------------------------------------------------------

def _filter_junk_bookmarks(roots: list[TocNode]) -> list[TocNode]:
    """Remove PDF navigation artifacts (_GoBack, etc.) from the TOC tree."""
    result: list[TocNode] = []
    for node in roots:
        if _JUNK_BOOKMARKS.match(node.title):
            continue
        node.children = _filter_junk_bookmarks(node.children)
        result.append(node)
    return result


def _prune_toc(roots: list[TocNode], min_page: int, max_page: int) -> list[TocNode]:
    """Keep only TOC nodes that overlap with the page range."""
    result: list[TocNode] = []
    for node in roots:
        if node.end_page < min_page or node.start_page > max_page:
            continue
        pruned = TocNode(
            level=node.level,
            title=node.title,
            start_page=max(node.start_page, min_page),
            end_page=min(node.end_page, max_page),
            children=_prune_toc(node.children, min_page, max_page),
        )
        result.append(pruned)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a RPG PDF into 5etools JSON using TOC-driven chunking.",
    )
    _cli.add_common_args(parser, default_chunk=6, default_model=DEFAULT_MODEL)

    parser.add_argument(
        "--force-toc", action="store_true", dest="force_toc",
        help="Abort if the PDF has no bookmarks (default: fall back to single section)",
    )
    parser.add_argument(
        "--toc-max-level", type=int, default=99, metavar="N", dest="toc_max_level",
        help="Deepest bookmark level to consider (default: all levels)",
    )

    args = parser.parse_args()

    pdf_path = args.pdf
    if not pdf_path.exists():
        sys.exit(f"File not found: {pdf_path}")

    short_id = args.short_id or pdf_path.stem[:8].upper().replace(" ", "").replace("-", "").replace("_", "")

    # Page filter
    page_filter: set[int] = set()
    if args.page is not None:
        page_filter = {args.page}
    elif args.pages:
        page_filter = _parse_page_range(args.pages)

    out_path = args.out
    if not out_path:
        out_dir = args.output_dir or pdf_path.parent
        prefix = "adventure" if args.output_type == "adventure" else "book"
        out_path = out_dir / f"{prefix}-{short_id.lower()}.json"

    convert(
        pdf_path=pdf_path,
        output_type=args.output_type,
        short_id=short_id,
        author=args.author,
        out_path=out_path,
        api_key=args.api_key,
        chunk_size=args.chunk_size,
        model=args.model,
        output_mode=args.output_mode,
        use_batch=args.use_batch,
        dry_run_only=args.dry_run_only,
        debug_dir=args.debug_dir,
        verbose=args.verbose,
        page_filter=page_filter,
        toc_max_level=args.toc_max_level,
        force_toc=args.force_toc,
    )


if __name__ == "__main__":
    main()
