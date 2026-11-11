---
name: pdf-table-markdown
description: >
  Convert an RPG PDF from the rpg-lib library into clean Markdown with indra-ocr,
  and when the book is built from numbered roll tables (dN index pages, d4/d6
  option tables laid out in two columns) merge in pdftotext -layout so the die
  numbers stay attached to their entries. Uses pdf-translators/converters/
  layout_table_merge.py, which is deterministic (no LLM) and gated on
  word-for-word checks against the PDF. Book-specific fixes go in a patches
  JSON in ~/src/homebrew-private, never the public mytools repo. Also checks the
  library for duplicate copies of the book first. Invoke as
  /pdf-table-markdown <book title or rpg-lib id or pdf path>.
argument-hint: <book title | rpg-lib id | pdf path>
tools: Read, Write, Edit, Bash, Grep, ToolSearch, AskUserQuestion
---

# PDF → Markdown for roll-table books (indra-ocr + pdftotext)

Worked out on Nord Games' *The Oracle Character Generator* (rpg-lib #1168) and
reused on the Oracle Monster (#1170) and Story (#10342) generators. Read this
before converting any table-heavy RPG PDF.

## The tools, and what each is good and bad at

| Tool | Where | Good at | Bad at |
|---|---|---|---|
| `indra-ocr` | `~/.venv/bin/indra-ocr` | prose, headings, paragraphs; OCR of scanned pages; per-page JSON (`--format json`) | side-by-side roll tables: the die number is its own text block, so it lands mid-entry (`some words, 1 more words`) or the table comes out as one HTML row per printed line; junk OCR'd from artwork (`## E`, `(9)`, stray Devanagari) |
| `pdftotext -layout` | poppler-utils | keeps two-column table rows aligned: `1      Name. Entry text…`; deterministic, sub-second | no Markdown at all; text-layer only (useless on scans) |
| `layout_table_merge.py` | `~/src/mytools/pdf-translators/converters/` | merges the two per page, verifies every page word-for-word | layout heuristics fit two-column dN books; anything else falls back to indra-ocr |

**indra-ocr flags that do NOT fix the table problem** (measured, don't re-try them):
- `--mode text` — identical output on pages whose text layer already passes its checks.
- `--model-order` — worse: bunches the numbers ahead of every entry (`1 2 3 4 Name. …`).

`indra-ocr` logs per page `text|hybrid|ocr` and `order=pdf|model` with `--timings`; read
that before theorising about ordering. Check the *PDF* page number (pdftotext `-f N -l N`),
not the printed one, when matching a log line to content.

## Procedure

### 1. Find the book, and check for duplicates first

1. Load `mcp__rpg-library__search_books` / `get_book` via ToolSearch. Search `title_query`
   with the distinctive word; `get_book` gives `filepath`, `pdf_creator` and bookmarks.
2. If several entries share the title, **compare the actual files** — sizes and
   `sha256sum`. Byte-identical copies are duplicates; same title/page count/bookmarks but a
   different hash is a revision — the later `pdf_creator` version and mtime is usually the
   current one. Convert the current one.
3. If the library lists duplicates or a stale revision as current, offer to file an issue
   against rpg-lib in `kostadis/mytools` (precedent: issue #106) via the GitHub MCP —
   label `bug`, a table of id / path / size / hash / creator / mtime, and no automatic
   "which copy wins" fix (that is a precision decision for a review queue).

### 2. Plain conversion (always fine for prose books)

```bash
indra-ocr BOOK.pdf --out "<same folder as the PDF>/" --timings   # writes <stem>.md
```
Before writing next to the PDF, `ls` the folder — never overwrite an existing `.md`.
~11 s for 109 pages on 16 cores. Spot-check a table page; if the book has no roll tables
and the prose reads fine, stop here.

### 3. Diagnose a table book

```bash
pdftotext -f N -l N -layout BOOK.pdf -      # one page, aligned
```
Classify every page: an index page has a header like `d12   Role   Page`; an option page has
lines like `  1      Name. text…` in two columns. Count the kinds — they should match the
book's structure (e.g. 5 themes × 5 sections → 25 index pages). Look at any page that is
neither.

### 4. Merge

```bash
cd ~/src/mytools/pdf-translators
indra-ocr BOOK.pdf --format json > /scratch/indra.jsonl        # or omit --indra-json below
python3 converters/layout_table_merge.py BOOK.pdf --indra-json /scratch/indra.jsonl \
    [--patches ~/src/homebrew-private/book/<slug>/merge-patches.json] \
    --out "<pdf folder>/<stem>.combined.md"
```
Exit 0 only if every check passes:
- index tables 1..N and option tables 1..K, one die size book-wide;
- every index row's (name, page) is a heading actually on that page;
- **word multiset of every output page == pdftotext's for that page**;
- options missing from indra-ocr's text are listed (indra garble; pdftotext is used) — not failures.

Write to a scratchpad first; copy next to the PDF only after a clean run.

### 5. When a check fails — fix the rule, not the output

Read the failing page with `pdftotext -layout | cat -A` and find the layout cause. Rules
that each fixed a real miss (all already in the parser):

| Symptom | Cause | Rule |
|---|---|---|
| entry cut in half, `'Name': entries [1, 2]` | pdftotext pads blank lines where the OTHER column has text | blank lines never end an entry |
| a heading glued onto the previous entry | heading happens to start at the entry-text column | short unpunctuated line after a finished sentence = heading |
| heading's second line read as description | heading printed over two lines | join short lines before any description |
| continuation lines not aligned at all | justified text laid out raggedly | use `known_titles` mode (headings from the index page) |
| heading is a whole wrapped clause | e.g. `but the hero is / protected by a / power.` | `known_titles`, matching 1–5 lines by `title_key` |
| body word matches a heading (`rain.` vs a heading *Rain*) | key ignores punctuation | trailing period must agree |
| index row text missing its end | long result wrapped onto the next index line | join wrapped index rows |
| `(Order #N)` lines everywhere | DriveThruRPG purchase watermark (has the buyer's name) | dropped in `body_lines`; never let it into output |

After any parser change: rerun the Oracle Character book and `cmp` against the previous
output (must be byte-identical unless the change was meant to alter it), and run
`pytest tests/test_layout_table_merge.py`. Add a synthetic-text test per new rule — **no
book text in tests**, the repo is public.

### 6. Prose pages: per-book patches (human-reviewed)

indra-ocr's prose pages can carry artwork junk, a garbled logo title, wrong paragraph
breaks, single-word OCR errors (a dropped first letter). Fix them in
`~/src/homebrew-private/book/<slug>/merge-patches.json` (format in the script's docstring):
`replace` pairs must match exactly once; declare `extra_words` / `dropped_words` so the
word check still passes; `replace_first_table` swaps an HTML table for Markdown. Show the
user the patch list before relying on it — each is a judgement about what the book says.
Confirm the fix against pdftotext's text, never against memory.

### 7. Report honestly

Say what came from which tool, list every patch and every indra disagreement, name the
pages that fell back, and keep the indra-only `.md` unless the user says to delete it.

## Hard rules

- **mytools is public.** Book text, patches, extracted tables → `~/src/homebrew-private`
  (private, commit to `master` directly, as earlier book-data commits did). Code and
  synthetic tests only in mytools; scan new repo files for book text before committing.
- Don't overwrite files next to the user's PDFs; new name, or `--force` only with consent.
- Deterministic all the way: no LLM in the conversion. An LLM may help diagnose; it never
  decides what the book says.

$ARGUMENTS
