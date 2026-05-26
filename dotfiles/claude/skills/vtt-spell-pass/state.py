#!/usr/bin/env python3
"""Read/write the spell-pass state file at
``notes/.vtt_spell_pass_state.json``. Persists tokens the user has marked
"ignore" so they don't get re-asked next session, plus a record of which
transcripts have been processed.

Schema:
{
  "ignored_tokens": ["Joe", "Gabe", ...],
  "processed_vtts": ["summaries/20260427/...vtt", ...]
}

Used by the skill workflow — ``find_unknowns.py`` doesn't read this
directly; the SKILL.md instructions filter the unknown list against the
``ignored_tokens`` set in-conversation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_FILENAME = ".vtt_spell_pass_state.json"


def default_state() -> dict:
    return {"ignored_tokens": [], "processed_vtts": []}


def load(path: Path) -> dict:
    if not path.exists():
        return default_state()
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default_state()
    d.setdefault("ignored_tokens", [])
    d.setdefault("processed_vtts", [])
    return d


def save(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def add_ignored(path: Path, tokens: list[str]) -> dict:
    s = load(path)
    seen = {t.lower() for t in s["ignored_tokens"]}
    for t in tokens:
        if t.lower() not in seen:
            s["ignored_tokens"].append(t)
            seen.add(t.lower())
    save(path, s)
    return s


def add_processed(path: Path, vtt: str) -> dict:
    s = load(path)
    if vtt not in s["processed_vtts"]:
        s["processed_vtts"].append(vtt)
    save(path, s)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True, type=Path)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    p_ignore = sub.add_parser("ignore")
    p_ignore.add_argument("tokens", nargs="+")
    p_processed = sub.add_parser("processed")
    p_processed.add_argument("vtt")
    args = ap.parse_args()

    if args.cmd == "show":
        print(json.dumps(load(args.state), indent=2))
    elif args.cmd == "ignore":
        s = add_ignored(args.state, args.tokens)
        print(f"Ignored set now: {len(s['ignored_tokens'])} tokens")
    elif args.cmd == "processed":
        s = add_processed(args.state, args.vtt)
        print(f"Processed VTTs: {len(s['processed_vtts'])}")


if __name__ == "__main__":
    main()
