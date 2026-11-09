#!/usr/bin/env python3
"""Extract the roll tables from the Nord Games Oracle generators into JSON.

Deterministic: pdftotext -layout, parsed with the page parser shared with
pdf-translators/converters/layout_table_merge.py. No LLM.

The output is the books' own content, so it is NEVER written into this
(public) repo. Default destination (see books.py):
    ~/src/homebrew-private/book/<slug>/tables.json     ($ORACLE_DATA_DIR overrides the base)

The d12 index pages are the authority for structure: they name every result
and the page it is on, so option pages are parsed against those known headings.

Usage:
    python3 extract.py [npc|monster|story|all] [--pdf PATH] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "pdf-translators"))
from books import BOOKS, tables_path  # noqa: E402
from converters.layout_table_merge import (  # noqa: E402
    INDEX_HEAD, body_lines, build_index_page, build_option_page, join_lines,
    pdftotext_page, title_key, words,
)

OPTION_NAME = re.compile(r"^((?:\S+\s){0,5}?\S+?)\.\s+(.*)$")

# d12 index rows whose wording differs from the printed heading, verified against the PDF.
# book -> {index text: printed heading}
INDEX_ERRATA: dict[str, dict[str, str]] = {
    "story": {
        "to lay foundationa...": "to lay foundations…",                         # Sidequests Intent #12, typo
        "but a curse is making things harder.": "but a curse makes things harder.",  # Sidequests Development #6
    },
}


def page_count(pdf: str) -> int:
    out = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True, check=True).stdout
    return int(re.search(r"^Pages:\s+(\d+)", out, re.M).group(1))


def extract(book: str, pdf: str) -> tuple[dict, list[str]]:
    spec = BOOKS[book]
    problems: list[str] = []
    errata: list[str] = []
    n = page_count(pdf)
    pages = {p: body_lines(pdftotext_page(pdf, p)) for p in range(1, n + 1)}

    # pass 1: theme title pages and d12 index pages
    themes: list[dict] = []
    index: list[tuple[int, dict, str, list]] = []
    theme = None
    for p, lines in pages.items():
        text = " ".join(l.strip() for l in lines if l.strip())
        if any(INDEX_HEAD.match(l) for l in lines):
            if theme is None:
                problems.append(f"p{p}: index page before any {spec['theme_label']} title page")
                continue
            try:
                die, col, rows, _ = build_index_page(lines)
            except ValueError as e:
                problems.append(f"p{p}: {e}")
                continue
            if die != 12 or [r[0] for r in rows] != list(range(1, 13)):
                problems.append(f"p{p}: d{die} {col} rows {[r[0] for r in rows]}")
            fixes = INDEX_ERRATA.get(book, {})
            for i, (roll, name, pg) in enumerate(rows):
                if name in fixes:
                    errata.append(f"p{p}: {theme['name']} {col} #{roll}: index prints {name!r}, "
                                  f"heading is {fixes[name]!r}")
                    rows[i] = (roll, fixes[name], pg)
            index.append((p, theme, col, rows))
        elif text and len(text.split()) <= 4 and p > 3:
            theme = {"name": text.title(), "sections": {}}
            themes.append(theme)

    # pass 2: option pages, parsed against the headings the index names. The index's
    # page numbers are sometimes wrong (two results swapped between adjacent pages),
    # so every page of a section is parsed against ALL of that section's names, and
    # a result is looked up across the section's pages; wrong page numbers are errata.
    section_of: dict[int, int] = {}            # option page -> index page
    for p, _, _, rows in index:
        for _, _, pg in rows:
            section_of[pg] = p
    names_of = {p: [name for _, name, _ in rows] for p, _, _, rows in index}
    found: dict[int, dict[str, dict]] = {}     # index page -> title_key -> subsection
    for pg, ip in sorted(section_of.items()):
        try:
            subs, _ = build_option_page(pages[pg], known_titles=names_of[ip])
        except ValueError as e:
            problems.append(f"p{pg}: {e}")
            continue
        for s in subs:
            k = title_key(s["title"])
            if k in found.setdefault(ip, {}):
                problems.append(f"p{pg}: heading {s['title']!r} found twice in its section")
            found[ip][k] = s | {"page": pg}
        # nothing dropped or invented: the page's words == headings + descriptions + options
        parts_out = []
        for s in subs:
            parts_out += [s["title"], join_lines(s["desc"])]
            parts_out += [f"{n} {join_lines(parts)}" for n, parts in s["entries"]]
        got, want = words(" ".join(parts_out)), words("\n".join(pages[pg]))
        if got != want:
            problems.append(f"p{pg}: word mismatch missing={dict(want - got)} extra={dict(got - want)}")

    for p, theme, col, rows in index:
        results = []
        for roll, name, pg in rows:
            sub = found.get(p, {}).get(title_key(name))
            if sub is None:
                problems.append(f"p{p}: {theme['name']} {col} #{roll} {name!r} not found in its section")
                continue
            if sub["page"] != pg:
                errata.append(f"p{p}: {theme['name']} {col} #{roll} {name!r}: index says "
                              f"page {pg}, printed on page {sub['page']}")
                pg = sub["page"]
            opts = []
            for k, parts in sub["entries"]:
                t = join_lines(parts)
                m = OPTION_NAME.match(t)
                if not m:
                    problems.append(f"p{pg}: {name} #{k}: no option name in {t[:50]!r}")
                    continue
                opts.append({"roll": k, "name": m.group(1), "text": m.group(2)})
            if [o["roll"] for o in opts] != [1, 2, 3, 4]:
                problems.append(f"p{pg}: {name!r} options {[o['roll'] for o in opts]}")
            results.append({"roll": roll, "name": sub["title"], "page": pg,
                            "description": join_lines(sub["desc"]), "options": opts})
        theme["sections"][col] = results

    themes = [t for t in themes if t["sections"]]  # e.g. the story book's "Pregenerated Stories"
    if len(themes) != spec["themes"]:
        problems.append(f"expected {spec['themes']} {spec['theme_label']}s, found "
                        f"{[t['name'] for t in themes]}")
    for t in themes:
        if list(t["sections"]) != spec["sections"]:
            problems.append(f"{t['name']}: sections {list(t['sections'])}, expected {spec['sections']}")

    data = {"source": {"title": spec["title"], "publisher": "Nord Games", "pdf": Path(pdf).name,
                       "rpg_lib_id": spec["rpg_lib_id"]},
            "theme_label": spec["theme_label"], "sections": spec["sections"],
            "errata": errata, "themes": themes}
    return data, problems


def run(book: str, pdf: str | None, out: Path | None) -> int:
    spec = BOOKS[book]
    out = out or tables_path(book)
    if REPO in out.resolve().parents:
        print(f"refusing to write book content inside the public repo: {out}", file=sys.stderr)
        return 2
    data, problems = extract(book, pdf or spec["pdf"])
    n_res = sum(len(s) for t in data["themes"] for s in t["sections"].values())
    n_opt = sum(len(r["options"]) for t in data["themes"] for s in t["sections"].values() for r in s)
    print(f"[{book}] {spec['theme_label']}s={len(data['themes'])} results={n_res} options={n_opt}")
    for x in data["errata"]:
        print(f"[{book}] erratum (recorded, not a failure): {x}")
    if problems:
        print(f"[{book}] PROBLEMS ({len(problems)}), nothing written:")
        for x in problems:
            print("  ", x)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"[{book}] wrote {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("book", nargs="?", default="all", choices=[*BOOKS, "all"])
    ap.add_argument("--pdf", help="override the PDF path (single book only)")
    ap.add_argument("--out", type=Path, help="override the output path (single book only)")
    a = ap.parse_args()
    books = list(BOOKS) if a.book == "all" else [a.book]
    if len(books) > 1 and (a.pdf or a.out):
        ap.error("--pdf/--out need a single book")
    return max(run(b, a.pdf, a.out) for b in books)


if __name__ == "__main__":
    sys.exit(main())
