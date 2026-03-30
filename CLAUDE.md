# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Converts tabletop RPG PDFs (primarily D&D/AD&D sourcebooks and modules) into [5etools](https://5e.tools) homebrew JSON format. Three specialized converters handle different PDF types, wrapped by a Flask web UI.

## Running tests

```bash
pytest test_pdf_to_5etools.py -v        # converter tests
pytest test_adventure_editor.py -v      # adventure editor tests (81 tests)
pytest test_validate_adventure.py -v    # JSON structure validator (44 tests, includes all official adventures)
```

Tests mock all external dependencies (PyMuPDF, Anthropic API, Tesseract, PIL, pdf2image) — no API key or system packages required.

To run a single test:
```bash
pytest test_pdf_to_5etools.py -v -k "test_function_name"
pytest test_adventure_editor.py -v -k "test_function_name"
pytest test_validate_adventure.py -v -k "test_function_name"
```

## Running the web UI

```bash
python3 app.py          # serves at http://localhost:5100
PORT=8080 python3 app.py
```

## Running converters directly

```bash
python3 pdf_to_5etools.py input.pdf [options]
python3 pdf_to_5etools_ocr.py input.pdf [options]
python3 pdf_to_5etools_1e.py input.pdf [options]
```

Requires `ANTHROPIC_API_KEY` env var or `--api-key KEY`. Default model: `claude-haiku-4-5-20251001` (all three converters). Use `--dry-run` to estimate token cost without making API calls. Use `--batch` (all three scripts) for the Batch API — 50% cheaper but async. Use `--output-mode server` for two-file permanent installs; `--extract-monsters`/`--monsters-only` for stat block extraction. All scripts share a common argument set (see `cli_args.py`). OCR script adds `--dpi N`, `--force-ocr`, `--lang LANG`. 1e script adds `--module-code CODE`, `--system 1e|2e`, `--skip-pages RANGE`, `--no-cr-adjustment`. All scripts support `--no-toc-hint` to skip injecting the PDF bookmark outline into Claude prompts.

## Architecture

### Shared CLI layer — `cli_args.py`

All three converters import from `cli_args.py` for their argparse setup:
- `add_common_args(parser, *, default_chunk, default_model)` — adds every argument shared by all three converters (`--type`, `--output-mode`, `--id`, `--author`, `--out`, `--output-dir`, `--api-key`, `--pages-per-chunk`, `--model`, `--batch`, `--extract-monsters`, `--monsters-only`, `--debug-dir`, `--dry-run`, `--verbose`, `--no-toc-hint`, `--pages`, `--page`). Note `--id` always uses `dest="short_id"`; `--batch` always uses `dest="use_batch"`.
- `add_ocr_args(parser, *, default_dpi)` — adds `--dpi`, `--force-ocr`, `--lang` (shared by OCR and 1e converters only).

Each converter calls the relevant helpers then adds its own unique args:
- **`pdf_to_5etools.py`**: `add_common_args` (no unique args)
- **`pdf_to_5etools_ocr.py`**: `add_common_args` + `add_ocr_args` (no unique args)
- **`pdf_to_5etools_1e.py`**: `add_common_args` + `add_ocr_args` + `--module-code`, `--system`, `--skip-pages`, `--no-cr-adjustment`, `--no-retry`, `--trigger-config`

**When adding or changing any shared CLI argument, edit `cli_args.py` only** — changes propagate to all three converters automatically.

### Shared API layer — `claude_api.py`

All three converters delegate Claude API calls to `claude_api.py`, which owns:
- `MAX_OUTPUT_TOKENS = 20_000` — single place to change the output token budget
- `COMMON_TAG_RULES` — shared prompt fragment listing all valid `{@tag}` references; injected into every converter's `SYSTEM_PROMPT` via f-string. Update here when the set of supported 5etools inline tags changes.
- `COMMON_NESTING_RULES` — shared prompt fragment governing section/entries nesting and `headers[]` content. Rules enforced: (1) `{"type":"section"}` for top-level chapters/locations only; (2) sub-rooms (A1, C3, E7…) go as `{"header": "name", "depth": 1}` objects in `headers[]`, not flat strings; (3) do not repeat the section's own name as a header entry; (4) do not include "Creatures", "Treasure", "Development", stat-block names, or encounter-group names in `headers[]`.
- `_parse_claude_response` — strips markdown fences, parses JSON, returns `(list, bool)`
- `_recover_partial_json` — salvages complete entries from truncated/malformed responses
- `call_claude(client, chunk_text, model, system_prompt, verbose, debug_dir, chunk_id)` — full retry logic: tail retry on `max_tokens` with partial output, split retry on `max_tokens` or `end_turn` with malformed JSON
- `call_claude_batch(client, chunks, model, system_prompt, verbose, debug_dir)` — submits all chunks as a single Batch API request (50% cheaper, async); polls every 15 s until complete; returns results in chunk order
- `dry_run(client, chunk_texts, chunks, model, system_prompt, use_batch, verbose)` — calls `count_tokens` for every non-empty chunk and prints a cost estimate; no inference
- `_model_tier(model)` / `_PRICE` — maps model name to haiku/sonnet/opus tier and pricing for cost estimates

Each converter's `call_claude` is a thin wrapper that passes its own `SYSTEM_PROMPT` and handles any converter-specific preprocessing (1e: `_CHUNK_PREFIX + _neutralize_triggers + _sanitize_text`) or error handling (1e: `BadRequestError` → `None`). Future fixes to retry/parse/prompt logic go in `claude_api.py` only.

`claude_api` is imported at module top-level (before `SYSTEM_PROMPT` is defined) so that `_api.COMMON_TAG_RULES` is available when the f-string prompt is constructed.

### PDF bookmark / TOC extraction — `pdf_utils.py`

`pdf_utils.py` is a shared library (depends on PyMuPDF, kept separate from `claude_api.py` which has no PDF dependency) that owns:
- `extract_pdf_toc(pdf_path, max_level=3) -> str | None` — reads the PDF's built-in bookmark outline via `doc.get_toc()` and returns a formatted text block (or `None` if the PDF has no bookmarks). Prepended to every Claude chunk so Claude sees authoritative section names and page numbers. Disable with `--no-toc-hint`.
- `_decode_pdf_string(text)` — fixes Windows-1252/Mac-Roman characters (smart quotes `\x90`→`'`, curly brackets `\x8d`/`\x8e`→`'`/`'`) that PyMuPDF passes through as raw bytes.

Bookmark levels: L1 = document title (skipped as min-level), L2 = top-level sections, L3 = subsections, L4+ (Treasure, XP Award…) excluded by default.

All three converters import `extract_pdf_toc` from `pdf_utils` (lazy import inside `convert()`). `pdf_to_5etools.py` also re-exports it for backwards compatibility.

### Converter pipeline (all three scripts share this structure)

1. **Text extraction** — PyMuPDF (`fitz`) extracts text with font-size/bold/italic metadata; OCR scripts additionally use Tesseract for image-heavy pages
2. **Running-header detection** — recurring page headers/footers identified by stream position (first/last block) and bottom-band position across ≥3 pages; completely excluded from annotated text so Claude never sees them
3. **Annotation** — heuristics tag headings (`[H1]`/`[H2]`/`[H3]`), italic/bold spans, tables, and boxed text
4. **Chunking** — pages grouped into chunks (default: 6 for standard, 4 for OCR, 3 for 1e) and sent to Claude API; `MAX_CHUNK_CHARS = 80_000` prevents silent truncation
5. **TOC hint injection** — if the PDF has bookmarks, `extract_pdf_toc` output is prepended to each chunk so Claude uses exact bookmark names for section headings
6. **Claude pass** — structured prompt returns JSON array of 5etools entry objects; retried automatically on truncation or malformed output
7. **Post-processing** — chunks merged; stray non-`section` top-level entries hoisted into the preceding section; sequential IDs assigned; TOC synthesised; final JSON written

### The three converters

- **`pdf_to_5etools.py`** — digitally-typeset PDFs with selectable text
- **`pdf_to_5etools_ocr.py`** — extends standard with Tesseract OCR fallback (<50 chars/page threshold), two-column layout detection, heading inference from character height
- **`pdf_to_5etools_1e.py`** — 1e/2e AD&D modules; adds keyed-room detection, inline stat block parsing, automatic stat conversion (descending AC → ascending, THAC0 → attack bonus, MV inches → feet, HD → CR), and content filter substitutions via `triggers.json`

All three support `--batch` (Batch API, 50% cheaper, async).

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

### Module-specific fix scripts

One-shot scripts for fixing structural issues in specific module conversions. Not general-purpose — kept for reference and re-use on similar modules:

- **`fix_t14_1e.py`** — fixes Temple of Elemental Evil (T1-4) conversion: dissolves "Room Key" wrappers, promotes dungeon rooms, folds orphaned entries into preceding rooms, rebuilds TOC
- **`fix_t14_split.py`** — splits a merged T1-4 chapter (Levels Three + Zuggtmoy + Greater Temple) into three proper chapters

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

### `find_triggers.py`

Standalone helper for identifying content-filter trigger phrases in rejected chunks. Reads debug input files or stdin, outputs a `triggers.json` for use with `--trigger-config`.

### `triggers.json`

Regex-based substitution rules applied during 1e conversion to neutralize content filter triggers before sending to Claude. Extended via `find_triggers.py` when new triggers are discovered.

## Key 1e stat conversion formulas

```
5e AC = 19 − 1e_AC          (descending → ascending)
attack bonus = 20 − THAC0
speed (ft) = MV_inches × 5
CR = table lookup from HD (see hd_to_cr() in pdf_to_5etools_1e.py)
```

## Important notes

- Classic AD&D modules (T1-4, GDQ series, etc.) often trigger content filters in smaller models. Use `--model claude-sonnet-4-6` for reliable conversion.
- The 1e converter stores the original stat line in `_1e_original` for manual review.
- `--debug-dir DIR` saves raw chunk I/O for debugging failed conversions.
- **5etools TOC/data alignment**: `adventure[0].contents[n]` maps to `adventureData[0].data[n]` by direct array index. Every top-level `data[]` entry must be `type: "section"` — non-section entries shift all subsequent chapter navigation by 1. The post-processing hoist step and adventure_editor save guard enforce this automatically.
- **Structure validation** — run `python3 validate_adventure.py adventure.json` after conversion or editing to catch structural issues (TOC misalignment, unknown tags, missing fields). Validated against all 98 official adventure files.
- **Retry logic lives in `claude_api.py`** — do not duplicate it in the individual converters.
- **Shared prompt fragments live in `claude_api.py`** (`COMMON_TAG_RULES`, `COMMON_NESTING_RULES`) — do not duplicate tag or nesting rules in individual converters.
- **TOC hint lives in `pdf_utils.py`** (`extract_pdf_toc`, `_decode_pdf_string`) — all converters import from there, not from each other.
- **`{@tag}` validation** — run `python3 validate_tags.py adventure.json` after conversion to catch unknown tags (which cause blank pages in 5etools). Use `--fix` to replace them with plain text in-place.
- **5etools source ID conflicts** — adventure and bestiary files must use different `_meta.sources[].json` IDs or 5etools treats them as the same homebrew. The monster_editor uses `{source}b` (e.g. `TOWORLDSb`) for bestiary files while keeping individual monsters' `"source"` field pointing to the adventure source so `{@creature}` tags link correctly.
- **5etools NPC filter** — named NPCs with `isNpc: true` are hidden by default in the bestiary; toggle the "Adventure NPC" filter button to see them.

## UI preferences

- **No confirmation dialogs for undoable actions.** If an operation can be undone (delete, move, dissolve, etc.), do not show `confirm()` or `prompt()` dialogs. Instead, provide separate buttons for each action and rely on undo. Confirmation dialogs break flow and are unnecessary when undo exists.
- **Never put `pk` (JSON path keys) in HTML strings or `onclick` attributes.** Path keys like `[0,"entries",2]` contain double quotes that break HTML attribute parsing. Always use `addEventListener` with closures instead. Use CSS class names (`.btn-done`, `.btn-cancel`, `.btn-add-child`) on the HTML elements, then attach handlers after setting `innerHTML`. See `buildTreeNode` and `buildEditForm` in `adventure_editor.py` for the pattern.

## Refactoring rule

When you find logic (parsing, prompt fragments, retry handling, tag rules, etc.) that is duplicated across converter files, **ask the user whether to refactor it into `claude_api.py` before proceeding**. The goal is that any fix or enhancement to shared behaviour is made in exactly one place.
