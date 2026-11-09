"""layout_table_merge.py — merge indra-ocr markdown with pdftotext -layout for
two-column books of numbered roll tables.

indra-ocr renders prose well but mangles side-by-side roll tables: the die
number sits in its own text block beside the entry, so it is spliced into the
middle of the entry text (``information, 1 myth``) or bunched ahead of all
entries (``1 2 3 4 Berserker. …``), and some tables come out as one-HTML-row-per-
printed-line.  ``pdftotext -layout`` keeps those rows aligned.  This script
classifies each page and takes the best source per page:

  dN index page   (header ``d12  <Column>  Page``)  -> markdown table from pdftotext
  option page     (two columns of ``N   Name. text``) -> ``### heading``, description
                                                      and ``| dN | Option |`` tables
                                                      from pdftotext
  anything else                                    -> indra-ocr's per-page markdown,
                                                      plus optional per-book patches

Deterministic checks (exit 1 on any failure):
  * every index table is numbered 1..N, every option table 1..K, with a
    consistent K across the book
  * each index row (name, page) matches a heading actually found on that page
  * word multiset of every output page == word multiset of pdftotext's text for
    that page (patches declare the words they deliberately add or drop)
  * each option's text also appears in indra-ocr's text for the page; misses
    are reported (not failures) — indra-ocr garbles, pdftotext is used

Built against The Oracle Character Generator (Nord Games).  The layout
heuristics are general for this style of book; anything book-specific
(junk OCR'd from artwork, a garbled cover, paragraph breaks on prose pages)
belongs in a patches JSON kept OUTSIDE this public repo, e.g.
~/src/homebrew-private/book/<slug>/merge-patches.json.

Usage:
    python3 converters/layout_table_merge.py BOOK.pdf --out BOOK.combined.md
    python3 converters/layout_table_merge.py BOOK.pdf --indra-json indra.jsonl \\
        --patches ~/src/homebrew-private/book/<slug>/merge-patches.json --out out.md

Patches JSON:
    {"pages": {
        "2": {"replace_first_table": "## Table of Contents\\n\\n| ... |",
              "replace": [["old text", "new text"], ...],   # each must match once
              "extra_words": {"Section": 1},                # words added on purpose
              "dropped_words": {"p": 7}},                   # words removed on purpose
        ...}}

Requires ``pdftotext`` (poppler-utils) and, unless --indra-json is given,
``indra-ocr`` on PATH.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ENTRY = re.compile(r"^(\s*)(\d{1,2})(\s{2,})(\S.*)$")
INDEX_HEAD = re.compile(r"^\s*d(\d{1,3})\s{2,}(\S.*?)\s{2,}Page\s*$")
INDEX_ROW = re.compile(r"^\s*(\d{1,3})\s{2,}(\S.*?)\s{2,}(\d{1,3})\s*$")
OPTION_PAGE = re.compile(r"^\s{0,6}\d{1,2}\s{3,}[A-Z]")
FOOTER = re.compile(r"^\s*-\d+-\s*$")
WATERMARK = re.compile(r"\(Order #\d+\)\s*$")  # DriveThruRPG per-purchaser stamp
NON_LATIN_JUNK = re.compile(r"[ऀ-ॿ]")  # Devanagari: seen as OCR junk on Latin pages


# ---------------------------------------------------------------- text utils

def pdftotext_page(pdf: str, p: int) -> str:
    return subprocess.run(
        ["pdftotext", "-f", str(p), "-l", str(p), "-layout", pdf, "-"],
        capture_output=True, text=True, check=True,
    ).stdout


def body_lines(text: str) -> list[str]:
    return [l.rstrip() for l in text.replace("\f", "").split("\n")
            if not FOOTER.match(l) and not WATERMARK.search(l)]


def title_key(s: str) -> str:
    """Heading identity for matching index rows to printed headings: letters and
    digits only, so 'A leader...' == 'A leader…' and line wraps don't matter."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def words(s: str) -> Counter:
    s = re.sub(r"<[^>]+>", " ", s).replace("&amp;", "&")
    s = s.replace("**", " ").replace("|", " ")
    return Counter(re.findall(r"[A-Za-z0-9’']+", s))


def letters(s: str) -> str:
    return re.sub(r"[^a-z]", "", re.sub(r"<[^>]+>", " ", s).lower())


def join_lines(parts: list[str]) -> str:
    out = ""
    for p in (x.strip() for x in parts):
        if not p:
            continue
        if not out:
            out = p
        elif out.endswith("-") and len(out) > 1 and out[-2].isalpha():
            out += p  # keep the hyphen, drop the break: city-|states -> city-states
        else:
            out += " " + p
    return out


# ------------------------------------------------------------- page parsing

def find_gutter(lines: list[str]) -> int | None:
    """Column index of the widest all-blank vertical strip in the middle of the page."""
    width = max((len(l) for l in lines), default=0)
    occ = [0] * width
    for l in lines:
        for i, ch in enumerate(l):
            if ch != " ":
                occ[i] += 1
    lo, hi = int(width * 0.35), int(width * 0.70)
    best, run_start, best_len = None, None, 0
    for i in range(lo, min(hi, width - 1) + 1):
        if occ[i] == 0:
            if run_start is None:
                run_start = i
            if i - run_start + 1 > best_len:
                best_len, best = i - run_start + 1, run_start
        else:
            run_start = None
    return best if best_len >= 2 else None


def parse_column_known(lines: list[str], known_titles: list[str]) -> list[dict]:
    """parse_column when the headings are known in advance (from the dN index page).

    A heading is the longest run of 1-5 consecutive non-entry lines whose text
    matches a known title (title_key); every other line belongs to the current
    description or entry regardless of indentation. Needed where pdftotext lays
    justified text out raggedly, so continuation lines don't align, and where
    headings are whole clauses wrapped over several lines."""
    def ends_sentence(s: str) -> bool:
        return s.replace("…", "...").rstrip().endswith(".")

    # a body line that is just a heading word ('mayhem.') must not match the heading
    # 'Mayhem': the trailing period has to agree with the known title's
    targets = {(title_key(t), ends_sentence(t)) for t in known_titles}
    rows = [l for l in lines if l.strip()]
    subs: list[dict] = []
    cur = entry = None
    i = 0
    while i < len(rows):
        raw = rows[i]
        m = ENTRY.match(raw)
        if m and cur is not None:
            entry = [int(m.group(2)), [m.group(4)]]
            cur["entries"].append(entry)
            i += 1
            continue
        for k in range(min(5, len(rows) - i), 0, -1):
            seg = rows[i:i + k]
            text = " ".join(seg)
            if not any(ENTRY.match(x) for x in seg) and (title_key(text), ends_sentence(text)) in targets:
                cur = {"title": join_lines(seg), "desc": [], "entries": []}
                subs.append(cur)
                entry = None
                i += k
                break
        else:
            if entry is not None:
                entry[1].append(raw)
            elif cur is not None:
                cur["desc"].append(raw)
            else:
                raise ValueError(f"text before any known heading: {raw.strip()[:60]!r}")
            i += 1
    return subs


def parse_column(lines: list[str], known_titles: list[str] | None = None) -> list[dict]:
    """One column -> [{title, desc:[lines], entries:[[n, [lines]]]}]."""
    if known_titles is not None:
        return parse_column_known(lines, known_titles)
    subs: list[dict] = []
    cur = entry = None
    entry_indent = 0
    for raw in lines:
        if not raw.strip():
            # pdftotext pads with blank lines where the OTHER column has text, so a
            # blank line does not end an entry; only alignment does.
            continue
        m = ENTRY.match(raw)
        if m:
            if cur is None:
                raise ValueError(f"entry before any heading: {raw.strip()[:60]!r}")
            entry = [int(m.group(2)), [m.group(4)]]
            entry_indent = len(m.group(1)) + len(m.group(2)) + len(m.group(3))
            cur["entries"].append(entry)
            continue
        indent = len(raw) - len(raw.lstrip())
        s = raw.strip()
        looks_heading = len(s.split()) <= 3 and not re.search(r"[.,;:!?’'\"]$", s)
        if entry is not None and abs(indent - entry_indent) <= 1:
            # continuation lines align with the entry text; a short unpunctuated
            # line after a finished sentence is the next heading that happens to
            # sit at the same column
            done = re.search(r"[.!?][’'\"]?$", entry[1][-1].strip())
            if not (done and looks_heading):
                entry[1].append(raw)
                continue
        entry = None
        if cur is not None and not cur["entries"] and not cur["desc"] and looks_heading:
            cur["title"] += " " + s  # heading printed over two lines
            continue
        if cur is None or cur["entries"]:
            cur = {"title": s, "desc": [], "entries": []}
            subs.append(cur)
        else:
            cur["desc"].append(raw)
    return subs


def render_entry(text: str) -> str:
    m = re.match(r"^((?:\S+\s){0,5}?\S+?\.)\s+(.*)$", text)
    body = f"**{m.group(1)}** {m.group(2)}" if m else text
    return body.replace("|", "\\|")


def build_option_page(lines: list[str], known_titles: list[str] | None = None
                      ) -> tuple[list[dict], str]:
    g = find_gutter(lines)
    if g is None:
        raise ValueError("no column gutter found")
    subs = (parse_column([l[:g] for l in lines], known_titles)
            + parse_column([l[g:] for l in lines], known_titles))
    die = max((len(s["entries"]) for s in subs), default=0)
    md = []
    for s in subs:
        md.append(f"### {s['title']}\n")
        if s["desc"]:
            md.append(join_lines(s["desc"]) + "\n")
        md.append(f"| d{die} | Option |\n|---|---|")
        md += [f"| {n} | {render_entry(join_lines(parts))} |" for n, parts in s["entries"]]
        md.append("")
    return subs, "\n".join(md)


def build_index_page(lines: list[str]) -> tuple[int, str, list[tuple[int, str, int]], str]:
    die, col, rows = 0, None, []
    for l in lines:
        if not l.strip():
            continue
        h = INDEX_HEAD.match(l)
        if h:
            die, col = int(h.group(1)), h.group(2).strip()
            continue
        r = INDEX_ROW.match(l)
        if r:
            rows.append((int(r.group(1)), r.group(2).strip(), int(r.group(3))))
        elif rows and col is not None:
            n, name, pg = rows[-1]  # a long result wrapped onto the next line
            rows[-1] = (n, f"{name} {l.strip()}", pg)
        else:
            raise ValueError(f"unparsed index line: {l.strip()!r}")
    md = [f"## {col}\n", f"| d{die} | {col} | Page |", "|---|---|---|"]
    md += [f"| {n} | {name} | {pg} |" for n, name, pg in rows]
    return die, col, rows, "\n".join(md) + "\n"


# ------------------------------------------------------------------ patches

def apply_patches(p: int, md: str, patch: dict) -> str:
    if "replace_first_table" in patch:
        s, e = md.find("<table>"), md.find("</table>")
        if s < 0 or e < 0:
            raise ValueError(f"page {p}: replace_first_table but no <table>")
        new = patch["replace_first_table"]
        # if the replacement brings its own heading, drop the heading line directly above the table
        before = md[:s].rstrip("\n")
        line_start = before.rfind("\n") + 1
        if new.startswith("#") and before[line_start:].startswith("#"):
            s = line_start
        md = md[:s] + new + md[e + len("</table>"):]
    for old, new in patch.get("replace", []):
        n = md.count(old)
        if n != 1:
            raise ValueError(f"page {p}: patch {old!r} matched {n} times")
        md = md.replace(old, new)
    return md


# --------------------------------------------------------------------- main

def run_indra(pdf: str) -> dict[int, dict]:
    out = subprocess.run(["indra-ocr", pdf, "--format", "json"],
                         capture_output=True, text=True, check=True).stdout
    return {d["page"] + 1: d for d in map(json.loads, filter(None, out.splitlines()))}


def merge(pdf: str, indra: dict[int, dict], patches: dict) -> tuple[str, list[str], list[str], Counter]:
    pages_patch = {int(k): v for k, v in patches.get("pages", {}).items()}
    problems: list[str] = []
    notes: list[str] = []
    out: list[str] = []
    index_tables: list[tuple[int, str, int, list]] = []
    headings_on: dict[int, list[str]] = {}
    option_sizes: Counter = Counter()
    counts: Counter = Counter()

    for p in range(1, len(indra) + 1):
        lines = body_lines(pdftotext_page(pdf, p))
        imd = indra[p]["markdown"]
        patch = pages_patch.get(p, {})
        try:
            if any(INDEX_HEAD.match(l) for l in lines):
                die, col, rows, md = build_index_page(lines)
                if [r[0] for r in rows] != list(range(1, die + 1)):
                    problems.append(f"p{p}: d{die} rows {[r[0] for r in rows]}")
                index_tables.append((p, col, die, rows))
                kind = "index"
            elif any(OPTION_PAGE.match(l) for l in lines):
                subs, md = build_option_page(lines)
                headings_on[p] = [s["title"] for s in subs]
                il = letters(imd)
                for s in subs:
                    nums = [e[0] for e in s["entries"]]
                    option_sizes[len(nums)] += 1
                    if nums != list(range(1, len(nums) + 1)):
                        problems.append(f"p{p} {s['title']!r}: entries {nums}")
                    for n, parts in s["entries"]:
                        if letters(join_lines(parts)) not in il:
                            notes.append(f"p{p} {s['title']} #{n}: not verbatim in indra-ocr text")
                kind = "options"
            else:
                md = apply_patches(p, imd, patch)
                if md.strip() and "\n" not in md.strip() and not md.startswith("#"):
                    md = "# " + md.strip().title()  # bare section-title page
                kind = "indra"
        except ValueError as e:
            problems.append(f"p{p}: {e} -> fell back to indra-ocr markdown")
            md, kind = imd, "indra-fallback"
        counts[kind] += 1

        # word-for-word coverage against pdftotext
        if kind in ("index", "options"):
            built = "\n".join(l for l in md.split("\n")
                              if not re.match(r"^\| d\d+ \||^\|---|^## \S+$", l))
            want = words("\n".join(l for l in lines if not INDEX_HEAD.match(l)))
        else:
            built = md
            want = words("\n".join(lines))
            want += Counter(patch.get("extra_words", {}))
            want -= Counter(patch.get("dropped_words", {}))
        got = words(built)
        if kind == "indra" and md.startswith("# ") and "\n" not in md.strip():
            want = Counter({k.lower(): v for k, v in want.items()})
            got = Counter({k.lower(): v for k, v in got.items()})
        if want != got:
            problems.append(f"p{p} ({kind}): word mismatch missing={dict(want - got)} "
                            f"extra={dict(got - want)}")
        if NON_LATIN_JUNK.search(md):
            problems.append(f"p{p} ({kind}): non-Latin OCR junk left in text")
        out.append(f"<!-- page {p} ({kind}) -->\n\n{md.strip()}\n")

    if len(option_sizes) > 1:
        problems.append(f"option tables have mixed sizes: {dict(option_sizes)}")
    for p, col, die, rows in index_tables:
        for n, name, pg in rows:
            if name not in headings_on.get(pg, []):
                problems.append(f"p{p} {col} #{n} {name!r} -> page {pg}: "
                                f"headings there {headings_on.get(pg)}")

    stats = Counter(pages=sum(counts.values()), **counts,
                    index_tables=len(index_tables),
                    option_tables=sum(option_sizes.values()))
    return "\n".join(out), problems, notes, stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pdf")
    ap.add_argument("--out", required=True, help="output markdown path")
    ap.add_argument("--indra-json", help="existing `indra-ocr --format json` output "
                                         "(default: run indra-ocr now)")
    ap.add_argument("--patches", help="per-book patches JSON (keep outside this repo)")
    ap.add_argument("--force", action="store_true", help="overwrite --out if it exists")
    a = ap.parse_args(argv)

    if Path(a.out).exists() and not a.force:
        print(f"refusing to overwrite {a.out} (use --force)", file=sys.stderr)
        return 2
    if a.indra_json:
        indra = {d["page"] + 1: d for d in map(json.loads, filter(None, open(a.indra_json)))}
    else:
        indra = run_indra(a.pdf)
    patches = json.load(open(a.patches)) if a.patches else {}

    md, problems, notes, stats = merge(a.pdf, indra, patches)
    Path(a.out).write_text(md)

    print(" ".join(f"{k}={v}" for k, v in stats.items()))
    print(f"PROBLEMS ({len(problems)}):")
    for x in problems:
        print("  ", x)
    print(f"indra-ocr disagreements, pdftotext used ({len(notes)}):")
    for x in notes:
        print("  ", x)
    print(f"wrote {a.out}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
