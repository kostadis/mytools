# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Converts tabletop RPG PDFs (primarily D&D/AD&D sourcebooks and modules) into [5etools](https://5e.tools) homebrew JSON format. A single unified converter (`pdf_to_5etools_v2.py`) handles all PDF types — digital, scanned, OCR'd 1e/2e modules — by routing bookmarked digital PDFs to a fast PyMuPDF path and everything else to [Marker](https://github.com/VikParuchuri/marker) for ML-based layout and heading extraction. Wrapped by a Flask web UI.

Prior-generation v1 heuristic converters (six scripts) are preserved at tag `v1.0`. See the "v1 / v2 history" section below.

## Running tests

```bash
pytest test_adventure_model.py -v       # adventure data model tests
pytest test_adventure_editor.py -v      # adventure editor tests
pytest test_validate_adventure.py -v    # JSON structure validator (includes all official adventures)
```

Tests mock all external dependencies (PyMuPDF, Anthropic API) — no API key or system packages required.

To run a single test:
```bash
pytest test_adventure_model.py -v -k "test_function_name"
pytest test_adventure_editor.py -v -k "test_function_name"
pytest test_validate_adventure.py -v -k "test_function_name"
```

## Running the web UI

```bash
python3 app.py          # serves at http://localhost:5100
PORT=8080 python3 app.py
```

## Running the converter directly

```bash
python3 pdf_to_5etools_v2.py input.pdf [options]
```

Requires `ANTHROPIC_API_KEY` env var or `--api-key KEY`. Default model: `claude-haiku-4-5-20251001`. Marker pipeline also requires the `marker-env/` virtualenv (see setup below).

**Routing:** `profile_pdf()` inspects the PDF at startup:
- Has bookmarks AND selectable text → **PyMuPDF fast path**. Chunks by bookmark tree. ~100× faster than Marker.
- Anything else (scans, un-bookmarked digital) → **Marker path**. Runs Marker to produce markdown with `#`/`##`/`###` headings; synthesises a `TocNode` tree from those headings (with the keyed-room heuristic flattening numbered rooms to a common level); chunks the same way as the fast path.
- `--force-marker` bypasses the fast path and always uses Marker. Useful when the PDF has bookmarks but the text layer is unreliable (OCR'd-to-PDF scans, broken embedded fonts).

**Common flags:** `--dry-run` (estimate cost, no API calls), `--batch` (50% cheaper via Batch API, async), `--output-mode server` (two-file permanent install), `--extract-monsters`/`--monsters-only` (bestiary extraction, see below), `--debug-dir DIR` (save raw chunk I/O), `--verbose`. See `cli_args.py` for the full shared argument set.

**Bestiary extraction:**
- `--extract-monsters`: after the adventure conversion, run a second Claude pass that pulls stat blocks out of the generated JSON. Writes `<stem>-bestiary.json` next to the adventure file with source ID `{SOURCE}b` (separate so both homebrews can be loaded together without conflicting). Detects both italic-string stat lines (the v2 prompt's default format: `{@i Name: AC X, MV Y, ...}`) and legacy table stat blocks. Inherits `--model` and `--batch` from the main pass.
- `--monsters-only`: bypass the adventure pipeline entirely. Always runs Marker on the full PDF, splits the markdown on `##` headings, keeps sections whose first ~8 body lines mention "Armor Class" / "AC N", and sends those to Claude. Produces only the bestiary file. Cheapest path if all you need is the stat blocks (~2–3× fewer tokens than a full conversion).

**Marker setup (one-time):**
```bash
python3 -m venv marker-env
source marker-env/bin/activate
pip install marker-pdf pymupdf
# First run downloads ~5 GB of model weights from HuggingFace.
```

A CUDA GPU is strongly recommended (4080 or similar: ~5 s/page; CPU: 10–30 s/page). The venv is gitignored.

## Architecture

### Shared CLI layer — `cli_args.py`

`pdf_to_5etools_v2.py` imports from `cli_args.py` for its argparse setup:
- `add_common_args(parser, *, default_chunk, default_model)` — adds every shared argument (`--type`, `--output-mode`, `--id`, `--author`, `--out`, `--output-dir`, `--api-key`, `--pages-per-chunk`, `--model`, `--batch`, `--extract-monsters`, `--monsters-only`, `--debug-dir`, `--dry-run`, `--verbose`, `--no-toc-hint`, `--pages`, `--page`). Note `--id` uses `dest="short_id"`; `--batch` uses `dest="use_batch"`.
- `add_ocr_args(parser, *, default_dpi)` — legacy helper retained for `cli_args`-style extension by downstream tools; not currently used by v2 (Marker handles OCR internally, no DPI/language knobs).

v2 adds one unique arg: `--force-marker` (bypass fast path).

**When adding or changing any shared CLI argument, edit `cli_args.py` only.**

### Shared API layer — `claude_api.py`

All converters delegate Claude API calls to `claude_api.py`, which owns:
- `MAX_OUTPUT_TOKENS = 20_000` — single place to change the output token budget
- `MAX_VALIDATION_RETRIES = 1` — how many times to retry when validation finds structural errors in parsed output
- `COMMON_TAG_RULES` — shared prompt fragment listing all valid `{@tag}` references; injected into every converter's `SYSTEM_PROMPT` via f-string. Update here when the set of supported 5etools inline tags changes.
- `COMMON_NESTING_RULES` — shared prompt fragment governing section/entries nesting and `headers[]` content. Rules enforced: (1) `{"type":"section"}` for top-level chapters/locations only; (2) sub-rooms (A1, C3, E7…) go as `{"header": "name", "depth": 1}` objects in `headers[]`, not flat strings; (3) do not repeat the section's own name as a header entry; (4) do not include "Creatures", "Treasure", "Development", stat-block names, or encounter-group names in `headers[]`.
- `validate_entries(entries, chunk_id)` — validates parsed JSON entries through the `adventure_model` data model; returns list of error messages (empty = valid)
- `_parse_claude_response` — strips markdown fences, parses JSON, returns `(list, bool)`
- `_recover_partial_json` — salvages complete entries from truncated/malformed responses
- `call_claude(client, chunk_text, model, system_prompt, verbose, debug_dir, chunk_id)` — full retry logic: tail retry on `max_tokens` with partial output, split retry on `max_tokens` or `end_turn` with malformed JSON. After parsing, runs `validate_entries` and retries with a correction prompt if structural errors are found (unknown tags, missing fields, etc.). Controlled by `MAX_VALIDATION_RETRIES`.
- `call_claude_batch(client, chunks, model, system_prompt, verbose, debug_dir)` — submits all chunks as a single Batch API request (50% cheaper, async); polls every 15 s until complete; returns results in chunk order. Validates all results post-batch and reports errors (no automatic retry in batch mode — re-run without `--batch` to enable retry).
- `dry_run(client, chunk_texts, chunks, model, system_prompt, use_batch, verbose)` — calls `count_tokens` for every non-empty chunk and prints a cost estimate; no inference
- `_model_tier(model)` / `_PRICE` — maps model name to haiku/sonnet/opus tier and pricing for cost estimates

Each converter's `call_claude` is a thin wrapper that passes its own `SYSTEM_PROMPT` and handles any converter-specific preprocessing (1e: `_CHUNK_PREFIX + _neutralize_triggers + _sanitize_text`) or error handling (1e: `BadRequestError` → `None`). Future fixes to retry/parse/prompt logic go in `claude_api.py` only.

`claude_api` is imported at module top-level (before `SYSTEM_PROMPT` is defined) so that `_api.COMMON_TAG_RULES` is available when the f-string prompt is constructed.

### PDF bookmark / TOC extraction — `pdf_utils.py`

`pdf_utils.py` is a shared library (depends on PyMuPDF, kept separate from `claude_api.py` which has no PDF dependency) that owns:
- `extract_pdf_toc(pdf_path, max_level=3) -> str | None` — reads the PDF's built-in bookmark outline via `doc.get_toc()` and returns a formatted text block (or `None` if the PDF has no bookmarks). Prepended to every Claude chunk so Claude sees authoritative section names and page numbers. Disable with `--no-toc-hint`.
- `_decode_pdf_string(text)` — fixes Windows-1252/Mac-Roman characters (smart quotes `\x90`→`'`, curly brackets `\x8d`/`\x8e`→`'`/`'`) that PyMuPDF passes through as raw bytes.
- `TocNode` — dataclass representing a node in the PDF bookmark tree with computed page ranges. Fields: `level`, `title`, `start_page`, `end_page`, `children`. Properties: `page_count`. Methods: `walk()` (pre-order traversal of self + all descendants).
- `parse_toc_tree(raw_toc, total_pages, max_level=99) -> list[TocNode]` — converts PyMuPDF `doc.get_toc(simple=True)` output into a tree of `TocNode` objects. Normalises levels (shallowest becomes 1), computes `end_page` for each node (runs until next sibling/uncle starts), and builds parent-child relationships via stack-based algorithm.
- `get_toc_tree(pdf_path, max_level=99) -> list[TocNode]` — convenience wrapper that opens the PDF, calls `get_toc()`, and delegates to `parse_toc_tree()`. Returns empty list if no bookmarks.

Bookmark levels: L1 = document title (skipped as min-level), L2 = top-level sections, L3 = subsections, L4+ (Treasure, XP Award…) excluded by default.

`pdf_to_5etools_v2.py` imports `TocNode`, `get_toc_tree`, `parse_toc_tree`, and `extract_pdf_toc` for both the fast and Marker paths.

### v2 converter pipeline — `pdf_to_5etools_v2.py`

Single unified pipeline, shape below:

1. **Profile** — `profile_pdf()` samples ~10 pages; decides `has_bookmarks + has_selectable_text` → fast path, else Marker.
2. **Extract structure** (fast path): `get_toc_tree()` reads PDF bookmarks into a `TocNode` tree. (Marker path): `run_marker()` invokes `marker_single` as a subprocess, producing markdown; `parse_markdown_headings()` extracts `#`/`##`/`###` headings with line-number offsets; `normalise_numbered_rooms()` flattens keyed-room patterns (e.g. "101. ARMORY") to a common level; `build_synthetic_toc()` reuses `parse_toc_tree` with line numbers standing in for page numbers.
3. **Chunk** — one chunk per top-level `TocNode`. Fast path extracts page text via PyMuPDF; Marker path takes the markdown slice between heading line numbers.
4. **Claude pass** — `build_prompt(node, body)` attaches sub-section hints from the TocNode children; `claude_api.call_claude` owns all retry/validation/recovery logic. Batch mode via `call_claude_batch`.
5. **Assemble** — `assemble_adventure()` wraps each chunk's `entries[]` in a `SectionEntry` and calls `HomebrewAdventure.build()`, which auto-assigns IDs and builds the TOC from the section tree.
6. **Write** — `.to_json()` on the built document.

**System prompt** (in `pdf_to_5etools_v2.SYSTEM_PROMPT`) is deliberately slim: markdown headings are declared authoritative, so Claude renders prose inside pre-built structure rather than inferring structure from font heuristics. `{_api.COMMON_TAG_RULES}` and `{_api.COMMON_NESTING_RULES}` are still injected.

### Typed data model — `adventure_model.py`

Dataclass-based model for constructing and validating 5etools adventure JSON. Used by the TOC-driven converters and by `claude_api.validate_entries()` for validation retry.

**Key classes:**
- `ValidationMode` (enum) — `WARN` (collect issues) or `STRICT` (raise immediately)
- `BuildContext` — threaded through all objects; manages validation mode, result collection, duplicate ID detection
- `EntryBase` — base for all entry types with `type`, `name`, `id`, `page`, context fields
- Entry types: `SectionEntry`, `EntriesEntry`, `InsetEntry`, `InsetReadaloudEntry`, `QuoteEntry`, `ListEntry`, `TableEntry`, `ImageEntry`, `ItemEntry`, `HrEntry`, `GenericEntry`, `TableGroupEntry`, `FlowchartEntry`, `FlowBlockEntry`, `StatblockEntry`, `SpellcastingEntry`
- `Meta`, `MetaSource` — document metadata with source validation
- `TocEntry`, `TocHeader` — table of contents with depth support
- `AdventureIndex`, `AdventureData` — index and data sections
- `HomebrewAdventure` — top-level homebrew document builder with `build()` convenience method (auto-assigns IDs, builds TOC)
- `OfficialAdventureData` — official adventure format

**Key functions:**
- `validate_tags(text, path, ctx)` — checks `{@tag}` references and brace balance
- `parse_entry(raw, ctx, path)` — deserialises raw JSON dict to typed entry object
- `parse_document(raw, ctx)` — detects format (official/homebrew) and parses full document

**Imports from sibling modules:** `validate_adventure.{VALID_ENTRY_TYPES, KNOWN_TAGS, TAG_RE}`.

**Tests:** `pytest test_adventure_model.py -v` (~90 tests covering entry construction, validation modes, serialization round-trips, document parsing, contents/data alignment, ID assignment, TOC building, and integration against official adventure files).

### Output modes

- **Homebrew** (default): single `.json` loadable via 5etools Manage Homebrew UI
- **Server**: two files (`adventure-SHORT.json` + `adventures-short.json`) for permanent self-hosted installs

### `toc_editor.py` — TOC editor UI

Flask app (port 5101) for reviewing and correcting the `contents[]` TOC in a generated adventure JSON. Three-level hierarchy:

- **Section rows** (level 1) — top-level `data[]` entries; ↑↓ moves the whole block, ↳ demotes to `entries` inside the section above (server-side, modifies `data[]`)
- **Header rows** (level 2, italic) — entries in `headers[]`; ↑↓ moves the header + its sub-headers as a unit within the section; ↳ demotes to sub-header under the previous header
- **Sub-header rows** (level 3, grey) — stored as `{"header": "name", "depth": 1}` in `headers[]`; ↑↓ moves within the parent header block

Highlights mismatches (yellow = name doesn't match `data[]` at same index, red = `data[]` entry is not a `section`). Multi-select checkboxes on section rows + "Demote selected" toolbar button for bulk demote. Save rewrites both `contents[]` and reorders `data[]` to match any section moves, then appends a `{before, after}` pair to `toc_corrections.jsonl`.

```bash
python3 toc_editor.py [file.json] [--port N]
```

### `toc_fixer.py` — heuristic TOC & nesting repair

Flask app (port 5102) for restructuring the `data[]` nesting AND rebuilding `contents[]` after conversion. LLMs often produce flat or incorrectly-nested trees; this tool uses the PDF's bookmark outline and pattern heuristics to assign correct levels, then lets the user manually adjust before saving.

```bash
python3 toc_fixer.py [file.json] [--pdf file.pdf] [--port N]
# http://localhost:5102
```

Three-panel UI: PDF TOC (authoritative) | Current JSON TOC | Proposed TOC (live preview). Flat heading table below with per-row level dropdowns.

**Heuristics (applied in sequence or independently):**
- **PDF Anchor** — PDF level-1 bookmarks → `proposed_level=1`; all other headings assigned to the enclosing `pdf_section` by sequential scan. Requires PDF file.
- **Keyed Room** — within each `pdf_section` group:
  - `A.`, `B.`, `A Name` (single letter, < 40 chars) → `letter_level` (anchor+1)
  - `A1.`, `A 1.`, `GT 1.` (letter+number) → `room_level` (anchor+2)
  - **Interrupted-series promotion**: if a heading at level < `room_level` appears between consecutive numbered members (e.g. between A4 and A5), all numbered members of that letter group are promoted to `letter_level`
  - **Deduplication**: for headings sharing the same keyed-room pattern (e.g. bare `"A15"` and `"A15. Microbiology Lab"`), only the longest name is kept; the shorter wrapper node is silently absorbed during rebuild

**Rebuild algorithm** (`rebuild_tree`): stack-based (Markdown-heading style). Each heading is placed under the nearest ancestor at a lower level; non-heading leaf content is preserved at its original node. Top-level wrapper items (parent of a kept sub-heading) are skipped rather than folded. `fix_adventure_json.assign_ids` + `build_toc` are called after rebuild to produce clean IDs and `contents[]`.

Save writes a `.bak` backup then overwrites the JSON.

**Imports from sibling modules:** `fix_adventure_json.{assign_ids, reset_ids, build_toc}`, `toc_editor.list_json_files`, `pdf_utils._decode_pdf_string`.

### `fix_adventure_json.py` — chapter-index normalizer

Post-processes a converter-generated adventure JSON to fix chapter-index mismatches. Non-section top-level entries in `data[]` cause `contents[i]` and `data[i]` to diverge, breaking sidebar navigation. Also used as a library by `toc_fixer.py`.

```bash
python3 fix_adventure_json.py input.json [output.json]
```

Exports: `normalize_chapters()`, `reset_ids()`, `assign_ids()`, `build_toc()`. Overwrites in place with `.bak` backup if no output path given.

### `patch_5e_chapters.py` — re-convert specific chapters

Re-converts specific chapters from a 1e source JSON into an existing 5e adventure JSON, fixing structural issues without re-doing the whole document. Restores chapter structure from the 1e source, then re-runs the 5e conversion on individual room entries.

```bash
python3 patch_5e_chapters.py source_1e.json target_5e.json --chapters 16,19-20 [--model MODEL]
```

### `merge_patch.py` — patch incomplete conversions

Re-runs the converter on specific pages and merges the result into an existing adventure JSON without re-doing the whole document.

```bash
python3 merge_patch.py adventure.json --list                    # show sections with indices
python3 merge_patch.py adventure.json patch.json --at N [--dry-run]
```

Creates a `.bak` backup, re-sequences IDs after merge, and reports TOC/data alignment mismatches.

### `app.py` — Flask web UI

Single-file Flask app with inline HTML/CSS/JS (Bootstrap 5.3.3). Jobs tracked by UUID with thread-safe logging; progress streamed to browser via Server-Sent Events (SSE). Converters run as subprocesses.

### `convert_1e_to_5e.py`

Post-processing tool that takes a 1e-converter-generated adventure JSON and rewrites the mechanics for 5e while preserving all flavour text. Per-room: removes 1e stat lines, adds `{@creature}` tags, appends a "5e Encounter" inset with XP budget and difficulty rating, updates trap saves to 5e DCs, and adjusts encounter sizes. Usage:

```bash
python3 convert_1e_to_5e.py input.json output.json [--chapters A-B] [--dry-run] [--model MODEL]
```

Default model is `claude-sonnet-4-6`. Contains hardcoded T1-4 zone/level mappings — adapt `ZONES` dict for other modules.

### `validate_tags.py` — post-conversion tag checker

Scans a generated adventure JSON for unknown `{@tag}` references. Unknown tags throw a JS error in the 5etools renderer, causing blank pages. Exits non-zero if any are found.

```bash
python3 validate_tags.py adventure.json           # report unknown tags
python3 validate_tags.py adventure.json --fix     # replace in-place with plain text
```

The known-tag list is derived from `render.js` case statements. Common bad tags produced by Claude: `{@scroll X}` → `{@item scroll of X}`, `{@npc X}` → plain text or `{@creature X}`.

### `extract_monsters.py` — CLI monster extractor

Scans a parsed adventure JSON for embedded stat block tables (entries containing "Armor Class" rows) and sends them to Claude for conversion into 5etools bestiary JSON format. Can be used standalone or as a library (exports `_has_ac_table`, `statblock_to_text`, `SYSTEM_PROMPT`).

```bash
python3 extract_monsters.py adventure.json                    # extract all stat blocks
python3 extract_monsters.py adventure.json --dry-run          # list found blocks, no API calls
python3 extract_monsters.py adventure.json --model claude-sonnet-4-6 --out bestiary.json
```

Detects two table formats: key-value rows (`["Armor Class", "14"]`) and multi-column (`colLabels: ["Armor Class", "Hit Points", "Speed"]`). Inherits names from parent entries for unnamed stat blocks.

### `monster_editor.py` — monster extraction UI

Flask app (port 5103) for interactive stat block discovery and extraction from a parsed adventure JSON. Imports discovery logic from `extract_monsters.py` and API calls from `claude_api.py`.

```bash
python3 monster_editor.py [file.json] [--port N]
# http://localhost:5103
```

**Features:**
- Discovers all stat blocks in the adventure JSON with location metadata (data[] index, parent section, AC/HP/CR summary)
- Each monster row has a **View** link to the 5etools adventure page (`#SOURCE,N,slug`)
- Editable names, include/exclude checkboxes, expandable raw JSON preview
- **Extract Selected** sends checked stat blocks to Claude in batches of 5
- **Merge into existing file** checkbox: appends new monsters to an existing bestiary, replacing same-named entries (for incremental fixes)
- Progress bar with polling during extraction, download link on completion

**Source ID handling:** The bestiary file gets its own source ID (`{adventure_source}b`, e.g. `TOWORLDSb`) in `_meta.sources` so it doesn't conflict with the adventure file when both are loaded in 5etools. Individual monsters keep `"source": "{adventure_source}"` so `{@creature}` tags in the adventure link correctly.

**Imports from sibling modules:** `extract_monsters.{_has_ac_table, statblock_to_text, SYSTEM_PROMPT}`, `claude_api.call_claude`, `toc_editor.list_json_files`.

### `adventure_editor.py` — visual block editor

Flask app (port 5104) for editing 5etools adventure/book JSON as a block tree with live preview. Two-panel layout: collapsible block tree (left) + CSS-approximated 5etools preview (right).

```bash
python3 adventure_editor.py [file.json] [--port N]
# http://localhost:5104
# or: ./start_editor.sh [file.json]
```

**Block types supported:** section, entries, inset, insetReadaloud, list, table, image, quote, hr.

**Features:**
- Collapsible block tree with row numbers, color-coded type badges; collapse/expand all, expand to level 1-3
- Click a node to edit inline (buffered edit with Done/Cancel — no live re-rendering while typing)
- Block operations: move up/down, promote (outdent)/demote (indent) nesting, add sibling/child, dissolve (remove block, keep children), delete
- Multi-select: Ctrl+click to toggle, Shift+click for range select; bulk move up/down, promote, demote, dissolve, delete, flag
- Add block modal with type picker; smart paste for tables (tab/pipe/colon-separated) and stat blocks (auto-parses AC/HP/CR/abilities/traits)
- Tag toolbar for inserting `{@spell}`, `{@creature}`, `{@dc}`, `{@damage}`, etc. into textareas
- "Join lines" button on text/quote editors for fixing PDF copy-paste line breaks (handles hyphenated words, preserves paragraph breaks)
- Preview panel auto-scrolls to selected block with blue highlight
- Persistent undo/redo log saved to `{filename}.undolog.json`; History dropdown to jump to any state; Ctrl+Z / Ctrl+Shift+Z keyboard shortcuts
- Flag system: `_flags` metadata on entries (1e-stat, review, todo) with colored dots in tree, prev/next navigation, bulk flag/clear
- Save rebuilds IDs and TOC via `fix_adventure_json`, auto-promotes non-section top-level entries to prevent TOC misalignment, creates `.bak` backup

**Imports from sibling modules:** `toc_editor.list_json_files`, `fix_adventure_json.{assign_ids, reset_ids, build_toc}`.

**Tests:** `pytest test_adventure_editor.py -v` (81 tests covering load, save, undo, move, promote, demote, dissolve, bulk operations, flags, join lines, no-pk-in-onclick regression).

### `validate_adventure.py` — adventure JSON structural validator

Validates 5etools adventure JSON structure against patterns from the 98 official adventure data files. Works as both a CLI tool and importable library.

```bash
python3 validate_adventure.py adventure.json                              # validate one file
python3 validate_adventure.py *.json                                      # validate multiple
python3 validate_adventure.py --official-dir ../data/adventure/           # validate official files
```

**Checks:** top-level structure (official vs homebrew format), `_meta` sources, contents/data alignment (count, names, all-sections), 25 valid entry types, 80+ valid `{@tag}` names (errors on unknown tags which cause blank pages), unbalanced braces, table/list/image structure, ID uniqueness. Errors = must fix, warnings = should review.

**As a library:** `from validate_adventure import validate; result = validate(json_data)` returns a `ValidationResult` with `.errors`, `.warnings`, `.ok`.

**Tests:** `pytest test_validate_adventure.py -v` (44 tests including integration against all 98 official adventure files).

## Key 1e stat conversion formulas

Used by `convert_1e_to_5e.py` (post-conversion mechanical rewrite). v2 keeps stat lines verbatim as italic strings; mechanical conversion is a separate pass.

```
5e AC = 19 − 1e_AC          (descending → ascending)
attack bonus = 20 − THAC0
speed (ft) = MV_inches × 5
CR = table lookup from HD (see hd_to_cr() in convert_1e_to_5e.py)
```

## v1 / v2 history

Tag `v1.0` (on `kostadis-dev`) preserves the heuristic-era converters:
- `pdf_to_5etools.py`, `pdf_to_5etools_ocr.py`, `pdf_to_5etools_1e.py` — page-count chunking with `[H1]`/`[H2]`/`[ROOM-KEY-N]` annotations
- `pdf_to_5etools_toc.py`, `pdf_to_5etools_ocr_toc.py`, `pdf_to_5etools_1e_toc.py` — bookmark-driven chunking with the same annotation front-end
- `fix_t14_1e.py`, `fix_t14_split.py` — T1-4-specific post-conversion repair scripts
- `find_triggers.py`, `triggers.json` — content-filter trigger-substitution infrastructure used by the 1e path

v2 eliminates most of that by moving structure extraction out of Claude's prompt. The heuristic annotations, the repair scripts, and the trigger substitutions exist in v1 only because Claude was making scope decisions it shouldn't — Marker extracts structure deterministically before Claude runs, so none are needed in v2.

To resurrect any v1 file: `git checkout v1.0 -- pdf-translators/<filename>`.

## Important notes

- **Default model recommendation** — the spike comparing Haiku vs Sonnet on Marker-processed 1e content showed Haiku handles the rendering job correctly and is ~4× cheaper. v2 defaults to Haiku; override with `--model claude-sonnet-4-6` only if specific content needs it. This is a reversal of the v1-era rule ("use Sonnet for 1e for reliability"), driven entirely by Marker shouldering the structure work.
- **Content-filter rejections** — Marker output strips the dense bold-all-caps formatting that triggered filters on raw 1e text. Fewer rejections in practice; no trigger-substitution infrastructure needed.
- `--debug-dir DIR` saves raw chunk I/O for debugging failed conversions.
- **5etools TOC/data alignment**: `adventure[0].contents[n]` maps to `adventureData[0].data[n]` by direct array index. Every top-level `data[]` entry must be `type: "section"`. `HomebrewAdventure.build()` enforces this automatically via `assign_ids()` + `build_toc()`.
- **Structure validation** — run `python3 validate_adventure.py adventure.json` after conversion or editing to catch structural issues (TOC misalignment, unknown tags, missing fields). Validated against all 98 official adventure files.
- **Validation retry** — `call_claude` automatically validates parsed output through `adventure_model` and retries with a correction prompt if structural errors are found (unknown tags, missing fields, etc.). Controlled by `MAX_VALIDATION_RETRIES` in `claude_api.py`. Batch mode reports errors but does not auto-retry.
- **Retry logic lives in `claude_api.py`** — do not duplicate it in the converter.
- **Shared prompt fragments live in `claude_api.py`** (`COMMON_TAG_RULES`, `COMMON_NESTING_RULES`) — do not duplicate tag or nesting rules in the converter.
- **TOC / structured TOC live in `pdf_utils.py`** (`extract_pdf_toc`, `TocNode`, `parse_toc_tree`, `get_toc_tree`, `_decode_pdf_string`).
- **Adventure data model lives in `adventure_model.py`** — typed dataclass model for constructing and validating entries. Used by v2 for assembly and by `claude_api.validate_entries()` for validation retry. Tag/entry-type constants come from `validate_adventure.py`.
- **`{@tag}` validation** — run `python3 validate_tags.py adventure.json` after conversion to catch unknown tags (which cause blank pages in 5etools). Use `--fix` to replace them with plain text in-place.
- **5etools source ID conflicts** — adventure and bestiary files must use different `_meta.sources[].json` IDs or 5etools treats them as the same homebrew. The monster_editor uses `{source}b` (e.g. `TOWORLDSb`) for bestiary files while keeping individual monsters' `"source"` field pointing to the adventure source so `{@creature}` tags link correctly.
- **5etools NPC filter** — named NPCs with `isNpc: true` are hidden by default in the bestiary; toggle the "Adventure NPC" filter button to see them.

## UI preferences

- **No confirmation dialogs for undoable actions.** If an operation can be undone (delete, move, dissolve, etc.), do not show `confirm()` or `prompt()` dialogs. Instead, provide separate buttons for each action and rely on undo. Confirmation dialogs break flow and are unnecessary when undo exists.
- **Never put `pk` (JSON path keys) in HTML strings or `onclick` attributes.** Path keys like `[0,"entries",2]` contain double quotes that break HTML attribute parsing. Always use `addEventListener` with closures instead. Use CSS class names (`.btn-done`, `.btn-cancel`, `.btn-add-child`) on the HTML elements, then attach handlers after setting `innerHTML`. See `buildTreeNode` and `buildEditForm` in `adventure_editor.py` for the pattern.

## Refactoring rule

When you find logic (parsing, prompt fragments, retry handling, tag rules, etc.) that could live in a shared module (`claude_api.py`, `pdf_utils.py`, `adventure_model.py`) instead of in `pdf_to_5etools_v2.py`, **ask the user whether to hoist it before proceeding**. The goal is that any fix or enhancement to shared behaviour is made in exactly one place.
