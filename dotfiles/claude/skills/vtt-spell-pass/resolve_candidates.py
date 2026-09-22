#!/usr/bin/env python3
"""Classify a VTT's proper-noun candidates against the campaign's canon chain.

The replacement for this skill's flat known/unknown split. ``find_unknowns.py``
collapses five sources of very different authority into one ``known`` set and
then answers a yes/no question: is this token in the set? Two things get lost
in that collapse, and both are silent.

**A glossary hit is a RULING, not a fact about the set.** "Zaltier" is in the
known set (as a wrong-form) and "Zalthir" is in it (as a canonical), so neither
is reported — the replacement happens in ``apply_replacements.py`` and the GM
sees a count, not a card. That is fine for a wrong-form already ruled on, and
it is the reason a transposed-letter pair can ride along unreviewed when the
ruling behind it was itself never shown.

**A filename becomes evidence.** ``parse_npc_dossiers`` humanises the file stem
— ``docs/npcs/sequioa.md`` puts "Sequioa" in the known set, so the misspelling
is silently accepted forever after and never surfaces as a candidate. The canon
rule says exactly the opposite: a filename is not evidence.

So this script asks the chain instead of a set, one candidate at a time, and
keeps the tier and the citing source attached to every answer:

  confirmed   resolved, is_change=false — canon, nothing to show
  ruling      resolved, is_change=true  — a name CHANGE the GM must see, with
                                          the tier and line that ruled it
  ambiguous   tiers disagree — no canonical, the GM decides
  not_canon   in none of the five tiers — a new-name candidate, near misses
                                          attached as questions

Only ``confirmed`` is silent. The other three are the review queue, ordered by
how much they need a human.

Usage:
  resolve_candidates.py --vtt <path> --campaign-dir <path>
                        [--campaign-generator <path>] [--min-count N] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# find_unknowns owns candidate extraction (cue stripping, speaker labels,
# the mid-sentence test, stopwords). Reused rather than reimplemented — a
# second extractor would drift from the first and quietly change what gets
# reviewed.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from find_unknowns import PROPER_RE, SENTENCE_END, STOPWORDS, extract_text  # noqa: E402

DEFAULT_CG_PATHS = [
    Path.home() / "src" / "CampaignGenerator",
    Path.home() / "CampaignGenerator",
]


def load_resolver(campaign_generator: Path | None):
    """Import entity_registry.resolve from a CampaignGenerator checkout."""
    candidates = [campaign_generator] if campaign_generator else DEFAULT_CG_PATHS
    for root in candidates:
        if root and (root / "entity_registry" / "resolve.py").exists():
            sys.path.insert(0, str(root))
            from entity_registry import resolve  # noqa: PLC0415
            return resolve
    tried = ", ".join(str(c) for c in candidates if c)
    raise SystemExit(
        f"Could not find entity_registry/resolve.py. Tried: {tried}\n"
        f"Pass --campaign-generator <path-to-CampaignGenerator>."
    )


def candidates(vtt_text: str) -> Counter:
    """Proper-noun candidates and their counts, using find_unknowns' rules:
    a capitalised run that appears mid-sentence at least once."""
    text = extract_text(vtt_text)
    counts: Counter = Counter()
    mid: set[str] = set()
    for sentence in SENTENCE_END.split(text):
        for m in PROPER_RE.finditer(sentence):
            tok = m.group(1).strip()
            if tok in STOPWORDS or len(tok) < 3:
                continue
            counts[tok] += 1
            if m.start() > 0:
                mid.add(tok)
    return Counter({t: n for t, n in counts.items() if t in mid})


def classify(resolve, campaign_dir: Path, counts: Counter) -> dict:
    buckets: dict[str, list] = {
        "ruling": [], "ambiguous": [], "not_canon": [], "confirmed": []
    }
    for token, n in counts.most_common():
        r = resolve.resolve_name(campaign_dir, token)
        entry = {"token": token, "count": n}
        if r["status"] == "resolved":
            entry.update(
                canonical=r["canonical"], tier=r["tier"],
                authority=r["authority"], is_change=r["is_change"],
            )
            if r.get("parenthetical"):
                entry["parenthetical_unclassified"] = r["parenthetical"]
            buckets["ruling" if r["is_change"] else "confirmed"].append(entry)
        elif r["status"] == "ambiguous":
            entry.update(favoured=r["favoured"], conflicts=r["conflicts"])
            buckets["ambiguous"].append(entry)
        else:
            entry["near_misses"] = r.get("near_misses", [])
            buckets["not_canon"].append(entry)
    return buckets


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vtt", required=True, type=Path)
    ap.add_argument("--campaign-dir", required=True, type=Path)
    ap.add_argument("--campaign-generator", type=Path, default=None)
    ap.add_argument("--min-count", type=int, default=1)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    resolve = load_resolver(args.campaign_generator)
    counts = candidates(args.vtt.read_text(encoding="utf-8"))
    counts = Counter({t: n for t, n in counts.items() if n >= args.min_count})
    buckets = classify(resolve, args.campaign_dir, counts)

    out = {
        "vtt": str(args.vtt),
        "campaign_dir": str(args.campaign_dir),
        "candidates": sum(counts.values()),
        "distinct": len(counts),
        "counts": {k: len(v) for k, v in buckets.items()},
        **buckets,
    }
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    print(f"{out['distinct']} distinct candidates in {args.vtt.name}\n")
    for bucket, header in [
        ("ruling", "NAME CHANGES — show each of these to the GM"),
        ("ambiguous", "AMBIGUOUS — sources disagree, the GM rules"),
        ("not_canon", "NOT CANON — new-name candidates, do not invent a spelling"),
    ]:
        rows = buckets[bucket]
        print(f"── {header}  ({len(rows)})")
        for e in rows:
            if bucket == "ruling":
                print(f"   {e['token']!r} ×{e['count']} → {e['canonical']!r}  "
                      f"[tier {e['tier']} {e['authority']}]")
                if e.get("parenthetical_unclassified"):
                    print(f"       parenthetical (UNCLASSIFIED): "
                          f"{e['parenthetical_unclassified']}")
            elif bucket == "ambiguous":
                f = e["favoured"]
                others = ", ".join(f"{c['value']!r} (tier {c['tier']})"
                                   for c in e["conflicts"])
                print(f"   {e['token']!r} ×{e['count']}: {f['value']!r} "
                      f"(tier {f['tier']}) vs {others}")
            else:
                nm = ", ".join(f"{m['candidate']!r}" for m in e["near_misses"][:3])
                print(f"   {e['token']!r} ×{e['count']}"
                      + (f"   near: {nm}" if nm else ""))
        print()
    print(f"── confirmed canon (silent): {len(buckets['confirmed'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
