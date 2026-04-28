#!/usr/bin/env python3
"""
validate_tags.py — Check a generated adventure JSON for unknown {@tag} references.

Unknown tags throw a JS error in 5etools, causing blank page rendering.

Usage:
    python3 validate_tags.py adventure.json
    python3 validate_tags.py adventure.json --fix     # replace unknown tags with plain text
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# All tags recognised by the 5etools renderer (extracted from render.js).
KNOWN_TAGS = {
    "@", "@5etools", "@5etoolsImg", "@ability", "@actResponse", "@actSave",
    "@actSaveFail", "@actSaveFailBy", "@actSaveSuccess", "@actSaveSuccessOrFail",
    "@actTrigger", "@action", "@adventure", "@area", "@atk", "@atkr",
    "@autodice", "@b", "@background", "@bold", "@book", "@boon", "@card",
    "@chance", "@charoption", "@cite", "@class", "@classFeature", "@code",
    "@coinflip", "@color", "@comic", "@comicH1", "@comicH2", "@comicH3",
    "@comicH4", "@comicNote", "@condition", "@creature", "@creatureFluff",
    "@cult", "@d20", "@damage", "@dc", "@dcYourSpellSave", "@deck", "@deity",
    "@dice", "@disease", "@facility", "@feat", "@filter", "@font", "@footnote",
    "@h", "@hazard", "@help", "@highlight", "@hit", "@hitYourSpellAttack",
    "@hom", "@homebrew", "@i", "@initiative", "@italic", "@item",
    "@itemMastery", "@itemProperty", "@kbd", "@language", "@legroup", "@link",
    "@loader", "@m", "@note", "@object", "@optfeature", "@psionic",
    "@quickref", "@race", "@raceFluff", "@recharge", "@recipe", "@reward",
    "@s", "@s2", "@savingThrow", "@scaledamage", "@scaledice", "@sense",
    "@skill", "@skillCheck", "@spell", "@status", "@strike", "@strikeDouble",
    "@style", "@sub", "@subclass", "@subclassFeature", "@sup", "@table",
    "@tip", "@trap", "@u", "@u2", "@underline", "@underlineDouble", "@unit",
    "@variantrule", "@vehicle", "@vehupgrade",
}

TAG_RE = re.compile(r'\{(@\w+)([^}]*)\}')


def scan(obj: object, path: str = "") -> list[tuple[str, str, str]]:
    """Return list of (path, tag, full_match) for every {@tag} found."""
    hits = []
    if isinstance(obj, str):
        for m in TAG_RE.finditer(obj):
            hits.append((path, m.group(1), m.group(0)))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            hits.extend(scan(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            hits.extend(scan(item, f"{path}[{i}]"))
    return hits


def fix_unknown(text: str) -> str:
    """Replace unknown {@tag text} with just the display text."""
    def replace(m: re.Match) -> str:
        tag = m.group(1)
        rest = m.group(2).strip()
        if tag in KNOWN_TAGS:
            return m.group(0)
        # Use the last pipe-separated segment as display text, or the whole rest
        display = rest.split("|")[-1].strip() if rest else tag
        return display or m.group(0)
    return TAG_RE.sub(replace, text)


def fix_obj(obj: object) -> object:
    if isinstance(obj, str):
        return fix_unknown(obj)
    if isinstance(obj, dict):
        return {k: fix_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [fix_obj(item) for item in obj]
    return obj


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate {@tags} in a 5etools adventure JSON.")
    parser.add_argument("file", help="Path to adventure JSON file")
    parser.add_argument("--fix", action="store_true",
                        help="Rewrite the file replacing unknown tags with plain text")
    args = parser.parse_args()

    path = Path(args.file)
    data = json.loads(path.read_text(encoding="utf-8"))

    all_hits = scan(data)

    unknown: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for loc, tag, full in all_hits:
        if tag not in KNOWN_TAGS:
            unknown[tag].append((loc, full))

    if not unknown:
        print("OK — all tags are recognised by 5etools.")
        if args.fix:
            print("(Nothing to fix.)")
        return

    print(f"Found {sum(len(v) for v in unknown.values())} unknown tag(s):\n")
    for tag in sorted(unknown):
        print(f"  {tag}  ({len(unknown[tag])} occurrence(s))")
        for loc, full in unknown[tag][:5]:
            print(f"    {loc}: {full}")
        if len(unknown[tag]) > 5:
            print(f"    … and {len(unknown[tag]) - 5} more")
    print()
    print("Common fixes:")
    print("  {@scroll X}  →  {@item scroll of X}")
    print("  {@npc X}     →  plain text or {@creature X}")

    if args.fix:
        fixed = fix_obj(data)
        path.write_text(json.dumps(fixed, indent="\t", ensure_ascii=False), encoding="utf-8")
        print(f"\nFixed and wrote {path}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
