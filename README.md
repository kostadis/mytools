# PDF → 5etools Converters

Convert RPG sourcebook and adventure PDFs into [5etools](https://5e.tools) homebrew JSON, ready to load via **Manage Homebrew → Load from File** or install permanently on a self-hosted server.

Two converters are provided:

| Script | Best for |
|---|---|
| `pdf_to_5etools.py` | Digitally-typeset PDFs with selectable text |
| `pdf_to_5etools_ocr.py` | Scanned or image-based PDFs; also handles mixed PDFs |

A browser-based UI (`app.py`) wraps both scripts so you never have to touch the command line.

---

## Contents

```
pdf-translators/
├── app.py                  Web UI (Flask)
├── pdf_to_5etools.py       Standard converter
├── pdf_to_5etools_ocr.py   OCR-enhanced converter
├── test_pdf_to_5etools.py  Unit tests (pytest)
└── README.md               This file
```

---

## Requirements

### Standard converter

```bash
pip install pymupdf anthropic
```

### OCR converter (additional)

```bash
pip install pytesseract pillow pdf2image
# Ubuntu / Debian system packages:
sudo apt install tesseract-ocr tesseract-ocr-eng poppler-utils
```

### Web UI (additional)

```bash
pip install flask
```

### API key

Both converters call the Anthropic API. Set your key once as an environment variable or pass it with `--api-key`:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

---

## Web UI (recommended)

```bash
python3 app.py
```

Then open **http://localhost:5100** in your browser.

The UI exposes every option from both scripts:

- Drag-and-drop PDF upload
- Standard or OCR-enhanced extraction mode
- All output, Claude, and advanced options
- Live streaming progress log
- Download button for the finished JSON

To use a different port:

```bash
PORT=8080 python3 app.py
```

---

## Command-line usage

### Standard converter

```bash
python3 pdf_to_5etools.py <input.pdf> [options]
```

**Common examples**

```bash
# Quickstart — all defaults, outputs <stem>_5etools.json next to the PDF
python3 pdf_to_5etools.py "Lost Mine of Phandelver.pdf"

# Name the adventure and set the author
python3 pdf_to_5etools.py "MyAdventure.pdf" --id MYADV --author "Jane Smith"

# Book (rulebook / sourcebook) instead of adventure
python3 pdf_to_5etools.py "Rulebook.pdf" --type book

# Write output to a specific directory
python3 pdf_to_5etools.py "MyAdventure.pdf" --output-dir ~/5etools/homebrew

# Two-file server format (copies into data/ dirs for permanent install)
python3 pdf_to_5etools.py "MyAdventure.pdf" --output-mode server --output-dir /tmp/out

# Estimate token cost before committing (free, no inference)
python3 pdf_to_5etools.py "BigBook.pdf" --dry-run

# 50 % cheaper via Batch API (async — completes in minutes, not seconds)
python3 pdf_to_5etools.py "BigBook.pdf" --batch

# Extract monster stat blocks as well as adventure text
python3 pdf_to_5etools.py "Adventure.pdf" --extract-monsters

# Extract monsters only (skip adventure text — fastest option for bestiaries)
python3 pdf_to_5etools.py "MonsterManual.pdf" --monsters-only
```

**All options**

| Option | Default | Description |
|---|---|---|
| `--type adventure\|book` | `adventure` | Content type |
| `--output-mode homebrew\|server` | `homebrew` | Single homebrew file or two-file server install |
| `--id SHORT_ID` | Derived from filename | Uppercase identifier, e.g. `MYADV` |
| `--author "Name"` | `Unknown` | Author string embedded in the JSON |
| `--out output.json` | `<stem>_5etools.json` | Full output path (overrides `--output-dir`) |
| `--output-dir DIR` | Same folder as the PDF | Directory to write output file(s) into |
| `--api-key KEY` | `$ANTHROPIC_API_KEY` | Anthropic API key |
| `--pages-per-chunk N` | `6` | Pages sent to Claude per API call |
| `--model MODEL` | `claude-haiku-4-5-20251001` | Claude model to use |
| `--batch` | off | Use Batch API (50 % cheaper, async) |
| `--extract-monsters` | off | Second Claude pass to extract stat blocks |
| `--monsters-only` | off | Skip adventure text; extract stat blocks only |
| `--dry-run` | off | Count tokens and estimate cost, no inference |
| `--debug-dir DIR` | off | Save raw chunk I/O for debugging |
| `--verbose` | off | Print detailed progress |

---

### OCR-enhanced converter

```bash
python3 pdf_to_5etools_ocr.py <input.pdf> [options]
```

Accepts all the same options as the standard converter, plus:

| Option | Default | Description |
|---|---|---|
| `--dpi N` | `300` | Render resolution for OCR pages |
| `--force-ocr` | off | OCR every page, even those with digital text |
| `--lang LANG` | `eng` | Tesseract language code(s), e.g. `eng+fra` |

**When to use OCR mode**

- The PDF is a scan (photographed pages, no selectable text)
- Digital extraction produces garbled text, mojibake, or near-empty pages
- The book uses decorative fonts that confuse the text layer

The script tries digital extraction first on every page; it only falls back to Tesseract OCR when a page yields fewer than 50 readable characters. Use `--force-ocr` to bypass this and OCR everything.

**Examples**

```bash
# Scanned module, load via UI
python3 pdf_to_5etools_ocr.py "ScannedModule.pdf" --force-ocr

# Higher resolution for small or dense text
python3 pdf_to_5etools_ocr.py "Sourcebook.pdf" --dpi 400

# French-language PDF
python3 pdf_to_5etools_ocr.py "Module.pdf" --lang fra
```

---

## How it works

### Text extraction (standard)

1. **PyMuPDF** reads every page, extracting text with font-size and bold/italic metadata.
2. A heuristic pass computes the median body font size and flags text as H1/H2/H3 based on size ratios (×1.4 / ×1.2 / ×1.05).
3. Pages are grouped into chunks and sent to the **Anthropic API**. Claude receives annotated text (`[H1] Title`, `[italic]text[/italic]`, etc.) and returns a JSON array of 5etools entry objects.
4. Chunks are merged, sequential IDs are assigned, a table of contents is synthesised, and the final JSON is written.

### OCR fallback

Pages below the 50-character threshold are rendered to images at the configured DPI and processed by **Tesseract**. The script then:

- Detects two-column layouts by looking for gaps in the x-distribution of words, and re-orders text left-column-first.
- Infers heading level from character height relative to the page average.
- Detects boxed/inset text by checking block bounding-box indentation.
- Detects tables by looking for runs of lines with 2+ whitespace-separated tokens.

Claude is then given the same structured prompt, extended with OCR-specific instructions.

### Output format

**Homebrew mode** (default) produces a single JSON file loadable via **Manage Homebrew → Load from File**:

```
managebrew.html → Load from File → select <stem>_5etools.json
```

**Server mode** produces two files for a permanent self-hosted install:

| File | Destination |
|---|---|
| `adventure-SHORT.json` | `data/adventure/` |
| `adventures-short.json` | `data/` (merge into `adventures.json`) |

---

## Loading in 5etools

1. Open your local 5etools instance (e.g. `http://localhost:5050`).
2. Go to **Manage Homebrew** (`managebrew.html`).
3. Click **Load from File** and select the generated `.json`.
4. Navigate to **Adventures** (or **Books**) — your content appears in the list.

For monster-only output, the creatures appear in **Bestiary** (`bestiary.html`).

---

## Running the tests

```bash
cd pdf-translators
pytest test_pdf_to_5etools.py -v
```

The tests cover all pure-logic functions in both scripts (`normalise_path`, heading detection, chunk splitting, Claude response parsing, ID assignment, TOC building, table marker injection, etc.) and mock out the external dependencies (PyMuPDF, Anthropic SDK, Tesseract) so no API key or system packages are needed.
