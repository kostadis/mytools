#!/usr/bin/env python3
"""Phase 1 — deterministic mechanical-residue scanner for session_doc narrations.

Regex/rule-based, no LLM. Surfaces *candidate* mechanical residue in narration
prose: raw numbers riding on DC/AC/HP/damage/healing/feet/rounds/initiative,
out-of-fiction table-speak, and real player names appearing as speakers.

Hard invariant (see SKILL.md "Why this design" / GitHub issue #151): this
scanner has NO category for spell names or magic vocabulary. It cannot flag
"Fireball" or "Speak with Dead" as residue because it never looks for
vocabulary at all — only numbers and fixed table-speak phrases. That is what
makes the spell-stripping incident structurally impossible here, not a
prompt instruction that an LLM could still get wrong.

Usage:
    python find_residue.py --file <narration.md> [--protect <file>]... \\
        [--state <campaign>/notes/.scrub_state.json] [--players "Gabe,Joe Beda"]

Emits JSON to stdout: {"file": ..., "candidates": [...]}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Translation-scale tables, ported directly from the existing (human-authored)
# scrub_mechanics_prompt.md tiers. These are lookup tables, not invention —
# Phase 1 attaches a *tier hint*, never a full sentence rewrite. The actual
# prose rendering happens in Phase 2, in front of the GM, one candidate at a
# time (see SKILL.md).
# ---------------------------------------------------------------------------

DAMAGE_SCALE = [
    (1, 10, "glancing, absorbed — a bruise through armor, shaken off"),
    (11, 20, "real impact — a hit that costs something"),
    (21, 40, "serious — takes a chunk out of what's left"),
    (41, None, "brutal — for typed sources, render the sensation of the element; no gore"),
]

HP_SCALE = [
    (0, 9, "on the verge of collapse — running on reflex"),
    (10, 19, "on the edge — one more bad round ends it"),
    (20, 35, "worn down, accumulated hits, still margin"),
    (36, None, "hurt but functional, reserve still there"),
]

DC_SCALE = [
    (0, 10, "routine effort"),
    (11, 15, "hard push, real resistance"),
    (16, 20, "near the edge of what a person can do"),
    (21, None, "leaves a mark — almost impossible"),
]


def tier_hint(value: int, scale: list[tuple[int, int | None, str]]) -> str | None:
    for lo, hi, hint in scale:
        if value >= lo and (hi is None or value <= hi):
            return hint
    return None


NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
}
_NUM_WORD_ALT = "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))
# NB: _NUM_WORD_ALT must be wrapped in its own group before the optional
# hyphen suffix — otherwise "|" binds the suffix only to the *last*
# alternative in the chain (e.g. "ten"), so "twenty-two" would match only
# "twenty" and silently drop "-two".
_NUM_TOKEN = rf"(?:\d+|(?:{_NUM_WORD_ALT})(?:-(?:{_NUM_WORD_ALT}))?)"


def word_to_int(tok: str) -> int | None:
    tok = tok.lower().strip()
    if tok.isdigit():
        return int(tok)
    if "-" in tok:
        a, b = tok.split("-", 1)
        if a in NUMBER_WORDS and b in NUMBER_WORDS:
            return NUMBER_WORDS[a] + NUMBER_WORDS[b]
    return NUMBER_WORDS.get(tok)


# ---------------------------------------------------------------------------
# Candidate categories. Each entry: (category, compiled regex, scale_or_None)
# All patterns are number- or fixed-phrase-based. None reference spell names,
# creature names, or any open-ended vocabulary list — see module docstring.
# ---------------------------------------------------------------------------

PATTERNS = [
    ("dc_number", re.compile(r"\bDC[\s-]*(\d+)\b"), DC_SCALE),
    ("ac_number", re.compile(r"\bAC[\s-]*(\d+)\b"), None),
    ("hp_number", re.compile(
        r"\b(\d+)\s*(?:hp|hit points?)\b|\b(?:hp|hit points?)[\s:]*(\d+)\b",
        re.IGNORECASE), HP_SCALE),
    ("damage_number", re.compile(
        rf"\b({_NUM_TOKEN})\s*(?:points?\s+of\s+)?damage\b|\bdeals?\s+({_NUM_TOKEN})\b",
        re.IGNORECASE), DAMAGE_SCALE),
    ("heal_number", re.compile(
        rf"\bheal(?:ed|s|ing)?\s+(?:for\s+)?({_NUM_TOKEN})\b", re.IGNORECASE), HP_SCALE),
    ("foot_count", re.compile(
        rf"\b({_NUM_TOKEN})[\s-]*(?:foot|feet|ft\.?)\b", re.IGNORECASE), None),
    ("round_count", re.compile(
        r"\b(?:first|second|third|fourth|fifth|sixth|\d+(?:st|nd|rd|th))\s+round\b"
        r"|\b(\d+)\s*seconds?\s+of\s+combat\b", re.IGNORECASE), None),
    ("initiative", re.compile(
        r"\binitiative\s+(?:order|tracker)\b"
        r"|\brolled?\s+for\s+initiative\b"
        r"|\b[+-]\s?\d+\s+(?:to\s+)?initiative\b", re.IGNORECASE), None),
    ("roll_callout", re.compile(
        r"\broll(?:ed|ing)?\s+(?:an?\s+)?(?:\w+\s+){0,2}?(?:check|save|saving throw)\b"
        r"|\bpassive\s+(?:investigation|perception|insight|\w+)\b", re.IGNORECASE), None),
    ("roll_result_dialogue", re.compile(
        rf"\bI\s+(?:got|have|rolled)\s+(?:a\s+)?(?:natural\s+)?({_NUM_TOKEN})\b",
        re.IGNORECASE), None),
    # Broad and deliberately noisy: catches "you rolled pretty good medicine",
    # "if we roll, we got what we got", "he rolled a whatever" — real-world
    # residue this campaign's narration actually contains that the narrower
    # categories above miss. Also catches non-residue like "he rolled over
    # in his sleep" or "rolled up his sleeves" — expected false positives,
    # same as foot_count (see SKILL.md). Surface, let the GM reject.
    ("dice_verb", re.compile(
        r"\b(?:you|I|we|he|she|they)(?:'ve|'d|'re)?\s+roll(?:ed|ing)?\b",
        re.IGNORECASE), None),
    ("advantage_with_number", re.compile(
        r"[+-]\s?\d+.{0,20}?(?:advantage|disadvantage)"
        r"|(?:advantage|disadvantage).{0,20}?[+-]\s?\d+", re.IGNORECASE), None),
]

TABLE_SPEAK_PHRASES = [
    "the DM", "the GM", "came the call", "the table debated", "we rolled",
    "someone rolled", "he looked it up", "she looked it up",
    "the initiative tracker", "run the numbers", "assessing the damage",
]


def split_frontmatter(text: str) -> tuple[str, str, int]:
    """Return (frontmatter, body, body_start_line). body_start_line is 1-indexed."""
    if not text.startswith("---\n"):
        return "", text, 1
    end = text.find("\n---\n", 4)
    if end == -1:
        return "", text, 1
    fm = text[: end + 5]
    return fm, text[end + 5:], fm.count("\n") + 1


_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def mask_html_comments(text: str) -> str:
    """Blank out <!-- ... --> spans so no pattern can match inside them.

    Every character is replaced with a space except newlines, so offsets and
    line numbers stay exact and `context` can still be taken from the
    unmasked line.

    Why: sd_narrate writes a `<!-- table-speech reclassified: ... -->` hatch
    quoting the raw table speech it pulled — roll instructions included
    ("Valphine, roll your insight."). That is an audit record of text already
    removed from the fiction, and assemble.py strips the comment at assembly.
    A match inside it is therefore always a false positive. This mirrors the
    existing frontmatter handling: a region the scanner should not read.

    Narrowing only — this can suppress false hits, never mask a real one,
    because prose outside comments is left byte-identical.
    """
    def _blank(m: re.Match) -> str:
        return "".join("\n" if ch == "\n" else " " for ch in m.group(0))

    return _COMMENT_RE.sub(_blank, text)


def load_player_names(party_md: Path | None) -> list[str]:
    if not party_md or not party_md.is_file():
        return []
    names = []
    text = party_md.read_text(encoding="utf-8")
    for m in re.finditer(r"Player:\s*([A-Za-z][A-Za-z'.\- ]*)", text):
        name = m.group(1).split(",")[0].strip()
        name = re.split(r"\bFaith\b|\bClass\b", name)[0].strip()
        if name:
            names.append(name)
    return sorted(set(names), key=len, reverse=True)


def load_protect_terms(paths: list[Path]) -> set[str]:
    terms: set[str] = set()
    for p in paths:
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                terms.add(line.lower())
    return terms


def load_state_ignored(state_path: Path | None) -> set[str]:
    if not state_path or not state_path.is_file():
        return set()
    data = json.loads(state_path.read_text(encoding="utf-8"))
    return {x.lower() for x in data.get("ignored", [])}


def scan(body: str, body_start_line: int, player_names: list[str],
         protect: set[str], ignored: set[str]) -> list[dict]:
    lines = body.split("\n")
    # Matched against the masked copy so <!-- --> spans are unreadable to every
    # pattern; `context` is still taken from the unmasked line above.
    masked_lines = mask_html_comments(body).split("\n")
    candidates = []
    cid = 0

    def add(category, line_no, match_text, context, hint=None):
        nonlocal cid
        if match_text.lower() in protect or match_text.lower() in ignored:
            return
        cid += 1
        candidates.append({
            "id": f"c{cid}",
            "category": category,
            "line": line_no,
            "match": match_text,
            "context": context.strip(),
            "hint": hint,
        })

    for i, line in enumerate(lines):
        line_no = body_start_line + i
        scan_line = masked_lines[i]
        stripped = scan_line.strip()
        if not stripped:
            continue

        for category, pattern, scale in PATTERNS:
            for m in pattern.finditer(scan_line):
                match_text = m.group(0)
                hint = None
                if scale is not None:
                    num_tok = next((g for g in m.groups() if g), None)
                    val = word_to_int(num_tok) if num_tok else None
                    if val is not None:
                        hint = tier_hint(val, scale)
                add(category, line_no, match_text, line, hint)

        low = scan_line.lower()
        for phrase in TABLE_SPEAK_PHRASES:
            if phrase.lower() in low:
                idx = low.find(phrase.lower())
                add("table_speak", line_no, scan_line[idx: idx + len(phrase)], line)

        for name in player_names:
            if re.search(rf"\b{re.escape(name)}\b", scan_line):
                add("player_name", line_no, name, line)

    return candidates


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", required=True, type=Path)
    ap.add_argument("--protect", action="append", default=[], type=Path,
                     help="Flat file of terms to never flag (one per line). Repeatable.")
    ap.add_argument("--state", type=Path, default=None,
                     help="Path to .scrub_state.json — its 'ignored' list is subtracted.")
    ap.add_argument("--party-md", type=Path, default=None,
                     help="docs/party.md — sourced for real player names (out-of-fiction).")
    args = ap.parse_args()

    if not args.file.is_file():
        print(f"error: not a file: {args.file}", file=sys.stderr)
        return 2

    raw = args.file.read_text(encoding="utf-8")
    _, body, body_start_line = split_frontmatter(raw)

    player_names = load_player_names(args.party_md)
    protect = load_protect_terms(args.protect)
    ignored = load_state_ignored(args.state)

    candidates = scan(body, body_start_line, player_names, protect, ignored)

    print(json.dumps({
        "file": str(args.file),
        "player_names_loaded": player_names,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
