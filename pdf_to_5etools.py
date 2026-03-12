#!/usr/bin/env python3
"""
pdf_to_5etools.py
=================
Converts a RPG sourcebook or adventure PDF into the 5etools adventure/book JSON
format, ready to be loaded as homebrew in a local 5etools instance.

Dependencies
------------
    pip install pymupdf anthropic

Usage
-----
    python3 pdf_to_5etools.py <input.pdf> [options]

Options
-------
    --type adventure|book     Output format (default: adventure)
    --id   SHORT_ID           Short identifier, e.g. "MYMOD" (default: derived from filename)
    --author "Author Name"    Author string (default: "Unknown")
    --out  output.json        Output filename (default: <stem>_5etools.json)
    --api-key KEY             Anthropic API key (or set ANTHROPIC_API_KEY env var)
    --pages-per-chunk N       Pages to send to Claude at once (default: 6)
    --model MODEL             Claude model (default: claude-sonnet-4-20250514)
    --verbose                 Print progress details

How it works
------------
1.  PyMuPDF extracts text from every page, preserving font size and bold/italic
    metadata so the converter can detect headings vs body text without Claude.

2.  A lightweight heuristic pass identifies heading levels by analysing the
    distribution of font sizes across the document.

3.  Pages are grouped into chunks and sent to the Anthropic API.  Claude is
    given a structured prompt that asks it to return only valid JSON matching
    the 5etools entries schema (section / entries / table / list / etc.).

4.  The chunks are stitched together, a table-of-contents is synthesised from
    the heading structure, and the final adventure-index object and
    adventure-data file are written to disk.

5etools format cheat-sheet (adventure)
---------------------------------------
adventures.json entry:
{
    "name": "Title",
    "id":   "SHORT",         # uppercase, unique across your homebrew
    "source": "SHORT",       # same as id
    "group": "homebrew",
    "published": "YYYY-MM-DD",
    "author": "Name",
    "contents": [            # mirrors the TOC; used for sidebar nav
        { "name": "Chapter 1", "headers": ["Section A", "Section B"] },
        ...
    ]
}

adventure-SHORT.json:
{
    "data": [                # top-level array of section objects
        {
            "type": "section",
            "name": "Chapter 1",
            "id": "000",     # 3-digit string, unique within file
            "entries": [
                "Plain paragraph string.",
                {
                    "type": "entries",
                    "name": "Sub-section",
                    "id": "001",
                    "entries": [ ... ]
                },
                {
                    "type": "table",
                    "caption": "Table Title",
                    "colLabels": ["Col1", "Col2"],
                    "colStyles": ["text-center", "text"],
                    "rows": [["a", "b"], ["c", "d"]]
                },
                {
                    "type": "list",
                    "items": ["Item one", "Item two"]
                },
                {
                    "type": "inset",         # sidebar / boxed text
                    "name": "Inset Title",
                    "entries": ["..."]
                },
                {
                    "type": "image",
                    "href": { "type": "internal", "path": "img/..." },
                    "title": "Caption"
                }
            ]
        }
    ]
}

Inline tags supported by 5etools renderer:
    {@b text}          bold
    {@i text}          italic
    {@creature Name}   link to bestiary
    {@spell Name}      link to spell
    {@item Name}       link to item
    {@dc N}            difficulty class
    {@dice NdN+N}      dice roll
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

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("PyMuPDF is required.  Install with:  pip install pymupdf")

try:
    import anthropic
except ImportError:
    sys.exit("anthropic is required.  Install with:  pip install anthropic")



def normalise_path(raw: str) -> Path:
    r"""
    Accept any of these path formats and return a usable Path:
      Windows absolute:   G:\My Drive\foo.pdf   or   G:/My Drive/foo.pdf
      WSL mount:          /mnt/g/My Drive/foo.pdf
      Linux/relative:     ~/foo.pdf  or  ./foo.pdf
    """
    import re as _re
    s = raw.strip().strip('"\' ')      # strip surrounding quotes & whitespace
    m = _re.match(r'^([A-Za-z]):[/\\](.*)', s)
    if m:
        drive = m.group(1).lower()
        rest  = m.group(2).replace('\\', '/').replace('\\', '/')
        s = f'/mnt/{drive}/{rest}'
    return Path(s).expanduser().resolve()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL  = "claude-haiku-4-5-20251001"
DEFAULT_CHUNK  = 6   # pages per API call
MAX_CHUNK_CHARS = 12_000  # safety cap on chars sent per call

SYSTEM_PROMPT = textwrap.dedent("""
You are an expert at converting RPG sourcebook text into the 5etools adventure
JSON format.  You will receive the raw text of several consecutive pages from a
PDF, annotated with heading level hints (H1/H2/H3).

Return ONLY a valid JSON array of 5etools entry objects.  Do not include any
explanation, markdown fences, or extra text — only the raw JSON array.

The array should contain the entries that appear in those pages.  Use these
object types:

  Plain paragraph → a bare JSON string
  Named section   → {"type":"entries","name":"Title","entries":[...]}
  Top section     → {"type":"section","name":"Title","entries":[...]}
  Bulleted list   → {"type":"list","items":["a","b"]}
  Table           → {"type":"table","caption":"","colLabels":[],"colStyles":[],"rows":[[]]}
  Boxed/sidebar   → {"type":"inset","name":"Title","entries":[...]}
  Read-aloud text → {"type":"inset","name":"","entries":["text..."]}

Rules:
- Preserve all flavour text and game rules accurately.
- Use {@b text} for bold, {@i text} for italic.
- Use {@creature Name} when a monster name appears.
- Use {@spell Name} for spell names, {@item Name} for magic item names.
- Use {@dice NdN} for dice expressions.
- Nest sub-sections inside their parent section's entries array.
- Do NOT add IDs — those are added later.
- Tables must have colLabels and rows even if only one column.
- If a page contains only an image description or blank content, return [].
""").strip()

MONSTER_SYSTEM_PROMPT = textwrap.dedent("""
You are an expert at converting D&D 5e monster stat blocks from PDF text into
the 5etools bestiary JSON format.

Examine the text carefully. Find ONLY stat blocks — sections with AC, HP, ability
scores (STR/DEX/CON/INT/WIS/CHA), and Actions. Ignore flavour text, encounter
tables, and narrative descriptions of monsters.

Return ONLY a valid JSON array of monster objects. Return [] if no stat blocks
are present. No markdown fences, no explanation — only the raw JSON array.

Each monster object must include these fields (omit optional ones if not present):

REQUIRED:
  name        string   — creature name
  source      string   — will be filled in by the script, use "HOMEBREW"
  size        array    — ["T","S","M","L","H","G"] (Tiny/Small/Medium/Large/Huge/Gargantuan)
  type        string or {"type":"humanoid","tags":["human"]}
  alignment   array    — use abbreviations: ["L","G"] / ["N","E"] / ["U"] for unaligned etc.
  ac          array    — [15] or [{"ac":15,"from":["chain mail"]}]
  hp          object   — {"average":22,"formula":"3d8+9"}
  speed       object   — {"walk":30} or {"walk":30,"fly":60,"swim":30}
  str,dex,con,int,wis,cha  integers
  passive     integer  — passive Perception
  cr          string   — "1/4","1/2","1","2" etc.

OPTIONAL (include if present in the stat block):
  save        object   — {"str":"+4","con":"+6"}
  skill       object   — {"perception":"+5","stealth":"+4"}
  senses      array    — ["darkvision 60 ft.","tremorsense 30 ft."]
  languages   array    — ["Common","Elvish"] or ["—"] if none
  immune      array    — damage types: ["fire","poison"]
  resist      array    — damage types
  vulnerable  array    — damage types
  conditionImmune array — ["charmed","frightened"]
  trait       array    — [{"name":"Trait Name","entries":["Description."]}]
  action      array    — [{"name":"Multiattack","entries":["The creature makes two attacks."]}]
               For attacks use: "{@atk mw} {@hit 5} to hit, reach 5 ft., one target. {@h}{@damage 2d6+3} slashing damage."
  bonus       array    — bonus actions, same format as action
  reaction    array    — reactions, same format as action
  legendary   array    — legendary actions
  spellcasting array   — spellcasting trait (complex, see below)
  isNamedCreature bool — true if this is a unique NPC with a proper name
  isNpc       bool     — true for NPCs

Spellcasting format:
{
  "name": "Spellcasting",
  "type": "spellcasting",
  "headerEntries": ["The mage is a 5th-level spellcaster...spell save {@dc 13}; {@hit 5} to hit..."],
  "spells": {
    "0": {"spells": ["mage hand","prestidigitation"]},
    "1": {"slots": 4, "spells": ["magic missile","shield"]},
    "2": {"slots": 3, "spells": ["misty step"]}
  },
  "footerEntries": []
}

Alignment abbreviations: L=Lawful, N=Neutral, C=Chaotic, G=Good, E=Evil, U=Unaligned, A=Any
""").strip()


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def extract_pages(pdf_path: Path) -> list[dict]:
    """Return a list of page dicts with keys: page_num, blocks.
    Each block: {text, size, bold, italic, is_heading, heading_level}
    """
    doc = fitz.open(str(pdf_path))
    pages: list[dict] = []

    # First pass: collect all font sizes to establish heading thresholds
    all_sizes: list[float] = []
    for page in doc:
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        for blk in blocks:
            if blk.get("type") != 0:
                continue
            for line in blk.get("lines", []):
                for span in line.get("spans", []):
                    s = span.get("size", 0)
                    if s > 0:
                        all_sizes.append(s)

    if not all_sizes:
        doc.close()
        return []

    all_sizes.sort()
    body_size = _median(all_sizes)
    # Heading thresholds: H1 > body*1.4, H2 > body*1.2, H3 > body*1.05
    h1_thresh = body_size * 1.40
    h2_thresh = body_size * 1.20
    h3_thresh = body_size * 1.05

    # Second pass: build structured page list
    for page_idx, page in enumerate(doc):
        raw_blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        structured: list[dict] = []
        for blk in raw_blocks:
            if blk.get("type") != 0:  # skip images
                continue
            for line in blk.get("lines", []):
                text_parts = []
                max_size  = 0.0
                is_bold   = False
                is_italic = False
                for span in line.get("spans", []):
                    t = span.get("text", "").strip()
                    if not t:
                        continue
                    text_parts.append(t)
                    sz = span.get("size", 0)
                    if sz > max_size:
                        max_size = sz
                    flags = span.get("flags", 0)
                    if flags & 2**4:  # bold flag
                        is_bold = True
                    if flags & 2**1:  # italic flag
                        is_italic = True

                text = " ".join(text_parts).strip()
                if not text:
                    continue

                heading_level = 0
                is_heading = False
                if max_size >= h1_thresh and (is_bold or len(text) < 80):
                    heading_level = 1
                    is_heading = True
                elif max_size >= h2_thresh and (is_bold or len(text) < 80):
                    heading_level = 2
                    is_heading = True
                elif max_size >= h3_thresh and is_bold and len(text) < 80:
                    heading_level = 3
                    is_heading = True

                structured.append({
                    "text": text,
                    "size": max_size,
                    "bold": is_bold,
                    "italic": is_italic,
                    "is_heading": is_heading,
                    "heading_level": heading_level,
                })

        pages.append({"page_num": page_idx + 1, "blocks": structured})

    doc.close()
    return pages


def _median(values: list[float]) -> float:
    n = len(values)
    if n == 0:
        return 12.0
    mid = n // 2
    return values[mid] if n % 2 else (values[mid - 1] + values[mid]) / 2


# ---------------------------------------------------------------------------
# Page → annotated text string
# ---------------------------------------------------------------------------

def page_to_annotated_text(page: dict) -> str:
    """Convert a page's blocks into a readable string with heading hints."""
    lines: list[str] = []
    for blk in page["blocks"]:
        text = blk["text"]
        if blk["is_heading"]:
            lvl = blk["heading_level"]
            prefix = {1: "[H1]", 2: "[H2]", 3: "[H3]"}.get(lvl, "[H3]")
            lines.append(f"{prefix} {text}")
        else:
            if blk["italic"] and not blk["bold"]:
                lines.append(f"[italic]{text}[/italic]")
            else:
                lines.append(text)
    return "\n".join(lines)


def chunk_pages(pages: list[dict], chunk_size: int) -> list[list[dict]]:
    """Split pages into chunks of at most chunk_size pages."""
    return [pages[i:i + chunk_size] for i in range(0, len(pages), chunk_size)]


# ---------------------------------------------------------------------------
# Claude API call
# ---------------------------------------------------------------------------

def _parse_claude_response(raw: str, verbose: bool,
                            debug_dir: Path | None = None,
                            chunk_id: str = "") -> list[Any]:
    """Parse a raw Claude text response into a JSON list."""
    raw = raw.strip()
    # Save raw response before any stripping
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / f"{chunk_id}-response.txt").write_text(raw, encoding="utf-8")

    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        result = json.loads(raw)
        if not isinstance(result, list):
            result = [result]
        if debug_dir:
            (debug_dir / f"{chunk_id}-parsed.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        return result
    except json.JSONDecodeError as e:
        print(f"    [WARN] JSON parse error in {chunk_id}: {e}", flush=True)
        print(f"    Raw response (first 400 chars): {raw[:400]}", flush=True)
        if debug_dir:
            (debug_dir / f"{chunk_id}-parse-error.txt").write_text(
                f"Error: {e}\n\n{raw}", encoding="utf-8"
            )
        if verbose:
            print(f"    Full raw response saved to {debug_dir}/{chunk_id}-response.txt")
        return []


def call_claude(client: anthropic.Anthropic, chunk_text: str,
                model: str, verbose: bool,
                debug_dir: Path | None = None,
                chunk_id: str = "chunk-0000") -> list[Any]:
    """Send a single chunk to Claude and return parsed JSON array (standard API)."""
    if verbose:
        print(f"    Sending {len(chunk_text):,} chars to Claude...", flush=True)
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / f"{chunk_id}-input.txt").write_text(chunk_text, encoding="utf-8")

    message = client.messages.create(
        model=model,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": chunk_text}],
    )
    result = _parse_claude_response(message.content[0].text, verbose,
                                    debug_dir=debug_dir, chunk_id=chunk_id)

    # If parse failed AND the response looks truncated, retry with half the input
    if not result and message.stop_reason == 'max_tokens':
        print(f"    [RETRY] Hit max_tokens — splitting chunk and retrying...", flush=True)
        half = len(chunk_text) // 2
        split_point = chunk_text.rfind('\n--- Page', 0, half + 1)
        if split_point == -1:
            split_point = half
        for part_idx, part in enumerate([chunk_text[:split_point], chunk_text[split_point:]]):
            if not part.strip():
                continue
            sub_id = f"{chunk_id}-part{part_idx}"
            print(f"      Retrying {sub_id} ({len(part):,} chars)...", flush=True)
            result.extend(call_claude(client, part, model, verbose,
                                      debug_dir=debug_dir, chunk_id=sub_id))

    return result


def call_claude_batch(client: anthropic.Anthropic, chunks: list[str],
                      model: str, verbose: bool,
                      debug_dir: Path | None = None) -> list[list[Any]]:
    """
    Submit all chunks as a single Batch API request (50 % cheaper, async).
    Polls until complete, then returns results in chunk order.
    """
    import time as _time

    print(f"  Submitting {len(chunks)} requests to Batch API...", flush=True)

    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        for i, text in enumerate(chunks):
            (debug_dir / f"chunk-{i:04d}-input.txt").write_text(text, encoding="utf-8")
        print(f"  [DEBUG] Saved {len(chunks)} chunk inputs to {debug_dir}/", flush=True)

    requests = [
        {
            "custom_id": f"chunk-{i:04d}",
            "params": {
                "model": model,
                "max_tokens": 8192,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": text}],
            },
        }
        for i, text in enumerate(chunks)
    ]

    batch = client.messages.batches.create(requests=requests)
    batch_id = batch.id
    print(f"  Batch ID: {batch_id}", flush=True)
    print("  Waiting for batch to complete (polls every 15 s)...", flush=True)

    # Poll until processing_status == "ended"
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        status = batch.processing_status
        counts = batch.request_counts
        print(
            f"    status={status}  "
            f"processing={counts.processing}  "
            f"succeeded={counts.succeeded}  "
            f"errored={counts.errored}",
            flush=True,
        )
        if status == "ended":
            break
        _time.sleep(15)

    # Collect results in order
    results_map: dict[str, list[Any]] = {}
    for result in client.messages.batches.results(batch_id):
        cid = result.custom_id
        if result.result.type == "succeeded":
            msg = result.result.message
            if msg.stop_reason == 'max_tokens':
                print(f"    [WARN] {cid} hit max_tokens — response may be truncated. "
                      f"Try --pages-per-chunk with a smaller value.", flush=True)
            raw = msg.content[0].text
            results_map[cid] = _parse_claude_response(
                raw, verbose, debug_dir=debug_dir, chunk_id=cid
            )
        else:
            print(f"    [WARN] {cid} failed: {result.result.type}", flush=True)
            if debug_dir:
                (debug_dir / f"{cid}-api-error.txt").write_text(
                    str(result.result), encoding="utf-8"
                )
            results_map[cid] = []

    ordered = [results_map.get(f"chunk-{i:04d}", []) for i in range(len(chunks))]

    # Always print per-chunk summary
    print(f"\n  Chunk results summary:", flush=True)
    for i, entries in enumerate(ordered):
        cid = f"chunk-{i:04d}"
        status = f"{len(entries)} entries"
        flag = "  ← EMPTY — check debug files" if len(entries) == 0 else ""
        print(f"    {cid}: {status}{flag}", flush=True)
    print(flush=True)

    return ordered



def call_claude_for_monsters(client: anthropic.Anthropic, chunk_text: str,
                              model: str, source_id: str,
                              verbose: bool,
                              debug_dir: Path | None = None,
                              chunk_id: str = "chunk-0000") -> list[Any]:
    """
    Second-pass Claude call: extract structured monster stat blocks from a chunk.
    Returns a list of 5etools monster objects (may be empty if no stat blocks found).
    """
    if verbose:
        print(f"    [monsters] Scanning {len(chunk_text):,} chars for stat blocks...",
              flush=True)

    message = client.messages.create(
        model=model,
        max_tokens=8192,
        system=MONSTER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": chunk_text}],
    )

    monsters = _parse_claude_response(
        message.content[0].text, verbose,
        debug_dir=debug_dir,
        chunk_id=f"{chunk_id}-monsters"
    )

    # Stamp source and mark as NPC if not already set
    for m in monsters:
        if isinstance(m, dict):
            m["source"] = source_id

    if monsters and verbose:
        names = [m.get("name","?") for m in monsters if isinstance(m, dict)]
        print(f"    [monsters] Found {len(monsters)}: {', '.join(names)}", flush=True)

    return monsters


# ---------------------------------------------------------------------------
# ID assignment
# ---------------------------------------------------------------------------

_id_counter = 0

def reset_ids() -> None:
    global _id_counter
    _id_counter = 0


def assign_ids(entries: list[Any]) -> list[Any]:
    """Recursively assign numeric IDs to section/entries objects."""
    global _id_counter
    for entry in entries:
        if isinstance(entry, dict):
            t = entry.get("type", "")
            if t in ("section", "entries", "inset"):
                entry["id"] = f"{_id_counter:03d}"
                _id_counter += 1
            if "entries" in entry and isinstance(entry["entries"], list):
                assign_ids(entry["entries"])
            if "items" in entry and isinstance(entry["items"], list):
                assign_ids(entry["items"])
    return entries


# ---------------------------------------------------------------------------
# TOC extraction from final data
# ---------------------------------------------------------------------------

def build_toc(data: list[Any]) -> list[dict]:
    """Build the 'contents' array for the index file from the section tree."""
    toc: list[dict] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        t = entry.get("type", "")
        name = entry.get("name", "Untitled")
        if t == "section":
            chapter: dict = {"name": name, "headers": []}
            for sub in entry.get("entries", []):
                if isinstance(sub, dict) and sub.get("type") == "entries":
                    chapter["headers"].append(sub.get("name", ""))
            toc.append(chapter)
    return toc


# ---------------------------------------------------------------------------
# Main conversion driver
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
    output_mode: str,   # "homebrew" = single file for Load from File
                        # "server"   = two files for permanent server install
    use_batch: bool,    # True = Batch API (50% cheaper, async ~minutes)
    dry_run_only: bool, # True = count tokens + estimate cost, no inference
    extract_monsters: bool, # True = second Claude pass to extract stat blocks
    monsters_only: bool,    # True = skip adventure extraction, monsters only
    debug_dir: Path | None,  # directory to dump raw chunk I/O for debugging
    verbose: bool,
) -> None:
    print(f"\n{'='*60}")
    print(f"  PDF → 5etools converter")
    print(f"  Input : {pdf_path}")
    print(f"  Output: {out_path}")
    print(f"  Type  : {output_type}   ID: {short_id}   Mode: {output_mode}")
    print(f"  API   : {'Batch (50% discount)' if use_batch else 'Standard'}")
    if monsters_only:
        print(f"  Mode  : MONSTERS ONLY (adventure extraction skipped)")
    elif extract_monsters:
        print(f"  Mode  : Extract monsters enabled (second Claude pass per chunk)")
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        print(f"  Debug : {debug_dir}")
    print(f"{'='*60}\n")

    # ── 1. Extract pages ────────────────────────────────────────────────────
    print("[1/5] Extracting text from PDF...", flush=True)
    pages = extract_pages(pdf_path)
    print(f"      {len(pages)} pages extracted.")

    if not pages:
        sys.exit("No text could be extracted from the PDF.")

    # ── 2. Chunk ─────────────────────────────────────────────────────────────
    print(f"[2/5] Chunking into groups of {chunk_size} pages...", flush=True)
    chunks = chunk_pages(pages, chunk_size)
    print(f"      {len(chunks)} chunks.")

    # ── 3. Call Claude per chunk ─────────────────────────────────────────────
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit(
            "No Anthropic API key found.  Set ANTHROPIC_API_KEY env var or "
            "pass --api-key."
        )

    client = anthropic.Anthropic(api_key=key)
    all_entries: list[Any] = []

    api_label = "Batch API (50% discount)" if use_batch else "Standard API"
    print(f"[3/5] Converting {len(chunks)} chunks via Claude ({model}) [{api_label}]...",
          flush=True)

    # Build the annotated text for every chunk up front
    chunk_texts: list[str] = []
    for chunk in chunks:
        chunk_text = ""
        for p in chunk:
            annotated = page_to_annotated_text(p)
            if annotated.strip():
                chunk_text += f"\n--- Page {p['page_num']} ---\n{annotated}\n"
        if len(chunk_text) > MAX_CHUNK_CHARS:
            chunk_text = chunk_text[:MAX_CHUNK_CHARS]
            if verbose:
                print(f"    [WARN] Chunk trimmed to {MAX_CHUNK_CHARS} chars.")
        chunk_texts.append(chunk_text)

    if dry_run_only:
        # ── Dry run: count tokens, print estimate, exit early ─────────
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            sys.exit(
                "No Anthropic API key found. Token counting requires an API key.\n"
                "Set ANTHROPIC_API_KEY or pass --api-key."
            )
        client = anthropic.Anthropic(api_key=key)
        dry_run(client, chunk_texts, chunks, model, use_batch, verbose)
        return

    all_monsters: list[Any] = []

    if not monsters_only:
        # ── Adventure extraction ──────────────────────────────────────────
        if use_batch:
            non_empty = [(i, t) for i, t in enumerate(chunk_texts) if t.strip()]
            if not non_empty:
                print("    [WARN] All chunks empty — nothing to send.")
            else:
                texts_to_send = [t for _, t in non_empty]
                batch_results = call_claude_batch(
                    client, texts_to_send, model, verbose, debug_dir=debug_dir
                )
                for entries in batch_results:
                    all_entries.extend(entries)
        else:
            for i, chunk_text in enumerate(chunk_texts):
                page_nums = [p["page_num"] for p in chunks[i]]
                print(f"  Chunk {i+1}/{len(chunks)}  "
                      f"(pages {page_nums[0]}–{page_nums[-1]})", flush=True)
                if not chunk_text.strip():
                    if verbose:
                        print("    [SKIP] Empty chunk.")
                    continue
                entries = call_claude(client, chunk_text, model, verbose,
                                      debug_dir=debug_dir,
                                      chunk_id=f"chunk-{i:04d}")
                print(f"    → {len(entries)} entries parsed"
                      + ("  ← EMPTY — check debug files" if debug_dir and not entries else ""),
                      flush=True)
                all_entries.extend(entries)
        print(f"      Total raw entries collected: {len(all_entries)}")
    else:
        print("[3/5] Skipping adventure extraction (--monsters-only)", flush=True)

    # ── Monster extraction pass ───────────────────────────────────────────
    if extract_monsters or monsters_only:
        label = "[3/5]" if monsters_only else "[3b]"
        print(f"{label} Extracting monster stat blocks...", flush=True)
        for i, chunk_text in enumerate(chunk_texts):
            if not chunk_text.strip():
                continue
            monsters = call_claude_for_monsters(
                client, chunk_text, model, short_id, verbose,
                debug_dir=debug_dir, chunk_id=f"chunk-{i:04d}"
            )
            all_monsters.extend(monsters)
        print(f"      Total monsters found: {len(all_monsters)}", flush=True)

    # ── 4. Assign IDs ────────────────────────────────────────────────────────
    print("[4/5] Assigning IDs...", flush=True)
    reset_ids()
    assign_ids(all_entries)

    # ── 5. Build output files ────────────────────────────────────────────────
    print("[5/5] Writing output files...", flush=True)

    toc = build_toc(all_entries)
    today = date.today().isoformat()
    title = pdf_path.stem.replace("_", " ").replace("-", " ").title()

    import time as _time

    index_key = "adventure" if output_type == "adventure" else "book"
    data_key  = f"{index_key}Data"

    if output_type == "book":
        all_entries = [
            {
                "type": "section",
                "name": title,
                "id": "000",
                "entries": all_entries,
            }
        ]

    index_entry: dict = {
        "name": title,
        "id": short_id,
        "source": short_id,
        "group": "homebrew",
        "published": today,
        "author": author,
        "contents": toc,
    }

    print(f"\n{'='*60}")
    print("  Done!")

    if monsters_only:
        # ── Monsters-only: minimal homebrew JSON with just the monster array ──
        homebrew_obj: dict = {
            "_meta": {
                "sources": [
                    {
                        "json": short_id,
                        "abbreviation": short_id[:8],
                        "full": title,
                        "version": "1.0.0",
                        "authors": [author],
                        "convertedBy": ["pdf_to_5etools"],
                        "url": None,
                        "color": "",
                    }
                ],
                "dateAdded": int(_time.time()),
                "dateLastModified": int(_time.time()),
            },
            "monster": all_monsters,
        }
        out_path.write_text(
            json.dumps(homebrew_obj, indent="\t", ensure_ascii=False), encoding="utf-8"
        )
        print(f"  Output file: {out_path}  ({len(all_monsters)} monsters)")
        print(f"{'='*60}")
        print()
        print("  To load in 5etools (Manage Homebrew):")
        print("    1. Open  http://localhost:5050/managebrew.html")
        print("    2. Click 'Load from File'")
        print(f"   3. Select {out_path.name}")
        print("    4. Monsters appear in bestiary.html")
        print()
        return

    if output_mode == "homebrew":
        # ── Single-file format: load via Manage Homebrew → Load from File ──
        homebrew_obj: dict = {
            "_meta": {
                "sources": [
                    {
                        "json": short_id,
                        "abbreviation": short_id[:8],
                        "full": title,
                        "version": "1.0.0",
                        "authors": [author],
                        "convertedBy": ["pdf_to_5etools"],
                        "url": None,
                        "color": "",
                    }
                ],
                "dateAdded": int(_time.time()),
                "dateLastModified": int(_time.time()),
            },
            index_key: [index_entry],
            data_key: [
                {
                    "id": short_id,
                    "source": short_id,
                    "data": all_entries,
                }
            ],
        }
        out_path.write_text(
            json.dumps(homebrew_obj, indent="\t", ensure_ascii=False), encoding="utf-8"
        )
        print(f"  Output file: {out_path}")
        print(f"{'='*60}")
        print()
        print("  To load in 5etools (Manage Homebrew):")
        print("    1. Open  http://localhost:5050/managebrew.html")
        print("    2. Click 'Load from File'")
        print(f"   3. Select {out_path.name}")
        print("    4. Your content appears under Adventures (or Books) in the nav.")

    else:
        # ── Two-file server format: copy files into 5etools data/ dirs ──
        data_path = out_path
        if output_type == "adventure":
            data_obj: dict = {"data": all_entries}
        else:
            data_obj = {"data": all_entries}   # already wrapped above

        data_path.write_text(
            json.dumps(data_obj, indent="\t", ensure_ascii=False), encoding="utf-8"
        )

        index_obj: dict = {index_key: [index_entry]}
        index_path = out_path.parent / f"{index_key}s-{short_id.lower()}.json"
        index_path.write_text(
            json.dumps(index_obj, indent="\t", ensure_ascii=False), encoding="utf-8"
        )

        print(f"  Data file  : {data_path}")
        print(f"  Index file : {index_path}")
        if all_monsters:
            bestiary_path = out_path.parent / f"bestiary-{short_id.lower()}.json"
            bestiary_obj: dict = {"monster": all_monsters}
            bestiary_path.write_text(
                json.dumps(bestiary_obj, indent="\t", ensure_ascii=False),
                encoding="utf-8"
            )
            print(f"  Bestiary   : {bestiary_path}  ({len(all_monsters)} monsters)")
        print(f"{'='*60}")
        print()
        if output_type == "adventure":
            print("  To install on your 5etools server:")
            print(f"    cp {data_path.name} ~/5etools/data/adventure/")
            print(f"    cp {index_path.name} ~/5etools/data/")
            print("    # Then add the index entry to data/adventures.json")
            print("    sudo systemctl restart 5etools")
        else:
            print("  To install on your 5etools server:")
            print(f"    cp {data_path.name} ~/5etools/data/book/")
            print(f"    cp {index_path.name} ~/5etools/data/")
            print("    # Then add the index entry to data/books.json")
            print("    sudo systemctl restart 5etools")

    print()



# ---------------------------------------------------------------------------
# Dry-run: token counting + cost estimate (no API inference charges)
# ---------------------------------------------------------------------------

# Pricing per million tokens (update if Anthropic changes rates)
_PRICE = {
    "haiku":  {"input": 0.80,  "output": 4.00},
    "sonnet": {"input": 3.00,  "output": 15.00},
    "opus":   {"input": 15.00, "output": 75.00},
}

def _model_tier(model: str) -> str:
    m = model.lower()
    if "haiku"  in m: return "haiku"
    if "sonnet" in m: return "sonnet"
    if "opus"   in m: return "opus"
    return "sonnet"  # safe default

def dry_run(
    client: anthropic.Anthropic,
    chunk_texts: list[str],
    chunks: list,           # parallel list — used for page-range labels
    model: str,
    use_batch: bool,
    verbose: bool,
) -> None:
    """Count tokens for every chunk and print a cost estimate. No inference."""
    tier   = _model_tier(model)
    prices = _PRICE.get(tier, _PRICE["sonnet"])
    discount = 0.5 if use_batch else 1.0

    print(f"\n[DRY-RUN] Token count + cost estimate")
    print(f"  Model  : {model}  ({'Batch API -50%%' if use_batch else 'Standard API'})")
    print(f"  Pricing: ${prices['input']:.2f} / ${prices['output']:.2f} per M tokens "
          f"(in/out){'  ×0.5 batch discount' if use_batch else ''}")
    print()

    total_input  = 0
    # Estimate output at ~1 000 tokens per chunk (typical 5etools JSON response)
    est_output_per_chunk = 1_000
    skipped = 0

    for i, chunk_text in enumerate(chunk_texts):
        if not chunk_text.strip():
            skipped += 1
            continue

        # Use the Anthropic token-counting endpoint (free, no inference)
        resp = client.messages.count_tokens(
            model=model,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": chunk_text}],
        )
        tok = resp.input_tokens
        total_input += tok

        if verbose or len(chunk_texts) <= 12:
            # Show page range when chunks list has the right structure
            try:
                if chunks and hasattr(chunks[i][0], "__getitem__"):
                    page_nums = [p["page_num"] for p in chunks[i]]
                else:
                    page_nums = [p for p, _ in chunks[i]]
                label = f"pages {page_nums[0]}–{page_nums[-1]}"
            except Exception:
                label = f"chunk {i}"
            print(f"  chunk-{i:04d}  ({label})  →  {tok:,} input tokens")

    total_output = est_output_per_chunk * (len(chunk_texts) - skipped)

    cost_input  = total_input  / 1_000_000 * prices["input"]  * discount
    cost_output = total_output / 1_000_000 * prices["output"] * discount
    cost_total  = cost_input + cost_output

    print()
    print(f"  ─────────────────────────────────────────")
    print(f"  Chunks          : {len(chunk_texts) - skipped} "
          f"({skipped} empty/skipped)")
    print(f"  Total input     : {total_input:,} tokens  "
          f"→  ${cost_input:.4f}")
    print(f"  Est. output     : ~{total_output:,} tokens  "
          f"→  ${cost_output:.4f}")
    print(f"  ─────────────────────────────────────────")
    print(f"  Estimated total : ${cost_total:.4f}  "
          f"({'with' if use_batch else 'without'} batch discount)")
    print(f"  ─────────────────────────────────────────")
    print()
    print("  No API inference was performed. Remove --dry-run to convert.")
    print()

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a RPG PDF into 5etools adventure/book JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Output modes:
          homebrew  Single JSON file → load via Manage Homebrew > Load from File (default)
          server    Two files (data + index) → copy into 5etools data/ dirs for permanent install

        Examples:
          python3 pdf_to_5etools.py "Lost Mine.pdf"
          python3 pdf_to_5etools.py "MyAdventure.pdf" --id MYADV --author "Jane Smith"
          python3 pdf_to_5etools.py "MyAdventure.pdf" --output-dir ~/5etools/homebrew
          python3 pdf_to_5etools.py "Rulebook.pdf" --type book --output-mode server --output-dir /tmp/out
          python3 pdf_to_5etools.py "BigBook.pdf" --batch                  # 50% cheaper, async
          python3 pdf_to_5etools.py "BigBook.pdf" --dry-run                # estimate cost first
          python3 pdf_to_5etools.py "BigBook.pdf" --dry-run --batch        # estimate batch cost
        """),
    )
    parser.add_argument("pdf", type=Path, help="Input PDF file")
    parser.add_argument(
        "--type",
        choices=["adventure", "book"],
        default="adventure",
        dest="output_type",
        help="Content type (default: adventure)",
    )
    parser.add_argument(
        "--output-mode",
        choices=["homebrew", "server"],
        default="homebrew",
        dest="output_mode",
        help=(
            "homebrew = single file for Load from File (default); "
            "server = two files for permanent server install"
        ),
    )
    parser.add_argument(
        "--id",
        default=None,
        help="Short uppercase ID, e.g. MYMOD (default: derived from filename)",
    )
    parser.add_argument("--author", default="Unknown", help="Author name")
    parser.add_argument(
        "--out", type=Path, default=None,
        help="Full output filename (overrides --output-dir)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None, dest="output_dir",
        help="Directory to write output file(s) into (default: same folder as the PDF)",
    )
    parser.add_argument("--api-key", default=None, help="Anthropic API key")
    parser.add_argument(
        "--pages-per-chunk",
        type=int,
        default=DEFAULT_CHUNK,
        dest="chunk_size",
        help=f"Pages per Claude call (default: {DEFAULT_CHUNK})",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Claude model (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        dest="use_batch",
        help=(
            "Use the Anthropic Batch API (50%% cheaper, but async — "
            "takes minutes to complete rather than streaming immediately)"
        ),
    )
    parser.add_argument(
        "--extract-monsters",
        action="store_true",
        dest="extract_monsters",
        help=(
            "Run a second Claude pass on each chunk to extract monster stat blocks "
            "into the bestiary. Monsters appear in bestiary.html after loading."
        ),
    )
    parser.add_argument(
        "--monsters-only",
        action="store_true",
        dest="monsters_only",
        help=(
            "Skip adventure text extraction entirely — only extract monster stat "
            "blocks. Produces a bestiary-only homebrew JSON. Fastest and cheapest "
            "if you only need the bestiary entries."
        ),
    )
    parser.add_argument(
        "--debug-dir",
        type=Path,
        default=None,
        dest="debug_dir",
        help=(
            "Directory to save raw chunk inputs and Claude responses for debugging. "
            "Creates one -input.txt and one -response.txt / -parsed.json per chunk."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run_only",
        help=(
            "Count tokens and estimate API cost without calling Claude. "
            "Requires an API key (token counting is free)."
        ),
    )
    parser.add_argument("--verbose", action="store_true")

    args = parser.parse_args()

    pdf_path: Path = normalise_path(str(args.pdf))
    if not pdf_path.exists():
        sys.exit(f"PDF not found: {pdf_path}")

    short_id: str = (
        args.id
        or re.sub(r"[^A-Z0-9]", "", pdf_path.stem.upper())[:8]
        or "HOMEBREW"
    )

    prefix = "adventure" if args.output_type == "adventure" else "book"
    out_dir: Path = (
        args.out.parent if args.out
        else (normalise_path(str(args.output_dir)) if args.output_dir else pdf_path.parent)
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path: Path = args.out or out_dir / f"{prefix}-{short_id.lower()}.json"

    debug_dir = (
        normalise_path(str(args.debug_dir)) if args.debug_dir else None
    )

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
        extract_monsters=args.extract_monsters,
        monsters_only=args.monsters_only,
        debug_dir=debug_dir,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
