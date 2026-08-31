#!/usr/bin/env python3
"""Lightweight preflight checks for campaign chapter markdown.

This script intentionally flags possible issues rather than deciding them.
Use it before and after an editorial pass to catch transcript artifacts,
timeline slips, and repeated narration motifs that are easy to miss by eye.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


CHECKS: list[tuple[str, str, str]] = [
    ("transcript-artifact", r"\bFat painting\b", "possible garbled 'That painting'"),
    ("transcript-artifact", r"\bframed by boarding\b", "possible garbled 'framed by morning'"),
    ("grammar", r"\bwith we mortals\b", "likely 'with us mortals'"),
    ("transcript-artifact", r"\bskulled reproduction\b", "possible garbled phrase"),
    ("canon-spelling", r"\bFaerzess\b", "check spelling: faerzress/Faerzress"),
    ("canon-spelling", r"\bZugztmoy\b", "check spelling: Zuggtmoy"),
    ("canon-spelling", r"\bBlingdenston\b", "check spelling: Blingdenstone"),
    ("canon-spelling", r"\bVelkenyvelve\b", "check spelling: Velkynvelve"),
    ("canon-spelling", r"\bPliinki\b", "verify local canon spelling versus Plinki/Pliinki"),
    ("timeline-risk", r"\bCandlekeep had been\b", "may imply Candlekeep already happened"),
    ("timeline-risk", r"\balready returned\b", "check whether event has happened yet"),
    ("overclaim-risk", r"\bconfirmed that\b", "ensure this is revealed canon, not inference"),
    ("overclaim-risk", r"\bproved that\b", "ensure proof level is supported"),
]

MOTIFS: list[tuple[str, str, int]] = [
    ("zalthir-class-motif", r"\bThere was a class\b|\bhad a curriculum for this\b", 1),
    ("notes-motif", r"\bI took notes\b", 4),
    ("daz-ledger-motif", r"\bledger\b|\baudit(?:ing)?\b", 5),
]


def line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("chapter", type=Path)
    args = parser.parse_args()

    text = args.chapter.read_text(encoding="utf-8")
    findings: list[str] = []

    for category, pattern, note in CHECKS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            line = line_number(text, match.start())
            excerpt = match.group(0)
            findings.append(f"{line}: [{category}] {excerpt!r} - {note}")

    for category, pattern, threshold in MOTIFS:
        matches = list(re.finditer(pattern, text, flags=re.IGNORECASE))
        if len(matches) > threshold:
            lines = ", ".join(str(line_number(text, m.start())) for m in matches)
            findings.append(
                f"-: [{category}] {len(matches)} occurrences over threshold {threshold}; lines {lines}"
            )

    if findings:
        print("\n".join(findings))
    else:
        print("No preflight flags.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
