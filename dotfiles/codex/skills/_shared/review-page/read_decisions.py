#!/usr/bin/env python3
"""Validate and normalize a JSON file exported by a Codex review page."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

VALID = {"approve", "reject", "discuss"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="inp", required=True, type=Path, help="exported decisions JSON")
    parser.add_argument("--out", type=Path, help="write normalized JSON here (default: stdout)")
    args = parser.parse_args()

    try:
        payload = json.loads(args.inp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read decisions: {exc}", file=sys.stderr)
        return 2

    decisions = payload.get("decisions")
    if not payload.get("savedAt") or not isinstance(decisions, dict):
        print("error: input is not a saved review decision file", file=sys.stderr)
        return 1

    bad = {key: value for key, value in decisions.items() if value not in VALID}
    if bad:
        print(f"error: unrecognised verdicts: {bad}", file=sys.stderr)
        return 2

    notes = payload.get("notes") if isinstance(payload.get("notes"), dict) else {}
    tally = {value: sum(1 for choice in decisions.values() if choice == value) for value in sorted(VALID)}
    normalized = {
        "schemaVersion": payload.get("schemaVersion", 1),
        "reviewId": payload.get("reviewId"),
        "savedAt": payload["savedAt"],
        "decided": len(decisions),
        "tally": tally,
        "decisions": decisions,
        "notes": notes,
        "discuss": sorted(key for key, value in decisions.items() if value == "discuss"),
        "unmarked": payload.get("unmarked", []),
    }

    blob = json.dumps(normalized, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(blob + "\n", encoding="utf-8")
        print(f"{len(decisions)} decided -> {args.out}")
    else:
        print(blob)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
