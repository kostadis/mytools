#!/usr/bin/env python3
"""
fix_t14_1e.py
=============
Post-process adventure-t14-1e.json to fix structural issues specific to the
Temple of Elemental Evil conversion.

Fixes applied
-------------
1. Chapter 16 ("Dungeon") renamed to "Dungeon Level One"; the "Level One"
   sub-entry wrapper is dissolved — its contents (random-encounter table,
   roll-text string, Details entry, and the "Room Key" rooms 101–115) are
   promoted to direct children of the chapter.

2. "Room Key" wrapper entries in dungeon chapters are dissolved — their
   child room entries are promoted to siblings.

3. In all dungeon chapters, any entry that is neither a numbered room
   (name starts with a digit) nor a random-table/inset, and that appears
   *after* the first numbered room, is folded into the most recent
   preceding room.  Orphaned plain strings between rooms are folded in the
   same way.  Entries appearing before the first room are left in place as
   chapter-level introduction text.

4. Room 403 (Study): Barkinar and Deggum stat blocks replaced/added;
   "Senshock (continued)" extracted and promoted to room "404. Mages' Study".

5. adventure.contents is rebuilt from the normalised data so sidebar
   navigation stays in sync.

Usage
-----
    python3 fix_t14_1e.py [input.json [output.json]]

Defaults: ~/adventure-t14-1e.json, overwritten in place (backup kept).
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

# ── Chapter indices (0-based) that are "dungeon" chapters ────────────────────
DUNGEON_CHAPTERS: list[int] = [16, 17, 18, 19, 20]

# ── Helpers ───────────────────────────────────────────────────────────────────

def is_numbered_room(entry: Any) -> bool:
    """Return True if entry is a numbered room (name starts with a digit)."""
    if isinstance(entry, str):
        return False
    return bool(re.match(r"^\d", entry.get("name", "")))


def is_random_table(entry: Any) -> bool:
    """Return True if entry is a random-encounter table or inset block."""
    if isinstance(entry, str):
        return False
    if entry.get("type") in ("table", "inset"):
        return True
    return bool(re.match(r"random", entry.get("name", ""), re.I))


# ── Fix 1: Chapter 16 rename + dissolve "Level One" wrapper ──────────────────

def fix_ch16(chapter: dict) -> None:
    """Rename ch16 and flatten the Level One / Room Key nesting."""
    chapter["name"] = "Dungeon Level One"

    entries = chapter.get("entries", [])
    if not entries:
        return

    first = entries[0]
    if not (isinstance(first, dict) and first.get("name") == "Level One"):
        print("  [fix1] WARNING: expected 'Level One' as first entry — skipping")
        return

    # Dissolve Level One: collect its children, flattening the inner Room Key
    promoted: list[Any] = []
    for child in first.get("entries", []):
        if isinstance(child, dict) and child.get("name") == "Room Key":
            # Inline Room Key's rooms
            promoted.extend(child.get("entries", []))
        else:
            promoted.append(child)

    chapter["entries"] = promoted + entries[1:]
    print(f"  [fix1] Dissolved 'Level One' wrapper → {len(promoted)} entries promoted")


# ── Fix 2: Dissolve top-level "Room Key" wrappers ────────────────────────────

def dissolve_room_keys(chapter: dict) -> None:
    """Inline any top-level 'Room Key' entry in a dungeon chapter."""
    entries = chapter.get("entries", [])
    new_entries: list[Any] = []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("name") == "Room Key":
            rooms = entry.get("entries", [])
            new_entries.extend(rooms)
            print(f"  [fix2] Dissolved 'Room Key' → {len(rooms)} rooms inlined")
        else:
            new_entries.append(entry)
    chapter["entries"] = new_entries


# ── Fix 3: Fold orphan entries into preceding room ────────────────────────────

def fold_orphans(chapter: dict) -> None:
    """
    Walk the chapter's top-level entries.  After the first numbered room
    has been seen, any entry that is not itself a numbered room or a
    random-table/inset is appended to the 'entries' list of the most
    recently seen room.
    """
    entries = chapter.get("entries", [])
    result: list[Any] = []
    last_room: dict | None = None
    folded = 0

    for entry in entries:
        if is_numbered_room(entry):
            result.append(entry)
            last_room = entry
        elif is_random_table(entry):
            # Tables/insets are always kept at chapter level
            result.append(entry)
        elif isinstance(entry, str):
            if last_room is not None:
                # Orphan string between/after rooms → fold
                last_room.setdefault("entries", []).append(entry)
                folded += 1
            else:
                # Before first room → chapter intro, keep
                result.append(entry)
        else:
            # Named non-room entry
            if last_room is not None:
                last_room.setdefault("entries", []).append(entry)
                folded += 1
                print(f"  [fix3] Folded {entry.get('name')!r} into {last_room.get('name')!r}")
            else:
                # Before first room → chapter intro, keep
                result.append(entry)

    if folded:
        print(f"  [fix3] Total folded: {folded} entries")
    chapter["entries"] = result


# ── Fix 4: Room 403/404 — stat blocks and Senshock extraction ────────────────

def fix_room_403_404(chapters: list) -> None:
    """
    Fix structural and content issues in the Greater Temple dungeon chapter:

    a) Replace the truncated Barkinar stat line with the full stats.
    b) Add the full Deggum stat block (missing from converted output).
    c) Extract the "Senshock (continued)" sub-entry from room 403 and promote
       it to its own top-level room entry "404. Mages' Study".
    """
    gt_ch = next(
        (ch for ch in chapters if ch.get("name") == "The Greater Temple"),
        None,
    )
    if gt_ch is None:
        print("  [fix4] 'The Greater Temple' chapter not found — skipping")
        return

    entries = gt_ch.get("entries", [])
    r403_idx = next(
        (i for i, e in enumerate(entries)
         if isinstance(e, dict) and re.match(r"^403[a-z]?\.", e.get("name", ""))),
        None,
    )
    if r403_idx is None:
        print("  [fix4] Room 403 not found — skipping")
        return

    r403 = entries[r403_idx]

    # ── a) Barkinar ───────────────────────────────────────────────────────────
    barkinar = next(
        (e for e in r403.get("entries", [])
         if isinstance(e, dict) and e.get("name") == "Barkinar"),
        None,
    )
    if barkinar:
        desc = barkinar["entries"][0] if barkinar.get("entries") else ""
        barkinar["entries"] = [
            desc,
            "{@i Barkinar: AC \u22121 (plate +1, shield +2), MV 12\", Level 7 Cleric,"
            " hp 60, #AT 1, D by weapon (staff of striking) or spell,"
            " SA wears boots of levitation, SD spells; XP 1680}",
            "S 11 I 16 W 17 D 10 Co 16 Ch 8",
            {
                "type": "entries",
                "name": "Spells Memorized",
                "entries": [
                    "{@b First level:} {@spell command}, {@spell cure light wounds} (\u00d72),"
                    " {@spell remove fear}, {@spell sanctuary}",
                    "{@b Second level:} {@spell hold person} (\u00d72), resist fire,"
                    " {@spell silence} 15\u2019 radius, slow poison",
                    "{@b Third level:} {@spell dispel magic}, prayer, {@spell bestow curse}",
                    "{@b Fourth level:} cure serious wounds",
                ],
            },
        ]
        print("  [fix4a] Replaced Barkinar stat block")
    else:
        print("  [fix4a] Barkinar sub-entry not found — skipped")

    # ── b) Deggum ─────────────────────────────────────────────────────────────
    deggum = next(
        (e for e in r403.get("entries", [])
         if isinstance(e, dict) and e.get("name") == "Deggum"),
        None,
    )
    if deggum:
        desc = deggum["entries"][0] if deggum.get("entries") else ""
        deggum["entries"] = [
            desc,
            "{@i Deggum: AC 2 (chain & shield), MV 12\", Level 5/4 Cleric/Magic-User,"
            " hp 21, #AT 1, D by weapon or spell, SA spells,"
            " SD ring of fire resistance; XP 1118}",
            "S 12 I 15 W 18 D 7 Co 10 Ch 11",
            {
                "type": "entries",
                "name": "Cleric Spells Memorized",
                "entries": [
                    "{@b First level:} {@spell bless}, {@spell cure light wounds},"
                    " {@spell detect magic}, {@spell sanctuary} (\u00d72)",
                    "{@b Second level:} {@spell augury}, chant, {@spell hold person},"
                    " poison, spiritual hammer",
                    "{@b Third level:} continual darkness, {@spell animate dead}",
                ],
            },
            {
                "type": "entries",
                "name": "Magic-User Spells Memorized",
                "entries": [
                    "{@b First level:} {@spell magic missile} (\u00d73)",
                    "{@b Second level:} {@spell invisibility} (\u00d72)",
                ],
            },
        ]
        print("  [fix4b] Replaced Deggum stat block")
    else:
        print("  [fix4b] Deggum sub-entry not found — skipped")

    # ── c) Senshock (continued) → room 404 ───────────────────────────────────
    r403_entries = r403.get("entries", [])
    senshock_idx = next(
        (i for i, e in enumerate(r403_entries)
         if isinstance(e, dict) and e.get("name") == "Senshock (continued)"),
        None,
    )
    if senshock_idx is not None:
        senshock_cont = r403_entries.pop(senshock_idx)
        r404: dict = {
            "type": "entries",
            "name": "404. Mages\u2019 Study",
            "entries": senshock_cont.get("entries", []),
        }
        entries.insert(r403_idx + 1, r404)
        print(f"  [fix4c] Created room 404 from 'Senshock (continued)'"
              f" ({len(r404['entries'])} entries)")
    else:
        print("  [fix4c] 'Senshock (continued)' not in room 403 — skipped")


# ── Fix 5: Rebuild adventure.contents ────────────────────────────────────────

def build_toc(chapters: list[dict]) -> list[dict]:
    """Rebuild the adventure contents (TOC) from the normalised chapter data."""
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


# ── Main ──────────────────────────────────────────────────────────────────────

def fix(in_path: Path, out_path: Path) -> None:
    print(f"Reading {in_path} …")
    with open(in_path, encoding="utf-8") as f:
        obj = json.load(f)

    adv_list = obj.get("adventure") or obj.get("book") or []
    data_list = obj.get("adventureData") or obj.get("bookData") or []
    if not adv_list or not data_list:
        sys.exit("ERROR: could not find adventure/adventureData keys in JSON.")

    adv_meta = adv_list[0]
    chapters: list[dict] = data_list[0]["data"]

    print(f"Total chapters: {len(chapters)}\n")

    for idx in DUNGEON_CHAPTERS:
        if idx >= len(chapters):
            print(f"Chapter {idx}: out of range, skipped")
            continue

        ch = chapters[idx]
        print(f"Chapter {idx}: {ch.get('name')!r}")

        if idx == 16:
            fix_ch16(ch)

        dissolve_room_keys(ch)
        fold_orphans(ch)
        print()

    # Fix 4: room 403 stat blocks + extract room 404
    print("Fix 4: rooms 403/404")
    fix_room_403_404(chapters)
    print()

    # Rebuild TOC
    toc = build_toc(chapters)
    adv_meta["contents"] = toc
    print(f"TOC rebuilt: {len(toc)} chapters\n")

    # Write output
    if out_path == in_path:
        bak = in_path.with_suffix(".json.bak")
        shutil.copy2(in_path, bak)
        print(f"Backup: {bak}")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent="\t", ensure_ascii=False)
    print(f"Written: {out_path}")


if __name__ == "__main__":
    default_in = Path.home() / "adventure-t14-1e.json"

    if len(sys.argv) >= 2:
        in_path = Path(sys.argv[1])
    else:
        in_path = default_in

    out_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else in_path

    fix(in_path, out_path)
