# rpg-lib — TODO / Bugs

_Last touched 2026-04-12. Fifteen PRs (#1–#15) merged; six live-DB backfills applied._

## Open

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

### Follow-up: extract shared `<DimensionGrid>` component
PRs #7 and #8 both render a "list of `{value, count}` rows as clickable tiles" grid — `BrowseIndex.vue` for the standalone directory pages and `LibraryBrowse.vue` for the in-search facet view. The markup and styles are duplicated across the two files. A small extract-component PR could pull the grid into `components/DimensionGrid.vue` and have both views use it. Cosmetic refactor, no behaviour change.

---

## Closed

### #15 ~~Frostmaiden series merge~~
**Fixed in kostadis/mytools#15 (merged).** One DMsGuild product (`product_id=193137`) was split across three series names due to inconsistent folder naming. Per-book inspection confirmed all three variants are the same product. Merged into `Icewind Dale: Rime of the Frostmaiden DM's Resource` (47 books). Six books from a separate product (`product_id=1399969`, Notice Board Seeds + Strange Encounters) were incorrectly grouped in the same series — their series field was cleared; collection-based deduplication handles them correctly.

### #14 ~~MCP server user_data.db not attached~~
**Fixed in kostadis/mytools#14 (merged).** `library_mcp.py` called `get_db(_db_path)` without `user_db_path`, crashing any query that JOINs `user_data.favorites`. Added `--user-db` CLI arg (defaults to `user_data.db` alongside `--db`); silently skipped if file doesn't exist.

### #13 ~~Campaign & location tags~~
**Shipped in kostadis/mytools#13 (merged).** 7 campaign tags (`curse_of_strahd`, `rime_of_the_frostmaiden`, `descent_into_avernus`, `waterdeep_adventures`, `out_of_the_abyss`, `tyranny_of_dragons`, `tomb_of_annihilation`) and 5 location tags (`ravenloft`, `icewind_dale`, `underdark`, `waterdeep`, `avernus`) added to `CANONICAL_TAGS`. `SERIES_IMPLIED_TAGS` extended with 12 regex patterns. `CAMPAIGN_IMPLIED_LOCATIONS` dict auto-adds the location tag when a campaign tag is applied. `--backfill-campaign-tags` CLI flag re-runs rules against all enriched books. Backfill applied: 281 books tagged. As a side effect, also tagged 35 DDAL-DRW/DDAL-EB books with `organized_play` (closing the PR #16 backfill item). 47 new tests in `test_campaign_tags.py`.

### #12 ~~NLQ test case-sensitivity~~
**Fixed in kostadis/mytools#12 (merged).** `test_wiki.TestParseQuery.test_extracts_all_fields` was asserting `"Adventure"` but `parse_query` correctly lowercases via `.lower()`. Fixed the expected value in the test to `"adventure"`.

### #10 ~~Related books navigation does nothing~~
**Fixed in kostadis/mytools#10 (merged).** Clicking a related book on the BookDetail page stayed on the same URL fragment — Vue Router reused the component instance without re-firing `onMounted`. Fixed by adding `watch(() => route.params.id, ...)` and extracting a reusable `loadBook(id)` function called by both `onMounted` and the watcher.

### #9 ~~Favorites (heart toggle)~~
**Shipped in kostadis/mytools#9 (merged).** Heart toggle on any book in table, card, or detail view. Persisted in a separate `user_data.db` attached to the read-only library connection via `ATTACH DATABASE`, so the library DB stays `?mode=ro`. LEFT JOIN on all summary-producing queries surfaces `is_favorite`. `POST /book/{id}/favorite` / `DELETE /book/{id}/favorite` endpoints. "Favorites only" checkbox in the sidebar composes with keyword search and all other filters.

### #1 ~~`library_mcp.search_books` crashes on any query containing `&`~~
**Fixed in kostadis/mytools#2 (merged).** The `&` was a red herring. Real cause: `_row_to_summary` reads `min_level`/`max_level` but six SELECTs in `library_api/db.py` didn't project those columns. `sqlite3.Row[missing]` raises `IndexError: No item with that key`, so any non-empty result through those paths crashed. Plain queries "worked" only because they returned 0 rows. Fixed all six SELECTs. Added `TestRowToSummaryContract` (11 tests) that exercises every `_row_to_summary` call site with non-empty results and asserts the full key set, so future column additions fail loudly.

### #2 ~~`find_books_by_tag` doesn't match AL content~~
**Fixed in two parts.**
- **Data backfill:** one-off `organized_play` backfill on 74 AL books. Canonical `organized_play` tag already existed in the vocabulary; it was just under-applied (21/95 → 95/95).
- **Enricher rule (kostadis/mytools#1 merged):** `SERIES_IMPLIED_TAGS` rule table + `apply_series_implied_tags` helper. Any future enrichment of an AL filename/collection automatically gets `organized_play` without relying on the LLM (which was tagging it on only ~22% of AL books).
- **Not adopted:** a new `adventurers_league` canonical tag. Would have broken the vocabulary's campaign-line-agnostic discipline.

### #3 ~~Series name fragmentation (`--normalize-series` pass)~~
**Shipped in kostadis/mytools#3 (merged) and applied to the live DB.** New `--normalize-series` CLI flag runs three passes: structural cleanup (whitespace, em/en dashes, trailing punctuation), `SERIES_ALIASES` one-hop lookup (8 entries for AL Season 1 / 3 / 5 cluster merges plus the Frostmaiden plural → singular), and AL filename-code reassignment (`DDEX{S}` / `DDAL{SS}` parsing for books in the unqualified AL bucket).

Live-DB run: 67 books updated (21 via filename code). AL cluster compressed from 10 → 7 series. Canonical form: `D&D Adventurers League - Season N (Campaign Name)`. Also corrected a wrong label in the existing data — 4 DDEX3 books were labelled `Season 3 (Elemental Evil)` but DDEX3 is actually Rage of Demons (Elemental Evil was Season 2 / DDEX2). 40 new tests across 6 classes.

### #4 ~~Pathfinder conversion twins~~
**Reframed and fixed in kostadis/mytools#5 (merged) plus a live-DB backfill.** The original TODO said twin pairs cluttered search results, but the existing `(publisher, normalized_collection)` variant dedup was already collapsing them — verified with `search('Thimblerigging', grouped=True)` returning 1 group with `variant_count=2`.

The actual bug was narrower: 27 PF conversions in the library were misclassified as `D&D 5e` (the LLM read the 5e base title). Fix: `apply_pathfinder_conversion_rule` post-LLM override in `validate_enrichment` — if filename matches `[-_]PF(?:\.pdf|_)` AND current `game_system` is in a D&D-family set, override to `Pathfinder 1e` and rewrite tags (`5e`/`5e_2024`/etc → `pf1e`).

Self-protection: gating on D&D-family system means non-D&D files with `_PF` in the name are left alone. Verified against 12 real false-positive risks: Dune (×5, `_pf_` is a version marker), Vampire: TM, John Carter, Historia (×2), Savage Worlds, plus some System Neutral / Universal — all untouched. Backfill applied: 27/27 books now `Pathfinder 1e`. 21 new tests.

### #5 ~~Prefix-match false positive on `Night's Dark Terror`~~
**Fixed in kostadis/mytools#4 (merged).** The TODO's original framing was slightly wrong: there was no existing prefix filter in the code. The false positive was introduced by the `\bDDEX` regex I wrote for PR #1, which matched `DDEXP_B10_NightsDarkTerror.pdf` (a scanner-added prefix on a 1986 Basic D&D module). Word boundary alone doesn't care what comes after the match.

Fix: `\bDDAL(?![A-Za-z])|\bDDEX(?![A-Za-z])` — negative lookahead rejects letter suffixes but still accepts digits (`DDAL05-08`), separators (`DDAL-DRW06`, `DDAL-EB-01`), and triple-segment codes (`DDAL050801`). Live DB impact was zero (book 13041 hadn't been tagged — task-2 backfill skipped it because its series column is `Basic D&D Expert Set`, and the task-6 enricher rule only fires on fresh enrichments, which happened before PR #1 merged).

### #6 ~~Indexer filename-level duplicates slipping past `is_duplicate=0`~~
**Fixed in kostadis/mytools#6 (merged) plus a live-DB backfill.** Found while surveying for PR #5: the same PDF dropped into multiple product folders (free-sample PDFs, publisher catalogues, "thank you" inserts) showed up as multiple rows with distinct filepaths but identical content. The pre-existing `_DUPLICATE_SUFFIX` regex only caught `book (1).pdf`-style filenames and missed this entire class. **5.8% of the live library was phantom-duplicate rows** — extreme example: `Castle_Oldskull_Treasury_2009_-_2024.pdf` appeared 41 times.

New `pdf_indexer.py --dedup-content` flag runs a pure SQL pass that flags duplicates by `(filename, page_count, pdf_title, pdf_author)`, keeping the MIN(id) row in each cluster. Idempotent, reversible (filepath data preserved on all rows), conservative key verified against real edge cases like `Trophy_Loom.pdf` with two distinct page counts (kept as separate revisions). 12 new tests in a new `test_indexer.py` file.

Backfill applied: **604 rows flagged** across 483 clusters. Live count went from 8113 → 7653.

### #7 ~~Browse-by-X directory views~~
**Shipped in kostadis/mytools#7 (merged).** New parameterized view `BrowseIndex.vue` at `/browse/:type` for `type ∈ {series, publisher, game_system, tag}` — a directory index into the four topic-hub dimensions. Each row links to the existing `TopicHub`. Live filter input, sort toggle (by count / by name), friendly error for unknown types, filter + sort auto-reset when navigating between types.

Reuses `store.loadFilters()` data already loaded on app mount; no new API endpoint or store action. Nav bar gained: `Search | Browse: Series | Publishers | Systems | Tags | Graph`. (The old "Browse" link at `/` was renamed "Search" to disambiguate.)

### #8 ~~LibraryBrowse "Group by" toggle with drill-in and filter chips~~
**Shipped in kostadis/mytools#8 (merged).** The search-context complement to #7: a "Group by: Books / Series / Publishers / Systems / Tags" toggle inside `LibraryBrowse` that re-aggregates the current search results by the chosen dimension. Answer to "which series contain horror books?" without leaving the search.

**Backend:** new `search_facets()` function (built on an extracted `_build_search_where()` helper shared with `search_books`, so the WHERE clauses stay in sync) + `FacetsResponse` model + `GET /api/library/search/facets` endpoint. 11 new `TestSearchFacets` cases.

**Frontend:** `groupBy` + `facets` state in the Pinia store, `fetchFacets` / `setGroupBy` / `drillInFacet` actions, a facet-grid conditional render inside LibraryBrowse, and — critically — an active-filter chip banner above the results. The chip banner makes the drill-in flow legible: after clicking Group by Publisher → Chaosium, chips show `[Search: horror ✕] [Publisher: Chaosium ✕]` and each can be removed individually. Plus `setGroupBy` auto-clears any existing filter on the target dimension so clicking "Group by: Publisher" after drilling in always shows the full publisher list for the remaining search context.

Browser-tested by the user across both drill-in escape paths — this is the reason the PR got bigger than initially planned.

---

## Live-DB data mutations applied this session

Four deterministic backfills were applied to `rpg_library.db` and verified before the corresponding PRs were merged. Each was snapshotted to a rollback TSV before the UPDATE; the TSVs were retained until the post-state was verified stable, then deleted. The merged enricher rules in PRs #1, #4, #5, and #6 produce the same effect on any future re-indexing / re-enrichment, so the rollback files would be regeneratable from the merged code if ever needed.

| When | What | Rows | Origin |
|---|---|---:|---|
| 2026-04-11 12:26 | `organized_play` tag added on AL books missing it | 74 | Task 2 (one-off SQL backfill, see PR #1 for the durable rule) |
| 2026-04-11 13:11 | `--normalize-series` applied: structural cleanup, alias map, AL filename-code reassignment | 67 | PR #3 (`pdf_enricher.py --normalize-series`) |
| 2026-04-11 13:46 | `game_system` flipped `D&D 5e → Pathfinder 1e` for misclassified PF conversions, system tags rewritten | 27 | PR #5 (`apply_pathfinder_conversion_rule`) |
| 2026-04-11 14:32 | Phantom duplicates flagged `is_duplicate=1` by content fingerprint | 604 | PR #6 (`pdf_indexer.py --dedup-content`) |

**Total row updates across all backfills:** 772.
