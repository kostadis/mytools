# oracle-npc

Command-line NPC generator driven by the tables in **The Oracle Character Generator** (Nord Games). It is rpg-lib book #1168, the InDesign 18.5 build. See issue #106 for the library's duplicate copies.

**This repo is public, so it holds no book content.** `extract.py` reads your own copy of the PDF and writes the tables to
`~/src/homebrew-private/book/oracle-character-generator/tables.json` (override with `$ORACLE_DATA` or `--out`). `oracle_npc.py` reads them from that same path. `extract.py` refuses to write inside this repo.

## Setup (once)

```bash
python3 extract.py          # needs pdftotext + pdfinfo (poppler-utils); default PDF path is the Drive copy
```

No pip dependencies; stdlib only.

## Use

```bash
./oracle_npc.py                               # one NPC, random theme
./oracle_npc.py -n 3 --theme villains         # three villains (any word prefix: vill, scoun, nob, ...)
./oracle_npc.py --theme heroes --role paladin --flaw brash/reckless   # fix results, roll the rest
./oracle_npc.py --mix                         # each section rolled on a random theme
./oracle_npc.py --brief -n 10                 # one summary line each
./oracle_npc.py --no-detail                   # d12 results only, skip the d4 options
./oracle_npc.py --json --seed 7               # machine-readable, reproducible
./oracle_npc.py --list                        # every theme's d12 results
./oracle_npc.py --list nobles                 # one theme, with every d4 option
```

The book's own example (Instructions page) reproduces exactly:

```bash
./oracle_npc.py --theme heroes --role paladin/devotion --personality driven \
    --motivation peace --flaw brash --intrigue "embarrassing connection"
```

## How it rolls

The book has 5 **themes**: Heroes & Champions, Merchants & Artisans, Nobles & Clergy, Townsfolk & Travelers and Villains & Scoundrels. Each theme has the same 5 **sections**: Role, Personality, Motivation, Flaw and Intrigue.

For each section, the tool rolls d12 to get a result, such as *Paladin*. It then rolls d4 on that result's own options for detail, such as *Devotion*. The summary line combines the titles, the way the book's Instructions describe.

- `--role NAME[/OPTION]` (and the same flag for each other section) fixes a result instead of rolling it. Names match exactly, or by unique prefix. A bad name lists the valid choices.
- `--mix` is a house option, not a rule from the book. It rolls each section on an independently chosen random theme. It can't be combined with `--theme` or fixed results.

## Extraction notes

The extraction is deterministic: `pdftotext -layout`, parsed with the page parser from `pdf-translators/converters/layout_table_merge.py`, which `extract.py` imports rather than copying. No LLM is involved. Before writing anything, `extract.py` checks the following and writes nothing if any check fails:

- 5 themes, each with exactly the 5 sections in order.
- Every d12 table covers 1–12.
- Every d12 row's page holds a heading with exactly that name.
- Every option table covers 1–4, and every option splits into a name and its text.

Result: 300 d12 results and 1,200 options, with no errata needed.
