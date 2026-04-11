# rpg-lib — TODO / Bugs

_Last touched 2026-04-11. Five PRs (#1–#5) merged in this session; three live-DB data backfills applied. All original TODO bugs and data-quality items are closed._

## Open

### Indexer: filename-level duplicates slipping past `is_duplicate=0`
Found while surveying for the PF conversion fix (task 4). Several filenames appear in many non-duplicate rows:
- `Castle_Oldskull_Treasury_2009_-_2024.pdf` × 41
- `Free_Adventures_Exclusive_Discounts_and_More.pdf` × 25
- `Othrys_Free_Sample_(08-20-2021).pdf` × 12
- `How_MSF_is_responding_to_the_war_in_Ukraine___Doctors_Without_Borders_-_USA.pdf` × 8
- `0_DoW_Print and Assembly Instructions_*.pdf` × 4 each
- `193137-Icewind_Dale_Travel_Cheatsheet*.pdf` × 4 each

These look like the same file indexed once per folder (the indexer probably keys on filepath, not on content hash, and the same file is dropped into multiple campaign folders). The same root cause is also why some 5e/PF twin pairs show up twice each in the PF survey. The dedup pass that sets `is_duplicate=1` is missing this class.

**Fix direction:** add a pass to the indexer (or a one-off normalizer) that flags `is_duplicate=1` on rows where `(filename, page_count, file_size)` already exists on a kept row, regardless of folder. Or move to content hashing if the indexer has bandwidth for it.

### `DDAL-DRW*` / `DDAL-EB-*` `organized_play` backfill
35 books in the library are organized-play DMsGuild content (Dreams of the Red Wizards arcs, Eberron / Oracle of War / Season 9) but don't currently have the `organized_play` tag. Task 2's backfill SQL only checked `series LIKE '%DDAL%'`, and these books have `Dreams of the Red Wizards` / `Oracle of War` in their series column with `DDAL-...` only in filename/collection.

**Fix:** small one-off SQL UPDATE — extend the predicate to also check `collection LIKE '%DDAL%'` (or `filename LIKE '%DDAL-DRW%' OR filename LIKE '%DDAL-EB%'`). The merged enricher rule from PR #1 + #4 already handles this correctly for new enrichments; this is purely existing-row catch-up.

### `Rime of the Frostmaiden DM's Resource` cluster
PR #3 merged the plural-vs-singular variant. Three potentially-mergeable variants remain:
- `Rime of the Frostmaiden DM's Resource` (19)
- `Icewind Dale: Rime of the Frostmaiden DM's Resource` (26, post-PR-#3)
- `Ten-Towns - an Icewind Dale: Rime of the Frostmaiden DM's resource` (8)

All three are `Dungeon Masters Guild` publisher and look structurally similar but might be genuinely distinct product lines from different DM's Guild creators. Needs per-book inspection or a list of product IDs before merging. Not urgent — keyword search still finds them.

### Pre-existing NLQ test failure
`test_wiki.TestParseQuery.test_extracts_all_fields` has been failing since before this session. Expected tag `adventure`, got `Adventure` — case-sensitivity in the mocked `parse_query` path. Not blocking; noise in the test output. Trace: case-preservation in `library_api/nlq.py` between LLM extraction and the test's assertion.

### `APGDMG002PF.pdf` edge case
One PF conversion in the library (`APGDMG002PF.pdf`, "Journey into the Realms (5e)") doesn't match the PR #5 regex because there's no separator before `PF`. Currently still classified as D&D 5e. Not worth widening the regex (false-positive risk on any filename randomly ending in "PF") — could be hand-corrected if it ever matters.

### Catalogue gaps (inventory, not bugs)
Notes from the AL survey on 2026-04-11 — acquisition targets if completeness matters:
- D&D Adventurers League Seasons 2, 4, 6, 7 missing entirely
- Season 8 has only one adventure (`DDAL08-13 Vampire of Skullport`)
- CCC (Convention-Created Content) line is nearly empty (1 book: `CCC-AETHER`)

### Unqualified AL bucket — second-pass classification
After PR #3, 34 books remain in the unqualified `D&D Adventurers League` series. Mostly AL program materials (DM Guide, Player Guide, FAQ, logsheets, Season 9 Oracle of War) but some are substring-classifiable:
- `Curse-of-Strahd-Extended-Dark-Gifts*` → Season 4 (Curse of Strahd)
- `DDALRoD_CharacterSheet*` → Season 3 (Rage of Demons)
- `ADVLeague_PlayerGuide_TODv1*` → Season 1 (Tyranny of Dragons)
- `*Oracle_of_War*`, `*S9_AL_*` → Season 9 (Eberron)

A small substring-heuristic pass would shrink this to ~25. Not in any current PR scope.

---

## Closed (this session)

### #1 ~~`library_mcp.search_books` crashes on any query containing `&`~~
**Fixed in kostadis/mytools#2 (merged).** The `&` was a red herring. Real cause: `_row_to_summary` reads `min_level`/`max_level` but six SELECTs in `library_api/db.py` didn't project those columns. `sqlite3.Row[missing]` raises `IndexError: No item with that key`, so any non-empty result through those paths crashed. Plain queries "worked" only because they returned 0 rows. Fixed all six SELECTs. Added `TestRowToSummaryContract` (11 tests) that exercises every `_row_to_summary` call site with non-empty results and asserts the full key set, so future column additions fail loudly.

### #2 ~~`find_books_by_tag` doesn't match AL content~~
**Fixed in two parts.**
- **Data backfill (2026-04-11):** one-off `organized_play` backfill on 74 AL books. Canonical `organized_play` tag already existed in the vocabulary; it was just under-applied (21/95 → 95/95). Rollback: `rollback_organized_play_backfill_20260411_122627.tsv`.
- **Enricher rule (kostadis/mytools#1 merged):** `SERIES_IMPLIED_TAGS` rule table + `apply_series_implied_tags` helper. Any future enrichment of an AL filename/collection automatically gets `organized_play` without relying on the LLM (which was tagging it on only ~22% of AL books).
- **Not adopted:** a new `adventurers_league` canonical tag. Would have broken the vocabulary's campaign-line-agnostic discipline.

### #3 ~~Series name fragmentation (`--normalize-series` pass)~~
**Shipped in kostadis/mytools#3 (merged) and applied to the live DB.** New `--normalize-series` CLI flag runs three passes: structural cleanup (whitespace, em/en dashes, trailing punctuation), `SERIES_ALIASES` one-hop lookup (8 entries for AL Season 1 / 3 / 5 cluster merges plus the Frostmaiden plural → singular), and AL filename-code reassignment (`DDEX{S}` / `DDAL{SS}` parsing for books in the unqualified AL bucket).

Live-DB run: 67 books updated (21 via filename code). AL cluster compressed from 10 → 7 series. Canonical form: `D&D Adventurers League - Season N (Campaign Name)`. Also corrected a wrong label in the existing data — 4 DDEX3 books were labelled `Season 3 (Elemental Evil)` but DDEX3 is actually Rage of Demons (Elemental Evil was Season 2 / DDEX2). Rollback: `rollback_normalize_series_20260411_131103.tsv`. 40 new tests across 6 classes.

### #4 ~~Pathfinder conversion twins~~
**Reframed and fixed in kostadis/mytools#5 (merged) plus a live-DB backfill.** The original TODO said twin pairs cluttered search results, but the existing `(publisher, normalized_collection)` variant dedup was already collapsing them — verified with `search('Thimblerigging', grouped=True)` returning 1 group with `variant_count=2`.

The actual bug was narrower: 27 PF conversions in the library were misclassified as `D&D 5e` (the LLM read the 5e base title). Fix: `apply_pathfinder_conversion_rule` post-LLM override in `validate_enrichment` — if filename matches `[-_]PF(?:\.pdf|_)` AND current `game_system` is in a D&D-family set, override to `Pathfinder 1e` and rewrite tags (`5e`/`5e_2024`/etc → `pf1e`).

Self-protection: gating on D&D-family system means non-D&D files with `_PF` in the name are left alone. Verified against 12 real false-positive risks: Dune (×5, `_pf_` is a version marker), Vampire: TM, John Carter, Historia (×2), Savage Worlds, plus some System Neutral / Universal — all untouched. Backfill applied: 27/27 books now `Pathfinder 1e`. Rollback: `rollback_pf_conversion_backfill_20260411_134639.tsv`. 21 new tests.

### #5 ~~Prefix-match false positive on `Night's Dark Terror`~~
**Fixed in kostadis/mytools#4 (merged).** The TODO's original framing was slightly wrong: there was no existing prefix filter in the code. The false positive was introduced by the `\bDDEX` regex I wrote for PR #1, which matched `DDEXP_B10_NightsDarkTerror.pdf` (a scanner-added prefix on a 1986 Basic D&D module). Word boundary alone doesn't care what comes after the match.

Fix: `\bDDAL(?![A-Za-z])|\bDDEX(?![A-Za-z])` — negative lookahead rejects letter suffixes but still accepts digits (`DDAL05-08`), separators (`DDAL-DRW06`, `DDAL-EB-01`), and triple-segment codes (`DDAL050801`). Live DB impact was zero (book 13041 hadn't been tagged — task-2 backfill skipped it because its series column is `Basic D&D Expert Set`, and the task-6 enricher rule only fires on fresh enrichments, which happened before PR #1 merged).

---

## Live-DB data mutations applied this session

Three deterministic backfills were applied to `rpg_library.db` and verified before the corresponding PRs were merged. Each was snapshotted to a rollback TSV before the UPDATE; the TSVs were retained until the post-state was verified stable, then deleted on 2026-04-11. The merged enricher rules in PRs #1, #4, and #5 produce the same effect on any future re-enrichment, so the rollback files would be regeneratable from the merged code if ever needed.

| When | What | Rows | Origin |
|---|---|---:|---|
| 2026-04-11 12:26 | `organized_play` tag added on AL books missing it | 74 | Task 2 (one-off SQL backfill, see PR #1 for the durable rule) |
| 2026-04-11 13:11 | `--normalize-series` applied: structural cleanup, alias map, AL filename-code reassignment | 67 | PR #3 (`pdf_enricher.py --normalize-series`) |
| 2026-04-11 13:46 | `game_system` flipped `D&D 5e → Pathfinder 1e` for misclassified PF conversions, system tags rewritten | 27 | PR #5 (`apply_pathfinder_conversion_rule`) |
