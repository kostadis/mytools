---
name: project-spell-canon
description: spell_canon.py canonicalises hand-written-bible proper-noun spellings (propose→review→apply); two-pass threshold workflow
metadata:
  node_type: memory
  type: project
  originSessionId: 374c07c8-3825-4bfe-9ecf-1596ac85bef3
---

`spell_canon.py` (CampaignGenerator, merged via PR #69) fixes proper-noun spelling drift in a hand-written bible **at the source**, before it propagates through `split_chapters.py` → per-chapter files → fact extraction. Two subcommands with a human checkpoint between (spelling/identity is a precision decision):

- `propose bible.md --inventory inv.md --out map.json` — non-destructive; clusters near-duplicate proper nouns into a reviewable `{variant: canonical}` map + report. Authority: a token close to a `**bold**` name in the module inventory → inventory spelling (Phase A); else a rare typo of an established frequent name → that name (Phase B).
- `apply bible.md --map map.json` — deterministic whole-word, case-preserving replace; possessives intact (`Zalthri's→Zalthir's`); `--dry-run`.

**Two-pass workflow (this is the non-obvious part):** run `propose` at the default `--sim 0.88` first = high precision, near-zero false positives → review → apply. THEN run a second `propose --sim 0.80` to sweep the transposition tail (`Gyrgum→Grygum`, `Serith→Sarith`, ratio ~0.83) — but that looser pass drags in real-word false positives (`Earth→Death`, `Brother→Other`, `Elves→Delve`) and needs careful human pruning. Guards that hold the precision: morphology (plurals/inflections), capitalisation (lowercase common-word collisions), edit-distance ≤2.

**Inventory authority wins even over your own frequency:** ruled `Rusharoo→Rasharoo`, `Jadgar→Jadger`, `Mithril→Mithral` (FR canon) despite the bible using the wrong spelling many times. But the inventory is only the published-book list — homebrew names (`Eldgrim`, `Maerith`, `Daral`) and place names (`Raucus` Mesa) are NOT in it and must be ruled by hand.

First run (2026-05-30): 287 fixes on the OOTA bible, chapters regenerated. `split_chapters.py` now ASCII-transliterates accents in slugs so `Faerûn` in a heading → `faerun` in the filename. Inventory at [[reference-oota-inventory]]; relates to [[project-ensemble-replaces-claude-extraction]] (cleaner extraction input).
