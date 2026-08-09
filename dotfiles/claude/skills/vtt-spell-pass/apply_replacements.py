#!/usr/bin/env python3
"""Apply known wrong-form -> canonical replacements to a VTT transcript.

Reads the corrections glossary, then performs word-boundary replacements
on the transcript. Writes the corrected file alongside the original with
suffix ``.cleaned.vtt`` (or to --output if given).

Possessive handling: if "Glabbagool" is the canonical and "Lavagul's"
is a wrong-form, the apostrophe form is replaced as written. The script
also auto-fixes the bare possessive form: e.g. if "Lavagul" is a known
wrong-form for "Glabbagool", "Lavagul's" -> "Glabbagool's" is also
applied.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))
from find_unknowns import parse_glossary  # type: ignore


def word_pattern(literal: str) -> re.Pattern:
    """Compile a boundary-safe, case-insensitive pattern for a wrong-form.

    ``\\b`` asserts a transition between a word char and a non-word char, so a
    wrong-form whose first or last char is punctuation (``L.A.``, ``Glabagul-``)
    can never match its normal context -- ``\\bL\\.A\\.\\b`` needs a WORD char
    after the final period, but real text has a space there. Such rows sit in
    the glossary looking valid and never fire (or worse, only fire glued to the
    next word). Use ``\\b`` for word-char edges and explicit lookarounds for
    punctuation edges; word-char-edged forms behave exactly as before.
    """
    lead = r"\b" if re.match(r"\w", literal[:1]) else r"(?<!\w)"
    tail = r"\b" if re.match(r"\w", literal[-1:]) else r"(?!\w)"
    return re.compile(lead + re.escape(literal) + tail, re.IGNORECASE)


def is_self_matching(wrong: str, right: str) -> bool:
    """True if applying ``wrong -> right`` is not idempotent.

    When the canonical contains the wrong-form as a whole word, the rule fires
    on text that is ALREADY CORRECT and appends the remainder again:

        "Brin -> Brin Bundlewine"  turns  "Brin Bundlewine"
                                   into   "Brin Bundlewine Bundlewine"

    The trigger is a correct transcript, not a mangled one, so the better the
    transcription the more damage the rule does. Such a row is expressing
    "expand a short name to the full name", which a single word-boundary
    substitution cannot do safely -- it has no way to tell an unexpanded
    mention from an already-expanded one. Skip the rule rather than corrupt.
    """
    return word_pattern(wrong).search(right) is not None


def apply(
    text: str, replacements: list[tuple[str, str]]
) -> tuple[str, list[tuple[str, str, int]], list[tuple[str, str]]]:
    """Returns (new_text, [(wrong, right, count), ...], [(wrong, right), ...skipped])."""
    log: list[tuple[str, str, int]] = []
    skipped: list[tuple[str, str]] = []
    # Sort longest-first so multi-word forms replace before subword forms
    for wrong, right in sorted(replacements, key=lambda x: -len(x[0])):
        # Guard: never apply a non-idempotent rule (see is_self_matching).
        if is_self_matching(wrong, right):
            skipped.append((wrong, right))
            continue
        # Case-insensitive match so mid-sentence lowercase forms are caught
        # (VTT transcripts capitalise at sentence start; wrong-forms in the
        # glossary are Title Case but appear lowercase mid-sentence in the VTT)
        new_text, n = word_pattern(wrong).subn(right, text)
        if n:
            log.append((wrong, right, n))
            text = new_text
        # Possessive auto-extension: only if the wrong form doesn't already end in 's
        if not wrong.endswith("'s"):
            new_text, n = word_pattern(wrong + "'s").subn(right + "'s", text)
            if n:
                log.append((wrong + "'s", right + "'s", n))
                text = new_text
    return text, log, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vtt", required=True, type=Path)
    ap.add_argument("--glossary", required=True, type=Path)
    ap.add_argument("--output", type=Path,
                    help="Output path. Default: <vtt-stem>.cleaned.vtt next to original")
    ap.add_argument("--in-place", action="store_true",
                    help="Overwrite the original VTT (use with caution)")
    args = ap.parse_args()

    vtt_text = args.vtt.read_text(encoding="utf-8")
    replacements, _ = parse_glossary(args.glossary)
    new_text, log, skipped = apply(vtt_text, replacements)

    if args.in_place:
        out_path = args.vtt
    elif args.output:
        out_path = args.output
    else:
        out_path = args.vtt.with_suffix(".cleaned.vtt")

    out_path.write_text(new_text, encoding="utf-8")

    print(f"Wrote {out_path}")
    print(f"Replacements applied:")
    total = 0
    for wrong, right, n in log:
        print(f"  {wrong!r} -> {right!r}: {n}")
        total += n
    print(f"Total: {total}")

    if skipped:
        print(f"\nSKIPPED {len(skipped)} non-idempotent rule(s) "
              f"(canonical contains the wrong-form; would double on correct text):")
        for wrong, right in skipped:
            print(f"  {wrong!r} -> {right!r}")
        print("Run lint_glossary.py for the full report and how to fix these.")


if __name__ == "__main__":
    main()
