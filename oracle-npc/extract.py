#!/usr/bin/env python3
"""Extract the roll tables from The Oracle Character Generator (Nord Games) into JSON.

Deterministic: pdftotext -layout, parsed with the page parser shared with
pdf-translators/converters/layout_table_merge.py. No LLM.

The output is the book's own content, so it is NEVER written into this
(public) repo. Default destination is the private homebrew repo:
    ~/src/homebrew-private/book/oracle-character-generator/tables.json
Override with $ORACLE_DATA or --out.

Book layout: 5 themes, each opened by a one-line title page; each theme has 5
sections (Role, Personality, Motivation, Flaw, Intrigue); each section is a
d12 index page (result -> page) followed by pages of d4 option tables, one per
d12 result.

Usage:
    python3 extract.py [--pdf PATH] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pdf-translators"))
from converters.layout_table_merge import (  # noqa: E402
    INDEX_HEAD, OPTION_PAGE, body_lines, build_index_page, build_option_page,
    join_lines, pdftotext_page,
)

DEFAULT_PDF = Path(
    "/mnt/g/My Drive/Kickstarter/NordGames/Oracle Character Generator PDF/"
    "The_Oracle_Character_Generator.pdf"   # rpg-lib #1168, the InDesign 18.5 build
)
DEFAULT_OUT = Path(os.environ.get(
    "ORACLE_DATA",
    Path.home() / "src/homebrew-private/book/oracle-character-generator/tables.json",
))
SECTIONS = ["Role", "Personality", "Motivation", "Flaw", "Intrigue"]
OPTION_NAME = re.compile(r"^((?:\S+\s){0,5}?\S+?)\.\s+(.*)$")


def page_count(pdf: Path) -> int:
    import subprocess
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, check=True).stdout
    return int(re.search(r"^Pages:\s+(\d+)", out, re.M).group(1))


def extract(pdf: Path) -> tuple[dict, list[str]]:
    problems: list[str] = []
    themes: list[dict] = []
    theme = None
    index_pages: list[tuple[int, dict, str, list]] = []  # (page, theme, column, rows)
    options_on: dict[int, dict[str, dict]] = {}         # page -> title -> subsection

    for p in range(1, page_count(pdf) + 1):
        lines = body_lines(pdftotext_page(str(pdf), p))
        text = " ".join(l.strip() for l in lines if l.strip())
        if any(INDEX_HEAD.match(l) for l in lines):
            if theme is None:
                problems.append(f"p{p}: index page before any theme title page")
                continue
            die, col, rows, _ = build_index_page(lines)
            index_pages.append((p, theme, col, rows))
        elif any(OPTION_PAGE.match(l) for l in lines):
            subs, _ = build_option_page(lines)
            options_on[p] = {s["title"]: s for s in subs}
        elif text and len(text.split()) <= 4 and "&" in text:
            # theme title page, e.g. "heroes & champions"
            theme = {"name": text.title(), "sections": {}}
            themes.append(theme)

    for p, theme, col, rows in index_pages:
        if [n for n, _, _ in rows] != list(range(1, 13)):
            problems.append(f"p{p}: {theme['name']} {col} rows {[n for n, _, _ in rows]}")
        results = []
        for n, name, pg in rows:
            sub = options_on.get(pg, {}).get(name)
            if sub is None:
                problems.append(f"p{p}: {theme['name']} {col} #{n} {name!r} not found on page {pg}")
                continue
            opts = []
            for k, parts in sub["entries"]:
                t = join_lines(parts)
                m = OPTION_NAME.match(t)
                if not m:
                    problems.append(f"p{pg}: {name} #{k}: no option name in {t[:50]!r}")
                    continue
                opts.append({"roll": k, "name": m.group(1), "text": m.group(2)})
            if [o["roll"] for o in opts] != [1, 2, 3, 4]:
                problems.append(f"p{pg}: {name} options {[o['roll'] for o in opts]}")
            results.append({"roll": n, "name": name, "page": pg,
                            "description": join_lines(sub["desc"]), "options": opts})
        theme["sections"][col] = results

    names = [t["name"] for t in themes]
    if len(themes) != 5:
        problems.append(f"expected 5 themes, found {names}")
    for t in themes:
        if list(t["sections"]) != SECTIONS:
            problems.append(f"{t['name']}: sections {list(t['sections'])}, expected {SECTIONS}")

    data = {
        "source": {"title": "The Oracle Character Generator", "publisher": "Nord Games",
                   "pdf": pdf.name, "rpg_lib_id": 1168},
        "sections": SECTIONS,
        "themes": themes,
    }
    return data, problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args()
    if REPO in a.out.resolve().parents:
        print(f"refusing to write book content inside the public repo: {a.out}", file=sys.stderr)
        return 2
    data, problems = extract(a.pdf)
    n_res = sum(len(s) for t in data["themes"] for s in t["sections"].values())
    n_opt = sum(len(r["options"]) for t in data["themes"] for s in t["sections"].values() for r in s)
    print(f"themes={len(data['themes'])} results={n_res} options={n_opt}")
    if problems:
        print(f"PROBLEMS ({len(problems)}), nothing written:")
        for x in problems:
            print("  ", x)
        return 1
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
