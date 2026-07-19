#!/usr/bin/env python3
"""Phase 1b — deterministically apply already-approved durable rules.

Mirrors vtt-spell-pass's "collapse the set first" step: before bothering the
GM with candidates, silently fix everything a prior session already ruled on
(state.json "rules"), then re-scan with find_residue.py so only the true
residual — genuinely new decisions — gets asked about.

Literal, case-sensitive substring replacement only. No regex, no
case-insensitive matching (that's the landmine vtt-spell-pass's apply
documents: a short rule text that's also a common word/phrase would
over-replace). Never touches frontmatter.

Usage:
    python apply_known_rules.py --file <narration.md> --state <state.json> \\
        --output /tmp/preview.md
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
    ap.add_argument("--state", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()

    if not args.file.is_file():
        print(f"error: not a file: {args.file}", file=sys.stderr)
        return 2

    raw = args.file.read_text(encoding="utf-8")
    frontmatter, body, _ = split_frontmatter(raw)

    rules = []
    if args.state.is_file():
        rules = json.loads(args.state.read_text(encoding="utf-8")).get("rules", [])

    applied = 0
    for rule in rules:
        match, repl = rule["match"], rule["replacement"]
        count = body.count(match)
        if count:
            body = body.replace(match, repl)
            applied += count
            print(f"[rule] {match!r} -> {repl!r}  ({count}x)", file=sys.stderr)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(frontmatter + body, encoding="utf-8")
    print(f"applied {applied} durable-rule replacement(s) across {len(rules)} rule(s)",
          file=sys.stderr)
    print(f"wrote preview: {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
