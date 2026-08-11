#!/usr/bin/env python3
"""Lint a VTT-corrections glossary for rules that corrupt correct text.

The glossary is applied automatically to every future transcript, so a bad row
is not a one-off -- it is a standing rewrite rule. This script checks the rows
themselves (and, optionally, how they behave against real transcripts) BEFORE
apply_replacements.py runs.

Checks
------
ERROR   doubling      Canonical contains the wrong-form as a word, so the rule
                      fires on ALREADY-CORRECT text and appends the remainder
                      again ("Brin Bundlewine" -> "Brin Bundlewine Bundlewine").
                      apply_replacements.py now skips these, so the row is dead
                      weight until it is rewritten.
ERROR   conflict      One wrong-form mapped to two different canonicals. Which
                      one wins depends on row order -- not a decision to leave
                      to sorting.
ERROR   noop          wrong == right. Usually a typo in the row.
WARN    chained       A canonical also appears as someone else's wrong-form, so
                      output depends on which rule runs first. apply() sorts
                      longest-wrong-form-first, which is unrelated to intent.
WARN    split_section Same canonical has rows in two different sections.
                      add_to_glossary.py only looks inside the named section,
                      so the next append silently creates a third row.
WARN    common_word   Wrong-form is an ordinary English word. Replacement is
                      case-insensitive, so the rule also rewrites the lowercase
                      word in running prose ("dazzling" -> "Dazlyn").
WARN    corpus_lower  (only with --corpus) Wrong-form actually occurs lowercase
                      in a real transcript. This is the empirical version of
                      common_word and is far more reliable -- it catches
                      campaign-specific collisions no word list would know.

Exit status: 1 if any ERROR, else 0. WARNs never fail the run; several are
legitimate once reviewed.

Usage
-----
    lint_glossary.py --glossary notes/vtt_transcription_corrections.md
    lint_glossary.py --glossary <path> --corpus summaries/*/*.vtt
    lint_glossary.py --glossary <path> --quiet      # errors only
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from apply_replacements import is_self_matching  # type: ignore

# Ordinary English words that plausibly show up in a D&D transcript AND get
# used as names. Deliberately small and hand-picked: this check is a hint, not
# an authority. --corpus is the reliable version. Extend freely.
COMMON_WORDS = {
    "all", "and", "are", "back", "bean", "bless", "brace", "bright", "call",
    "charm", "chosen", "clear", "close", "cold", "cost", "dawn", "dazzling",
    "dear", "deep", "does", "down", "draw", "dust", "east", "eight", "embrace",
    "even", "evens", "fair", "fall", "fine", "fire", "five", "flash", "four",
    "free", "gain", "gem", "glory", "gold", "good", "grace", "grand", "half",
    "hard", "heart", "here", "hits", "home", "hoop", "hope", "hours", "iron",
    "keep", "kind", "king", "last", "leaf", "light", "like", "long", "lord",
    "lucky", "mark", "marked", "mate", "may", "mercy", "mind", "moral", "more",
    "moss", "natural", "near", "nine", "noble", "north", "odds", "old", "only",
    "over", "part", "passive", "peak", "pride", "quest", "radiant", "rage",
    "ready", "rest", "rich", "right", "rock", "rose", "rough", "sacred",
    "shadow", "sharp", "shield", "silver", "six", "smith", "some", "song",
    "south", "spring", "star", "starry", "stone", "storm", "summer", "sun",
    "swift", "sword", "time", "true", "under", "wave", "well", "west", "will",
    "winter", "wise", "wonder", "would", "young",
}

SEV_ERROR = "ERROR"
SEV_WARN = "WARN"


def parse_rows(path: Path):
    """Parse glossary rows, keeping section and line number for reporting.

    Returns [(line_no, section, wrong, canonical), ...] -- one entry per
    wrong-form, mirroring find_unknowns.parse_glossary's comma-splitting.
    """
    bold_re = re.compile(r"\*\*(.+?)\*\*")
    paren_re = re.compile(r"\s*\([^)]*\)\s*$")
    rows = []
    section = "(no section)"

    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if line.startswith("#"):
            section = line.lstrip("#").strip()
            continue
        if not line.startswith("|") or line.startswith("|---") or line.startswith("| Wrong"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 2:
            continue
        wrong_col, right_col = cols[0], cols[1]
        m = bold_re.search(right_col)
        canonical = paren_re.sub("", (m.group(1) if m else right_col).strip()).strip()
        if not canonical:
            continue
        for variant in wrong_col.split(","):
            v = variant.strip()
            if v:
                rows.append((line_no, section, v, canonical))
    return rows


def load_corpus(paths: list[Path]) -> str:
    parts = []
    for p in paths:
        try:
            parts.append(p.read_text(encoding="utf-8", errors="replace"))
        except OSError as e:
            print(f"  (skipping unreadable corpus file {p}: {e})", file=sys.stderr)
    return "\n".join(parts)


def lint(rows, corpus_text: str | None):
    findings = []  # (severity, check, line_no, message)

    by_wrong = defaultdict(set)
    canonical_sections = defaultdict(set)
    for line_no, section, wrong, canonical in rows:
        by_wrong[wrong.lower()].add(canonical)
        canonical_sections[canonical].add(section)
    canonicals_lc = {c.lower() for _, _, _, c in rows}

    seen_conflict = set()
    for line_no, section, wrong, canonical in rows:
        # -- ERROR: non-idempotent doubling --------------------------------
        if is_self_matching(wrong, canonical):
            doubled = re.sub(r"\b" + re.escape(wrong) + r"\b", canonical,
                             canonical, flags=re.IGNORECASE)
            findings.append((
                SEV_ERROR, "doubling", line_no,
                f"{wrong!r} -> {canonical!r}: applying this to the already-correct "
                f"{canonical!r} yields {doubled!r}. "
                f"Either drop the row (let {wrong!r} stand on its own) or map it to "
                f"a canonical that does not contain it."))

        # -- ERROR: no-op ---------------------------------------------------
        if wrong.lower() == canonical.lower():
            findings.append((
                SEV_ERROR, "noop", line_no,
                f"{wrong!r} maps to itself. Remove the row."))

        # -- ERROR: same wrong-form, two canonicals -------------------------
        if len(by_wrong[wrong.lower()]) > 1 and wrong.lower() not in seen_conflict:
            seen_conflict.add(wrong.lower())
            targets = ", ".join(repr(t) for t in sorted(by_wrong[wrong.lower()]))
            findings.append((
                SEV_ERROR, "conflict", line_no,
                f"{wrong!r} is mapped to more than one canonical: {targets}. "
                f"Row order decides the winner."))

        # -- WARN: chained rules --------------------------------------------
        if wrong.lower() in canonicals_lc and wrong.lower() != canonical.lower():
            findings.append((
                SEV_WARN, "chained", line_no,
                f"{wrong!r} is itself a canonical elsewhere but is rewritten to "
                f"{canonical!r} here. Any rule producing {wrong!r} leaves output "
                f"that this rule may or may not reach, depending on order."))

        # -- WARN: common English word ---------------------------------------
        if wrong.lower() in COMMON_WORDS:
            findings.append((
                SEV_WARN, "common_word", line_no,
                f"{wrong!r} is an ordinary word; matching is case-insensitive, so "
                f"this also rewrites lowercase {wrong.lower()!r} in prose. "
                f"Prefer a targeted edit on the one transcript."))

        # -- WARN: empirical lowercase collision -----------------------------
        # Search the corpus AS WRITTEN (never case-folded) for a genuinely
        # lowercase occurrence -- case-folding the corpus would make every
        # wrong-form match itself.
        if corpus_text and wrong.lower() not in COMMON_WORDS and wrong.lower() != wrong:
            # Same edge-aware boundaries as apply_replacements.word_pattern, so
            # this check agrees with what the applier would actually rewrite
            # (\b around punctuation-edged forms like "L.A." never matches).
            lw = wrong.lower()
            lead = r"\b" if re.match(r"\w", lw[:1]) else r"(?<!\w)"
            tail = r"\b" if re.match(r"\w", lw[-1:]) else r"(?!\w)"
            if re.search(lead + re.escape(lw) + tail, corpus_text):
                findings.append((
                    SEV_WARN, "corpus_lower", line_no,
                    f"{wrong!r} occurs in lowercase in the corpus; this rule would "
                    f"rewrite those occurrences too."))

    # -- WARN: canonical split across sections -------------------------------
    for canonical, sections in sorted(canonical_sections.items()):
        if len(sections) > 1:
            where = ", ".join(sorted(sections))
            findings.append((
                SEV_WARN, "split_section", 0,
                f"{canonical!r} has rows in multiple sections ({where}). "
                f"add_to_glossary.py searches only within one section, so the next "
                f"append will create yet another row."))

    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glossary", required=True, type=Path)
    ap.add_argument("--corpus", nargs="*", type=Path, default=[],
                    help="Transcript files to check wrong-forms against empirically")
    ap.add_argument("--quiet", action="store_true", help="Show ERRORs only")
    args = ap.parse_args()

    if not args.glossary.exists():
        print(f"glossary not found: {args.glossary}", file=sys.stderr)
        return 2

    rows = parse_rows(args.glossary)
    corpus_text = load_corpus(args.corpus) if args.corpus else None

    findings = lint(rows, corpus_text)
    if args.quiet:
        findings = [f for f in findings if f[0] == SEV_ERROR]

    errors = sum(1 for f in findings if f[0] == SEV_ERROR)
    warns = len(findings) - errors

    print(f"{args.glossary}: {len(rows)} wrong-form(s)"
          + (f", corpus {len(args.corpus)} file(s)" if args.corpus else ""))
    if not findings:
        print("clean.")
        return 0

    order = {SEV_ERROR: 0, SEV_WARN: 1}
    for sev, check, line_no, msg in sorted(findings, key=lambda f: (order[f[0]], f[2])):
        loc = f"{args.glossary}:{line_no}" if line_no else str(args.glossary)
        print(f"\n{sev} [{check}] {loc}\n  {msg}")

    print(f"\n{errors} error(s), {warns} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
