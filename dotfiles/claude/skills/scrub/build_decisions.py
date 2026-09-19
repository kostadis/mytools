#!/usr/bin/env python3
"""Build exact apply_scrub decisions from an approved batch-review file.

Accepted review rows contain an absolute source line, an exact old span, and
the approved replacement. The builder slices from the real source line,
groups multiple replacements on one line, and emits full-line old/new pairs.
It makes no scope or prose decisions.

Usage:
    python build_decisions.py --file preview.md --review review.json \
        --output decisions.json

Review shape:
    [{"id": 1, "line": 21, "old": "I have twenty-two.",
      "new": "Let me look.", "decision": "accept"}]

Only rows with decision ``accept`` are emitted. Rows marked ``keep``,
``protect``, or ``skip`` remain review/manifest data and are ignored here.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path


ALLOWED_DECISIONS = {"accept", "keep", "protect", "skip"}


def load_review(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("decisions") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("review must be a JSON array or an object with a decisions array")
    return rows


def build(source: str, rows: list[dict]) -> list[dict]:
    lines = source.splitlines()
    grouped: OrderedDict[int, list[dict]] = OrderedDict()

    for index, row in enumerate(rows, start=1):
        decision = row.get("decision")
        if decision not in ALLOWED_DECISIONS:
            raise ValueError(
                f"review row {index}: decision must be one of "
                f"{sorted(ALLOWED_DECISIONS)}, got {decision!r}"
            )
        if decision != "accept":
            continue
        line = row.get("line")
        old = row.get("old")
        new = row.get("new")
        if not isinstance(line, int) or line < 1 or line > len(lines):
            raise ValueError(f"review row {index}: invalid source line {line!r}")
        if not isinstance(old, str) or not old:
            raise ValueError(f"review row {index}: old must be a non-empty string")
        if not isinstance(new, str):
            raise ValueError(f"review row {index}: new must be a string")
        grouped.setdefault(line, []).append(row)

    decisions = []
    for line_number, line_rows in grouped.items():
        old_line = lines[line_number - 1]
        new_line = old_line
        for row in line_rows:
            old = row["old"]
            count = new_line.count(old)
            if count != 1:
                label = row.get("id", "?")
                raise ValueError(
                    f"review row {label}, line {line_number}: expected exactly one "
                    f"occurrence of {old!r}, found {count}"
                )
            new_line = new_line.replace(old, row["new"], 1)
        decisions.append({"line": line_number, "old": old_line, "new": new_line})

    return decisions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    try:
        if not args.file.is_file():
            raise ValueError(f"not a file: {args.file}")
        if not args.review.is_file():
            raise ValueError(f"not a file: {args.review}")
        decisions = build(
            args.file.read_text(encoding="utf-8"),
            load_review(args.review),
        )
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(decisions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"built {len(decisions)} line decision(s) from approved review")
    print(f"wrote: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
