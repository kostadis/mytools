#!/usr/bin/env python3
"""Deterministic merge/dedupe — module-inventory Phase 3.

Phase 2 runs one LLM agent per chunk of the source module; each agent groups
Phase-1 raw candidates into full names, assigns a category, and writes a short
description with citations (see SKILL.md for the expected per-chunk JSON
shape). Merging those chunk outputs back into one entity per name is a
structural task, not a judgment call, so it happens here in code rather than
by asking another LLM pass to eyeball hundreds of entries — that is exactly
the kind of scope/attribution decision the project's LLM Pipeline Design Rule
says needs a deterministic pass or a human, not an LLM guess.

A group of same-name sightings is CLEAN (auto-mergeable) only if every
sighting agrees on category and none of the tracked exclusivity attributes
(species, alive/dead status, gender) conflict. Anything else is CONTESTED and
is left for a human ruling (SKILL.md Phase 4) — nothing here decides who's
right. Near-duplicate names (different entries, similar spelling) are flagged
separately and never auto-merged, since filename/spelling similarity is not
evidence of sameness on its own.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

EXCLUSIVITY_GROUPS = {
    "species": {
        "human", "dwarf", "elf", "half-elf", "halfling", "gnome", "half-orc",
        "orc", "drow", "dragonborn", "tiefling", "goliath", "tabaxi",
        "svirfneblin", "duergar", "genasi", "aasimar", "firbolg", "kobold",
        "goblin", "bugbear", "hobgoblin", "kuo-toa", "myconid", "derro",
        "gith", "githyanki", "githzerai", "warforged", "kenku", "lizardfolk",
        "tortle", "yuan-ti", "changeling", "shifter",
    },
    "status": {"alive", "dead", "deceased", "undead"},
    "gender": {"male", "female"},
}


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


class DSU:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def load_chunks(paths: list[Path]) -> list[dict]:
    entries = []
    for p in paths:
        data = json.loads(p.read_text(encoding="utf-8"))
        label = data.get("chunk_label", p.stem)
        for e in data.get("entries", []):
            entries.append({**e, "_chunk": label})
    return entries


def group_entries(entries: list[dict]) -> dict[str, list[dict]]:
    dsu = DSU()
    for e in entries:
        key = norm(e["name"])
        dsu.union(key, key)
        for alias in e.get("aliases", []) or []:
            dsu.union(key, norm(alias))

    groups: dict[str, list[dict]] = {}
    for e in entries:
        root = dsu.find(norm(e["name"]))
        groups.setdefault(root, []).append(e)
    return groups


def _attribute_values(entry: dict, group: str) -> set[str]:
    vals = set()
    attrs = entry.get("attributes") or {}
    v = attrs.get(group)
    if isinstance(v, str) and v.lower() in EXCLUSIVITY_GROUPS[group]:
        vals.add(v.lower())
    # fallback: scan description text for exclusivity words as a weak signal
    desc = (entry.get("description") or "").lower()
    for word in EXCLUSIVITY_GROUPS[group]:
        if re.search(rf"\b{re.escape(word)}\b", desc):
            vals.add(word)
    return vals


def _canonical_name(members: list[dict]) -> str:
    names = [m["name"] for m in members]
    # prefer the longest name seen (fullest form), tie-break by frequency
    counts: dict[str, int] = {}
    for n in names:
        counts[n] = counts.get(n, 0) + 1
    return sorted(set(names), key=lambda n: (-len(n), -counts[n]))[0]


def merge_group(members: list[dict]) -> dict:
    categories = {m.get("category", "other") for m in members}
    conflicts = {}
    for group in EXCLUSIVITY_GROUPS:
        seen = set()
        for m in members:
            seen |= _attribute_values(m, group)
        if len(seen) > 1:
            conflicts[group] = sorted(seen)

    canonical = _canonical_name(members)
    aliases = sorted({m["name"] for m in members if m["name"] != canonical})
    for m in members:
        aliases.extend(a for a in (m.get("aliases") or []) if a != canonical)
    aliases = sorted(set(aliases))

    chunks = sorted({m.get("_chunk", "") for m in members if m.get("_chunk")})
    lines: list = []
    for m in members:
        lines.extend(m.get("lines") or [])
    lines = sorted(set(lines), key=lambda x: (isinstance(x, str), x))

    if len(categories) > 1 or conflicts:
        return {
            "name": canonical,
            "aliases": aliases,
            "status": "contested",
            "reason": (
                f"category disagreement: {sorted(categories)}" if len(categories) > 1
                else f"attribute conflict: {conflicts}"
            ),
            "sightings": [
                {
                    "chunk": m.get("_chunk"),
                    "category": m.get("category"),
                    "description": m.get("description"),
                    "lines": m.get("lines"),
                }
                for m in members
            ],
        }

    descriptions = [m.get("description", "").strip() for m in members if m.get("description", "").strip()]
    descriptions = sorted(set(descriptions), key=len, reverse=True)
    description = descriptions[0] if descriptions else ""
    extra = [d for d in descriptions[1:] if d.lower() not in description.lower()]

    return {
        "name": canonical,
        "aliases": aliases,
        "status": "clean",
        "category": categories.pop(),
        "description": description,
        "also_noted": extra,
        "chunks": chunks,
        "lines": lines,
    }


def find_possible_duplicates(merged: list[dict], sim: float) -> list[dict]:
    dupes = []
    known_names = [(m["name"], set(norm(a) for a in [m["name"], *m.get("aliases", [])])) for m in merged]
    for i in range(len(known_names)):
        for j in range(i + 1, len(known_names)):
            name_a, keys_a = known_names[i]
            name_b, keys_b = known_names[j]
            if keys_a & keys_b:
                continue  # already unioned via shared alias
            ratio = SequenceMatcher(None, norm(name_a), norm(name_b)).ratio()
            if ratio >= sim:
                dupes.append({"a": name_a, "b": name_b, "ratio": round(ratio, 3)})
    dupes.sort(key=lambda d: -d["ratio"])
    return dupes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chunks-dir", type=Path, help="directory of chunk_*.json Phase-2 outputs")
    ap.add_argument("--chunks", nargs="*", type=Path, help="explicit list of chunk JSON files")
    ap.add_argument("--sim", type=float, default=0.87, help="near-duplicate-name similarity floor")
    ap.add_argument("--out", type=Path, default=None, help="default: stdout")
    args = ap.parse_args()

    if args.chunks_dir:
        paths = sorted(args.chunks_dir.glob("*.json"))
    elif args.chunks:
        paths = args.chunks
    else:
        ap.error("pass --chunks-dir or --chunks")
        return 2

    if not paths:
        ap.error("no chunk files found")
        return 2

    entries = load_chunks(paths)
    groups = group_entries(entries)
    merged = [merge_group(members) for members in groups.values()]

    clean = [m for m in merged if m["status"] == "clean"]
    contested = [m for m in merged if m["status"] == "contested"]
    possible_duplicates = find_possible_duplicates(clean + contested, args.sim)

    clean.sort(key=lambda m: m["name"])
    contested.sort(key=lambda m: m["name"])

    result = {
        "clean": clean,
        "contested": contested,
        "possible_duplicates": possible_duplicates,
        "stats": {
            "chunk_files": len(paths),
            "total_sightings": len(entries),
            "groups": len(merged),
            "clean": len(clean),
            "contested": len(contested),
            "possible_duplicates": len(possible_duplicates),
        },
    }

    out_text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(out_text, encoding="utf-8")
        print(f"wrote {args.out} — {result['stats']}", file=sys.stderr)
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
