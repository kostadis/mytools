# Implementation Plan: Meeting Recording Slide Extractor

**Branch**: `001-slide-extractor` | **Date**: 2026-05-08 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/001-slide-extractor/spec.md`

## Summary

Build a four-stage local CLI pipeline that, given a Zoom viewer URL, screen-records
the browser during playback to capture slide transitions and scrape the transcript
panel, then extracts unique slides, understands their content via vision LLM (with
OCR fallback), and synthesises a Markdown meeting summary anchored by slides.

All stages communicate through versioned JSON contracts, are independently
re-runnable against URL-keyed cached artifacts, and are connected by a Playwright-
driven Capture adapter that keeps all Zoom-specific logic isolated.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**:
- `playwright` — browser automation, element screenshots, transcript DOM scraping
- `imagehash` — perceptual hashing (pHash) for slide change detection
- `Pillow` — image I/O and frame manipulation
- `pytesseract` / Tesseract 4+ — OCR fallback for slide text extraction
- `anthropic` — Claude vision API for slide understanding (claude-haiku-4-5-20251001 default)
- `pydantic` v2 — runtime schema validation for all inter-stage contracts
- `structlog` — structured JSON logging across all stages
- `typer` — CLI entry point with subcommands per stage
- `tomllib` (stdlib 3.11+) — configuration file parsing (TOML)
- `pytest` + `pytest-asyncio` — test runner; contract tests and golden fixture

**Storage**: Local filesystem; URL-keyed cache at `~/.local/share/notetaker/cache/<url_sha256>/`

**Testing**: pytest with mocked Anthropic API by default; live API tests behind
`--live-api` marker

**Target Platform**: macOS and Linux (where Playwright Chromium runs headlessly or
headed). Windows best-effort.

**Project Type**: CLI tool / local pipeline

**Performance Goals**: Post-capture processing (Stages 2–4) under 10 min for a
1-hour recording / 20–40 slides; scales approximately linearly with unique slide
count (~30 min for a 3-hour / ~80 slides).

**Constraints**: No video download; Capture duration equals playback duration (up
to 4 hours); 100–500 MB disk per recording; paid API calls must be cached and
budget-capped.

**Scale/Scope**: Single-user local tool; one recording processed at a time.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked post-design below.*

| Article | Requirement | Status | Notes |
|---------|-------------|--------|-------|
| I.1 | Stages independently runnable/testable/replaceable | ✅ Pass | `stages/` package per stage; CLI subcommand per stage |
| I.2 | Platform logic isolated to capture adapters | ✅ Pass | `stages/capture/adapters/zoom.py` only; downstream stages receive contracts |
| I.3 | Contracts versioned with migration path | ✅ Pass | Pydantic models with `schema_version` field; see `contracts/` |
| I.4 | Every stage re-runnable from cache | ✅ Pass | URL-keyed cache; each stage checks cache before executing |
| II.1 | Plan is HOW, spec is WHAT | ✅ Pass | This file |
| II.2 | Every stage documents its contract | ✅ Pass | `contracts/` directory |
| III.1 | Vision calls cached by content hash | ✅ Pass | Cache key = SHA-256 of frame image bytes |
| III.2 | Budget ceiling + degraded mode | ✅ Pass | `budget_ceiling_usd` config; OCR fallback on exhaustion |
| III.3 | Explicit user action starts capture | ✅ Pass | `notetaker capture <url>` — user-initiated; progress indicator shown |
| IV.1 | No magic numbers | ✅ Pass | All thresholds in `config.toml`; see Config Schema section |
| IV.2 | Sensible defaults | ✅ Pass | Defaults work on a typical Zoom recording without modification |
| IV.3 | Config documented | ✅ Pass | Each parameter has description + default in `config.toml` comments |
| V.1 | Structured stage logs | ✅ Pass | `structlog` with JSON renderer; stage context bound at entry |
| V.2 | Debug mode preserves intermediates | ✅ Pass | `--debug` flag; stages skip cleanup |
| V.3 | Failed runs diagnosable without re-run | ✅ Pass | Logs + preserved artifacts in cache dir |
| VI.1 | Credentials not logged | ✅ Pass | Browser profile path only; no cookie values logged |
| VI.2 | Retention policy | ✅ Pass | `retention_days` config (default: 30); cleanup on each run |
| VI.3 | Scope to entitled content | ✅ Pass | No DRM bypass; fail clearly if Zoom shows access error |
| VII.1 | Stage-level contract tests | ✅ Pass | `tests/contract/` per stage |
| VII.2 | Golden fixture for full pipeline | ✅ Pass | `tests/integration/` with fixture recording |
| VII.3 | Cost-sensitive tests mocked | ✅ Pass | `anthropic` calls mocked by default; `--live-api` opt-in |
| VIII.1 | Phased delivery | ✅ Pass | Stage 1 (Capture) ships standalone transcript value |
| VIII.2 | Task-sized commits | ✅ Pass | Enforced in workflow |
| VIII.3 | No silent spec drift | ✅ Pass | Governed |

**Post-design re-check**: ✅ All articles pass after Phase 1 design.

## Project Structure

### Documentation (this feature)

```text
specs/001-slide-extractor/
├── plan.md              # This file
├── research.md          # Phase 0 findings
├── data-model.md        # Entity model
├── quickstart.md        # End-to-end usage guide
├── contracts/
│   ├── transcript.schema.json
│   ├── slide_timeline.schema.json
│   ├── slide_content.schema.json
│   ├── aligned_segments.schema.json
│   └── summary.schema.json
├── checklists/
│   └── requirements.md
└── tasks.md             # Generated by /speckit-tasks (not yet created)
```

### Source Code (repository root)

```text
src/
└── notetaker/
    ├── __init__.py
    ├── cli.py                        # Typer app; subcommands: capture, extract, understand, synthesise, run
    ├── config.py                     # Config dataclass; loads config.toml + applies defaults
    ├── cache.py                      # URL-keyed artifact cache; retention enforcement
    ├── contracts/
    │   ├── __init__.py
    │   ├── transcript.py             # Pydantic: TranscriptSchema, Utterance
    │   ├── slide_timeline.py         # Pydantic: SlideTimelineSchema, SlideOccurrence
    │   ├── slide_content.py          # Pydantic: SlideContentSchema, SlideContent
    │   ├── aligned_segments.py       # Pydantic: AlignedSegmentsSchema, AlignedSegment
    │   └── summary.py                # Pydantic: SummarySchema
    ├── stages/
    │   ├── capture/
    │   │   ├── __init__.py
    │   │   ├── base.py               # CaptureAdapter ABC: .capture(url) -> (FrameDir, TranscriptPath)
    │   │   └── adapters/
    │   │       └── zoom.py           # ZoomAdapter: Playwright browser session, frame sampler, transcript scraper
    │   ├── extraction/
    │   │   ├── __init__.py
    │   │   ├── frame_sampler.py      # Sample frames from capture dir at configured interval
    │   │   └── slide_detector.py     # pHash comparison; emit SlideTimeline
    │   ├── understanding/
    │   │   ├── __init__.py
    │   │   ├── vision.py             # Anthropic Claude vision API; structured extraction
    │   │   └── ocr.py                # pytesseract fallback
    │   └── synthesis/
    │       ├── __init__.py
    │       ├── aligner.py            # Timestamp-based slide↔transcript alignment
    │       └── summarizer.py         # Claude text API; produces FinalSummary
    └── utils/
        ├── logging.py                # structlog setup; JSON + pretty console modes
        └── retry.py                  # @retry(attempts=N, delay=D) decorator

tests/
├── contract/
│   ├── test_transcript_contract.py
│   ├── test_slide_timeline_contract.py
│   ├── test_slide_content_contract.py
│   └── test_aligned_segments_contract.py
├── integration/
│   └── test_full_pipeline.py         # Uses golden fixture; --live-api to enable
└── unit/
    ├── test_slide_detector.py
    ├── test_aligner.py
    ├── test_cache.py
    └── test_retry.py

config.toml                           # Default config (committed); user overrides in ~/.config/notetaker/config.toml
pyproject.toml
```

**Structure Decision**: Single Python project. The `stages/` namespace enforces stage
isolation at the module level; the `contracts/` module is the only permitted import
across stage boundaries.

## Architecture Decisions

### Stage 1 — Capture (Zoom Adapter)

**Mechanism**: Playwright (Python async API) launches Chromium using the user's
existing browser profile directory, navigating to the Zoom viewer URL so the user's
existing Zoom session is active. The user starts playback; the adapter:

1. Detects the presentation area element via CSS selector and takes a
   `page.locator(SLIDE_SELECTOR).screenshot()` every `frame_sample_rate` seconds
   (default: 1 s), saving to `cache/<url_hash>/capture/frames/<timestamp_ms>.jpg`.
2. Simultaneously observes the transcript panel element via a Playwright
   `MutationObserver` bridge, collecting `{timestamp_ms, speaker, text}` tuples
   as lines appear, flushing to `cache/<url_hash>/capture/transcript_raw.jsonl`.
3. Detects playback end (Zoom "ended" state or user signal) and halts.

**Output contract**: `transcript.json` (schema v1) + frame directory manifest
`frames_manifest.json` listing all captured frames in order.

**Zoom-specific selectors** live exclusively in `zoom.py`. If Zoom updates its UI,
only this file changes.

**Browser profile**: Configured via `zoom_adapter.browser_profile_path` in
`config.toml`. Default: system Chrome user-data-dir. Playwright launches in
headed mode so the user can see and interact with the recording.

### Stage 2 — Slide Extraction

**Frame sampling**: The frame directory may contain one frame per second (up to
14,400 frames for a 4-hour recording). The extractor samples at
`extraction.sample_every_n_frames` (default: 1, i.e., all frames) and computes
a 64-bit pHash per frame using `imagehash.phash()`.

**Change detection**: When `imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)`
(Hamming distance) exceeds `extraction.slide_change_threshold` (default: 8), a slide
transition is recorded. Consecutive frames below threshold are grouped into one slide
occurrence.

**De-duplication**: A slide seen a second time (same pHash within threshold) creates
a new `SlideOccurrence` referencing the existing `slide_id`. Slide content is only
processed once per unique `frame_hash`.

**Output**: `slide_timeline.json` (schema v1).

### Stage 3 — Slide Understanding

**Vision call**: For each unique slide (by `frame_hash`), if not in cache, send the
frame image to `claude-haiku-4-5-20251001` with a structured extraction prompt
requesting JSON `{title, bullets[], visual_description, raw_ocr}`. Response is
validated against the SlideContent schema before caching.

**Budget enforcement**: A running cost accumulator tracks estimated spend (tokens ×
price from `understanding.model_pricing`). When spend exceeds
`understanding.budget_ceiling_usd`, remaining slides fall back to OCR.

**OCR fallback**: `pytesseract.image_to_string()` populates `raw_ocr`; `title` and
`bullets` are extracted via simple heuristics (first line = title, subsequent lines
= bullets). `extraction_method` field is set to `"ocr"`.

**Cache key**: `SHA-256(frame image bytes)` — identical slides across recordings
share one cache entry.

**Output**: `slide_content.json` (schema v1).

### Stage 4 — Synthesis

**Alignment**: For each `SlideOccurrence` in the timeline, collect all `Utterance`
records whose `[start_seconds, end_seconds]` overlaps with the slide's time window.
Concatenate to `transcript_text`. Utterances before the first slide or after the
last slide form a `"general_discussion"` pseudo-segment.

**Summary generation**: A single Claude (`claude-sonnet-4-6`, configurable) call
per aligned segment produces a `per_slide_summary`. A final Claude call over all
summaries produces `overall_summary`, `action_items[]`, and `decisions[]`.

**Output**: `summary.md` (human-readable Markdown) + `summary.json` (schema v1).

## Configuration Schema

```toml
# config.toml — all tunables with defaults and descriptions

[capture]
# CSS selector for the Zoom presentation area element
slide_element_selector = ".vjs-tech"
# CSS selector for the Zoom transcript panel container
transcript_panel_selector = ".transcript-panel__content"
# Interval between frame captures, in seconds
frame_sample_rate_seconds = 1
# Browser profile path for Playwright (default: system Chrome profile)
browser_profile_path = ""   # empty = auto-detect

[extraction]
# Hamming distance threshold for slide change detection (0–64)
slide_change_threshold = 8
# Process every Nth frame (1 = all frames)
sample_every_n_frames = 1

[understanding]
# Model for slide content extraction ("claude-haiku-4-5-20251001" or "claude-sonnet-4-6")
vision_model = "claude-haiku-4-5-20251001"
# Per-run budget ceiling in USD; 0.0 = no ceiling
budget_ceiling_usd = 2.00
# Price per million input tokens (update if model pricing changes)
input_token_price_per_million = 0.80
# Price per million output tokens
output_token_price_per_million = 4.00

[synthesis]
# Model for summary generation
summary_model = "claude-sonnet-4-6"

[api]
# Number of retry attempts on transient API/network failures
retry_count = 3
# Fixed delay between retries, in seconds
retry_delay_seconds = 1

[cache]
# Directory for artifact cache (~ expanded)
cache_dir = "~/.local/share/notetaker/cache"
# Retain cached artifacts for this many days (0 = keep forever)
retention_days = 30

[logging]
# Log level: DEBUG, INFO, WARNING, ERROR
level = "INFO"
# Output format: "json" (machine) or "console" (human)
format = "console"
```

## Complexity Tracking

> No constitution violations — this section is informational only.

No complexity violations identified. The 4-stage pipeline maps directly to the
constitutional requirement. The Playwright dependency is the only non-trivial
external tool, and it is confined to the Capture stage adapter.
