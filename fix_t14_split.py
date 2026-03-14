#!/usr/bin/env python3
"""
fix_t14_split.py
================
One-shot fix for a specific t14.json artefact where the converter
collapsed Dungeon Level Three, the Interdicted Prison of Zuggtmoy, and
the Greater Temple Room Key into a single chapter.

What this script does
---------------------
1. Renames ch14 "Dungeon" → "Dungeon Level One".
2. Splits the merged chapter (named "Dungeon Level One" but containing
   rooms 301–435) into three proper chapters:
     • Dungeon Level Three  (entries[0:42]  — intro + rooms 301–338)
     • The Interdicted Prison of Zuggtmoy  (entries[42:47] — rooms 350–353)
     • Room Key             (entries[47:]   — rooms 401–435)
3. Extracts "The Greater Temple" and "Temple Guard Forces and Tactical Notes"
   sub-entries from room 353 in the Zuggtmoy chapter, then renames the
   following "Room Key" chapter to "The Greater Temple" and prepends them.
4. Reassigns sequential IDs.
5. Rebuilds adventure.contents from the corrected chapter list.

Usage
-----
    python3 fix_t14_split.py [input.json [output.json]]

Defaults: ~/t14.json, overwritten in place (backup kept as .bak).
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any


# ── Helpers ───────────────────────────────────────────────────────────────────

def _section(name: str, entries: list[Any]) -> dict:
    return {"type": "section", "name": name, "entries": entries}


def build_toc(chapters: list[dict]) -> list[dict]:
    toc: list[dict] = []
    for ch in chapters:
        if not isinstance(ch, dict) or ch.get("type") != "section":
            continue
        item: dict = {"name": ch.get("name", "Untitled"), "headers": []}
        for sub in ch.get("entries", []):
            if isinstance(sub, dict) and sub.get("type") in ("entries", "section") and sub.get("name"):
                item["headers"].append(sub["name"])
        toc.append(item)
    return toc


_id_counter = 0

def _reset_ids() -> None:
    global _id_counter
    _id_counter = 0

def assign_ids(entries: list[Any]) -> None:
    global _id_counter
    for entry in entries:
        if isinstance(entry, dict):
            if entry.get("type") in ("section", "entries", "inset"):
                entry["id"] = f"{_id_counter:03d}"
                _id_counter += 1
            assign_ids(entry.get("entries", []))
            assign_ids(entry.get("items", []))


# ── Main fix ──────────────────────────────────────────────────────────────────

def fix(in_path: Path, out_path: Path) -> None:
    print(f"Reading {in_path} …")
    with open(in_path, encoding="utf-8") as f:
        obj = json.load(f)

    adv_list  = obj.get("adventure") or obj.get("book") or []
    data_list = obj.get("adventureData") or obj.get("bookData") or []
    if not adv_list or not data_list:
        sys.exit("ERROR: cannot find adventure/adventureData keys.")

    adv_meta = adv_list[0]
    chapters: list[dict] = data_list[0]["data"]
    print(f"Chapters before fix: {len(chapters)}")

    # ── 1. Find and rename "Dungeon" → "Dungeon Level One" ────────────────────
    dungeon_ch = next(
        (i for i, ch in enumerate(chapters) if ch.get("name") == "Dungeon"),
        None,
    )
    if dungeon_ch is not None:
        chapters[dungeon_ch]["name"] = "Dungeon Level One"
        print(f"  [1] Renamed ch{dungeon_ch} 'Dungeon' → 'Dungeon Level One'")
    else:
        print("  [1] 'Dungeon' chapter not found — skipping rename")

    # ── 2. Find the merged chapter and split it ────────────────────────────────
    # Heuristic: find the chapter whose entries span rooms 301–x AND 401–y.
    # (It might be named "Dungeon Level One" or "Dungeon Level Three".)
    merged_idx: int | None = None
    for i, ch in enumerate(chapters):
        names = [
            e.get("name", "") for e in ch.get("entries", []) if isinstance(e, dict)
        ]
        has_300s = any(re.match(r"^3\d\d[a-z]?\.", n) for n in names)
        has_400s = any(re.match(r"^4\d\d[a-z]?\.", n) for n in names)
        if has_300s and has_400s:
            merged_idx = i
            break

    if merged_idx is None:
        print("  [2] Merged chapter not found — nothing to split.")
    else:
        ch = chapters[merged_idx]
        print(f"  [2] Found merged chapter: ch{merged_idx} '{ch['name']!r}' "
              f"({len(ch['entries'])} entries)")

        entries = ch["entries"]

        # Find split points by first room number in each range
        zuggtmoy_start: int | None = None  # first 3xx room >= 339 or first 3xx after 338
        temple_start:   int | None = None  # first 4xx room

        # Rooms <= 338 → Level Three; 339–399 → Zuggtmoy; 400+ → Room Key
        ZUGGTMOY_ROOM_RE = re.compile(r"^3([3-9]\d|[4-9]\d|\d{2})[a-z]?\.")
        TEMPLE_ROOM_RE   = re.compile(r"^4\d\d")

        for idx, e in enumerate(entries):
            if not isinstance(e, dict):
                continue
            name = e.get("name", "")
            if temple_start is None and TEMPLE_ROOM_RE.match(name):
                temple_start = idx
            if zuggtmoy_start is None and ZUGGTMOY_ROOM_RE.match(name):
                # First room in 339+ range
                m = re.match(r"^3(\d\d)", name)
                if m and int(m.group(1)) >= 39:
                    zuggtmoy_start = idx

        # If no explicit 339+ room exists, look for the gap: first room after
        # a long run of 3xx rooms whose predecessor is > 338
        if zuggtmoy_start is None:
            # Walk backwards from temple_start to find where 3xx rooms >= 339 begin
            if temple_start:
                for idx in range(temple_start - 1, -1, -1):
                    e = entries[idx]
                    if not isinstance(e, dict):
                        continue
                    name = e.get("name", "")
                    m = re.match(r"^3(\d\d)", name)
                    if m and int(m.group(1)) <= 38:
                        # This is the last ≤ 338 room; zuggtmoy starts just after
                        zuggtmoy_start = idx + 1
                        break

        if zuggtmoy_start is None:
            zuggtmoy_start = temple_start  # fallback: no Prison section

        print(f"       Split points: zuggtmoy_start={zuggtmoy_start}, "
              f"temple_start={temple_start}")

        level3_entries  = entries[:zuggtmoy_start]
        zuggtmoy_entries = entries[zuggtmoy_start:temple_start]
        temple_entries  = entries[temple_start:]

        new_chapters = [
            _section("Dungeon Level Three", level3_entries),
            _section("The Interdicted Prison of Zuggtmoy", zuggtmoy_entries),
            _section("Room Key", temple_entries),
        ]
        for nc in new_chapters:
            print(f"       → '{nc['name']}': {len(nc['entries'])} entries")

        chapters[merged_idx:merged_idx + 1] = new_chapters
        print(f"  [2] Split into 3 chapters; total now: {len(chapters)}")

    # ── 3. Extract Greater Temple from Zuggtmoy chapter ──────────────────────
    ZUGGTMOY_NAME = "The Interdicted Prison of Zuggtmoy"
    GREATER_TEMPLE_CHAPTER = "Room Key"
    EXTRACT_NAMES = {"The Greater Temple", "Temple Guard Forces and Tactical Notes"}

    zuggtmoy_ch = next(
        (ch for ch in chapters if ch.get("name") == ZUGGTMOY_NAME),
        None,
    )
    room_key_idx = next(
        (i for i, ch in enumerate(chapters) if ch.get("name") == GREATER_TEMPLE_CHAPTER),
        None,
    )

    if zuggtmoy_ch is None:
        print(f"  [3] '{ZUGGTMOY_NAME}' chapter not found — skipping Greater Temple fix")
    elif room_key_idx is None:
        print(f"  [3] '{GREATER_TEMPLE_CHAPTER}' chapter not found — skipping Greater Temple fix")
    else:
        # Find room 353 by scanning Zuggtmoy entries
        room353 = next(
            (e for e in zuggtmoy_ch.get("entries", [])
             if isinstance(e, dict) and re.match(r"^353[a-z]?\.", e.get("name", ""))),
            None,
        )
        if room353 is None:
            print("  [3] Room 353 not found in Zuggtmoy chapter — skipping extraction")
        else:
            keep, extracted = [], []
            for e in room353.get("entries", []):
                if isinstance(e, dict) and e.get("name") in EXTRACT_NAMES:
                    extracted.append(e)
                else:
                    keep.append(e)
            room353["entries"] = keep
            print(f"  [3] Extracted {len(extracted)} entries from room 353: "
                  f"{[e.get('name') for e in extracted]}")

            gt_ch = chapters[room_key_idx]
            gt_ch["name"] = "The Greater Temple"
            gt_ch["entries"] = extracted + gt_ch["entries"]
            print(f"  [3] Renamed '{GREATER_TEMPLE_CHAPTER}' → 'The Greater Temple'; "
                  f"prepended {len(extracted)} entries ({len(gt_ch['entries'])} total)")

    # ── 4. Reassign IDs ───────────────────────────────────────────────────────
    _reset_ids()
    assign_ids(chapters)
    print(f"  [4] IDs reassigned")

    # ── 5. Rebuild TOC ────────────────────────────────────────────────────────
    adv_meta["contents"] = build_toc(chapters)
    print(f"  [5] TOC rebuilt: {len(adv_meta['contents'])} chapters")

    # ── Write output ──────────────────────────────────────────────────────────
    if out_path == in_path:
        bak = in_path.with_suffix(".json.bak")
        shutil.copy2(in_path, bak)
        print(f"  Backup: {bak}")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent="\t", ensure_ascii=False)
    print(f"  Written: {out_path}")


if __name__ == "__main__":
    default = Path.home() / "t14.json"
    in_path  = Path(sys.argv[1]) if len(sys.argv) >= 2 else default
    out_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else in_path
    fix(in_path, out_path)
