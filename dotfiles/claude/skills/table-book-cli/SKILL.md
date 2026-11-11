---
name: table-book-cli
description: >
  Turn an RPG book of random roll tables (NPC/monster/story/name generators —
  d12 index → d4 options, d100 ranges, "roll twice") into a command-line random
  generator in ~/src/mytools, the way dde-npc/ and oracle/ were built: a
  deterministic extract.py that reads the user's own PDF with pdftotext and
  writes tables.json to ~/src/homebrew-private (never the public repo), gated on
  coverage/structure/word-for-word checks with book errata recorded, plus a
  stdlib CLI with --seed/--json/--brief/--list and per-table fix flags. Also
  covers adding a book as a subcommand of an existing CLI (oracle npc|monster|
  story). Invoke as /table-book-cli <book title or rpg-lib id> [existing CLI to extend].
argument-hint: <book title | rpg-lib id> [existing CLI dir]
tools: Read, Write, Edit, Bash, Grep, ToolSearch, AskUserQuestion
---

# Random-table book → CLI generator

Precedents to read first — copy their shape, don't reinvent it:
- `~/src/mytools/dde-npc/` — one book, irregular tables (d100 ranges, errata, "roll twice").
- `~/src/mytools/oracle/` — three books behind one CLI (`oracle npc|monster|story`),
  registry in `books.py`, extraction through the shared page parser in
  `pdf-translators/converters/layout_table_merge.py` (see the `pdf-table-markdown` skill).

## Architecture (non-negotiable parts)

```
mytools/<tool>/                       PUBLIC — code only
  extract.py     PDF -> tables.json, deterministic, refuses to write inside the repo
  <cli>          stdlib-only generator, reads tables.json
  books.py       (multi-book) slug, pdf path, rpg-lib id, theme label, section names, counts
  README.md
~/src/homebrew-private/book/<slug>/tables.json   PRIVATE — the book's content
```
- Data path overridable by env var (`$DDE_DATA`, `$ORACLE_DATA_DIR`) and `--out`/`--data`.
- `extract.py` checks `REPO in out.resolve().parents` and exits 2 — the repo is public
  and must never hold book text, tables, patches or errata *content* beyond short keys.
- No LLM anywhere. pdftotext + regex/parser + checks. An LLM drafting the extraction
  would be deciding scope and attribution (which entry belongs to which table) — the
  precision decisions the global rule reserves for deterministic code + human review.

## Procedure

### 1. Find the PDF (and the right copy)
rpg-lib MCP (`search_books`, `get_book`) → `filepath`. If several copies exist, hash them
and use the current revision (see `pdf-table-markdown` step 1). Record the rpg-lib id in
the data's `source` block and the README.

### 2. Learn the book's own procedure before writing code
Read the Instructions / Examples pages (`pdftotext -f 2 -l 3`). Capture:
- the unit of generation (theme/environment → sections; or step 1..N);
- how results combine (titles joined with ` · `; or one sentence — the Story book chains
  `Actor… Action… Subject… Intent… , but Development.`);
- what the book sanctions vs. what would be a house rule (`--mix` across themes is
  sanctioned by the Monster book, a house option elsewhere — say which in `--help`/README);
- **the book's worked example** — it becomes the acceptance test (step 6).

### 3. Map the layout, then let the book define the structure
Classify every page with `pdftotext -layout` and count kinds against the expected shape
(Oracle: 5 sections × themes → index pages; 3 option pages per section). **Use the book's
own index as the structural authority**: index pages name every result and its page, so
parse option pages against those known headings (`known_titles` mode) instead of guessing
headings from layout. Theme boundaries come from title pages (≤4 words, not an index).

### 4. extract.py — checks gate the write
Write nothing unless all pass; print counts every run:
- expected number of themes/sections, exact section order;
- every table covers 1..N with no gaps/overlaps (dN or d100 ranges);
- every index row resolves to exactly one heading in its section;
- every option splits into name + text;
- **word multiset of each option page == words of what was extracted from it** — the
  check that catches text attached to the wrong entry, which counts alone never see.

**Errata are explicit, commented, and recorded — never matched around:**
- wrong page numbers in the index → look up across the whole section, append to
  `data["errata"]`, print every run (Oracle Monster: 5 swapped pairs);
- index wording ≠ printed heading (typos) → an `INDEX_ERRATA`/`ERRATA` dict keyed by the
  printed text with a comment per fix (Oracle Story: 2; dde-npc: 9 range typos);
- ranges the book omits → leave the gap, reroll on it, report it.
Show the user the errata list; each fix is a judgement about what the book means.

### 5. The CLI (stdlib, argparse)
Flags every generator gets: `-n`, `--seed`, `--json`, `--brief` (one line each),
`--no-detail` (skip the sub-rolls), `--width`, `--list [THEME]`, `--data`, `--theme`
(any word prefix; aliases like `--env` where the book calls it that), one **fix flag per
section** `--<section-slug> NAME[/OPTION]` (aliases for long names: `--type`, `--ability`).
- Name matching: exact → prefix (also ignoring the first word, so `harbour` finds
  *A harbour…*) → unique substring; compare on letters+digits only (`…` == `...`).
- Every miss exits with the list of valid choices.
- Contradictory flags error out (`--mix` with `--theme`/fixed results).
- Missing tables → tell the user the exact `extract.py` command.
- Several books with one shape → one engine + a registry + argparse subcommands; don't
  copy the generator per book. Move/rename an existing single-book tool with `git mv`.

### 6. Verify
- Reproduce the book's worked example exactly with fix flags (both Oracle examples do).
- Smoke every subcommand: random, `--brief -n 5`, `--json`, `--list`, `--list THEME`,
  a bad theme, a bad name, a contradictory flag pair, `--seed` reproducibility.
- If a shared parser changed: rerun its previous consumers and `cmp` their output
  (must be byte-identical), run its tests, add synthetic-text tests for each new rule.
- `grep` the new repo files for book text and purchase watermarks (`(Order #`, buyer
  name) before committing; also grep the generated tables for watermarks.

### 7. Ship (only on the user's say-so)
mytools: branch, commit only the tool's files (never the user's unrelated dirty files —
`dotfiles/claude/settings.json`, `.serena/`, `.tokensave/` are routinely dirty), push,
PR via `mcp__github__create_pull_request`, merge via `mcp__github__merge_pull_request`
(merge commit, `expectedHeadSha` = full 40-char sha), then `git checkout main && git pull`
and delete the local branch. After a `git mv`, stage the new path only — adding the old
path aborts the whole `git add`. homebrew-private: commit `tables.json` straight to
`master` and push. Offer a `~/.local/bin` symlink; note it points at the working tree, so
it breaks if the user checks out a branch where the tool doesn't exist yet.

## README checklist
Book + rpg-lib id; where data lives and the env var; setup command; usage examples
including the worked example; how rolling works per the book; which options are house
rules; extraction method and checks; every erratum category; what was NOT extracted
(e.g. the Story book's 25 pregenerated stories) and why. Add a one-line entry to
`~/src/mytools/CLAUDE.md` under RPG tooling.

$ARGUMENTS
