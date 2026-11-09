#!/usr/bin/env python3
"""Roll an NPC with The Oracle Character Generator tables (Nord Games).

Reads tables extracted by extract.py from YOUR copy of the PDF. The data
lives outside this repo (default ~/src/homebrew-private/book/oracle-character-generator/
tables.json, override with $ORACLE_DATA).

How the book works: pick a theme, roll d12 on each of its five sections
(Role, Personality, Motivation, Flaw, Intrigue) and combine the titles; for
detail, roll d4 on the chosen result's option table.

Examples:
    oracle_npc.py                          # one NPC, random theme
    oracle_npc.py -n 3 --theme villains    # three villains
    oracle_npc.py --theme heroes --role paladin --flaw "brash/reckless"
    oracle_npc.py --mix                    # each section from a random theme
    oracle_npc.py --brief -n 10            # one summary line each
    oracle_npc.py --json --seed 7
    oracle_npc.py --list                   # themes and their d12 results
    oracle_npc.py --list nobles            # one theme, with every option
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import textwrap
from pathlib import Path

DATA = Path(os.environ.get(
    "ORACLE_DATA",
    Path.home() / "src/homebrew-private/book/oracle-character-generator/tables.json"))


def load(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"no tables at {path}\nrun extract.py first (or set $ORACLE_DATA)")
    return json.loads(path.read_text())


def find_theme(data: dict, key: str) -> dict:
    """Theme by any case-insensitive prefix of any word: 'villains', 'scoun', 'nob'."""
    k = key.lower()
    hits = [t for t in data["themes"]
            if t["name"].lower().startswith(k) or any(w.startswith(k) for w in t["name"].lower().split())]
    if len(hits) != 1:
        names = ", ".join(t["name"] for t in data["themes"])
        sys.exit(f"--theme {key!r} matches {len(hits)} themes; choose one of: {names}")
    return hits[0]


def find_by_name(items: list[dict], key: str, what: str) -> dict:
    k = key.lower().strip()
    exact = [i for i in items if i["name"].lower() == k]
    hits = exact or [i for i in items if i["name"].lower().startswith(k)]
    if len(hits) != 1:
        sys.exit(f"{what} {key!r} matches {len(hits)}; choose one of: "
                 + ", ".join(i["name"] for i in items))
    return hits[0]


def roll_section(rng: random.Random, theme: dict, section: str, fixed: str | None,
                 detail: bool) -> dict:
    results = theme["sections"][section]
    want_opt = None
    if fixed:
        name, _, want_opt = fixed.partition("/")
        res = find_by_name(results, name, f"{theme['name']} {section}")
    else:
        res = rng.choice(results)
    out = {"section": section, "theme": theme["name"], "roll": res["roll"],
           "result": res["name"], "description": res["description"]}
    if detail or want_opt:
        opt = (find_by_name(res["options"], want_opt, f"{res['name']} option")
               if want_opt else rng.choice(res["options"]))
        out.update(option_roll=opt["roll"], option=opt["name"], option_text=opt["text"])
    return out


def make_npc(data: dict, rng: random.Random, args) -> dict:
    base = find_theme(data, args.theme) if args.theme else rng.choice(data["themes"])
    rolls = []
    for section in data["sections"]:
        theme = rng.choice(data["themes"]) if args.mix else base
        fixed = getattr(args, section.lower())
        rolls.append(roll_section(rng, theme, section, fixed, detail=not args.no_detail))
    return {"theme": "mixed" if args.mix else base["name"], "rolls": rolls,
            "summary": " · ".join(r["result"] for r in rolls)}


def label(r: dict) -> str:
    return f"{r['result']} ({r['option']})" if "option" in r else r["result"]


def render(npc: dict, brief: bool, width: int) -> str:
    head = f"[{npc['theme']}] " + " · ".join(label(r) for r in npc["rolls"])
    if brief:
        return head
    wrap = lambda s, ind: textwrap.fill(s, width, initial_indent=ind, subsequent_indent=ind)
    out = [head, "=" * min(len(head), width)]
    for r in npc["rolls"]:
        src = f"  [{r['theme']}]" if npc["theme"] == "mixed" else ""
        out.append(f"{r['section']}: {r['result']}  (d12={r['roll']}){src}")
        out.append(wrap(r["description"], "    "))
        if "option" in r:
            out.append(wrap(f"{r['option']} (d4={r['option_roll']}): {r['option_text']}", "    → "
                            ).replace("\n    → ", "\n      "))
        out.append("")
    return "\n".join(out).rstrip()


def list_tables(data: dict, which: str | None, width: int) -> str:
    themes = [find_theme(data, which)] if which else data["themes"]
    out = []
    for t in themes:
        out.append(f"## {t['name']}")
        for section, results in t["sections"].items():
            if which:
                out.append(f"  {section}")
                for r in results:
                    out.append(f"    {r['roll']:>2} {r['name']}: "
                               + ", ".join(o["name"] for o in r["options"]))
            else:
                out.append(textwrap.fill(", ".join(r["name"] for r in results), width,
                                         initial_indent=f"  {section:<12}", subsequent_indent=" " * 14))
        out.append("")
    return "\n".join(out).rstrip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", type=int, default=1, help="how many NPCs")
    ap.add_argument("--theme", help="heroes, merchants, nobles, townsfolk, villains (any word prefix)")
    ap.add_argument("--mix", action="store_true", help="roll each section on a random theme")
    for s in ("role", "personality", "motivation", "flaw", "intrigue"):
        ap.add_argument(f"--{s}", metavar="NAME[/OPTION]",
                        help=f"fix the {s} result (and optionally its d4 option) instead of rolling")
    ap.add_argument("--no-detail", action="store_true", help="skip the d4 option rolls")
    ap.add_argument("--brief", action="store_true", help="one summary line per NPC")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--width", type=int, default=100)
    ap.add_argument("--list", nargs="?", const="", metavar="THEME",
                    help="list d12 results (all themes), or every option for one theme")
    ap.add_argument("--data", type=Path, default=DATA, help=f"tables.json (default {DATA})")
    a = ap.parse_args(argv)

    data = load(a.data)
    if a.list is not None:
        print(list_tables(data, a.list or None, a.width))
        return 0
    if a.mix and (a.theme or any(getattr(a, s) for s in ("role", "personality", "motivation", "flaw", "intrigue"))):
        ap.error("--mix rolls a random theme per section; it can't be combined with --theme or fixed results")

    rng = random.Random(a.seed)
    npcs = [make_npc(data, rng, a) for _ in range(a.n)]
    if a.json:
        print(json.dumps(npcs if a.n > 1 else npcs[0], indent=1, ensure_ascii=False))
    else:
        print(("\n" if a.brief else "\n\n").join(render(x, a.brief, a.width) for x in npcs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
