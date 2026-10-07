#!/usr/bin/env python3
"""Validate and normalize a JSON file exported by a Codex review page.

The export lists every item the page asked about, either in `decisions` or in
`unmarked`. Notes must belong to one of those items, and no item may be both
decided and unmarked. With --items, the exported item set must equal the ids
in the review_items file the page was built from, which catches a stale
export from an earlier run.

Exit codes: 0 read, 1 not a saved export (no savedAt), 2 malformed input or
ids that do not match.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

VALID = {"approve", "reject", "discuss"}


class DecisionError(ValueError):
    """A decision export cannot be trusted or does not match its items file."""

    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.exit_code = exit_code


def expected_review_id(spec: dict) -> str:
    review_id = spec.get("reviewId")
    if review_id is not None:
        if not isinstance(review_id, str) or not review_id:
            raise DecisionError("items file has an invalid reviewId")
        return review_id
    title = spec.get("title")
    if not isinstance(title, str) or not title:
        raise DecisionError("items file has no title or reviewId")
    return re.sub(r"[^A-Za-z0-9_.:-]+", "-", title).strip("-")


def expected_item_ids(spec: object) -> set[str]:
    if not isinstance(spec, dict) or not isinstance(spec.get("items"), list):
        raise DecisionError("items file does not contain an items list")
    ids: list[str] = []
    for item in spec["items"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise DecisionError("items file contains an item without a string id")
        ids.append(item["id"])
    if not ids or len(ids) != len(set(ids)):
        raise DecisionError("items file must contain unique item ids")
    return set(ids)


def normalize(payload: object, spec: dict | None = None) -> dict:
    """Validate and normalize one browser export.

    Both the CLI and the HTTP save endpoint call this function. Keeping the
    trust boundary here prevents a served page from acquiring a second, looser
    interpretation of the decision format.
    """
    if not isinstance(payload, dict):
        raise DecisionError("input is not a JSON object")
    if payload.get("schemaVersion", 1) != 1:
        raise DecisionError(f"unsupported schemaVersion: {payload.get('schemaVersion')!r}")
    decisions = payload.get("decisions")
    if not isinstance(payload.get("savedAt"), str) or not payload["savedAt"].strip():
        raise DecisionError("input is not a saved review decision file", 1)
    if not isinstance(decisions, dict):
        raise DecisionError("input is not a saved review decision file", 1)

    bad = {
        key: value for key, value in decisions.items()
        if not isinstance(value, str) or value not in VALID
    }
    if bad:
        raise DecisionError(f"unrecognised verdicts: {bad}")

    notes = payload.get("notes", {})
    if not isinstance(notes, dict):
        raise DecisionError("'notes' is not an object")
    unmarked = payload.get("unmarked", [])
    if not isinstance(unmarked, list):
        raise DecisionError("'unmarked' is not a list")
    if not all(isinstance(item, str) for item in unmarked):
        raise DecisionError("'unmarked' ids must be strings")
    if len(unmarked) != len(set(unmarked)):
        raise DecisionError("'unmarked' contains duplicate ids")
    both = sorted(set(decisions) & set(unmarked))
    if both:
        raise DecisionError(f"ids both decided and unmarked: {both}")
    asked = set(decisions) | set(unmarked)
    stray = sorted(set(notes) - asked)
    if stray:
        raise DecisionError(f"notes for ids the page never asked about: {stray}")

    if spec is not None:
        expected = expected_item_ids(spec)
        if expected != asked:
            raise DecisionError(
                "this export was not made from --items "
                f"(only in export: {sorted(asked - expected)}, "
                f"only in items: {sorted(expected - asked)}). "
                "Is it a stale export from an earlier run?"
            )
        expected_id = expected_review_id(spec)
        if payload.get("reviewId") != expected_id:
            raise DecisionError(
                "this export has the wrong reviewId "
                f"({payload.get('reviewId')!r}; expected {expected_id!r}). "
                "Is it from another review page?"
            )

    tally = {
        value: sum(1 for choice in decisions.values() if choice == value)
        for value in sorted(VALID)
    }
    return {
        "schemaVersion": payload.get("schemaVersion", 1),
        "reviewId": payload.get("reviewId"),
        "savedAt": payload["savedAt"],
        "decided": len(decisions),
        "tally": tally,
        "decisions": decisions,
        "notes": notes,
        "discuss": sorted(key for key, value in decisions.items() if value == "discuss"),
        "unmarked": unmarked,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="inp", required=True, type=Path, help="exported decisions JSON")
    parser.add_argument("--items", type=Path,
                        help="the review_items JSON the page was built from; its ids must match the export's")
    parser.add_argument("--out", type=Path, help="write normalized JSON here (default: stdout)")
    args = parser.parse_args()

    try:
        payload = json.loads(args.inp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read decisions: {exc}", file=sys.stderr)
        return 2

    spec = None
    if args.items:
        try:
            spec = json.loads(args.items.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: cannot read items: {exc}", file=sys.stderr)
            return 2
    try:
        normalized = normalize(payload, spec)
    except DecisionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code

    blob = json.dumps(normalized, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(blob + "\n", encoding="utf-8")
        print(f"{len(decisions)} decided -> {args.out}")
    else:
        print(blob)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
