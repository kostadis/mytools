# Quickstart: Meeting Recording Slide Extractor

## Prerequisites

1. **Python 3.11+** installed
2. **Tesseract 4+** installed:
   - macOS: `brew install tesseract`
   - Ubuntu/Debian: `sudo apt install tesseract-ocr`
3. **Google Chrome** installed (Playwright will use your existing Chrome profile so
   your Zoom session is already active)
4. **Anthropic API key** set: `export ANTHROPIC_API_KEY=sk-ant-...`

## Install

```bash
pip install notetaker
# First run: install Playwright Chromium browser
playwright install chromium
```

## Usage

### Full pipeline (recommended)

Open the Zoom recording in Chrome, log in if needed, then:

```bash
notetaker run "https://zoom.us/rec/play/your-recording-id..."
```

This command:
1. Opens a headed Chrome window pointing to the Zoom URL
2. Waits for you to confirm playback has started (prompts in the terminal)
3. Captures frames and scrapes transcript throughout playback
4. After you signal playback is complete (press Enter), runs post-capture processing
5. Writes `summary.md` and `summary.json` to your cache directory

### Run stages individually

```bash
# Stage 1: Capture (requires browser + active playback)
notetaker capture "https://zoom.us/rec/play/..."

# Stage 2: Slide extraction from captured frames
notetaker extract "https://zoom.us/rec/play/..."

# Stage 3: Slide content understanding
notetaker understand "https://zoom.us/rec/play/..."

# Stage 4: Summary synthesis
notetaker synthesise "https://zoom.us/rec/play/..."
```

Stages 2–4 read from the URL-keyed cache written by the prior stage. They skip
execution if their output is already cached and up-to-date.

### Re-run a specific stage

```bash
# Re-run synthesis only (skips capture, extraction, understanding)
notetaker synthesise "https://zoom.us/rec/play/..." --force
```

### Debug mode

```bash
notetaker run "https://zoom.us/rec/play/..." --debug
```

Preserves all intermediate artifacts (raw frames, OCR outputs, raw API responses,
alignment tables) in the cache directory for inspection.

## Output location

```
~/.local/share/notetaker/cache/<url-hash>/synthesis/
├── summary.md      ← human-readable meeting summary
└── summary.json    ← machine-readable (SummarySchema v1.0)
```

## Configuration

Copy the default config and adjust:

```bash
mkdir -p ~/.config/notetaker
cp config.toml ~/.config/notetaker/config.toml
```

Key parameters to review before your first run:

| Parameter | Default | What to adjust |
|---|---|---|
| `capture.browser_profile_path` | auto-detect | Set explicitly if Chrome profile is not in the default location |
| `capture.frame_sample_rate_seconds` | `1` | Increase to `2`–`5` for very long meetings to reduce disk usage |
| `understanding.budget_ceiling_usd` | `2.00` | Raise for longer meetings with many unique slides |
| `understanding.vision_model` | `claude-haiku-4-5-20251001` | Switch to `claude-sonnet-4-6` for slides with complex diagrams |
| `cache.retention_days` | `30` | Recordings with sensitive content should use a shorter window |

## Troubleshooting

**"Zoom transcript panel not found"**: The Zoom web player was not showing the
transcript panel. Open the player, click the CC/Transcript button to show the
transcript, then re-run capture.

**"Budget ceiling reached"**: Slides after the cutoff used OCR fallback. Either
raise `understanding.budget_ceiling_usd` in your config and re-run
`notetaker understand`, or accept the OCR-only content for remaining slides.

**"Slide selectors returned no content"**: Zoom may have updated its web player
HTML. Check `zoom.py` for the current selectors and update them to match the current
Zoom player DOM.

**Stale cache after a partial capture**: Run `notetaker capture ... --force` to
redo the capture, which overwrites the prior session.

## Updating Zoom Selectors

If Zoom updates its web player, selectors may need updating. Open the recording in
Chrome DevTools (F12), inspect the presentation area and transcript panel elements,
and update these constants in `src/notetaker/stages/capture/adapters/zoom.py`:

```python
SLIDE_SELECTOR = ".vjs-tech"
TRANSCRIPT_PANEL_SELECTOR = ".transcript-panel__content"
TRANSCRIPT_LINE_SELECTOR = ".transcript-panel__content li"
```

No other files need changing (Article I.2).

## Running tests

```bash
# Default: skip live API tests
pytest

# Run unit + contract tests only
pytest tests/unit tests/contract

# Run the integration test (uses synthetic fixtures + mocked vision)
pytest tests/integration

# Opt in to live API calls (incurs cost)
pytest -m live_api
```
