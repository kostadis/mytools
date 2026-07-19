#!/usr/bin/env python3
"""Phase 3 — apply confirmed, per-instance scrub decisions.

Every decision here was individually confirmed by the GM in Phase 2 (see
SKILL.md). This script performs no judgment of its own: it takes an exact
line number and an exact old->new span, verifies the old text is still
present on that line (abort on drift rather than guess), and replaces it.
The original file is never modified; output goes to <file>.scrubbed.md.

This never operates on whole lines by default — only the matched span — so a
quoted line of dialogue is never silently dropped. If a decision's "old"
happens to be the full dialogue line (e.g. a roll-result rewrite), that's a
one-for-one sentence replacement the GM explicitly approved, not a deletion.

Usage:
    python apply_scrub.py --file <narration.md-or-preview> \\
        --decisions <decisions.json> --output <file>.scrubbed.md

decisions.json:
    [{"line": 21, "old": "\"I have twenty-two.\"", "new": "\"Let me look.\""}, ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from find_residue import split_frontmatter  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", required=True, type=Path)
    ap.add_argument("--decisions", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()

    if not args.file.is_file():
        print(f"error: not a file: {args.file}", file=sys.stderr)
        return 2
    if not args.decisions.is_file():
        print(f"error: not a file: {args.decisions}", file=sys.stderr)
        return 2

    raw = args.file.read_text(encoding="utf-8")
    frontmatter, body, body_start_line = split_frontmatter(raw)
    lines = body.split("\n")

    decisions = json.loads(args.decisions.read_text(encoding="utf-8"))
    applied, errors = 0, []

    for d in decisions:
        idx = d["line"] - body_start_line
        if idx < 0 or idx >= len(lines):
            errors.append(f"line {d['line']}: out of range")
            continue
        line = lines[idx]
        if line.count(d["old"]) != 1:
            errors.append(
                f"line {d['line']}: expected exactly one occurrence of "
                f"{d['old']!r}, found {line.count(d['old'])} — file may have drifted "
                f"since Phase 1/2; skipped"
            )
            continue
        lines[idx] = line.replace(d["old"], d["new"], 1)
        applied += 1

    if errors:
        print("errors (these decisions were NOT applied):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)

    out_body = "\n".join(lines)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(frontmatter + out_body, encoding="utf-8")

    print(f"applied {applied}/{len(decisions)} decision(s)", file=sys.stderr)
    print(f"wrote: {args.output}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
