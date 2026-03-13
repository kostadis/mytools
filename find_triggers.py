#!/usr/bin/env python3
"""
find_triggers.py — identify candidate content-filter trigger phrases in
rejected PDF chunks and emit a substitution config for pdf_to_5etools_1e.py.

Usage
-----
# Analyse one or more debug input files:
    python3 find_triggers.py chunk-0002-p8-input.txt [chunk-0003-p9-input.txt ...]

# Pipe or redirect text directly:
    cat rejected_page.txt | python3 find_triggers.py -

# Write a config file ready to use with --trigger-config:
    python3 find_triggers.py chunk*.txt --out triggers.json

Config format (JSON, consumed by pdf_to_5etools_1e.py --trigger-config):
    [
      {"pattern": "young girl",  "replacement": "young person",  "flags": "i"},
      {"pattern": "enslaved?",   "replacement": "captured",      "flags": "i"}
    ]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Known-safe words: common D&D / RPG vocabulary that should never be flagged
# ---------------------------------------------------------------------------
_SAFE = {
    "dragon", "dungeon", "fighter", "wizard", "cleric", "thief", "ranger",
    "paladin", "barbarian", "orc", "goblin", "troll", "giant", "demon",
    "devil", "undead", "skeleton", "zombie", "vampire", "lycanthrope",
    "spell", "magic", "sword", "axe", "dagger", "armor", "shield", "bow",
    "crossbow", "potion", "scroll", "wand", "staff", "ring", "amulet",
    "treasure", "gold", "silver", "copper", "platinum", "gems", "coins",
    "hit", "points", "level", "class", "race", "alignment", "chaotic",
    "lawful", "neutral", "evil", "good", "charisma", "strength", "dexterity",
    "constitution", "intelligence", "wisdom", "attack", "damage", "saving",
    "throw", "initiative", "movement", "encounter", "wandering", "monster",
    "room", "corridor", "door", "trap", "secret", "dungeon", "adventure",
    "module", "campaign", "player", "character", "game", "master", "role",
    "playing", "table", "dice", "roll", "check", "combat", "round", "turn",
    "inn", "tavern", "village", "town", "city", "castle", "keep", "temple",
    "shrine", "forest", "mountain", "river", "road", "path", "bridge",
    "farm", "barn", "cottage", "house", "building", "shop", "market",
    "merchant", "trader", "guard", "militia", "soldier", "knight", "lord",
    "lady", "king", "queen", "prince", "duke", "baron", "viscount",
    "druid", "faith", "cleric", "priest", "acolyte", "monk", "friar",
}

# ---------------------------------------------------------------------------
# Seed list: phrases already known to trigger the filter (from built-in list)
# ---------------------------------------------------------------------------
_KNOWN_TRIGGERS = [
    r'\benslave[ds]?\b',
    r'\benslavement\b',
    r',?\s*and\s+worse\b',
    r'\bwenche?s?\b',
    r'\bbuxom\b',
    r'\bharlots?\b',
    r'\bstrumpets?\b',
    r'\bconcubines?\b',
    r'\byoung\s+girl\b',
    r'\bteen[- ]?aged?\s+(?:girl|daughter)s?\b',
    r'\bcarousing\b',
    r'\blusts?\b|\blusted\b|\blusting\b',
    r'\blustful\b',
    r'\bBeloved\b',
    r'\bmurderous\b',
    r'\boppressors?\b',
    r'\bslaughter\b',
    r'\babominations?\b',
    r'\bpestilence\b',
    r'\bwickedness\b',
    r'\btyranny\b',
    r'\bhubris\b',
]

# Suggested replacements for common patterns (pattern fragment → replacement)
_SUGGESTIONS: list[tuple[str, str]] = [
    ("enslave",      "captured"),
    ("wench",        "barmaid"),
    ("harlot",       "commoner"),
    ("strumpet",     "commoner"),
    ("concubine",    "companion"),
    ("buxom",        "cheerful"),
    ("carousing",    "drinking"),
    ("young girl",   "young person"),
    ("teen",         "young adult"),
    ("maiden",       "person"),
    ("nubile",       "young"),
    ("nymphet",      "youth"),
    ("virgin",       "young person"),
    ("ravish",       "attack"),
    ("defile",       "desecrate"),
    ("violate",      "attack"),
    ("molest",       "harass"),
    ("debauch",      "corrupt"),
    ("lewd",         "improper"),
    ("lascivious",   "wicked"),
    ("licentious",   "corrupt"),
    ("wanton",       "reckless"),
    ("fornication",  "vice"),
    ("adultery",     "betrayal"),
    ("lust",         "greed"),
    ("lustful",      "greedy"),
    ("carnal",       "worldly"),
    ("copulate",     "consort"),
    ("brothel",      "tavern"),
    ("bordello",     "tavern"),
    ("prostitut",    "commoner"),
    ("whore",        "commoner"),
]


def _load_text(sources: list[str]) -> str:
    """Read all source files (or stdin if '-') into a single string."""
    parts: list[str] = []
    for src in sources:
        if src == "-":
            parts.append(sys.stdin.read())
        else:
            p = Path(src)
            if not p.exists():
                print(f"[WARN] File not found: {src}", file=sys.stderr)
                continue
            parts.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def _extract_words(text: str) -> list[str]:
    """Return all word-tokens (lower-case) from text, deduplicated."""
    tokens = re.findall(r"[A-Za-z]{3,}", text)
    return list(dict.fromkeys(t.lower() for t in tokens))


def _score_word(word: str) -> float:
    """
    Return a suspicion score 0–1.  Higher = more likely to trigger filter.

    Heuristics:
    - Word appears in the known-safe D&D vocab → 0
    - Word partially matches a known-trigger seed → 0.9
    - Word is in the suggestions list → 0.7
    - Word is short or all-caps (stat-block abbreviation) → 0
    - Otherwise: rough heuristic based on character patterns
    """
    if word in _SAFE:
        return 0.0
    # All-caps abbreviations (AC, MV, HD, etc.) are fine
    if word.upper() == word and len(word) <= 5:
        return 0.0

    for pattern in _KNOWN_TRIGGERS:
        if re.search(pattern, word, re.IGNORECASE):
            return 0.9

    for fragment, _ in _SUGGESTIONS:
        if fragment.lower() in word:
            return 0.7

    return 0.0


def _find_candidate_phrases(text: str) -> list[tuple[float, str, str]]:
    """
    Return list of (score, phrase, suggested_replacement) sorted by score desc.
    Checks both single words and common two-word phrases.
    """
    results: dict[str, tuple[float, str]] = {}

    # Single words
    for word in _extract_words(text):
        score = _score_word(word)
        if score > 0:
            replacement = ""
            for frag, repl in _SUGGESTIONS:
                if frag.lower() in word:
                    replacement = repl
                    break
            results[word] = (score, replacement)

    # Two-word phrases (bigrams)
    tokens = re.findall(r"[A-Za-z]{2,}", text)
    for i in range(len(tokens) - 1):
        phrase = f"{tokens[i].lower()} {tokens[i+1].lower()}"
        if phrase in results:
            continue
        phrase_score = max(_score_word(tokens[i].lower()),
                           _score_word(tokens[i+1].lower()))
        # Boost if both words together match a suggestions entry
        for frag, repl in _SUGGESTIONS:
            if frag.lower() in phrase:
                phrase_score = max(phrase_score, 0.8)
                results[phrase] = (phrase_score, repl)
                break

    return sorted(
        [(score, phrase, repl) for phrase, (score, repl) in results.items()],
        key=lambda x: -x[0],
    )


def _build_config(candidates: list[tuple[float, str, str]]) -> list[dict]:
    entries: list[dict] = []
    seen: set[str] = set()
    for score, phrase, replacement in candidates:
        if score < 0.5:
            continue
        # Build a simple word-boundary regex for the phrase
        words = phrase.split()
        pattern = r'\b' + r'\s+'.join(re.escape(w) for w in words) + r'\b'
        if pattern in seen:
            continue
        seen.add(pattern)
        entries.append({
            "pattern":     pattern,
            "replacement": replacement or f"[{phrase}]",
            "flags":       "i",
        })
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Identify content-filter trigger phrases in rejected PDF chunks.",
    )
    parser.add_argument(
        "sources", nargs="+", metavar="FILE",
        help="Debug input files to analyse, or '-' for stdin",
    )
    parser.add_argument(
        "--out", metavar="FILE",
        help="Write substitution config JSON to this file (default: stdout)",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.5, metavar="0-1",
        help="Minimum score to include in output (default: 0.5)",
    )
    parser.add_argument(
        "--show-all", action="store_true",
        help="Print all scored candidates, not just those above threshold",
    )
    args = parser.parse_args()

    text = _load_text(args.sources)
    if not text.strip():
        sys.exit("No text to analyse.")

    candidates = _find_candidate_phrases(text)

    # Print human-readable summary
    print("\nCandidate trigger phrases (score ≥ 0.0):")
    print(f"{'Score':>6}  {'Phrase':<30}  Suggested replacement")
    print("-" * 65)
    shown = 0
    for score, phrase, replacement in candidates:
        if not args.show_all and score < args.threshold:
            continue
        repl_display = replacement or "(no suggestion — review manually)"
        print(f"  {score:.2f}  {phrase:<30}  {repl_display}")
        shown += 1
    if shown == 0:
        print("  (none found above threshold)")
    print()

    # Build config
    config = _build_config(
        [(s, p, r) for s, p, r in candidates if s >= args.threshold]
    )

    if not config:
        print("No entries to write to config.")
        return

    config_json = json.dumps(config, indent=2, ensure_ascii=False)

    if args.out:
        Path(args.out).write_text(config_json + "\n", encoding="utf-8")
        print(f"Config written to: {args.out}")
        print(f"Use with: python3 pdf_to_5etools_1e.py ... --trigger-config {args.out}")
    else:
        print("Config JSON (save to a file and pass with --trigger-config):")
        print(config_json)


if __name__ == "__main__":
    main()
