#!/usr/bin/env python3
"""
patch_5e_chapters.py
====================
Fix specific chapters in an existing 5e adventure JSON by re-converting them
from the original 1e source using the corrected leaf-room approach.

Use this when the initial conversion produced incorrect JSON structure
(rooms nested inside other rooms, or rooms hidden inside a "Room Key" entry).

What it does
------------
For each specified chapter:
  1. Restores the chapter structure from the original 1e source JSON
     (this fixes any nesting damage from the previous run)
  2. Re-runs the 5e conversion using the fixed leaf-room approach
     (converts only the individual room entries in-place)
  3. Writes the result back into the existing 5e JSON file

All other chapters are left exactly as they are.

Usage
-----
    python3 patch_5e_chapters.py source_1e.json target_5e.json \\
        --chapters 16,19-20 [options]

Options
-------
    --api-key KEY     Anthropic API key (default: ANTHROPIC_API_KEY env var)
    --model MODEL     Claude model (default: claude-sonnet-4-6)
    --dry-run         Show what would be converted without calling the API
    --verbose         Show prompt sizes and API responses
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# Re-use all conversion logic from convert_1e_to_5e.py
sys.path.insert(0, str(Path(__file__).parent))
from convert_1e_to_5e import (
    _CHAPTER_ZONE,
    SKIP_CHAPTERS,
    convert_chapter,
    _parse_chapters,
)


def patch(src_1e: Path, target_5e: Path, chapter_filter: set[int],
          client, model: str, verbose: bool, dry_run: bool) -> None:

    print(f"Reading 1e source: {src_1e}")
    with open(src_1e, encoding="utf-8") as f:
        src_obj = json.load(f)

    print(f"Reading 5e target: {target_5e}")
    with open(target_5e, encoding="utf-8") as f:
        tgt_obj = json.load(f)

    # Locate data arrays
    src_data_key = "adventureData" if "adventureData" in src_obj else "bookData"
    tgt_data_key = "adventureData" if "adventureData" in tgt_obj else "bookData"

    src_chapters: list[dict] = src_obj[src_data_key][0]["data"]
    tgt_chapters: list[dict] = tgt_obj[tgt_data_key][0]["data"]

    if len(src_chapters) != len(tgt_chapters):
        print(f"WARNING: chapter count mismatch — "
              f"source has {len(src_chapters)}, target has {len(tgt_chapters)}.")
        print("         Chapters beyond the shorter list will be skipped.")

    chapters_to_patch = sorted(chapter_filter)
    print(f"Chapters to patch: {chapters_to_patch}\n")

    for idx in chapters_to_patch:
        if idx >= len(src_chapters):
            print(f"[{idx:2d}] ← out of range, skipped")
            continue

        name = src_chapters[idx].get("name", f"Chapter {idx}")
        print(f"[{idx:2d}] {name}")

        if idx in SKIP_CHAPTERS:
            print("  (skipped — intro/title chapter)")
            continue

        if idx not in _CHAPTER_ZONE:
            print("  (no zone defined — not a content chapter)")
            continue

        # Step 1: restore clean structure from 1e source (deep copy)
        import copy
        clean_chapter = copy.deepcopy(src_chapters[idx])

        # Step 2: convert in-place using fixed leaf-room approach
        convert_chapter(clean_chapter, idx, client, model, verbose, dry_run)

        # Step 3: splice into the target 5e JSON
        if idx < len(tgt_chapters):
            tgt_chapters[idx] = clean_chapter
        else:
            # Target is shorter — append
            while len(tgt_chapters) < idx:
                tgt_chapters.append({})
            tgt_chapters.append(clean_chapter)

        print()

    if dry_run:
        print("(dry run — no file written)")
        return

    # Keep a backup
    bak = target_5e.with_suffix(".json.bak")
    shutil.copy2(target_5e, bak)
    print(f"Backup written to {bak}")

    with open(target_5e, "w", encoding="utf-8") as f:
        json.dump(tgt_obj, f, indent="\t", ensure_ascii=False)
    print(f"Patched file written to {target_5e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-convert specific chapters of a 5e adventure JSON")
    parser.add_argument("source_1e", type=Path,
                        help="Original 1e source JSON (structural reference)")
    parser.add_argument("target_5e", type=Path,
                        help="Existing 5e JSON to patch (modified in place)")
    parser.add_argument("--chapters", required=True,
                        help="Chapters to re-convert, e.g. '16' or '19-20' or '16,19,20'")
    parser.add_argument("--api-key")
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        sys.exit("ERROR: set ANTHROPIC_API_KEY or pass --api-key")

    chapter_filter = _parse_chapters(args.chapters)

    client = None
    if not args.dry_run:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

    patch(args.source_1e, args.target_5e, chapter_filter,
          client, args.model, args.verbose, args.dry_run)


if __name__ == "__main__":
    main()
