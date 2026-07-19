#!/usr/bin/env python3
"""Durable decision store for the scrub skill.

Mirrors vtt-spell-pass/state.py: a small JSON file the GM's rulings persist
to, so the same false-positive or the same recurring translation isn't
re-asked every session.

Subcommands:
    show                                   print current state
    ignore <text> [<text> ...]             never flag these again (false positives)
    rule --match TEXT --replacement TEXT [--category CAT]
                                            durable literal auto-translation,
                                            applied deterministically by
                                            apply_known_rules.py on future runs
    processed <file>                       mark a narration file fully scrubbed

State file shape:
{
  "ignored": ["two-foot box", ...],
  "rules": [{"match": "the DM said", "replacement": "", "category": "table_speak"}],
  "processed": ["summaries/20260601/narration/session_doc_scene_01....md"]
}
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load(path: Path) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"ignored": [], "rules": [], "processed": []}


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state", required=True, type=Path)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("show")

    p_ignore = sub.add_parser("ignore")
    p_ignore.add_argument("text", nargs="+")

    p_rule = sub.add_parser("rule")
    p_rule.add_argument("--match", required=True)
    p_rule.add_argument("--replacement", required=True)
    p_rule.add_argument("--category", default="other")

    p_processed = sub.add_parser("processed")
    p_processed.add_argument("file")

    args = ap.parse_args()
    data = load(args.state)

    if args.cmd == "show":
        print(json.dumps(data, indent=2))
        return 0

    if args.cmd == "ignore":
        added = 0
        for t in args.text:
            if t not in data["ignored"]:
                data["ignored"].append(t)
                added += 1
        save(args.state, data)
        print(f"ignored {added} new term(s); {len(data['ignored'])} total")
        return 0

    if args.cmd == "rule":
        for r in data["rules"]:
            if r["match"] == args.match:
                r["replacement"] = args.replacement
                r["category"] = args.category
                save(args.state, data)
                print(f"updated rule: {args.match!r} -> {args.replacement!r}")
                return 0
        data["rules"].append({
            "match": args.match, "replacement": args.replacement, "category": args.category,
        })
        save(args.state, data)
        print(f"added rule: {args.match!r} -> {args.replacement!r}")
        return 0

    if args.cmd == "processed":
        if args.file not in data["processed"]:
            data["processed"].append(args.file)
            save(args.state, data)
        print(f"marked processed: {args.file}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
