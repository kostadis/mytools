#!/usr/bin/env python3
"""Audit a campaign entity registry for garblings masquerading as aliases.

An alias is an APPROVED CANONICAL ALTERNATE NAME — a plural, a short form, a
title, a diacritic-free rendering. It is NOT a transcription error. Earlier
registry-building passes did not draw that line, so ASR garblings were imported
as aliases; every one of them then reads as a "known name" to downstream
consumers and silently suppresses a real correction.

Emits three buckets:

  A  definitive   alias is a wrong-form in the VTT corrections glossary
                  (the GM already ruled on it). Safe to propose stripping.
  B  probable     alias is a near-miss of its OWN canonical. Mixed bag —
                  garblings AND legitimate variants. Needs GM adjudication.
  C  inverted     the CANONICAL name is itself a glossary wrong-form, or is a
                  duplicate of another registered entity. The rot is in the
                  name slot, not the alias list. Needs merge or rename.

Read-only. Writes nothing.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

import yaml


def parse_glossary(path: Path) -> dict[str, str]:
    """Map lowercased wrong-form -> canonical, from the VTT corrections table."""
    wrong: dict[str, str] = {}
    if not path or not path.exists():
        return wrong
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$", line)
        if not m:
            continue
        left, right = m.group(1), m.group(2)
        if left.strip().lower() == "wrong" or set(left.strip()) <= set("-: "):
            continue
        canon = re.sub(r"\*\*(.+?)\*\*", r"\1", right).strip()
        canon = re.sub(r"\s*\(.*?\)\s*$", "", canon).strip()
        for w in left.split(","):
            w = re.sub(r"\*+", "", w)
            w = re.sub(r"\s*\(.*?\)\s*", "", w).strip()
            if w:
                wrong.setdefault(w.lower(), canon)
    return wrong


def load_entities(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [e for e in (data.get("entities") or []) if isinstance(e, dict) and e.get("name")]


def is_near_miss(alias: str, canonical: str, lo: float, hi: float) -> float | None:
    """Similar enough to be a spelling variant, but not a containment short-form.

    Containment (``Kalan`` in ``Kalan Strongbranch``) is a legitimate short
    form, never a garbling — excluded outright.
    """
    a, c = alias.lower(), canonical.lower()
    if a in c or c in a:
        return None
    r = difflib.SequenceMatcher(None, a, c).ratio()
    return round(r, 2) if lo <= r < hi else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--registry", required=True, type=Path)
    ap.add_argument("--glossary", type=Path,
                    help="notes/vtt_transcription_corrections.md — enables bucket A and C")
    ap.add_argument("--min-similarity", type=float, default=0.80)
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a report")
    args = ap.parse_args()

    ents = load_entities(args.registry)
    wrong = parse_glossary(args.glossary) if args.glossary else {}
    by_name = {e["name"].lower(): e for e in ents}

    bucket_a, bucket_b, bucket_c = [], [], []

    for e in ents:
        name = e["name"]
        # C1: canonical name is itself a known wrong-form
        if name.lower() in wrong:
            target = wrong[name.lower()]
            bucket_c.append({
                "kind": "canonical_is_garbling",
                "entity": name,
                "glossary_canonical": target,
                "target_registered": target.lower() in by_name,
            })
        for raw in (e.get("aliases") or []):
            alias = str(raw).strip()
            if not alias:
                continue
            if alias.lower() in wrong:
                bucket_a.append({
                    "alias": alias, "entity": name,
                    "glossary_canonical": wrong[alias.lower()],
                    "type": e.get("type", ""),
                })
                continue
            sim = is_near_miss(alias, name, args.min_similarity, 1.0)
            if sim is not None:
                bucket_b.append({
                    "alias": alias, "entity": name, "similarity": sim,
                    "type": e.get("type", ""),
                })

    # C2: two registered entities that are the same name modulo a known correction
    seen_pairs = set()
    for w, canon in wrong.items():
        if w in by_name and canon.lower() in by_name and w != canon.lower():
            key = (by_name[w]["name"], by_name[canon.lower()]["name"])
            if key not in seen_pairs:
                seen_pairs.add(key)
                bucket_c.append({
                    "kind": "duplicate_entities",
                    "entity": key[0], "duplicate_of": key[1],
                })

    if args.json:
        json.dump({"A_definitive": bucket_a, "B_probable": bucket_b, "C_inverted": bucket_c},
                  sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    total_alias = sum(len(e.get("aliases") or []) for e in ents)
    print(f"registry: {args.registry}")
    print(f"entities: {len(ents)}   aliases: {total_alias}\n")

    print(f"=== A. DEFINITIVE garblings ({len(bucket_a)}) "
          f"— alias is a glossary wrong-form; GM already ruled ===")
    for r in sorted(bucket_a, key=lambda x: x["alias"].lower()):
        print(f"  {r['alias']!r:<34} on {r['entity']!r:<38} glossary -> {r['glossary_canonical']}")

    print(f"\n=== B. PROBABLE garblings ({len(bucket_b)}) "
          f"— near-miss of own canonical; MIXED, adjudicate each ===")
    for r in sorted(bucket_b, key=lambda x: (x["entity"].lower(), -x["similarity"])):
        print(f"  {r['alias']!r:<40} -> {r['entity']!r:<44} {r['similarity']} [{r['type']}]")

    print(f"\n=== C. INVERTED / DUPLICATE ({len(bucket_c)}) "
          f"— the CANONICAL slot is wrong; needs merge or rename ===")
    for r in bucket_c:
        if r["kind"] == "canonical_is_garbling":
            reg = "registered" if r["target_registered"] else "NOT registered"
            print(f"  canonical {r['entity']!r} is a glossary wrong-form of "
                  f"{r['glossary_canonical']!r} ({reg})")
        else:
            print(f"  {r['entity']!r} duplicates {r['duplicate_of']!r}")

    if not (bucket_a or bucket_c):
        print("\nNo definitive or inverted problems. Bucket B still needs a human pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
