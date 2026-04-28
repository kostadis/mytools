#!/usr/bin/env python3
"""
convert_1e_to_5e.py
===================
Transform a 1e-converter-generated 5etools adventure JSON into a 5th Edition
version, keeping all flavour text intact while replacing mechanics.

What it does
------------
- Removes 1e stat-block lines ({@i AC X; MV X; HD X ...})
- Adds {@creature name} tags to creature mentions in descriptive text
- Appends a "5e Encounter" inset per room with XP budget and difficulty rating
- Updates trap mechanics (save vs. X → DC N saving throw)
- Adjusts encounter sizes for 5e action economy

Encounter level targets (T1-4 specific)
----------------------------------------
  Chapters 3-8   Hommlet / surface       Party levels 1–4
  Chapters 9-10  Moathouse               Party levels 3–5
  Chapters 11-12 Nulb (transition)       Party levels 4–5
  Chapters 13-15 Temple approach         Party level 5
  Chapter  16    Dungeon Level 1         Party levels 5–7  (sandbox)
  Chapter  17    Dungeon Level 2         Party levels 6–8  (sandbox)
  Chapter  18    Dungeon Level 3         Party level 9
  Chapters 19-20 Dungeon Level 4 / Prison Party level 10 (deadly)
  Chapters 21-26 Elemental Nodes         Party level 10 (deadly)

Usage
-----
    python3 convert_1e_to_5e.py input.json output.json [options]

Options
-------
    --api-key KEY       Anthropic API key (default: ANTHROPIC_API_KEY env var)
    --model MODEL       Claude model (default: claude-sonnet-4-6)
    --chapters A-B      Only process chapters A through B (0-indexed)
    --dry-run           Print what would be sent without calling the API
    --verbose           Show raw API responses
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

# ── Zone configuration ─────────────────────────────────────────────────────────

ZONES: dict[str, dict] = {
    "hommlet": {
        "chapters": list(range(3, 9)),
        "level_range": (1, 4),
        "label": "Village of Hommlet (party levels 1–4)",
        "difficulty": "medium encounters typical; boss fights hard",
        "party_level": 2,
    },
    "moathouse": {
        "chapters": [9, 10],
        "level_range": (3, 5),
        "label": "Ruins of the Moathouse (party levels 3–5)",
        "difficulty": "medium to hard; boss fight (Lareth) is hard",
        "party_level": 4,
    },
    "nulb": {
        "chapters": [11, 12],
        "level_range": (4, 5),
        "label": "Nulb (party levels 4–5, transition zone)",
        "difficulty": "medium encounters; social encounters common",
        "party_level": 5,
    },
    "temple_approach": {
        "chapters": [13, 14, 15],
        "level_range": (5, 6),
        "label": "Temple Approach / Ground Level (party level 5)",
        "difficulty": "medium to hard",
        "party_level": 5,
    },
    "temple_l1": {
        "chapters": [16],
        "level_range": (5, 7),
        "label": "Temple Dungeon Level 1 (sandbox, party levels 5–7)",
        "difficulty": "mixed easy/medium/hard — sandbox; some rooms easy, some hard. "
                      "Boss fights hard or deadly. Party grows from level 5 to 7 here.",
        "party_level": 6,
    },
    "temple_l2": {
        "chapters": [17],
        "level_range": (6, 8),
        "label": "Temple Dungeon Level 2 (sandbox, party levels 6–8)",
        "difficulty": "mixed medium/hard — sandbox continues; elemental temple leaders "
                      "are hard or deadly boss fights.",
        "party_level": 7,
    },
    "temple_l3": {
        "chapters": [18],
        "level_range": (9, 9),
        "label": "Temple Dungeon Level 3 (party level 9)",
        "difficulty": "hard encounters standard; boss fights deadly",
        "party_level": 9,
    },
    "temple_l4": {
        "chapters": [19, 20],
        "level_range": (10, 10),
        "label": "Temple Level 4 / Prison of Zuggtmoy (party level 10)",
        "difficulty": "deadly throughout. Ideal path: party destroys elemental nodes, "
                      "defeats Zuggtmoy, THEN returns to deal with cult leaders here. "
                      "Cult leaders should be hard to deadly.",
        "party_level": 10,
    },
    "nodes": {
        "chapters": list(range(21, 27)),
        "level_range": (10, 10),
        "label": "Elemental Nodes (party level 10, very deadly)",
        "difficulty": "deadly throughout. Alien dimensions; retreat is difficult.",
        "party_level": 10,
    },
    "appendix": {
        "chapters": list(range(27, 31)),
        "level_range": (1, 10),
        "label": "Appendix",
        "difficulty": "reference material — update stat blocks to 5e format only",
        "party_level": 5,
    },
}

_CHAPTER_ZONE: dict[int, dict] = {}
for _z in ZONES.values():
    for _ch in _z["chapters"]:
        _CHAPTER_ZONE[_ch] = _z

SKIP_CHAPTERS = {0, 1, 2}

# ── 5e XP thresholds (party of 4) ─────────────────────────────────────────────

XP_THRESHOLDS: dict[int, dict[str, int]] = {
    1:  {"easy": 100,  "medium": 200,  "hard": 300,  "deadly": 400},
    2:  {"easy": 200,  "medium": 400,  "hard": 600,  "deadly": 800},
    3:  {"easy": 300,  "medium": 600,  "hard": 900,  "deadly": 1600},
    4:  {"easy": 500,  "medium": 1000, "hard": 1500, "deadly": 2000},
    5:  {"easy": 1000, "medium": 2000, "hard": 3000, "deadly": 4400},
    6:  {"easy": 1200, "medium": 2400, "hard": 3600, "deadly": 5600},
    7:  {"easy": 1400, "medium": 3000, "hard": 4400, "deadly": 6800},
    8:  {"easy": 1800, "medium": 3600, "hard": 5600, "deadly": 8400},
    9:  {"easy": 2200, "medium": 4400, "hard": 6400, "deadly": 9600},
    10: {"easy": 2400, "medium": 4800, "hard": 7600, "deadly": 11200},
}

# ── Creature mapping reference ─────────────────────────────────────────────────

CREATURE_MAPPING = """
## Humanoids & NPCs
Level 0 human (farmer/commoner) → commoner (CR 0)
Level 0 human fighter (militia) → guard (CR 1/8)
Level 1-2 fighter → bandit (CR 1/8) or guard (CR 1/8)
Level 3-4 fighter → veteran (CR 3)
Level 5+ fighter → gladiator (CR 5)
Level 1-2 cleric → acolyte (CR 1/4) or priest (CR 2)
Level 3+ cleric → priest (CR 2)
Level 1-3 thief → spy (CR 1)
Level 5+ thief/assassin → assassin (CR 8)
Level 3+ magic-user → mage (CR 6)
Brigand/bandit (0-level) → bandit (CR 1/8)
Bandit leader/captain → bandit captain (CR 2)
Man-at-arms → guard (CR 1/8)
Cultist (any temple) → cultist (CR 1/8) or cult fanatic (CR 2) by rank
Temple priest → priest (CR 2) or mage (CR 6) by level

## Common monsters
Gnoll → gnoll (CR 1/2)
Gnoll leader/sergeant → gnoll pack lord (CR 2)
Goblin → goblin (CR 1/4)
Hobgoblin → hobgoblin (CR 1/2)
Hobgoblin captain → hobgoblin captain (CR 3)
Bugbear → bugbear (CR 1)
Bugbear chief → bugbear chief (CR 3)
Ogre → ogre (CR 2)
Troll → troll (CR 5)
Hill giant → hill giant (CR 5)
Stone giant → stone giant (CR 7)

## Undead
Skeleton → skeleton (CR 1/4)
Zombie → zombie (CR 1/4)
Ghoul → ghoul (CR 1)
Ghast → ghast (CR 2)
Shadow → shadow (CR 1/2)
Specter → specter (CR 1)
Wight → wight (CR 3)
Wraith → wraith (CR 5)
Mummy → mummy (CR 3)
Vampire → vampire (CR 13)

## Oozes & slimes
Gray ooze → gray ooze (CR 1/2)
Ochre jelly → ochre jelly (CR 2)
Black pudding → black pudding (CR 4)
Gelatinous cube → gelatinous cube (CR 2)
Green slime → green slime hazard (no CR; contact = 1d6 acid/round)

## Animals & beasts
Farm dog / war dog → mastiff (CR 1/8) or wolf (CR 1/4)
Giant rat → giant rat (CR 1/8)
Giant centipede → giant centipede (CR 1/4)
Giant spider → giant spider (CR 1)
Giant snake (small/poisonous) → giant poisonous snake (CR 1/4)
Giant snake (large/constrictor) → giant constrictor snake (CR 2)
Giant lizard → giant lizard (CR 1/4)
Giant toad → giant toad (CR 1)
Cave bear → brown bear (CR 1) or polar bear (CR 2)
Stirge → stirge (CR 1/8)

## Elementals & planar
Air elemental → air elemental (CR 5)
Earth elemental → earth elemental (CR 5)
Fire elemental → fire elemental (CR 5)
Water elemental → water elemental (CR 5)
Invisible stalker → invisible stalker (CR 6)
Djinni → djinn (CR 11)
Efreeti → efreeti (CR 11)
Salamander → salamander (CR 5)
Xorn → xorn (CR 5)

## Fiends & demons
Type I demon (Vrock) → vrock (CR 9)
Type II demon (Hezrou) → hezrou (CR 8)
Type III demon (Glabrezu) → glabrezu (CR 9)
Type IV demon (Nalfeshnee) → nalfeshnee (CR 13)
Type V demon (Marilith) → marilith (CR 16)
Type VI demon (Balor) → balor (CR 19)
Succubus/Incubus → succubus/incubus (CR 4)
Zuggtmoy → Zuggtmoy, Demon Queen of Fungi (CR 23) [Out of the Abyss]

## Other notable
Gargoyle → gargoyle (CR 2)
Harpy → harpy (CR 1)
Minotaur → minotaur (CR 3)
Manticore → manticore (CR 3)
Medusa → medusa (CR 6)
Basilisk → basilisk (CR 3)
Beholder → beholder (CR 13)
Mind flayer → mind flayer (CR 7)
Wererat → wererat (CR 2)
Werewolf → werewolf (CR 3)
Doppelganger → doppelganger (CR 3)
"""

# ── Prompt ─────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are converting 1st Edition Advanced D&D adventure content into 5th Edition D&D \
for the 5etools homebrew JSON format.

You will receive a JSON array of room "entries" arrays. Each element of the outer \
array is the `entries` list of one room. Return a JSON array of the same length \
where each element is the updated `entries` list for that room.

RULES — follow exactly:
1. Keep ALL flavour text, room descriptions, and narrative prose verbatim.
2. Remove every 1e stat-block string. These look like:
   {@i Gnolls (4): AC 5, MV 9", HD 2, hp 10, 7, 7, 6, #AT 1, D 2-8}
   or plain strings with AC/MV/HD/THAC0 patterns.
3. In descriptive prose, wrap creature names with {@creature name} where they \
naturally appear (e.g. "four {@creature gnoll}s guard the door").
4. At the END of any entries list that had creatures, append ONE inset object:
   {"type":"inset","name":"Encounter (5e)","entries":["N {@creature x}, M {@creature y}",\
"Difficulty: Hard for 6th-level party (~2400 XP)"]}
5. Update trap text: "save vs. X" → "DC N [ability] saving throw, taking Xd6 [type] \
damage on a failed save, or half as much on a successful one."
6. Do NOT change any non-mechanical strings. Do not summarise or rephrase flavour text.
7. Preserve all non-string items (inset, table, list objects) exactly — only modify \
string values that contain 1e mechanics.
8. Return valid JSON with no markdown fences. The outer structure must be an array \
of arrays (one entries-array per room).\
"""


def make_user_prompt(zone: dict, rooms_entries: list[list]) -> str:
    lvl = zone["party_level"]
    thresh = XP_THRESHOLDS.get(lvl, XP_THRESHOLDS[5])
    payload = json.dumps(rooms_entries, ensure_ascii=False, indent=2)
    return (
        f"Zone: {zone['label']}\n"
        f"Difficulty guidance: {zone['difficulty']}\n\n"
        f"XP thresholds for party of 4 at level {lvl}:\n"
        f"  Easy ~{thresh['easy']} | Medium ~{thresh['medium']} | "
        f"Hard ~{thresh['hard']} | Deadly ~{thresh['deadly']}\n\n"
        f"Creature mapping:\n{CREATURE_MAPPING}\n\n"
        f"Convert the following rooms. Return a JSON array of arrays — "
        f"one entries-array per room, same order. No markdown fences.\n\n"
        f"{payload}"
    )


# ── Stat-block detection ───────────────────────────────────────────────────────

_STAT_RE = re.compile(
    r'(?:AC \d+|HD \d+|THAC0 \d+|MV \d+")',
    re.IGNORECASE,
)


def _str_has_stat_block(s: str) -> bool:
    return bool(_STAT_RE.search(s))


def directly_has_stat_blocks(entry: dict) -> bool:
    """True if this entry's own entries list contains a 1e stat-block string."""
    for item in entry.get("entries", []):
        if isinstance(item, str) and _str_has_stat_block(item):
            return True
    return False


def find_leaf_rooms(obj: Any, result: list[dict]) -> None:
    """Recursively collect dicts that directly own a 1e stat-block string.

    NOTE: call this on chapter["entries"] (a list), NOT on the chapter dict
    itself — otherwise the chapter dict can be falsely detected as a leaf room
    when stat-block strings appear at the top level of the chapter's entries
    (i.e. orphaned from missing rooms).
    """
    if isinstance(obj, dict):
        if directly_has_stat_blocks(obj):
            result.append(obj)
        else:
            for v in obj.values():
                find_leaf_rooms(v, result)
    elif isinstance(obj, list):
        for item in obj:
            find_leaf_rooms(item, result)


def find_orphaned_stat_strings(entries: list) -> list[int]:
    """Return indices of top-level stat-block strings in an entries list.

    These are 1e stat blocks that appear as bare strings directly in a chapter's
    entries array rather than inside a room dict — usually caused by the OCR
    converter failing to associate them with the preceding room.
    """
    return [i for i, e in enumerate(entries)
            if isinstance(e, str) and _str_has_stat_block(e)]


# ── API call ───────────────────────────────────────────────────────────────────

def rough_tokens(s: str) -> int:
    return len(s) // 4


def chunk_rooms(rooms: list[dict], max_tokens: int = 5000) -> list[list[dict]]:
    batches: list[list[dict]] = []
    current: list[dict] = []
    cur_tok = 0
    for room in rooms:
        t = rough_tokens(json.dumps(room.get("entries", []), ensure_ascii=False))
        if current and cur_tok + t > max_tokens:
            batches.append(current)
            current, cur_tok = [], 0
        current.append(room)
        cur_tok += t
    if current:
        batches.append(current)
    return batches


def call_claude(client: Any, model: str, zone: dict, batch: list[dict],
                verbose: bool, dry_run: bool) -> list[list] | None:
    """Send a batch of room dicts; receive back a list of updated entries arrays."""
    rooms_entries = [room.get("entries", []) for room in batch]
    user_msg = make_user_prompt(zone, rooms_entries)

    if dry_run:
        names = [r.get("name", "?") for r in batch]
        print(f"  [DRY-RUN] {len(batch)} rooms: {names}")
        print(f"            Prompt size ~{rough_tokens(user_msg)} tokens")
        return None  # return None so originals are kept

    if verbose:
        print(f"    Prompt ~{rough_tokens(user_msg)} tokens …", flush=True)

    for attempt in range(3):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = resp.content[0].text.strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            result = json.loads(raw)
            if not isinstance(result, list) or len(result) != len(batch):
                raise ValueError(
                    f"Expected list of length {len(batch)}, got {type(result).__name__} "
                    f"len={len(result) if isinstance(result, list) else '?'}"
                )
            return result
        except json.JSONDecodeError as exc:
            print(f"    [WARN] JSON parse error (attempt {attempt+1}/3): {exc}")
        except Exception as exc:
            msg = str(exc)
            if "content_filter" in msg.lower() or "400" in msg:
                print(f"    [SKIP] Content filter — keeping originals.")
                return None
            print(f"    [WARN] {exc} (attempt {attempt+1}/3)")
        if attempt < 2:
            time.sleep(3)

    print("    [SKIP] Max retries — keeping originals.")
    return None


# ── Chapter conversion ─────────────────────────────────────────────────────────

def convert_chapter(chapter: dict, ch_idx: int, client: Any, model: str,
                    verbose: bool, dry_run: bool) -> None:
    """Find leaf rooms in chapter, convert them in-place."""
    zone = _CHAPTER_ZONE.get(ch_idx)
    if zone is None:
        print("  (no zone config — skipping)")
        return

    entries = chapter.get("entries", [])

    # ── Handle orphaned top-level stat-block strings ───────────────────────
    # These are stat blocks that appear as bare strings directly in the chapter's
    # entries list (not inside any room dict), usually due to OCR extraction
    # failures.  Wrap them into a temporary pseudo-room, convert, then splice
    # the results back in place.
    orphan_indices = find_orphaned_stat_strings(entries)
    if orphan_indices:
        print(f"  {len(orphan_indices)} orphaned stat-block string(s) at top level")
        pseudo = {"type": "entries", "name": "_orphaned_", "entries":
                  [entries[i] for i in orphan_indices]}
        result = call_claude(client, model, zone, [pseudo], verbose, dry_run)
        if result and isinstance(result[0], list):
            # Splice: replace the first orphan index with all converted entries,
            # delete the remaining original orphan indices.
            converted = result[0]
            # Work backwards so index shifts don't affect earlier positions
            for pos in reversed(orphan_indices[1:]):
                entries.pop(pos)
            entries[orphan_indices[0]:orphan_indices[0]+1] = converted
        else:
            print("  (orphaned strings kept as-is)")

    # ── Leaf-room detection ────────────────────────────────────────────────
    # Start from entries list, NOT the chapter dict — otherwise a chapter with
    # top-level stat-block strings would itself be flagged as a leaf room.
    leaf_rooms: list[dict] = []
    find_leaf_rooms(entries, leaf_rooms)

    if not leaf_rooms and not orphan_indices:
        print("  (no 1e mechanics found)")
        return
    if not leaf_rooms:
        return

    print(f"  Zone: {zone['label']}")
    print(f"  Found {len(leaf_rooms)} leaf rooms with 1e mechanics")

    batches = chunk_rooms(leaf_rooms)
    total_converted = 0

    for b_idx, batch in enumerate(batches):
        names = [r.get("name", "?")[:30] for r in batch]
        print(f"    Batch {b_idx+1}/{len(batches)}: {names}", flush=True)
        result = call_claude(client, model, zone, batch, verbose, dry_run)

        if result is None:
            print(f"    → keeping originals for this batch")
            continue

        for room, new_entries in zip(batch, result):
            if isinstance(new_entries, list):
                # Only update the entries array; preserve name/type/id/etc.
                room["entries"] = new_entries
                total_converted += 1
            else:
                print(f"    [WARN] Unexpected result type for room "
                      f"'{room.get('name','?')}': {type(new_entries)}")

    if not dry_run:
        print(f"  → {total_converted}/{len(leaf_rooms)} rooms converted")


# ── Main ──────────────────────────────────────────────────────────────────────

def _patch_metadata(obj: dict, old_source: str, new_source: str) -> None:
    """Rewrite all source identifiers so 5etools treats the output as a distinct adventure."""
    import time as _time

    # _meta.sources
    for src in obj.get("_meta", {}).get("sources", []):
        if src.get("json") == old_source:
            src["json"] = new_source
            src["abbreviation"] = new_source
            src["full"] = src.get("full", old_source) + " \u2014 5e Conversion"
            src["version"] = "1.0.0"
            src.setdefault("convertedBy", [])
            if "convert_1e_to_5e" not in src["convertedBy"]:
                src["convertedBy"].append("convert_1e_to_5e")
    now = int(_time.time())
    obj["_meta"]["dateAdded"] = now
    obj["_meta"]["dateLastModified"] = now

    # adventure[] entries
    for adv in obj.get("adventure", []):
        if adv.get("source") == old_source:
            adv["source"] = new_source
        if adv.get("id") == old_source:
            adv["id"] = new_source
        if adv.get("name", "").endswith("(1E) Notes"):
            adv["name"] = adv["name"].replace("(1E) Notes", "(5E Conversion)")

    # adventureData[] / bookData[] entries
    for bucket in ("adventureData", "bookData"):
        for entry in obj.get(bucket, []):
            if entry.get("source") == old_source:
                entry["source"] = new_source
            if entry.get("id") == old_source:
                entry["id"] = new_source


def convert(in_path: Path, out_path: Path, client: Any, model: str,
            chapter_filter: set[int] | None, verbose: bool, dry_run: bool) -> None:
    print(f"Reading {in_path} …")
    with open(in_path, encoding="utf-8") as f:
        obj = json.load(f)

    # Determine original source ID before any patching
    original_source = (
        obj.get("_meta", {}).get("sources", [{}])[0].get("json", "")
    )
    new_source = original_source + "-5E" if original_source else "CONVERTED-5E"

    data_list = obj.get("adventureData") or obj.get("bookData") or []
    if not data_list:
        sys.exit("ERROR: no adventureData found.")

    chapters: list[dict] = data_list[0].get("data", [])
    print(f"Total chapters: {len(chapters)}")

    for idx, chapter in enumerate(chapters):
        name = chapter.get("name", f"Chapter {idx}")
        print(f"\n[{idx:2d}] {name}")

        if idx in SKIP_CHAPTERS:
            print("  (skipped — intro/title)")
            continue
        if chapter_filter is not None and idx not in chapter_filter:
            print("  (outside --chapters filter)")
            continue
        if idx not in _CHAPTER_ZONE:
            print("  (no zone defined — passing through)")
            continue

        # Chapters are modified in-place via find_leaf_rooms / room["entries"] = …
        convert_chapter(chapter, idx, client, model, verbose, dry_run)

    # Patch all source/id references so the output is a distinct 5etools entry
    _patch_metadata(obj, original_source, new_source)
    print(f"\nSource ID: {original_source!r} → {new_source!r}")

    print(f"Writing {out_path} …")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent="\t", ensure_ascii=False)
    print("Done.")


# ── CLI ────────────────────────────────────────────────────────────────────────

def _parse_chapters(value: str) -> set[int]:
    result: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if "-" in part:
            lo, _, hi = part.partition("-")
            result.update(range(int(lo), int(hi) + 1))
        else:
            result.add(int(part))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert 1e adventure JSON to 5e")
    parser.add_argument("input",  type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--api-key")
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--chapters",
                        help="Chapters to process, e.g. '16' or '4-18' or '16,17,18'")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        sys.exit("ERROR: set ANTHROPIC_API_KEY or pass --api-key")

    chapter_filter = _parse_chapters(args.chapters) if args.chapters else None

    client = None
    if not args.dry_run:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

    convert(args.input, args.output, client, args.model,
            chapter_filter, verbose=args.verbose, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
