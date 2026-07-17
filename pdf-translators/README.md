# PDF → 5etools Converter (v2)

Convert RPG sourcebook and adventure PDFs into [5etools](https://5e.tools) homebrew JSON, ready to load via **Manage Homebrew → Load from File** or install permanently on a self-hosted server.

Unlike v1 (three separate heuristic scripts — see [README_v1.md](README_v1.md)), v2 is a **single unified converter** that auto-routes each PDF to the right extraction path:

| PDF type | Path | Speed |
|---|---|---|
| Digital, bookmarked, selectable text | **PyMuPDF fast path** — chunks by the bookmark tree | ~100× faster |
| Scans, OCR'd modules, un-bookmarked digital | **Marker path** — ML layout/heading extraction, then synthesised TOC | ~5 s/page (GPU) |

The key design change: **structure extraction happens before Claude runs.** Marker (or the PDF's own bookmarks) produces an authoritative heading tree, so Claude only *renders prose inside pre-built structure* rather than inferring document structure from font heuristics. This eliminates the `[H1]`/`[ROOM-KEY-N]` annotations, the post-conversion repair scripts, and the content-filter trigger substitutions that v1 needed.

A browser-based UI (`editors/app.py`) wraps the converter so you never have to touch the command line.

---

## Contents

```
pdf-translators/
├── lib/
│   ├── cli_args.py           Shared argparse layer
│   ├── llm_backend.py        Provider/transport seam (claude / dgx / claude-code)
│   ├── claude_api.py         Retry / validation / recovery + prompt fragments
│   ├── pdf_utils.py          PDF bookmark + TOC extraction
│   ├── adventure_model.py    Typed 5etools data model
│   ├── validate_adventure.py Structural validator
│   ├── validate_tags.py      {@tag} checker
│   └── fix_adventure_json.py Chapter-index normalizer
├── converters/
│   └── pdf_to_5etools_v2.py  Unified converter (fast path + Marker path)
├── editors/
│   ├── app.py                 Web UI (Flask, port 5100)
│   ├── toc_editor.py          TOC editor UI (port 5101)
│   ├── toc_fixer.py           Heuristic TOC/nesting repair UI (port 5102)
│   ├── monster_editor.py      Stat-block extraction UI (port 5103)
│   ├── editor_server.py       Markdown + Adventure editor UI (port 5107)
│   ├── adventure_editor.py    Adventure editor Blueprint (served by editor_server.py)
│   └── markdown_editor.py     Markdown editor Blueprint (served by editor_server.py)
├── frontend/                  Vite/Vue SPA served by editors/editor_server.py
├── tests/                     pytest suite
└── README.md                  This file
```

---

## Requirements

### Core converter (fast path + UI)

```bash
pip install pymupdf anthropic flask
```

### Marker path (scans, un-bookmarked PDFs)

Marker runs in its own virtualenv (gitignored):

```bash
python3 -m venv marker-env
source marker-env/bin/activate
pip install marker-pdf pymupdf
# First run downloads ~5 GB of model weights from HuggingFace.
```

A CUDA GPU is strongly recommended (4080-class: ~5 s/page; CPU: 10–30 s/page).

### API key

The default `claude` provider calls the Anthropic API. Set your key once or pass `--api-key`:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

The `dgx` and `claude-code` providers need **no API key** (see [Providers](#providers) below).

---

## Web UI (recommended)

```bash
python3 editors/app.py
```

Then open **http://localhost:5100** in your browser.

- Drag-and-drop PDF upload
- Automatic fast-path / Marker routing
- All output, model, and advanced options
- Live streaming progress log (Server-Sent Events)
- Download button for the finished JSON

To use a different port:

```bash
PORT=8080 python3 editors/app.py
```

---

## Command-line usage

```bash
python3 converters/pdf_to_5etools_v2.py <input.pdf> [options]
```

**Common examples**

```bash
# Quickstart — auto-route, all defaults, outputs <stem>_5etools.json next to the PDF
python3 converters/pdf_to_5etools_v2.py "Lost Mine of Phandelver.pdf"

# Name the adventure and set the author
python3 converters/pdf_to_5etools_v2.py "MyAdventure.pdf" --id MYADV --author "Jane Smith"

# Book (rulebook / sourcebook) instead of adventure
python3 converters/pdf_to_5etools_v2.py "Rulebook.pdf" --type book

# Force the Marker path even though the PDF has bookmarks
# (use when the text layer is OCR'd-to-PDF or has broken embedded fonts)
python3 converters/pdf_to_5etools_v2.py "ScannedModule.pdf" --force-marker

# Estimate token cost before committing (free, no inference)
python3 converters/pdf_to_5etools_v2.py "BigBook.pdf" --dry-run

# 50% cheaper via the Anthropic Batch API (async — completes in minutes)
python3 converters/pdf_to_5etools_v2.py "BigBook.pdf" --batch

# Send 4 chunks at a time on the streaming path
python3 converters/pdf_to_5etools_v2.py "BigBook.pdf" --concurrency 4

# Extract monster stat blocks as well as adventure text
python3 converters/pdf_to_5etools_v2.py "Adventure.pdf" --extract-monsters

# Extract monsters only (skip adventure text — cheapest path for bestiaries)
python3 converters/pdf_to_5etools_v2.py "MonsterManual.pdf" --monsters-only
```

**Core options**

| Option | Default | Description |
|---|---|---|
| `--provider claude\|dgx\|claude-code` | `claude` | LLM backend (see [Providers](#providers)) |
| `--endpoint URL` | `http://192.168.1.147:8001/v1` | DGX vLLM base URL (`dgx` only) |
| `--type adventure\|book` | `adventure` | Content type |
| `--output-mode homebrew\|server` | `homebrew` | Single homebrew file or two-file server install |
| `--id SHORT_ID` | Derived from filename | Uppercase identifier, e.g. `MYADV` |
| `--author "Name"` | `Unknown` | Author string embedded in the JSON |
| `--out output.json` | `<stem>_5etools.json` | Full output path (overrides `--output-dir`) |
| `--output-dir DIR` | Same folder as the PDF | Directory to write output file(s) into |
| `--api-key KEY` | `$ANTHROPIC_API_KEY` | Anthropic API key (`claude` only) |
| `--pages-per-chunk N` | `1` | Pages per Claude call (Marker/TOC normally defines chunk boundaries) |
| `--model MODEL` | `claude-haiku-4-5-20251001` | Model id (`dgx` auto-discovers if omitted) |
| `--force-marker` | off | Bypass the fast path; always use Marker |
| `--batch` | off | Anthropic Batch API (50% cheaper, async) |
| `--concurrency N` | `1` claude / `8` dgx | Chunks sent at once on the streaming path |
| `--extract-monsters` | off | Second pass to extract stat blocks into a bestiary file |
| `--monsters-only` | off | Skip adventure text; extract stat blocks only |
| `--dry-run` | off | Estimate tokens/cost, no inference |
| `--no-toc-hint` | off | Don't inject the PDF bookmark outline as a section hint |
| `--pages RANGE` | — | Only process these pages, e.g. `10-20` or `5,10-15` |
| `--page N` | — | Only process this single page |
| `--debug-dir DIR` | off | Save raw chunk I/O for debugging |
| `--verbose` | off | Print detailed progress |

**Recovery options** (resume / rebuild without re-billing — see [Resuming a run](#resuming-a-run))

| Option | Description |
|---|---|
| `--reuse-responses` | Resume a crashed run: re-send only the missing/unusable chunks (streaming or `--batch`) |
| `--replay-responses DIR` | Rebuild output from a **complete** set of saved responses; no provider calls |
| `--resume-batch BATCH_ID` | Fetch results from an already-completed Anthropic Batch run (Anthropic-only) |

---

## Providers

v2 routes every Claude call through a provider-agnostic transport seam (`lib/llm_backend.py`). Pick the backend with `--provider`:

| Provider | What it calls | API key | Batch / dry-run cost | Default concurrency |
|---|---|---|---|---|
| `claude` *(default)* | Anthropic Messages API | required | yes / yes | 1 |
| `dgx` | OpenAI-compatible vLLM endpoint on the DGX Spark | none | no / size-only | 8 |
| `claude-code` | local `claude` CLI — spends your **Claude Code subscription** quota | none | no / size-only | 1 |

```bash
python3 converters/pdf_to_5etools_v2.py input.pdf --provider dgx           # local Spark model
python3 converters/pdf_to_5etools_v2.py input.pdf --provider dgx --endpoint http://HOST:8001/v1
python3 converters/pdf_to_5etools_v2.py input.pdf --provider claude-code   # your Claude subscription
```

- **`dgx`** — the served model id is auto-discovered from `/v1/models` unless `--model` is given. vLLM serves many requests concurrently, so `--concurrency` is the main throughput lever (~20 tok/s single-stream vs ~130 tok/s at 20 concurrent on the Spark).
- **`claude-code`** — requires the `claude` CLI installed and logged in (`claude login`) with a subscription. The transport scrubs `ANTHROPIC_API_KEY` from the child env so it uses the subscription login, not API billing. No `max_tokens` control and no truncation signal (the CLI always reports `end_turn`), so the tail/split *truncation* retry never fires for this provider — its validation/malformed-JSON retry still does. If you hit your usage cap mid-run the call errors cleanly; resume later with `--reuse-responses`.

`--batch`, `--resume-batch`, and dry-run **cost** figures are Anthropic-only and rejected up front for the other providers.

---

## How it works

The unified pipeline (`converters/pdf_to_5etools_v2.py`):

1. **Profile** — `profile_pdf()` samples ~10 pages. Has bookmarks **and** selectable text → fast path. Anything else → Marker path. `--force-marker` always uses Marker.
2. **Extract structure**
   - *Fast path:* `get_toc_tree()` reads the PDF bookmark outline into a `TocNode` tree.
   - *Marker path:* `run_marker()` shells out to `marker_single` to produce markdown with `#`/`##`/`###` headings; `parse_markdown_headings()` extracts them with line offsets; `normalise_numbered_rooms()` flattens keyed-room patterns (e.g. `101. ARMORY`) to a common level; `build_synthetic_toc()` reuses the same tree builder with line numbers standing in for page numbers.
3. **Chunk** — one chunk per top-level `TocNode`. Fast path pulls page text via PyMuPDF; Marker path slices the markdown between heading line numbers.
4. **Claude pass** — `build_prompt()` attaches sub-section hints from the node's children; `claude_api.call_claude` owns all retry / validation / recovery. The PDF's bookmark outline is prepended to each chunk as an authoritative section hint (disable with `--no-toc-hint`). Batch mode via `call_claude_batch`.
5. **Assemble** — `assemble_adventure()` wraps each chunk's `entries[]` in a `SectionEntry` and calls `HomebrewAdventure.build()`, which auto-assigns IDs and builds the TOC from the section tree.
6. **Write** — `.to_json()` writes the final document.

### Validation & retry

`call_claude` validates every parsed chunk through `adventure_model` and retries once with a correction prompt if structural errors are found (unknown `{@tag}`s, missing fields, etc.). After conversion, run the standalone checkers:

```bash
python3 lib/validate_adventure.py adventure.json   # structure: TOC/data alignment, entry types, braces, IDs
python3 lib/validate_tags.py adventure.json        # unknown {@tag}s (cause blank pages); --fix to strip them
```

### Resuming a run

Every run auto-saves each chunk's raw provider output to `<out_stem>-responses/{cid}-response.txt` (where `cid` is `{index:03d}-{slug}`). Chunking is deterministic, so three flags can reuse that work:

- **`--reuse-responses`** — mid-run resume on either path. Loads each chunk's saved response if it parses to real entries; only the missing/unusable chunks are re-sent. Tolerates a **partial** set — this is the flag for finishing a run that died midway. Re-run the original command verbatim with `--reuse-responses` added, keeping the same output target. Don't change anything that alters chunking (PDF, page selection, `--force-marker`).
- **`--replay-responses DIR`** — rebuild output from a **complete** set of saved responses; no provider calls. Use to re-parse a finished run after a parser fix.
- **`--resume-batch BATCH_ID`** — Anthropic-only; fetch results from a completed Batch run.

The cache key is `{index:03d}-{slug}` only — **not** model-aware — so a `claude --batch --reuse-responses` run will reuse chunks a prior `dgx` streaming run produced (cross-provider reuse is intentional).

### Bestiary extraction

- **`--extract-monsters`** — after the conversion, a second pass pulls stat blocks out of the generated JSON and writes `<stem>-bestiary.json` with source ID `{SOURCE}b` (separate so both homebrews load together without conflicting). Inherits `--model` and `--batch`.
- **`--monsters-only`** — bypass the adventure pipeline entirely. Always runs Marker, splits on `##` headings, keeps sections that mention "Armor Class"/"AC N", and sends those to Claude. ~2–3× fewer tokens than a full conversion.

### Output format

**Homebrew mode** (default) produces a single JSON loadable via **Manage Homebrew → Load from File**.

**Server mode** (`--output-mode server`) produces two files for a permanent self-hosted install:

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

Bestiary output appears in **Bestiary** (`bestiary.html`). Named NPCs with `isNpc: true` are hidden by default — toggle the "Adventure NPC" filter to see them.

---

## Extracting images from a PDF

The converter handles text and structure only — it does **not** pull maps or artwork out of the PDF. To grab every embedded image (for adding maps/handouts to your homebrew), use **`pdfimages`** from poppler-utils:

```bash
sudo apt install poppler-utils          # Ubuntu/Debian, if not already installed

mkdir -p images
pdfimages -all input.pdf images/img     # extract every image in its native format → images/img-000.png, ...
```

Useful flags:

| Flag | Effect |
|---|---|
| `-all` | Keep each image in its original encoding (jpg/png/…) — recommended |
| `-png` | Force every image to PNG |
| `-list` | List images (page, size, format) without extracting — preview first |
| `-f N` / `-l N` | First / last page to extract from |

---

## Editing & repair tools

After conversion, several Flask UIs help review and fix the output:

| Tool | Port | Purpose |
|---|---|---|
| `editors/toc_editor.py` | 5101 | Review/correct the `contents[]` TOC; highlight TOC↔data mismatches |
| `editors/toc_fixer.py` | 5102 | Heuristic `data[]` re-nesting using the PDF bookmark outline (`--pdf file.pdf`) |
| `editors/monster_editor.py` | 5103 | Interactive stat-block discovery and extraction |
| `editors/editor_server.py` | 5107 | Markdown Editor + visual Adventure block-tree editor (Vue SPA), undo/redo, live preview |

Plus command-line post-processors: `lib/fix_adventure_json.py` (chapter-index normaliser), `converters/merge_patch.py` (patch specific pages into an existing JSON), `converters/patch_5e_chapters.py`, `converters/convert_1e_to_5e.py` (1e → 5e mechanical rewrite), `converters/extract_monsters.py`. See [CLAUDE.md](CLAUDE.md) for full details.

---

## Running the tests

```bash
cd pdf-translators
pytest tests/test_adventure_model.py -v       # adventure data model
pytest tests/test_adventure_editor.py -v      # adventure editor
pytest tests/test_validate_adventure.py -v    # JSON validator (includes all official adventures)
```

Tests mock all external dependencies (PyMuPDF, Anthropic API) — no API key or system packages required.

---

## Model note

The spike comparing Haiku vs Sonnet on Marker-processed content showed Haiku handles the rendering job correctly at ~4× lower cost, so v2 defaults to **Haiku**. This reverses the v1-era "use Sonnet for 1e" rule: with Marker doing the structure extraction up front, Claude only renders prose, and the smaller model is reliable. Override with `--model claude-sonnet-4-6` only if specific content needs it.

Marker output also strips the dense bold-all-caps formatting that triggered content filters on raw 1e text, so the v1 trigger-substitution infrastructure is gone.

---

## v1 history

The prior-generation heuristic converters (`pdf_to_5etools.py`, `pdf_to_5etools_ocr.py`, `pdf_to_5etools_1e.py`, plus their TOC variants and repair scripts) are documented in [README_v1.md](README_v1.md) and [ARCHITECTURE_V1.md](ARCHITECTURE_V1.md). **No `v1.0` git tag exists in this repo** despite this note previously claiming one — `files-8.zip` (`pdf_to_5etools.py`, `pdf_to_5etools_ocr.py`) and `v1/pdf_utils_old.py` are the only surviving v1 code; `pdf_to_5etools_1e.py` and the TOC/repair-script variants appear to be lost entirely.
