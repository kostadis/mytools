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


def apply(text: str, replacements: list[tuple[str, str]]) -> tuple[str, list[tuple[str, str, int]]]:
    """Returns (new_text, [(wrong, right, count), ...])."""
    log: list[tuple[str, str, int]] = []
    # Sort longest-first so multi-word forms replace before subword forms
    for wrong, right in sorted(replacements, key=lambda x: -len(x[0])):
        # Exact wrong form (may include 's already)
        pattern = re.compile(r"\b" + re.escape(wrong) + r"\b")
        new_text, n = pattern.subn(right, text)
        if n:
            log.append((wrong, right, n))
            text = new_text
        # Possessive auto-extension: only if the wrong form doesn't already end in 's
        if not wrong.endswith("'s"):
            poss_pattern = re.compile(r"\b" + re.escape(wrong) + r"'s\b")
            new_text, n = poss_pattern.subn(right + "'s", text)
            if n:
                log.append((wrong + "'s", right + "'s", n))
                text = new_text
    return text, log


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
    new_text, log = apply(vtt_text, replacements)

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


if __name__ == "__main__":
    main()
