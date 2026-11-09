#!/usr/bin/env python3
"""Extract every dice table from Castle Oldskull DDE1 into a JSON file.

Deterministic: pdftotext -layout, then regex. No LLM.

The output is the book's own content, so it is NEVER written into this
(public) repo. Default destination is the private homebrew repo:
    ~/src/homebrew-private/book/dde1-castle-oldskull/tables.json
Override with $DDE_DATA or --out.

Usage:
    python3 extract.py [--pdf PATH] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

DEFAULT_PDF = Path(
    "/mnt/g/My Drive/DriveThru/Kent David Kelly/"
    "CASTLE OLDSKULL - Dungeon Delver Enhancer (Character Creator)/"
    "DDE1_DriveThruRPG_Edition_-_2nd_Printing_-_February_2017.pdf"
)
DEFAULT_OUT = Path(os.environ.get(
    "DDE_DATA",
    Path.home() / "src/homebrew-private/book/dde1-castle-oldskull/tables.json",
))

BULLET = ""          # private-use bullet glyph the PDF uses
MARK = "•"
PB = "\x0c"                 # page-break sentinel: transparent to table text, a separator elsewhere
PAGE_NOISE = re.compile(r"CASTLE OLDSKULL ~ DDE1|P a g e\s*\|?|\|\s*P a g e")
ENTRY = re.compile(r"\[(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?\]")
HEADING = re.compile(r"^[A-Z0-9][A-Z0-9 ,:()'’&/\-]{3,}$")
NAV = re.compile(r"^(click here|roll (once|once again) on table \d)", re.I)

# Printed-range typos in the book, each verified against the PDF text.
# (table key, printed lo, printed hi) -> (lo, hi) or None to drop the entry.
ERRATA: dict[tuple[str, int, int], tuple[int, int] | None] = {
    ("step-1-selecting-a-given-name", 95, 98): (96, 98),          # Tribal overlaps Swiss 86-95
    ("themes-and-level-titles-for-clerics", 54, 7): (5, 7),       # printed [54-07]
    ("themes-and-level-titles-for-bards", 65, 68): (66, 68),      # overlaps [61-65]
    ("uncommon-languages", 1, 15): (1, 5),                        # printed [01-15]
    ("uncommon-languages", 6, 1): (6, 10),                        # printed [06-01]
    ("fighting-styles-for-fighters", 31, 50): (41, 50),           # overlaps Heavy Footman [31-40]
    ("heraldic-ordinaries-geometric-symbols", 88, 94): (89, 94),  # overlaps Pile [83-88]
    ("orcish-names-for-male-characters-2", 1, 3): (1, 4),         # next entry starts [05-08]
    ("orcish-names-for-male-characters-2", 48, 48): (45, 48),     # printed [48-48] after [41-44]
}
# Misprinted rows to drop: (table key, lo, hi, text).
DROP_ENTRIES = {
    # table 1 prints a stray "[70-72] Rad- [73-75] Orth-" row, then repeats [67-69] Oth- / [70-72] Rad-
    ("orcish-names-for-male-characters", 73, 75, "Orth-"),
}
DEDUPE_TABLES = {"orcish-names-for-male-characters"}  # keep first of identical repeated rows
# Entries that do not belong to the table they were printed under.
DROP_TRAILING = {
    # the female [99] Ypolita / [00] Ysabella row is reprinted after the male table
    "latinized-swiss-names-for-male-characters": 2,
}
# Tables that are only navigation / book ads, not content.
SKIP_TABLES = re.compile(
    r"^(an-example-of-total-output|other-books|castle-oldskull-frpg|dungeon-masters-guild|hawk-moor|the-lyric-books)"
)


def to_int(s: str) -> int:
    return 100 if s in ("00", "000") else int(s)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower().replace("’", "")).strip("-")


def pdf_text(pdf: Path) -> list[str]:
    out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                         check=True, capture_output=True, text=True).stdout
    raw_lines = [None if PAGE_NOISE.search(r) else r.replace(BULLET, MARK).rstrip()
                 for r in out.replace("\f", "\n").split("\n")]
    # Make page breaks invisible: drop the footer/header and every blank line in
    # the same run, so text that wraps across pages stays one paragraph.
    lines, i = [], 0
    while i < len(raw_lines):
        if raw_lines[i] == "" or raw_lines[i] is None:
            j = i
            while j < len(raw_lines) and (raw_lines[j] == "" or raw_lines[j] is None):
                j += 1
            run = raw_lines[i:j]
            lines += [PB] if None in run else run
            i = j
        else:
            lines.append(raw_lines[i])
            i += 1
    return lines


def is_heading(line: str) -> bool:
    s = line.strip()
    return bool(HEADING.match(s)) and any(c.isalpha() for c in s) and not ENTRY.search(s)


def join(prev: str, more: str) -> str:
    more = more.strip()
    if not more:
        return prev
    if prev.endswith("-") and not prev.endswith(" -"):
        return prev[:-1] + more.lstrip(MARK + " ")
    if more.startswith(MARK):
        more = more.lstrip(MARK + " ")
        sep = " " if prev.rstrip().endswith((".", ")", ":", "!", "?")) or not prev.strip() else "; "
        return prev + sep + more if prev.strip() else more
    return prev + " " + more


def parse(lines: list[str]) -> dict:
    tables: dict[str, dict] = {}
    heading_parts: list[str] = []
    current: dict | None = None
    row: list[dict] = []          # entries on the last entry row, with column spans
    blank_run = 0

    def new_table(title: str) -> dict:
        key = slug(title) or "untitled"
        base, n = key, 2
        while key in tables:
            key, n = f"{base}-{n}", n + 1
        t = {"title": title, "entries": []}
        tables[key] = t
        return t

    lead = ""                     # label printed on the line just above its [range]

    def single_entry_row(l: str) -> bool:
        ms = list(ENTRY.finditer(l))
        return len(ms) == 1 and l[: ms[0].start()].strip() == ""

    for idx, line in enumerate(lines):
        if line == PB:
            continue
        s = line.strip()
        if not s:
            blank_run += 1
            lead = ""
            continue

        if is_heading(line):
            heading_parts = heading_parts + [s] if (heading_parts and blank_run == 0 and current is None) else [s]
            current, row, blank_run = None, [], 0
            continue

        matches = list(ENTRY.finditer(line))
        if matches and line[: matches[0].start()].strip() == "":
            row = []
            for i, m in enumerate(matches):
                lo = to_int(m.group(1))
                hi = to_int(m.group(2)) if m.group(2) else lo
                end = matches[i + 1].start() if i + 1 < len(matches) else len(line)
                seg = line[m.end():end]
                col = m.end() + len(seg) - len(seg.lstrip())
                # a range that restarts low begins a new sub-table
                if current is None or (lo <= 3 and current["entries"]
                                       and max(x["hi"] for x in current["entries"]) >= 95):
                    current = new_table(" ".join(heading_parts) or "untitled")
                e = {"lo": lo, "hi": hi, "text": " ".join(seg.split()).lstrip(MARK + " ")}
                if lead:
                    e["text"] = join(lead, e["text"])
                    lead = ""
                current["entries"].append(e)
                row.append({"e": e, "col": col,
                            "stop": matches[i + 1].start() if i + 1 < len(matches) else None})
            blank_run = 0
            continue

        # vertically-centred label: a line directly above a single-column [range] row
        indent = len(line) - len(line.lstrip())
        nxt = lines[idx + 1] if idx + 1 < len(lines) else ""
        if current is not None and indent >= 8 and single_entry_row(nxt) and not single_entry_row(line):
            lead = s.lstrip(MARK + " ")
            blank_run = 0
            continue

        # continuation of wrapped entries, split by column for two-column rows
        if row and blank_run <= 1 and indent >= row[0]["col"] - 4:
            # column i owns [its bracket start, next column's bracket start)
            for i, r in enumerate(row):
                lo_col = 0 if i == 0 else row[i - 1]["stop"]
                piece = line[lo_col: r["stop"]] if r["stop"] is not None else line[lo_col:]
                r["e"]["text"] = join(r["e"]["text"], piece)
        else:
            row = []
        blank_run = 0

    out = {}
    for key, t in tables.items():
        if SKIP_TABLES.match(key):
            continue
        es = [e for e in t["entries"] if not NAV.match(e["text"])]
        if key in DROP_TRAILING:
            es = es[: -DROP_TRAILING[key]]
        seen, fixed = set(), []
        for e in es:
            if (key, e["lo"], e["hi"], e["text"].strip()) in DROP_ENTRIES:
                continue
            if key in DEDUPE_TABLES:
                sig = (e["lo"], e["hi"], e["text"].strip())
                if sig in seen:
                    continue
                seen.add(sig)
            k = (key, e["lo"], e["hi"])
            if k in ERRATA:
                if ERRATA[k] is None:
                    continue
                e["printed"] = f"[{e['lo']}-{e['hi']}]"
                e["lo"], e["hi"] = ERRATA[k]
            e["text"] = re.sub(r"[;\s]*Click here to proceed[^.]*?table\.?", "", " ".join(e["text"].split())).strip()
            fixed.append(e)
        if fixed:
            t["entries"] = fixed
            out[key] = t
    return out


def check(tables: dict) -> list[str]:
    """Each table should tile 1..N exactly. Gaps are allowed (the generator rerolls) but reported."""
    problems = []
    for key, t in tables.items():
        es = t["entries"]
        top = max(e["hi"] for e in es)
        covered = [0] * (top + 1)
        for e in es:
            for v in range(e["lo"], e["hi"] + 1):
                covered[v] += 1
        gaps = [v for v in range(1, top + 1) if covered[v] == 0]
        dups = [v for v in range(1, top + 1) if covered[v] > 1]
        empty = [e["lo"] for e in es if not e["text"]]
        t["die"] = top
        t["gaps"] = gaps
        if gaps:
            problems.append(f"gap      {key}: {gaps}")
        if dups:
            problems.append(f"OVERLAP  {key}: {dups}")
        if empty:
            problems.append(f"EMPTY    {key}: {empty}")
    return problems


def section(lines: list[str], start: str, end: str) -> list[str]:
    i = next(n for n, l in enumerate(lines) if l.strip() == start and n > 1000)
    j = next(n for n, l in enumerate(lines[i + 1:], i + 1) if l.strip().startswith(end))
    return lines[i + 1: j]


ABILITIES = ["Strength", "Intelligence", "Wisdom", "Dexterity", "Constitution", "Charisma"]
SCORE = re.compile(r"^(\d{1,2})\+?$")


def parse_descriptors(lines: list[str]) -> dict:
    """Step 5: per ability, score -> list of descriptor words."""
    out = {}
    for ab in ABILITIES:
        body = section(lines, f"DESCRIPTORS FOR {ab.upper()}", "~")
        groups: list[dict] = []
        cur: dict | None = None
        for line in body + [""]:
            if line == PB or not line.strip():
                if cur:
                    groups.append(cur)
                cur = None
                continue
            cur = cur or {"score": None, "words": [], "note": False}
            for m in re.finditer(r"\S+(?: \S+)*", line):
                tok = m.group(0).strip("“”\"").lstrip(MARK + " ")
                if not tok or tok == ab or tok == "Exceptional":
                    continue
                if SCORE.match(tok) and m.start() < 30:
                    cur["score"] = int(SCORE.match(tok).group(1))
                elif m.start() >= 25:
                    if "descriptors for" in tok or "use the" in tok or "characters" in tok:
                        cur["note"] = True
                    cur["words"].append(tok)
        # A page break can split a score's six words into an unscored fragment
        # either after its score (previous row still short) or before it.
        table: dict[int, list[str]] = {}
        last, pending = None, []
        for g in groups:
            if g["note"]:
                last, pending = None, []
                continue
            if g["score"] is None:
                if last is not None and len(table[last]) < 6:
                    table[last] += g["words"]
                else:
                    pending += g["words"]
            else:
                table[g["score"]] = pending + g["words"]
                last, pending = g["score"], []
        out[ab] = {str(k): v for k, v in sorted(table.items())}
    return out


def parse_social(lines: list[str]) -> dict:
    """Step 23: starting rank by class, and the peerage ladder (rank -> example personages)."""
    body = section(lines, "STEP 23: DETERMINING SOCIAL STANDING", "STEP 24")
    start = {}
    for l in body:
        m = re.match(r"^[\s\u2022]*(?:\((?:Lowest|Highest)\)\s*)?([A-Z][a-z]+)s: (\d+)(?:st|nd|rd|th)\b", l)
        if m:
            start[m.group(1).lower()] = int(m.group(2))
    ranks: dict[int, dict] = {}
    caste = ""
    cur = None
    text_col = None
    pending_caste: list[str] = []
    for l in body:
        s = l.strip()
        if re.match(r"^(THE UNDER-CASTE:|CASTE [IVX]+:)$", s):
            pending_caste = [s.rstrip(":")]
            cur = None
            continue
        if pending_caste and len(pending_caste) == 1 and is_heading(l):
            pending_caste.append(s)
            caste = " — ".join(pending_caste)
            continue
        m = re.match(r"^\s{2,12}(\d{1,3})\s{3,}(\S.*)$", l)
        if m and 1 <= int(m.group(1)) <= 117:
            pending_caste = []
            cur = {"caste": caste, "personages": [m.group(2).lstrip(MARK + " ").strip()]}
            ranks[int(m.group(1))] = cur
            text_col = m.start(2)
            continue
        if cur is not None and s and not is_heading(l):
            ind = len(l) - len(l.lstrip())
            if s.startswith(MARK) or (text_col is not None and abs(ind - text_col) <= 1):
                cur["personages"].append(s.lstrip(MARK + " "))
            elif text_col is not None and ind > text_col:
                cur["personages"][-1] += " " + s
            else:
                cur = None
    for r in ranks.values():
        r["personages"] = [re.sub(r"\s*~.*$", "", " ".join(p.split())) for p in r["personages"]
                           if not p.startswith("You can scroll")]
    return {"start_rank_by_class": start,
            "peerage": {str(k): v for k, v in sorted(ranks.items())}}


def parse_wealth(lines: list[str]) -> list[dict]:
    """Step 25: starting gold by social-standing band."""
    body = " ".join(l.strip() for l in section(lines, "STEP 25: DETERMINING STARTING WEALTH", "STEP 26"))
    out = []
    for m in re.finditer(r"Social Standing (\d+) to (\d+) \(([^)]*?)(?:;[^)]*)?\): Roll (\(?\d+d6(?:\+\d+)?\)?)(?: x (\d+))?", body):
        out.append({"from": int(m.group(1)), "to": int(m.group(2)), "band": m.group(3),
                    "dice": m.group(4).strip("()"), "mult": int(m.group(5) or 1)})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args()
    lines = pdf_text(a.pdf)
    tables = parse(lines)
    problems = check(tables)
    data = {
        "source": "Castle Oldskull DDE1: Book One - The Dragon Rises (Kent David Kelly), 2nd printing Feb 2017",
        "tables": tables,
        "descriptors": parse_descriptors(lines),
        "social": parse_social(lines),
        "wealth": parse_wealth(lines),
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f"{len(tables)} dice tables, "
          f"{sum(len(v) for v in data['descriptors'].values())} descriptor rows, "
          f"{len(data['social']['peerage'])} peerage ranks, "
          f"{len(data['wealth'])} wealth bands -> {a.out}")
    for ab, rows in data["descriptors"].items():
        missing = [s for s in range(3, 20) if str(s) not in rows]
        if missing:
            problems.append(f"DESCRIPT {ab}: no row for scores {missing}")
    for p in problems:
        print("  ", p)


if __name__ == "__main__":
    main()
