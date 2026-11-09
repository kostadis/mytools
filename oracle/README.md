# oracle

One command for the three Nord Games **Oracle** generators:

| Command | Book | rpg-lib | Themes | Sections (d12 → d4) |
|---|---|---|---|---|
| `oracle npc` | The Oracle Character Generator | #1168 | 5 themes | Role · Personality · Motivation · Flaw · Intrigue |
| `oracle monster` | The Oracle Monster Generator | #1170 | 7 environments | Monster Type · Behavior · Archetype · Special Ability · Intrigue |
| `oracle story` | The Oracle Story Generator | #10342 | 5 themes | Actor · Action · Subject · Intent · Development |

**This repo is public, so it holds no book content.** `extract.py` reads your own copies of the PDFs and writes `~/src/homebrew-private/book/<slug>/tables.json` for each book. `$ORACLE_DATA_DIR` overrides the base directory. `extract.py` refuses to write inside this repo. The PDF paths and slugs are in `books.py`.

## Setup (once)

```bash
python3 extract.py            # all three books; or: extract.py npc|monster|story [--pdf P] [--out P]
```

Needs `pdftotext` and `pdfinfo` (poppler-utils). No pip dependencies; stdlib only.

## Use

```bash
./oracle npc                                   # random theme, all five sections, d4 detail
./oracle npc --theme villains -n 3
./oracle npc --theme heroes --role paladin/devotion --flaw brash
./oracle monster --env swamp --type dragon --ability "bestow curse"
./oracle monster --mix --brief -n 5            # each section from a random environment
./oracle story --theme sidequests --brief      # one-sentence hook
./oracle story --theme epic --actor celestial --action dominate --subject realm \
    --intent ruler --development undermined
./oracle story --list epic                     # every result and option for one theme
./oracle npc --json --seed 7
```

Shared flags: `-n`, `--theme` (`--env`/`--environment` for monsters, any word prefix), `--mix`, `--no-detail`, `--brief`, `--json`, `--seed`, `--width`, `--list [THEME]` and `--data`.

There is one fix flag per section, all taking `NAME[/OPTION]`. Monsters also accept `--type` and `--ability` as aliases.
- npc: `--role`, `--personality`, `--motivation`, `--flaw`, `--intrigue`
- monster: `--monster-type`, `--behavior`, `--archetype`, `--special-ability`, `--intrigue`
- story: `--actor`, `--action`, `--subject`, `--intent`, `--development`

Names match in this order: exactly; by prefix, also ignoring the first word (so `celestial` matches *A celestial…* and `dominate` matches *will dominate…*); then by a unique substring (`undermined`). A miss lists the valid choices.

The story command joins the five titles into one sentence, as the book describes. The worked examples from the npc and story books both reproduce exactly.

`--mix` is sanctioned by the monster book ("mix and match outcomes from different sections"). For npc and story it's a house option.

Want it on your PATH? `ln -s ~/src/mytools/oracle/oracle ~/.local/bin/oracle`

## Extraction

The extraction is deterministic: `pdftotext -layout`, parsed with `pdf-translators/converters/layout_table_merge.py`, which is imported rather than copied. No LLM is involved.

**The d12 index pages define the structure.** They name every result and the page it's on, so option pages are parsed against those known headings (`known_titles`). That copes with pdftotext's ragged justified text and with story headings that are whole clauses wrapped over several lines.

Nothing is written unless every check passes:
- The expected number of themes, each with exactly its five sections in order.
- Every d12 table covers 1–12 and every d4 table covers 1–4.
- Every result is found exactly once in its section.
- Every option splits into a name and its text.
- **Word for word:** every option page's words equal its headings plus descriptions plus options.

Book mistakes are recorded in each `tables.json` under `errata` and printed on every run:
- **monster:** 5 pairs of results whose index page numbers are swapped, in Forest Intrigue, Swamp Behavior, Swamp/Tundra/Waterways Special Ability. Results are looked up across their whole section, so these resolve automatically.
- **story:** 2 index rows whose wording differs from the printed heading. These are fixed in `INDEX_ERRATA` in `extract.py`.

Not extracted: the story book's 25 pregenerated stories (pp. 109–134). They're prose, not roll tables.

Results: npc 300 results / 1,200 options; monster 420 / 1,680; story 300 / 1,200.
