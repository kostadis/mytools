#!/usr/bin/env python3
"""
pdf_to_5etools_ocr.py
=====================
OCR-enhanced converter for RPG PDFs → 5etools adventure/book JSON.

Designed for scanned books, image-based PDFs, or any document where the
standard PyMuPDF text extraction in pdf_to_5etools.py produces poor results.

Strategy
--------
1.  Try PyMuPDF digital text extraction first on every page.
    If a page yields enough readable text (>50 chars after cleaning), use it.
    Digital text is always cleaner than OCR output.

2.  For pages that fail the threshold — or if --force-ocr is set — render
    the page to a high-resolution image (300 DPI) and run Tesseract OCR with
    a custom config tuned for multi-column RPG layouts.

3.  Layout analysis:
    - Detect multi-column pages by looking at the x-positions of words from
      Tesseract's detailed output and splitting at whitespace gaps > 20% of
      page width.
    - Re-order text left-column-first so Claude receives prose in the right
      reading order.
    - Detect tables by looking for rows with consistent tab-separated tokens.
    - Detect headings by font-size from PyMuPDF (digital pages) or by
      Tesseract's per-word confidence / character height (OCR pages).
    - Detect boxed/read-aloud text by checking if Tesseract found a large
      bounding-box region separated from the main body (inset detection).

4.  Image blocks are noted as [IMAGE] placeholders so Claude can emit a
    stub {@image} entry rather than silently dropping them.

5.  The annotated text per chunk is sent to Claude with the same structured
    prompt from the base script, extended with instructions for OCR noise
    and column handling.

Dependencies
------------
    pip install pymupdf anthropic pytesseract pillow pdf2image
    # Ubuntu/Debian system packages:
    sudo apt install tesseract-ocr tesseract-ocr-eng poppler-utils

Usage
-----
    python3 pdf_to_5etools_ocr.py <input.pdf> [options]

Options
-------
    --type adventure|book
    --id   SHORT_ID
    --author "Name"
    --out  output.json
    --api-key KEY          (or ANTHROPIC_API_KEY env var)
    --pages-per-chunk N    (default: 4 — smaller than base due to richer output)
    --dpi N                Render resolution for OCR pages (default: 300)
    --force-ocr            Skip digital extraction entirely; OCR every page
    --lang LANG            Tesseract language code(s), e.g. "eng" or "eng+fra"
    --model MODEL
    --verbose
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

# ── Hard dependencies ────────────────────────────────────────────────────────
try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("PyMuPDF required:  pip install pymupdf")

try:
    import anthropic
except ImportError:
    sys.exit("anthropic required:  pip install anthropic")

try:
    import pytesseract
    from PIL import Image, ImageFilter, ImageEnhance
    from pdf2image import convert_from_path
except ImportError:
    sys.exit(
        "OCR packages required:\n"
        "    pip install pytesseract pillow pdf2image\n"
        "    sudo apt install tesseract-ocr tesseract-ocr-eng poppler-utils"
    )

import claude_api as _api

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


# ── Constants ────────────────────────────────────────────────────────────────
DEFAULT_MODEL      = "claude-haiku-4-5-20251001"
DEFAULT_CHUNK      = 4
DEFAULT_DPI        = 300
MIN_DIGITAL_CHARS  = 50     # pages with fewer chars than this → OCR
MAX_CHUNK_CHARS    = 80_000  # safety cap (~20K tokens, well within 200K context)
COLUMN_GAP_RATIO   = 0.20   # gap > 20% of page width → column break

# Tesseract page-segmentation mode 1 = auto OSD, 6 = single block
# PSM 1 handles most RPG pages well (auto-detects orientation + columns)
TESS_CONFIG = r"--oem 3 --psm 1"

SYSTEM_PROMPT = textwrap.dedent(f"""
You are an expert at converting RPG sourcebook text into the 5etools adventure
JSON format.  The text you receive was extracted from a PDF (some pages via
direct extraction, some via OCR) and may contain minor OCR artefacts like
ligature mis-reads (ﬁ→fi, ﬂ→fl), hyphenated line-breaks, or stray characters.
Correct obvious OCR errors silently as you go.

The text is annotated with structural hints:
    [H1] Title        — top-level chapter heading
    [H2] Title        — section heading
    [H3] Title        — sub-section heading
    [TABLE-START]     — beginning of a detected table
    [TABLE-END]       — end of a detected table
    [INSET-START]     — beginning of boxed/read-aloud text
    [INSET-END]       — end of boxed/read-aloud text
    [IMAGE: caption]  — image placeholder
    [italic]…[/italic]— italic span
    [OCR]             — this page was OCR'd (expect minor noise)

Return ONLY a valid JSON array of 5etools entry objects.  No markdown fences,
no explanation — raw JSON only.

Use these object types:

  Plain paragraph  → a bare JSON string
  Named section    → {{"type":"entries","name":"Title","entries":[...]}}
  Top section      → {{"type":"section","name":"Title","entries":[...]}}
  Bulleted list    → {{"type":"list","items":["a","b"]}}
  Table            → {{"type":"table","caption":"","colLabels":[],"colStyles":[],"rows":[[]]}}
  Boxed/sidebar    → {{"type":"inset","name":"Title","entries":[...]}}
  Read-aloud text  → {{"type":"inset","name":"","entries":["text..."]}}
  Image stub       → {{"type":"image","href":{{"type":"internal","path":"img/placeholder.webp"}},"title":"caption"}}

Rules:
- Preserve all flavour text and game rules accurately.
{_api.COMMON_TAG_RULES}
{_api.COMMON_NESTING_RULES}
- Do NOT add IDs — those are added later.
- Tables must have colLabels and rows even if only one column.
- Merge hyphenated line-breaks: "adven-\\nture" → "adventure".
- If a page contains only noise or blank content, return [].
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
  source      string   — use "HOMEBREW" (filled in by the script)
  size        array    — ["T","S","M","L","H","G"]
  type        string or {"type":"humanoid","tags":["human"]}
  alignment   array    — ["L","G"] / ["N","E"] / ["U"] for unaligned etc.
  ac          array    — [15] or [{"ac":15,"from":["chain mail"]}]
  hp          object   — {"average":22,"formula":"3d8+9"}
  speed       object   — {"walk":30} or {"walk":30,"fly":60}
  str,dex,con,int,wis,cha  integers
  passive     integer  — passive Perception
  cr          string   — "1/4","1/2","1","2" etc.

OPTIONAL (include if present):
  save, skill, senses, languages, immune, resist, conditionImmune,
  trait, action, bonus, reaction, legendary, spellcasting,
  isNamedCreature, isNpc

Alignment abbreviations: L=Lawful, N=Neutral, C=Chaotic, G=Good, E=Evil, U=Unaligned, A=Any

Attack format in entries: "{@atk mw} {@hit 5} to hit, reach 5 ft., one target. {@h}{@damage 2d6+3} slashing damage."
""").strip()


# ═══════════════════════════════════════════════════════════════════════════
# Image preprocessing
# ═══════════════════════════════════════════════════════════════════════════

def preprocess_image(img: Image.Image) -> Image.Image:
    """
    Apply a sequence of preprocessing steps that improve Tesseract accuracy
    on typical RPG book pages: parchment backgrounds, decorative fonts, etc.
    """
    # Convert to grayscale
    img = img.convert("L")

    # Increase contrast — helps with faint text on textured backgrounds
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)

    # Sharpen slightly to crisp up edges
    img = img.filter(ImageFilter.SHARPEN)

    # Binarise with a moderate threshold (Otsu-like via point)
    # 140 is a good midpoint for cream/parchment backgrounds
    img = img.point(lambda p: 255 if p > 140 else 0, "1")

    return img


# ═══════════════════════════════════════════════════════════════════════════
# Tesseract OCR with layout analysis
# ═══════════════════════════════════════════════════════════════════════════

def ocr_page_image(img: Image.Image, lang: str = "eng") -> dict:
    """
    Run Tesseract on a pre-processed image.
    Returns:
        {
            "text": annotated full-page string,
            "columns": int,
        }
    """
    processed = preprocess_image(img)

    # Get detailed per-word data for layout analysis
    data = pytesseract.image_to_data(
        processed,
        lang=lang,
        config=TESS_CONFIG,
        output_type=pytesseract.Output.DICT,
    )

    page_width  = img.width
    page_height = img.height

    # ── Gather words with position info ──────────────────────────────────────
    words: list[dict] = []
    n = len(data["text"])
    for i in range(n):
        w = data["text"][i].strip()
        if not w:
            continue
        conf = int(data["conf"][i])
        if conf < 10:   # skip very low-confidence tokens (noise)
            continue
        words.append({
            "text":   w,
            "left":   data["left"][i],
            "top":    data["top"][i],
            "width":  data["width"][i],
            "height": data["height"][i],
            "block":  data["block_num"][i],
            "par":    data["par_num"][i],
            "line":   data["line_num"][i],
            "conf":   conf,
        })

    if not words:
        return {"text": "", "columns": 1}

    # ── Column detection ──────────────────────────────────────────────────────
    # Find the x-distribution of words; look for a significant gap in the
    # middle third of the page that separates two columns.
    mid_lo = page_width * 0.30
    mid_hi = page_width * 0.70
    mid_words = [w for w in words if mid_lo < w["left"] + w["width"] / 2 < mid_hi]

    columns = 1
    col_split_x = page_width // 2  # default midpoint

    if mid_words:
        xs = sorted(w["left"] for w in words)
        # Sliding-window gap detection
        gap_threshold = page_width * COLUMN_GAP_RATIO
        max_gap = 0
        best_split = page_width // 2
        for i in range(len(xs) - 1):
            gap = xs[i + 1] - xs[i]
            if gap > max_gap and mid_lo < xs[i] < mid_hi:
                max_gap = gap
                best_split = (xs[i] + xs[i + 1]) // 2

        if max_gap > gap_threshold:
            columns = 2
            col_split_x = best_split

    # ── Sort words into reading order ─────────────────────────────────────────
    # For two-column pages: left column first (top-to-bottom), then right.
    def reading_order_key(w: dict) -> tuple:
        col = 0 if (w["left"] + w["width"] // 2) < col_split_x else 1
        return (col, w["top"], w["left"])

    words.sort(key=reading_order_key)

    # ── Detect heading candidates by character height ─────────────────────────
    # Average word height across the page
    heights = [w["height"] for w in words if w["height"] > 0]
    avg_h = sum(heights) / len(heights) if heights else 20
    h1_h  = avg_h * 1.8
    h2_h  = avg_h * 1.4
    h3_h  = avg_h * 1.15

    # ── Reconstruct lines, tagging headings ──────────────────────────────────
    # Group words by (block, par, line) → lines
    from collections import defaultdict
    line_map: dict[tuple, list[dict]] = defaultdict(list)
    for w in words:
        line_map[(w["block"], w["par"], w["line"])].append(w)

    # Sort line keys by reading order (first word's position)
    def line_order_key(key: tuple) -> tuple:
        first = line_map[key][0]
        col = 0 if (first["left"] + first["width"] // 2) < col_split_x else 1
        return (col, first["top"])

    sorted_keys = sorted(line_map.keys(), key=line_order_key)

    annotated_lines: list[str] = []
    prev_block = None
    inset_active = False

    for key in sorted_keys:
        line_words = sorted(line_map[key], key=lambda w: w["left"])
        line_text  = " ".join(w["text"] for w in line_words).strip()
        if not line_text:
            continue

        block_num = key[0]
        # Blank line between blocks
        if prev_block is not None and block_num != prev_block:
            annotated_lines.append("")
        prev_block = block_num

        # Heading detection by character height
        max_h = max(w["height"] for w in line_words)
        is_short = len(line_text) < 80

        if max_h >= h1_h and is_short:
            annotated_lines.append(f"[H1] {line_text}")
        elif max_h >= h2_h and is_short:
            annotated_lines.append(f"[H2] {line_text}")
        elif max_h >= h3_h and is_short:
            annotated_lines.append(f"[H3] {line_text}")
        else:
            annotated_lines.append(line_text)

    # ── Crude inset/table detection based on block bounding boxes ────────────
    # A block that occupies < 60% of page width and is indented on both sides
    # is likely a sidebar or boxed text.
    block_bounds: dict[int, dict] = {}
    for w in words:
        b = w["block"]
        if b not in block_bounds:
            block_bounds[b] = {"left": w["left"], "right": w["left"] + w["width"],
                                "top": w["top"], "bottom": w["top"] + w["height"]}
        else:
            block_bounds[b]["left"]   = min(block_bounds[b]["left"], w["left"])
            block_bounds[b]["right"]  = max(block_bounds[b]["right"], w["left"] + w["width"])
            block_bounds[b]["top"]    = min(block_bounds[b]["top"], w["top"])
            block_bounds[b]["bottom"] = max(block_bounds[b]["bottom"], w["top"] + w["height"])

    inset_blocks: set[int] = set()
    for b, bbox in block_bounds.items():
        bw = bbox["right"] - bbox["left"]
        indent_left  = bbox["left"] / page_width
        indent_right = 1.0 - bbox["right"] / page_width
        if bw < page_width * 0.60 and indent_left > 0.08 and indent_right > 0.08:
            inset_blocks.add(b)

    # Rebuild final annotated text with inset markers
    # We re-walk sorted_keys and insert markers at block transitions
    final_lines: list[str] = []
    cur_inset: bool = False

    for key in sorted_keys:
        b = key[0]
        is_inset = b in inset_blocks

        if is_inset and not cur_inset:
            final_lines.append("[INSET-START]")
            cur_inset = True
        elif not is_inset and cur_inset:
            final_lines.append("[INSET-END]")
            cur_inset = False

        line_words = sorted(line_map[key], key=lambda w: w["left"])
        line_text  = " ".join(w["text"] for w in line_words).strip()
        if not line_text:
            continue

        max_h = max(w["height"] for w in line_words)
        is_short = len(line_text) < 80

        if max_h >= h1_h and is_short:
            final_lines.append(f"[H1] {line_text}")
        elif max_h >= h2_h and is_short:
            final_lines.append(f"[H2] {line_text}")
        elif max_h >= h3_h and is_short:
            final_lines.append(f"[H3] {line_text}")
        else:
            final_lines.append(line_text)

    if cur_inset:
        final_lines.append("[INSET-END]")

    # ── Detect tables (lines with 3+ tab/space-separated tokens aligned) ─────
    merged = _inject_table_markers(final_lines)

    return {
        "text": "\n".join(merged),
        "columns": columns,
    }


def _inject_table_markers(lines: list[str]) -> list[str]:
    """
    Scan for runs of lines that look like table rows (2+ whitespace-separated
    columns, consistent column count) and wrap them with [TABLE-START/END].
    """
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Skip already-annotated lines
        if line.startswith("["):
            result.append(line)
            i += 1
            continue

        # Detect potential table start: line with 2+ tokens separated by 2+ spaces
        tokens = re.split(r"  +|\t", line.strip())
        if len(tokens) >= 2:
            # Look ahead to see if subsequent lines have similar structure
            run = [line]
            j = i + 1
            while j < len(lines) and not lines[j].startswith("["):
                next_tokens = re.split(r"  +|\t", lines[j].strip())
                if len(next_tokens) >= 2:
                    run.append(lines[j])
                    j += 1
                else:
                    break
            if len(run) >= 3:  # at least 3 rows looks like a real table
                result.append("[TABLE-START]")
                result.extend(run)
                result.append("[TABLE-END]")
                i = j
                continue

        result.append(line)
        i += 1
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Digital page extraction (PyMuPDF, mirrored from base script)
# ═══════════════════════════════════════════════════════════════════════════

def extract_digital_page(page_obj: fitz.Page,
                          body_size: float) -> str | None:
    """
    Extract annotated text from a digitally-encoded PDF page.
    Returns None if the page doesn't have enough text (→ should OCR instead).
    """
    h1_thresh = body_size * 1.40
    h2_thresh = body_size * 1.20
    h3_thresh = body_size * 1.05

    raw_blocks = page_obj.get_text(
        "dict", flags=fitz.TEXT_PRESERVE_WHITESPACE
    )["blocks"]

    lines_out: list[str] = []
    total_chars = 0

    for blk in raw_blocks:
        if blk.get("type") != 0:
            # Image block
            lines_out.append("[IMAGE: embedded]")
            continue
        for line in blk.get("lines", []):
            text_parts: list[str] = []
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
                if flags & (1 << 4):
                    is_bold = True
                if flags & (1 << 1):
                    is_italic = True

            text = " ".join(text_parts).strip()
            if not text:
                continue
            total_chars += len(text)

            is_heading    = False
            heading_level = 0
            if max_size >= h1_thresh and (is_bold or len(text) < 80):
                heading_level = 1; is_heading = True
            elif max_size >= h2_thresh and (is_bold or len(text) < 80):
                heading_level = 2; is_heading = True
            elif max_size >= h3_thresh and is_bold and len(text) < 80:
                heading_level = 3; is_heading = True

            if is_heading:
                prefix = {1: "[H1]", 2: "[H2]", 3: "[H3]"}.get(heading_level, "[H3]")
                lines_out.append(f"{prefix} {text}")
            elif is_italic and not is_bold:
                lines_out.append(f"[italic]{text}[/italic]")
            else:
                lines_out.append(text)

    if total_chars < MIN_DIGITAL_CHARS:
        return None

    return "\n".join(lines_out)


def compute_body_size(pdf_doc: fitz.Document) -> float:
    sizes: list[float] = []
    # Sample first 20 pages for speed
    for i, page in enumerate(pdf_doc):
        if i >= 20:
            break
        for blk in page.get_text("dict")["blocks"]:
            if blk.get("type") != 0:
                continue
            for line in blk.get("lines", []):
                for span in line.get("spans", []):
                    s = span.get("size", 0)
                    if s > 0:
                        sizes.append(s)
    if not sizes:
        return 12.0
    sizes.sort()
    mid = len(sizes) // 2
    return sizes[mid]


# ═══════════════════════════════════════════════════════════════════════════
# Claude API — delegates to claude_api for shared retry/parse logic
# ═══════════════════════════════════════════════════════════════════════════


def call_claude(client: anthropic.Anthropic, chunk_text: str,
                model: str, verbose: bool,
                debug_dir: Path | None = None,
                chunk_id: str = "chunk-0000") -> list[Any]:
    """Send one chunk to Claude with the OCR system prompt."""
    return _api.call_claude(client, chunk_text, model, SYSTEM_PROMPT,
                            verbose, debug_dir, chunk_id)


def call_claude_for_monsters(client: anthropic.Anthropic, chunk_text: str,
                              model: str, source_id: str,
                              verbose: bool,
                              debug_dir: Path | None = None,
                              chunk_id: str = "chunk-0000") -> list[Any]:
    """Extract monster stat blocks from a chunk (second-pass call)."""
    if verbose:
        print(f"    [monsters] Scanning {len(chunk_text):,} chars for stat blocks...",
              flush=True)

    monsters = _api.call_claude(client, chunk_text, model, MONSTER_SYSTEM_PROMPT,
                                verbose, debug_dir, f"{chunk_id}-monsters")

    for m in monsters:
        if isinstance(m, dict):
            m["source"] = source_id

    if monsters and verbose:
        names = [m.get("name", "?") for m in monsters if isinstance(m, dict)]
        print(f"    [monsters] Found {len(monsters)}: {', '.join(names)}", flush=True)

    return monsters


# ═══════════════════════════════════════════════════════════════════════════
# ID assignment & TOC
# ═══════════════════════════════════════════════════════════════════════════

_id_counter = 0

def reset_ids() -> None:
    global _id_counter
    _id_counter = 0

def assign_ids(entries: list[Any]) -> list[Any]:
    global _id_counter
    for entry in entries:
        if isinstance(entry, dict):
            if entry.get("type") in ("section", "entries", "inset"):
                entry["id"] = f"{_id_counter:03d}"
                _id_counter += 1
            if "entries" in entry:
                assign_ids(entry["entries"])
            if "items" in entry:
                assign_ids(entry["items"])
    return entries

def build_toc(data: list[Any]) -> list[dict]:
    toc: list[dict] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "section":
            ch: dict = {"name": entry.get("name", "Untitled"), "headers": []}
            for sub in entry.get("entries", []):
                if isinstance(sub, dict) and sub.get("type") == "entries":
                    ch["headers"].append(sub.get("name", ""))
            toc.append(ch)
    return toc


# ═══════════════════════════════════════════════════════════════════════════
# Main conversion driver
# ═══════════════════════════════════════════════════════════════════════════

def convert(
    pdf_path: Path,
    output_type: str,
    short_id: str,
    author: str,
    out_path: Path,
    api_key: str | None,
    chunk_size: int,
    dpi: int,
    force_ocr: bool,
    lang: str,
    model: str,
    output_mode: str,   # "homebrew" = single file for Load from File
                        # "server"   = two files for permanent server install
    dry_run_only: bool, # True = count tokens + estimate cost, no inference
    extract_monsters: bool, # True = second Claude pass to extract stat blocks
    monsters_only: bool,    # True = skip adventure extraction, monsters only
    debug_dir: Path | None,  # directory to dump raw chunk I/O for debugging
    verbose: bool,
    page_filter: set[int],  # if non-empty, only process these page numbers
    use_toc_hint: bool = True,  # prepend PDF bookmark outline to each chunk
) -> None:
    print(f"\n{'='*62}")
    print(f"  PDF → 5etools OCR Converter")
    print(f"  Input :  {pdf_path}")
    print(f"  Output:  {out_path}")
    print(f"  Type  :  {output_type}   ID: {short_id}   Mode: {output_mode}")
    print(f"  DPI   :  {dpi}   Force-OCR: {force_ocr}   Lang: {lang}")
    if extract_monsters:
        print(f"  Mode  :  Extract monsters enabled (second Claude pass per chunk)")
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        print(f"  Debug :  {debug_dir}")
    if page_filter:
        print(f"  Pages :  {sorted(page_filter)}")
    print(f"{'='*62}\n")

    # ── Open PDF ──────────────────────────────────────────────────────────────
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    print(f"[1/5] PDF opened: {total_pages} pages.", flush=True)

    body_size = compute_body_size(doc)
    if verbose:
        print(f"      Estimated body font size: {body_size:.1f}pt")

    # ── Per-page extraction ───────────────────────────────────────────────────
    print("[2/5] Extracting pages (digital + OCR fallback) ...", flush=True)

    page_texts: list[str] = []
    ocr_count = 0
    digital_count = 0

    # Pre-render all pages that need OCR in one pass (pdf2image is faster in bulk)
    # First, decide which pages need OCR
    needs_ocr: list[int] = []
    digital_results: dict[int, str | None] = {}

    for page_idx in range(total_pages):
        if page_filter and page_idx + 1 not in page_filter:
            digital_results[page_idx] = ""   # skip this page
            continue
        if force_ocr:
            needs_ocr.append(page_idx)
            digital_results[page_idx] = None
        else:
            text = extract_digital_page(doc[page_idx], body_size)
            digital_results[page_idx] = text
            if text is None:
                needs_ocr.append(page_idx)

    doc.close()

    # Render OCR pages as images
    ocr_images: dict[int, Image.Image] = {}
    if needs_ocr:
        if verbose:
            print(f"      Rendering {len(needs_ocr)} pages at {dpi} DPI for OCR...",
                  flush=True)
        # Convert only needed pages (1-indexed for pdf2image)
        # Build a mapping page_idx → PIL Image
        for idx in needs_ocr:
            imgs = convert_from_path(
                str(pdf_path),
                dpi=dpi,
                first_page=idx + 1,
                last_page=idx + 1,
            )
            if imgs:
                ocr_images[idx] = imgs[0]

    # Now build final per-page annotated text
    for page_idx in range(total_pages):
        if digital_results[page_idx] is not None:
            page_texts.append(digital_results[page_idx])  # type: ignore[arg-type]
            digital_count += 1
        elif page_idx in ocr_images:
            result = ocr_page_image(ocr_images[page_idx], lang=lang)
            if result["text"].strip():
                ocr_flag = "[OCR]" + (
                    f" [2-COLUMN]" if result["columns"] == 2 else ""
                )
                page_texts.append(f"{ocr_flag}\n{result['text']}")
            else:
                page_texts.append("")
            ocr_count += 1
        else:
            page_texts.append("")

    print(f"      Digital: {digital_count}  |  OCR: {ocr_count}  |  "
          f"Blank: {total_pages - digital_count - ocr_count}", flush=True)

    # ── Chunk pages ───────────────────────────────────────────────────────────
    print(f"[3/5] Chunking into groups of {chunk_size} pages ...", flush=True)
    chunks: list[list[tuple[int, str]]] = []
    indexed = [(i + 1, t) for i, t in enumerate(page_texts)]
    for i in range(0, len(indexed), chunk_size):
        chunks.append(indexed[i:i + chunk_size])
    print(f"      {len(chunks)} chunks.", flush=True)

    # ── Call Claude ───────────────────────────────────────────────────────────
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit(
            "No Anthropic API key.  Set ANTHROPIC_API_KEY or pass --api-key."
        )
    client = anthropic.Anthropic(api_key=key)

    # Extract PDF bookmark TOC for use as a per-chunk hint to Claude
    from pdf_utils import extract_pdf_toc
    toc_hint: str | None = None
    if use_toc_hint:
        toc_hint = extract_pdf_toc(pdf_path)
        if toc_hint:
            n_bm = sum(1 for ln in toc_hint.splitlines()
                       if ln.strip() and not ln.startswith('==='))
            print(f"      PDF has {n_bm} bookmark entries — injecting as section hint.",
                  flush=True)
        else:
            print("      PDF has no bookmarks — section hint skipped.", flush=True)

    # Build chunk texts up front (needed for both dry-run and real run)
    chunk_texts: list[str] = []
    for chunk in chunks:
        chunk_text = ""
        for page_num, text in chunk:
            if text.strip():
                chunk_text += f"\n--- Page {page_num} ---\n{text}\n"
        if toc_hint and chunk_text.strip():
            chunk_text = toc_hint + "\n\n" + chunk_text
        if len(chunk_text) > MAX_CHUNK_CHARS:
            cut = chunk_text.rfind('\n--- Page', 0, MAX_CHUNK_CHARS)
            chunk_text = chunk_text[:cut] if cut != -1 else chunk_text[:MAX_CHUNK_CHARS]
            print(f"    [WARN] Chunk exceeds {MAX_CHUNK_CHARS:,} chars — trimmed to last page boundary. "
                  f"Consider reducing --pages-per-chunk.", flush=True)
        chunk_texts.append(chunk_text)

    if dry_run_only:
        # ── Dry run: count tokens, print estimate, exit early ─────────────
        dry_run(client, chunk_texts, chunks, model, use_batch=False, verbose=verbose)
        return

    all_entries: list[Any] = []
    all_monsters: list[Any] = []

    if not monsters_only:
        print(f"[4/5] Converting {len(chunks)} chunks via Claude ({model}) ...",
              flush=True)
        for i, (chunk, chunk_text) in enumerate(zip(chunks, chunk_texts)):
            page_nums = [p for p, _ in chunk]
            print(f"  Chunk {i+1}/{len(chunks)}  "
                  f"(pages {page_nums[0]}–{page_nums[-1]})", flush=True)
            if not chunk_text.strip():
                if verbose:
                    print("    [SKIP] Empty chunk.")
                continue
            entries = call_claude(client, chunk_text, model, verbose,
                                  debug_dir=debug_dir, chunk_id=f"chunk-{i:04d}")
            print(f"    → {len(entries)} entries parsed"
                  + ("  ← EMPTY — check debug files" if debug_dir and not entries else ""),
                  flush=True)
            all_entries.extend(entries)
        print(f"      Total entries: {len(all_entries)}", flush=True)
    else:
        print("[4/5] Skipping adventure extraction (--monsters-only)", flush=True)

    # ── Monster extraction pass ───────────────────────────────────────────
    if extract_monsters or monsters_only:
        label = "[4/5]" if monsters_only else "[4b]"
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

    # ── Hoist stray top-level non-section entries ─────────────────────────────
    # 5etools indexes chapters by direct array position: data[ixChapter].
    # Any non-section object at the top level shifts subsequent chapters by 1.
    fixed: list[Any] = []
    for item in all_entries:
        if isinstance(item, dict) and item.get("type") != "section":
            if fixed and isinstance(fixed[-1], dict) and fixed[-1].get("type") == "section":
                fixed[-1].setdefault("entries", []).append(item)
            else:
                fixed.append({"type": "section", "name": item.get("name", "Preamble"), "entries": [item] if item.get("type") != "entries" else item.get("entries", [])})
        else:
            fixed.append(item)
    all_entries = fixed

    # ── Post-process ──────────────────────────────────────────────────────────
    if monsters_only and not all_monsters:
        print("  [WARN] No monsters found — nothing to write.", flush=True)
        return
    print("[5/5] Finalising output ...", flush=True)
    reset_ids()
    assign_ids(all_entries)

    title   = pdf_path.stem.replace("_", " ").replace("-", " ").title()
    today   = date.today().isoformat()
    toc     = build_toc(all_entries)

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

    print(f"\n{'='*62}")
    print("  Done!")

    if monsters_only:
        homebrew_obj: dict = {
            "_meta": {
                "sources": [
                    {
                        "json": short_id,
                        "abbreviation": short_id[:8],
                        "full": title,
                        "version": "1.0.0",
                        "authors": [author],
                        "convertedBy": ["pdf_to_5etools_ocr"],
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
        print(f"{'='*62}")
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
                        "convertedBy": ["pdf_to_5etools_ocr"],
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
            **({"monster": all_monsters} if all_monsters else {}),
        }
        out_path.write_text(
            json.dumps(homebrew_obj, indent="\t", ensure_ascii=False), encoding="utf-8"
        )
        print(f"  Output file: {out_path}")
        print(f"{'='*62}")
        print()
        print("  To load in 5etools (Manage Homebrew):")
        print("    1. Open  http://localhost:5050/managebrew.html")
        print("    2. Click 'Load from File'")
        print(f"   3. Select {out_path.name}")
        print("    4. Your content appears under Adventures (or Books) in the nav.")

    else:
        # ── Two-file server format: copy files into 5etools data/ dirs ──
        data_obj: dict = {"data": all_entries}
        out_path.write_text(
            json.dumps(data_obj, indent="\t", ensure_ascii=False), encoding="utf-8"
        )
        index_obj: dict = {index_key: [index_entry]}
        index_path = out_path.parent / f"{index_key}s-{short_id.lower()}.json"
        index_path.write_text(
            json.dumps(index_obj, indent="\t", ensure_ascii=False), encoding="utf-8"
        )
        print(f"  Data file  : {out_path}")
        print(f"  Index file : {index_path}")
        if all_monsters:
            bestiary_path = out_path.parent / f"bestiary-{short_id.lower()}.json"
            bestiary_obj: dict = {"monster": all_monsters}
            bestiary_path.write_text(
                json.dumps(bestiary_obj, indent="\t", ensure_ascii=False),
                encoding="utf-8"
            )
            print(f"  Bestiary   : {bestiary_path}  ({len(all_monsters)} monsters)")
        print(f"{'='*62}")
        print()
        if output_type == "adventure":
            print("  To install on your 5etools server:")
            print(f"    cp {out_path.name} ~/5etools/data/adventure/")
            print(f"    cp {index_path.name} ~/5etools/data/")
            print("    # Then add the index entry to data/adventures.json")
            print("    sudo systemctl restart 5etools")
        else:
            print("  To install on your 5etools server:")
            print(f"    cp {out_path.name} ~/5etools/data/book/")
            print(f"    cp {index_path.name} ~/5etools/data/")
            print("    # Then add the index entry to data/books.json")
            print("    sudo systemctl restart 5etools")

    print()


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _parse_page_range(value: str) -> set[int]:
    """Parse a page range like "5", "10-20", or "5,10-15" into a set of page numbers."""
    result: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        m = re.match(r'^(\d+)-(\d+)$', part)
        if m:
            result.update(range(int(m.group(1)), int(m.group(2)) + 1))
        elif re.match(r'^\d+$', part):
            result.add(int(part))
    return result


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="OCR-enhanced PDF → 5etools adventure/book JSON converter.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Output modes:
          homebrew  Single JSON file → load via Manage Homebrew > Load from File (default)
          server    Two files (data + index) → copy into 5etools data/ dirs for permanent install

        Examples:
          # Scanned book, load via UI
          python3 pdf_to_5etools_ocr.py "ScannedModule.pdf" --force-ocr

          # Mixed PDF, permanent server install
          python3 pdf_to_5etools_ocr.py "Adventure.pdf" --id MYADV --output-mode server

          # Write output to a specific directory
          python3 pdf_to_5etools_ocr.py "Book.pdf" --output-dir ~/5etools/homebrew

          # High-res OCR for small text
          python3 pdf_to_5etools_ocr.py "Sourcebook.pdf" --type book --dpi 400

          # Non-English book
          python3 pdf_to_5etools_ocr.py "Module.pdf" --lang eng+fra
        """),
    )
    parser.add_argument("pdf", type=Path, help="Input PDF")
    parser.add_argument("--type", choices=["adventure", "book"],
                        default="adventure", dest="output_type",
                        help="Content type (default: adventure)")
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
    parser.add_argument("--id", default=None,
                        help="Short uppercase ID (default: derived from filename)")
    parser.add_argument("--author", default="Unknown")
    parser.add_argument(
        "--out", type=Path, default=None,
        help="Full output filename (overrides --output-dir)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None, dest="output_dir",
        help="Directory to write output file(s) into (default: same folder as the PDF)",
    )
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--pages-per-chunk", type=int, default=DEFAULT_CHUNK,
                        dest="chunk_size")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    parser.add_argument("--force-ocr", action="store_true",
                        help="OCR every page, even those with digital text")
    parser.add_argument("--lang", default="eng",
                        help="Tesseract language code (default: eng)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
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
    parser.add_argument(
        "--no-toc-hint",
        action="store_true",
        dest="no_toc_hint",
        help="Do not inject the PDF bookmark outline as a section hint for Claude.",
    )
    parser.add_argument(
        "--pages", default=None, metavar="RANGE",
        help='Only process these pages, e.g. "10-20" or "5,10-15".',
    )
    parser.add_argument(
        "--page", type=int, default=None, metavar="N",
        help="Only process this single page number.",
    )

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
    out_path: Path = args.out or out_dir / f"{prefix}-{short_id.lower()}-ocr.json"

    debug_dir = (
        normalise_path(str(args.debug_dir)) if args.debug_dir else None
    )

    page_filter: set[int] = _parse_page_range(args.pages) if args.pages else set()
    if args.page:
        page_filter.add(args.page)

    convert(
        pdf_path=pdf_path,
        output_type=args.output_type,
        short_id=short_id,
        author=args.author,
        out_path=out_path,
        api_key=args.api_key,
        chunk_size=args.chunk_size,
        dpi=args.dpi,
        force_ocr=args.force_ocr,
        lang=args.lang,
        model=args.model,
        output_mode=args.output_mode,
        dry_run_only=args.dry_run_only,
        extract_monsters=args.extract_monsters,
        monsters_only=args.monsters_only,
        debug_dir=debug_dir,
        verbose=args.verbose,
        page_filter=page_filter,
        use_toc_hint=not args.no_toc_hint,
    )


if __name__ == "__main__":
    main()
