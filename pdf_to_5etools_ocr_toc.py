#!/usr/bin/env python3
"""
pdf_to_5etools_ocr_toc.py — TOC-driven OCR converter for 5etools JSON.

Combines the TOC-driven chunking approach (from pdf_to_5etools_toc.py) with
the OCR text extraction pipeline (from pdf_to_5etools_ocr.py).

Use this for PDFs with selectable text that also has image-heavy pages
requiring OCR fallback (e.g., modern PDFs with scanned art pages).

For purely scanned 1e/2e modules, use pdf_to_5etools_1e_toc.py instead.

Usage:
    python3 pdf_to_5etools_ocr_toc.py input.pdf [options]

Requires ANTHROPIC_API_KEY env var or --api-key.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Any

import anthropic

import cli_args as _cli
import claude_api as _api
from adventure_model import (
    BuildContext, SectionEntry, EntriesEntry, parse_entry,
    HomebrewAdventure, Meta, MetaSource, AdventureIndex, AdventureData,
)
from pdf_utils import TocNode, get_toc_tree

# --- Reuse from the TOC converter (structure, assembly, pruning) ---
from pdf_to_5etools_toc import (
    chunk_by_toc,
    assemble_document,
    build_toc_from_tree,
    build_chapter_prompt,
    _prune_toc,
    _filter_junk_bookmarks,
)

# --- Lazy import of OCR converter (requires pytesseract/PIL/pdf2image) ---
_ocr = None


def _ensure_ocr_imports():
    global _ocr
    if _ocr is not None:
        return
    import pdf_to_5etools_ocr as mod
    _ocr = mod


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_DPI = 300
MAX_CHAPTER_CHARS = 80_000

# System prompt — OCR-aware version of the TOC prompt
SYSTEM_PROMPT = textwrap.dedent(f"""\
You are an expert at converting RPG sourcebook text into 5etools JSON entries.

You will receive the raw text of a SINGLE chapter or section from a PDF.
Some pages were extracted digitally, others via OCR (marked with [OCR]).
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
- Correct obvious OCR errors silently.
- Merge hyphenated line-breaks: "adven-\\nture" → "adventure".

The text uses structural annotations:
    [H1]/[H2]/[H3]       — heading levels
    [TABLE-START/END]     — detected table boundaries
    [INSET-START/END]     — boxed or indented text
    [IMAGE: caption]      — image placeholder
    [italic]…[/italic]    — italic span
    [OCR]                 — page was OCR'd (may have minor noise)
    [2-COLUMN]            — two-column layout detected

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
""").strip()


# ---------------------------------------------------------------------------
# OCR-aware page extraction → same format as standard converter pages
# ---------------------------------------------------------------------------

def extract_pages_ocr(
    pdf_path: Path,
    dpi: int = 300,
    force_ocr: bool = False,
    lang: str = "eng",
    verbose: bool = False,
    page_filter: set[int] | None = None,
) -> list[dict]:
    """Extract pages using digital text + OCR fallback.

    Returns list of dicts matching the standard converter format:
    [{"page_num": int, "blocks": [{"text": str, "is_heading": bool, ...}]}]

    Pages that were OCR'd are returned with a single block containing the
    full annotated text (including [OCR] flag).
    """
    _ensure_ocr_imports()
    import fitz
    from PIL import ImageEnhance, ImageFilter
    from pdf2image import convert_from_path

    doc = fitz.open(str(pdf_path))
    total_pages = doc.page_count
    body_size = _ocr.compute_body_size(doc)

    if verbose:
        print(f"      Estimated body font size: {body_size:.1f}pt")

    pages: list[dict] = []
    needs_ocr: list[int] = []
    digital_results: dict[int, str | None] = {}

    # First pass: try digital extraction
    for page_idx in range(total_pages):
        pnum = page_idx + 1
        if page_filter and pnum not in page_filter:
            digital_results[page_idx] = ""
            continue
        if force_ocr:
            needs_ocr.append(page_idx)
            digital_results[page_idx] = None
        else:
            text = _ocr.extract_digital_page(doc[page_idx], body_size)
            digital_results[page_idx] = text
            if text is None:
                needs_ocr.append(page_idx)

    doc.close()

    # OCR pass
    ocr_images: dict[int, Any] = {}
    if needs_ocr:
        if verbose:
            print(f"      Rendering {len(needs_ocr)} pages at {dpi} DPI for OCR...",
                  flush=True)
        for idx in needs_ocr:
            imgs = convert_from_path(
                str(pdf_path), dpi=dpi,
                first_page=idx + 1, last_page=idx + 1,
            )
            if imgs:
                ocr_images[idx] = imgs[0]

    # Build page list
    digital_count = 0
    ocr_count = 0
    for page_idx in range(total_pages):
        pnum = page_idx + 1
        if page_filter and pnum not in page_filter:
            continue

        if digital_results[page_idx] is not None and digital_results[page_idx] != "":
            # Digital extraction succeeded
            text = digital_results[page_idx]
            # Wrap as a single block for compatibility with page_to_annotated_text
            pages.append({
                "page_num": pnum,
                "blocks": [{"text": text, "is_heading": False,
                            "heading_level": 0, "bold": False, "italic": False}],
            })
            digital_count += 1
        elif page_idx in ocr_images:
            result = _ocr.ocr_page_image(ocr_images[page_idx], lang=lang)
            if result["text"].strip():
                ocr_flag = "[OCR]" + (
                    " [2-COLUMN]" if result["columns"] == 2 else "")
                text = f"{ocr_flag}\n{result['text']}"
                pages.append({
                    "page_num": pnum,
                    "blocks": [{"text": text, "is_heading": False,
                                "heading_level": 0, "bold": False, "italic": False}],
                })
            else:
                pages.append({"page_num": pnum, "blocks": []})
            ocr_count += 1
        elif digital_results.get(page_idx) == "":
            # Skipped page
            continue
        else:
            pages.append({"page_num": pnum, "blocks": []})

    print(f"      Digital: {digital_count}  |  OCR: {ocr_count}  |  "
          f"Total: {len(pages)}", flush=True)

    return pages


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
    dpi: int,
    force_ocr: bool,
    lang: str,
    debug_dir: Path | None,
    verbose: bool,
    page_filter: set[int],
    toc_max_level: int = 99,
    force_toc: bool = False,
) -> None:
    print(f"\n{'='*60}")
    print(f"  PDF → 5etools OCR TOC-driven converter")
    print(f"  Input : {pdf_path}")
    print(f"  Output: {out_path}")
    print(f"  Type  : {output_type}   ID: {short_id}   Mode: {output_mode}")
    print(f"  API   : {'Batch (50% discount)' if use_batch else 'Standard'}")
    print(f"  DPI   : {dpi}  Force OCR: {force_ocr}  Lang: {lang}")
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        print(f"  Debug : {debug_dir}")
    if page_filter:
        print(f"  Pages : {sorted(page_filter)}")
    print(f"{'='*60}\n")

    # ── 1. Extract pages (digital + OCR fallback) ───────────────────────────
    print("[1/5] Extracting text from PDF (OCR-capable)...", flush=True)
    pages = extract_pages_ocr(pdf_path, dpi=dpi, force_ocr=force_ocr,
                               lang=lang, verbose=verbose,
                               page_filter=page_filter or None)

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

    toc = build_toc_from_tree(toc_roots)

    title = pdf_path.stem.replace("_", " ").replace("-", " ").title()
    is_book = output_type == "book"

    meta = Meta(
        sources=[MetaSource(
            json=short_id, abbreviation=short_id, full=title,
            authors=[author], convertedBy=["pdf_to_5etools_ocr_toc"],
        )],
        _ctx=ctx,
    )
    index = AdventureIndex(name=title, id=short_id, source=short_id, contents=toc)
    adv_data = AdventureData(id=short_id, source=short_id, data=sections)

    doc = HomebrewAdventure(
        meta=meta, adventure=index, adventure_data=adv_data,
        is_book=is_book, _ctx=ctx,
    )
    doc.assign_ids()

    # ── 5. Write output ─────────────────────────────────────────────────────
    print("[5/5] Writing output...", flush=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, indent="\t", ensure_ascii=False)
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
        description="Convert a PDF into 5etools JSON using TOC-driven chunking with OCR fallback.",
    )
    _cli.add_common_args(parser, default_chunk=4, default_model=DEFAULT_MODEL)
    _cli.add_ocr_args(parser, default_dpi=DEFAULT_DPI)

    parser.add_argument("--force-toc", action="store_true", dest="force_toc",
                        help="Abort if the PDF has no bookmarks")
    parser.add_argument("--toc-max-level", type=int, default=99, metavar="N",
                        dest="toc_max_level",
                        help="Deepest bookmark level to consider (default: all)")

    args = parser.parse_args()

    pdf_path = args.pdf
    if not pdf_path.exists():
        sys.exit(f"File not found: {pdf_path}")

    short_id = args.short_id or pdf_path.stem[:8].upper().replace(" ", "").replace("-", "").replace("_", "")

    page_filter: set[int] = set()
    if args.page is not None:
        page_filter = {args.page}
    elif args.pages:
        from pdf_to_5etools import _parse_page_range
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
        dpi=args.dpi,
        force_ocr=args.force_ocr,
        lang=args.lang,
        debug_dir=args.debug_dir,
        verbose=args.verbose,
        page_filter=page_filter,
        toc_max_level=args.toc_max_level,
        force_toc=args.force_toc,
    )


if __name__ == "__main__":
    main()
