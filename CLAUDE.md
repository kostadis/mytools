# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Converts tabletop RPG PDFs (primarily D&D/AD&D sourcebooks and modules) into [5etools](https://5e.tools) homebrew JSON format. Three specialized converters handle different PDF types, wrapped by a Flask web UI.

## Running tests

```bash
pytest test_pdf_to_5etools.py -v
```

Tests mock all external dependencies (PyMuPDF, Anthropic API, Tesseract, PIL, pdf2image) — no API key or system packages required.

To run a single test:
```bash
pytest test_pdf_to_5etools.py -v -k "test_function_name"
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

Requires `ANTHROPIC_API_KEY` env var or `--api-key KEY`. Default model: `claude-haiku-4-5-20251001` (1e/OCR scripts) or `claude-sonnet-4-20250514` (standard script). Use `--dry-run` to estimate token cost without making API calls. Use `--output-mode server` for two-file permanent installs; `--extract-monsters`/`--monsters-only` for stat block extraction. OCR script adds `--dpi N`, `--force-ocr`, `--lang LANG`. 1e script adds `--module-code CODE`, `--system 1e|2e`, `--skip-pages RANGE`, `--no-cr-adjustment`. All scripts support `--no-toc-hint` to skip injecting the PDF bookmark outline into Claude prompts.

## Architecture

### Shared API layer — `claude_api.py`

All three converters delegate Claude API calls to `claude_api.py`, which owns:
- `MAX_OUTPUT_TOKENS = 20_000` — single place to change the output token budget
- `COMMON_TAG_RULES` — shared prompt fragment listing all valid `{@tag}` references; injected into every converter's `SYSTEM_PROMPT` via f-string. Update here when the set of supported 5etools inline tags changes.
- `_parse_claude_response` — strips markdown fences, parses JSON, returns `(list, bool)`
- `_recover_partial_json` — salvages complete entries from truncated/malformed responses
- `call_claude(client, chunk_text, model, system_prompt, verbose, debug_dir, chunk_id)` — full retry logic: tail retry on `max_tokens` with partial output, split retry on `max_tokens` or `end_turn` with malformed JSON

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

- **`pdf_to_5etools.py`** — digitally-typeset PDFs with selectable text; supports `--batch` (Batch API, 50% cheaper)
- **`pdf_to_5etools_ocr.py`** — extends standard with Tesseract OCR fallback (<50 chars/page threshold), two-column layout detection, heading inference from character height
- **`pdf_to_5etools_1e.py`** — 1e/2e AD&D modules; adds keyed-room detection, inline stat block parsing, automatic stat conversion (descending AC → ascending, THAC0 → attack bonus, MV inches → feet, HD → CR), and content filter substitutions via `triggers.json`

### Output modes

- **Homebrew** (default): single `.json` loadable via 5etools Manage Homebrew UI
- **Server**: two files (`adventure-SHORT.json` + `adventures-short.json`) for permanent self-hosted installs

### `toc_editor.py` — TOC editor UI

Flask app (port 5101) for reviewing and correcting the `contents[]` TOC in a generated adventure JSON. Shows TOC entries side-by-side with `data[]` sections at the same array index; highlights mismatches (yellow) and non-`section` top-level data entries (red). Supports drag-and-drop reorder (SortableJS), add/delete rows, and live name editing. Save writes back to the JSON and appends a `{before, after}` training pair to `toc_corrections.jsonl`.

```bash
python3 toc_editor.py [file.json] [--port N]
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
- **5etools TOC/data alignment**: `adventure[0].contents[n]` maps to `adventureData[0].data[n]` by direct array index. Every top-level `data[]` entry must be `type: "section"` — non-section entries shift all subsequent chapter navigation by 1. The post-processing hoist step enforces this automatically.
- **Retry logic lives in `claude_api.py`** — do not duplicate it in the individual converters.
- **Shared prompt fragments live in `claude_api.py`** (`COMMON_TAG_RULES`) — do not duplicate tag rules in individual converters.
- **TOC hint lives in `pdf_utils.py`** (`extract_pdf_toc`, `_decode_pdf_string`) — all converters import from there, not from each other.
- **`{@tag}` validation** — run `python3 validate_tags.py adventure.json` after conversion to catch unknown tags (which cause blank pages in 5etools). Use `--fix` to replace them with plain text in-place.

## Refactoring rule

When you find logic (parsing, prompt fragments, retry handling, tag rules, etc.) that is duplicated across converter files, **ask the user whether to refactor it into `claude_api.py` before proceeding**. The goal is that any fix or enhancement to shared behaviour is made in exactly one place.
