#!/usr/bin/env python3
"""
fix_adventure_json.py
=====================
Post-process a converter-generated 5etools adventure JSON to fix chapter-index
mismatches that cause duplicate-named sections (e.g. "Room Key" in multiple
levels) to all resolve to the same anchor in the 5etools viewer.

Root cause
----------
The converter accumulates entries from all chunks into a flat list and stores
it directly as adventureData.data[].  Non-section entries (strings, type
"entries", etc.) appear in data[] but not in adventure.contents[], causing
data[i] and contents[i] to diverge.  5etools' headerMap lookup uses the
data[] index as chapter number, so sidebar links built from contents[] resolve
to the wrong chapter → full-book-mode navigation always scrolls to the first
occurrence.

Fix
---
1.  normalize_chapters() — fold non-section top-level data entries into the
    preceding section so every data[i] is a section and data[i] == contents[i].
2.  Reassign sequential IDs (must be unique across the document).
3.  Rebuild adventure.contents from the normalised data.

Usage
-----
    python3 fix_adventure_json.py input.json [output.json]

If output.json is omitted the input file is overwritten (a .bak copy is kept).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any


# ── helpers ───────────────────────────────────────────────────────────────────

def normalize_chapters(entries: list[Any], default_name: str) -> list[dict]:
    """Fold non-section top-level entries into the preceding section."""
    chapters: list[dict] = []
    pending: list[Any] = []

    for entry in entries:
        if isinstance(entry, dict) and entry.get("type") == "section":
            if pending:
                if chapters:
                    chapters[-1].setdefault("entries", []).extend(pending)
                else:
                    chapters.append({"type": "section", "name": default_name, "entries": pending})
                pending = []
            chapters.append(entry)
        else:
            pending.append(entry)

    if pending:
        if chapters:
            chapters[-1].setdefault("entries", []).extend(pending)
        else:
            chapters.append({"type": "section", "name": default_name, "entries": pending})

    return chapters


_id_counter = 0

def reset_ids() -> None:
    global _id_counter
    _id_counter = 0


def assign_ids(entries: list[Any]) -> None:
    global _id_counter
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") in ("section", "entries", "inset"):
            entry["id"] = f"{_id_counter:03d}"
            _id_counter += 1
        if "entries" in entry:
            assign_ids(entry["entries"])
        if "items" in entry:
            assign_ids(entry["items"])


def build_toc(chapters: list[dict]) -> list[dict]:
    toc: list[dict] = []
    for ch in chapters:
        if not isinstance(ch, dict) or ch.get("type") != "section":
            continue
        ch_name = ch.get("name", "Untitled")
        item: dict = {"name": ch_name, "headers": []}
        ch_name_norm = (ch_name or "").strip().casefold()
        for sub in ch.get("entries", []):
            if isinstance(sub, dict) and sub.get("type") in ("entries", "section") and sub.get("name"):
                sub_name = sub["name"]
                # Don't list the chapter's own name in its mini-ToC — the
                # main sidebar already shows the chapter heading; repeating
                # it as a header produces a visible title + duplicate
                # title-as-subheader in 5etools.
                if (sub_name or "").strip().casefold() == ch_name_norm:
                    continue
                item["headers"].append(sub_name)
        toc.append(item)
    return toc


# ── main ──────────────────────────────────────────────────────────────────────

def fix(in_path: Path, out_path: Path) -> None:
    print(f"Reading {in_path} …")
    with open(in_path, encoding="utf-8") as f:
        obj = json.load(f)

    adventure_list = obj.get("adventure") or obj.get("book") or []
    data_list = obj.get("adventureData") or obj.get("bookData") or []

    if not adventure_list or not data_list:
        sys.exit("ERROR: could not find adventure/adventureData keys in JSON.")

    adv_meta = adventure_list[0]
    adv_data = data_list[0]

    raw_entries: list[Any] = adv_data.get("data", [])
    default_name = adv_meta.get("name", "Adventure")

    print(f"  Before: {len(raw_entries)} top-level data entries, "
          f"{len(adv_meta.get('contents', []))} contents entries")

    chapters = normalize_chapters(raw_entries, default_name)

    reset_ids()
    assign_ids(chapters)

    toc = build_toc(chapters)

    adv_data["data"] = chapters
    adv_meta["contents"] = toc

    print(f"  After:  {len(chapters)} chapters (data == contents: {len(chapters) == len(toc)})")

    # Keep a backup if overwriting in place
    if out_path == in_path:
        bak = in_path.with_suffix(".json.bak")
        shutil.copy2(in_path, bak)
        print(f"  Backup: {bak}")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent="\t", ensure_ascii=False)

    print(f"  Written: {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(f"Usage: {sys.argv[0]} input.json [output.json]")

    in_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else in_path

    fix(in_path, out_path)
