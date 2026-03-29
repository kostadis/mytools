#!/usr/bin/env python3
"""Extract monster stat blocks from a parsed adventure JSON and convert them
to 5etools bestiary format using Claude.

Usage:
    python3 extract_monsters.py adventure-toworlds.json
    python3 extract_monsters.py adventure-toworlds.json --dry-run
    python3 extract_monsters.py adventure-toworlds.json --model claude-sonnet-4-6
    python3 extract_monsters.py adventure-toworlds.json --out bestiary-toworlds.json
"""

import argparse
import json
import sys
import textwrap
import time
from pathlib import Path

import anthropic

import claude_api as _api

# ---------------------------------------------------------------------------
# System prompt for monster conversion
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = textwrap.dedent("""\
You are an expert at converting D&D 5e monster stat blocks into the 5etools
bestiary JSON format.

You will receive one or more stat blocks that have been extracted from an
adventure JSON file. They are represented as tables (key-value rows or
multi-column) plus trait/action entries. Convert each into a proper 5etools
monster object.

Return ONLY a valid JSON array of monster objects. Return [] if the input does
not contain a real stat block. No markdown fences, no explanation.

Each monster object must include these fields (omit optional ones if not present):

REQUIRED:
  name        string   -- creature name (strip parenthetical counts like "(2)")
  source      string   -- use "PLACEHOLDER" (script fills in the real source)
  size        array    -- ["M"] for Medium, ["S"] for Small, etc.
  type        string or {{"type":"humanoid","tags":["human"]}}
  alignment   array    -- ["L","G"] / ["N","E"] / ["U"] for unaligned etc.
  ac          array    -- [15] or [{{"ac":15,"from":["chain mail"]}}]
  hp          object   -- {{"average":22,"formula":"3d8+9"}}
  speed       object   -- {{"walk":30}} or {{"walk":30,"fly":60}}
  str,dex,con,int,wis,cha  integers (just the score, not the modifier)
  passive     integer  -- passive Perception
  cr          string   -- "1/4","1/2","1","2" etc.

OPTIONAL (include if present):
  save        object   -- {{"str":"+4","con":"+6"}}
  skill       object   -- {{"perception":"+5","stealth":"+4"}}
  senses      array    -- ["darkvision 60 ft.","tremorsense 30 ft."]
  languages   array    -- ["Common","Elvish"] or ["\\u2014"] if none
  immune      array    -- damage types: ["fire","poison"]
  resist      array    -- damage types
  vulnerable  array    -- damage types
  conditionImmune array -- ["charmed","frightened"]
  trait       array    -- [{{"name":"Trait Name","entries":["Description."]}}]
  action      array    -- [{{"name":"Multiattack","entries":["The creature makes two attacks."]}}]
               For attacks use: "{{@atk mw}} {{@hit 5}} to hit, reach 5 ft., one target. {{@h}}{{@damage 2d6+3}} slashing damage."
  bonus       array    -- bonus actions, same format as action
  reaction    array    -- reactions, same format as action
  legendary   array    -- legendary actions
  legendaryActions  number -- number of legendary actions per round (default 3)
  spellcasting array   -- see format below
  isNamedCreature bool -- true if this is a unique NPC with a proper name
  isNpc       bool     -- true for NPCs

Spellcasting format:
{{
  "name": "Spellcasting",
  "type": "spellcasting",
  "headerEntries": ["The mage is a 5th-level spellcaster...spell save {{@dc 13}}; {{@hit 5}} to hit..."],
  "spells": {{
    "0": {{"spells": ["{{@spell mage hand}}","{{@spell prestidigitation}}"]}},
    "1": {{"slots": 4, "spells": ["{{@spell magic missile}}","{{@spell shield}}"]}},
    "2": {{"slots": 3, "spells": ["{{@spell misty step}}"]}}
  }},
  "footerEntries": []
}}

For innate spellcasting use:
{{
  "name": "Innate Spellcasting",
  "type": "spellcasting",
  "headerEntries": ["The creature's innate spellcasting ability is Charisma (spell save DC 13). It can innately cast the following spells, requiring no material components:"],
  "will": ["{{@spell light}}"],
  "daily": {{
    "1e": ["{{@spell lesser restoration}}"],
    "3e": ["{{@spell cure wounds}}"]
  }},
  "footerEntries": []
}}

IMPORTANT formatting rules:
- Spell names must be wrapped in {{@spell name}} tags
- Attack entries must use {{@atk mw}} (melee weapon), {{@atk rw}} (ranged weapon), {{@atk ms}} (melee spell), {{@atk rs}} (ranged spell)
- Hit bonuses: {{@hit N}}
- Damage: {{@damage XdY+Z}}
- DCs: {{@dc N}}
- Hit shorthand: {{@h}} (expands to "Hit: ")
- Conditions: {{@condition poisoned}}, {{@condition frightened}}, etc.
- Strip count suffixes from names: "Klaven Void Zombie (2)" -> "Klaven Void Zombie"
- For named NPCs set isNamedCreature: true and isNpc: true

Alignment abbreviations: L=Lawful, N=Neutral, C=Chaotic, G=Good, E=Evil, U=Unaligned, A=Any
""")

# ---------------------------------------------------------------------------
# Extract stat block entries from adventure JSON
# ---------------------------------------------------------------------------

def _has_ac_table(entry):
    """Check if an entries dict directly contains an AC stat-block table."""
    for child in entry.get("entries", []):
        if isinstance(child, dict) and child.get("type") == "table":
            rows = child.get("rows", [])
            cols = child.get("colLabels", [])
            has_ac = any(
                isinstance(r, list) and len(r) > 0 and r[0] == "Armor Class"
                for r in rows
            )
            if has_ac or "Armor Class" in cols:
                return True
    return False


def extract_statblock_entries(obj, parent_name=""):
    """Walk the adventure JSON tree and return all entries containing stat-block tables.

    For unnamed entries, inherits the name from the nearest named ancestor.
    """
    results = []
    if isinstance(obj, dict):
        name = obj.get("name", "") or parent_name
        if obj.get("type") == "entries" and "entries" in obj:
            if _has_ac_table(obj):
                # If this entry has no name, inherit from parent
                if not obj.get("name") and parent_name:
                    obj = {**obj, "name": parent_name}
                results.append(obj)
                return results
            # No stat table found directly — recurse into children
            for child in obj["entries"]:
                results.extend(extract_statblock_entries(child, name))
            return results
        for k, v in obj.items():
            results.extend(extract_statblock_entries(v, name))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(extract_statblock_entries(item, parent_name))
    return results


def statblock_to_text(entry):
    """Convert a stat block entry dict to a readable text representation for Claude."""
    lines = []
    name = entry.get("name", "Unknown")
    lines.append(f"=== {name} ===")

    for child in entry.get("entries", []):
        if isinstance(child, str):
            lines.append(child)
        elif isinstance(child, dict):
            ctype = child.get("type", "")
            if ctype == "table":
                cols = child.get("colLabels", [])
                if cols:
                    lines.append("  ".join(cols))
                    lines.append("-" * 40)
                for row in child.get("rows", []):
                    if isinstance(row, list):
                        lines.append("  ".join(str(c) for c in row))
            elif ctype == "entries":
                cname = child.get("name", "")
                if cname:
                    lines.append(f"\n{cname}")
                for e in child.get("entries", []):
                    if isinstance(e, str):
                        lines.append(f"  {e}")
                    elif isinstance(e, dict) and e.get("type") == "list":
                        for item in e.get("items", []):
                            lines.append(f"  - {item}")
                    elif isinstance(e, dict) and e.get("type") == "table":
                        for row in e.get("rows", []):
                            if isinstance(row, list):
                                lines.append("  " + "  ".join(str(c) for c in row))
            elif ctype == "list":
                for item in child.get("items", []):
                    lines.append(f"  - {item}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract monsters from adventure JSON into 5etools bestiary format"
    )
    parser.add_argument("input", type=Path, help="Adventure JSON file")
    parser.add_argument("--out", "-o", type=Path, default=None,
                        help="Output bestiary JSON file (default: bestiary-<input>.json)")
    parser.add_argument("--model", default="claude-sonnet-4-6",
                        help="Claude model to use (default: claude-sonnet-4-6)")
    parser.add_argument("--api-key", default=None, help="Anthropic API key")
    parser.add_argument("--dry-run", action="store_true",
                        help="Just list found stat blocks, don't call Claude")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--batch-size", type=int, default=5,
                        help="Number of stat blocks to send per Claude call (default: 5)")
    args = parser.parse_args()

    # Load adventure JSON
    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    # Determine source ID
    source_id = "HOMEBREW"
    sources = data.get("_meta", {}).get("sources", [])
    if sources:
        source_id = sources[0].get("json", source_id)
    source_meta = sources[0] if sources else {
        "json": source_id,
        "abbreviation": source_id[:8],
        "full": args.input.stem,
        "version": "1.0.0",
        "authors": ["Unknown"],
        "convertedBy": ["extract_monsters"],
    }

    # Extract stat blocks
    statblocks = extract_statblock_entries(data)
    print(f"Found {len(statblocks)} stat blocks:")
    for sb in statblocks:
        print(f"  - {sb.get('name', '?')}")

    if args.dry_run:
        print("\n[dry-run] Would send these to Claude for conversion.")
        for sb in statblocks:
            print(f"\n{'='*60}")
            print(statblock_to_text(sb))
        return

    if not statblocks:
        print("No stat blocks found — nothing to do.")
        return

    # Set up Claude client
    client = anthropic.Anthropic(api_key=args.api_key)

    # Convert stat blocks to text and batch them
    texts = [statblock_to_text(sb) for sb in statblocks]
    all_monsters = []

    batch_size = args.batch_size
    batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]

    print(f"\nSending {len(batches)} batch(es) to Claude ({args.model})...")

    for batch_idx, batch in enumerate(batches):
        combined = "\n\n---\n\n".join(batch)
        print(f"  Batch {batch_idx + 1}/{len(batches)} ({len(batch)} stat blocks)...",
              flush=True)

        monsters = _api.call_claude(
            client, combined, args.model, SYSTEM_PROMPT,
            args.verbose, None, f"monsters-{batch_idx:04d}"
        )

        for m in monsters:
            if isinstance(m, dict):
                m["source"] = source_id

        all_monsters.extend(monsters)
        print(f"    Got {len(monsters)} monsters", flush=True)

    # Deduplicate by name (keep last occurrence which is usually better)
    seen = {}
    for m in all_monsters:
        if isinstance(m, dict):
            seen[m.get("name", "")] = m
    all_monsters = list(seen.values())

    print(f"\nTotal unique monsters: {len(all_monsters)}")

    # Build output
    out_path = args.out or Path(f"bestiary-{args.input.stem}.json")
    homebrew_obj = {
        "_meta": {
            "sources": [source_meta],
            "dateAdded": int(time.time()),
            "dateLastModified": int(time.time()),
        },
        "monster": all_monsters,
    }

    out_path.write_text(
        json.dumps(homebrew_obj, indent="\t", ensure_ascii=False), encoding="utf-8"
    )

    print(f"\nWrote {out_path} ({len(all_monsters)} monsters)")
    print(f"\nTo load in 5etools:")
    print(f"  1. Open bestiary.html → Manage Homebrew")
    print(f"  2. Load from File → select {out_path.name}")


if __name__ == "__main__":
    main()
