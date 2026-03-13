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

Requires `ANTHROPIC_API_KEY` env var or `--api-key KEY`. Default model: `claude-haiku-4-5-20251001`. Use `--dry-run` to estimate token cost without making API calls.

## Architecture

### Converter pipeline (all three scripts share this structure)

1. **Text extraction** — PyMuPDF (`fitz`) extracts text with font-size/bold/italic metadata; OCR scripts additionally use Tesseract for image-heavy pages
2. **Annotation** — heuristics tag headings (`[H1]`/`[H2]`/`[H3]`), italic/bold spans, tables, and boxed text
3. **Chunking** — pages grouped into chunks (default: 6 for standard, 4 for OCR, 3 for 1e) and sent to Claude API
4. **Claude pass** — structured prompt returns JSON array of 5etools entry objects
5. **Post-processing** — chunks merged, sequential IDs assigned, TOC synthesised, final JSON written

### The three converters

- **`pdf_to_5etools.py`** — digitally-typeset PDFs with selectable text; supports `--batch` (Batch API, 50% cheaper)
- **`pdf_to_5etools_ocr.py`** — extends standard with Tesseract OCR fallback (<50 chars/page threshold), two-column layout detection, heading inference from character height
- **`pdf_to_5etools_1e.py`** — 1e/2e AD&D modules; adds keyed-room detection, inline stat block parsing, automatic stat conversion (descending AC → ascending, THAC0 → attack bonus, MV inches → feet, HD → CR), and content filter substitutions via `triggers.json`

### Output modes

- **Homebrew** (default): single `.json` loadable via 5etools Manage Homebrew UI
- **Server**: two files (`adventure-SHORT.json` + `adventures-short.json`) for permanent self-hosted installs

### `app.py` — Flask web UI

Single-file Flask app with inline HTML/CSS/JS (Bootstrap 5.3.3). Jobs tracked by UUID with thread-safe logging; progress streamed to browser via Server-Sent Events (SSE). Converters run as subprocesses.

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
