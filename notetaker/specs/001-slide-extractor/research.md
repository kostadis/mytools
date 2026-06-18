# Research: Meeting Recording Slide Extractor

**Date**: 2026-05-08 | **Branch**: `001-slide-extractor`

## 1. Browser Automation for Frame Capture

**Decision**: Playwright (Python async API) with `page.locator(selector).screenshot()`
called at a configurable interval during playback.

**Rationale**: Playwright runs cross-platform without OS-level screen capture
permissions. Element-scoped screenshots isolate the presentation area from browser
chrome and the Zoom transcript panel, reducing noise in slide comparison. The async
API supports concurrent frame capture and transcript scraping within one event loop.

**Alternatives considered**:
- `mss` (OS-level screen capture): Requires window focus, OS permissions, and window
  coordinate tracking. Brittle when the browser window is resized or occluded.
  Rejected.
- `ffmpeg` + virtual display (Linux Xvfb): Generates a continuous video stream that
  must be split into frames downstream. Adds a large video file to disk — exactly
  what the architecture avoids. Rejected.

**Key detail — browser profile**: Playwright's `browser.launch_persistent_context()`
accepts a `user_data_dir` pointing to the user's existing Chrome profile. This
means Zoom session cookies are already present and the user does not need to log in
again. The profile path is configurable; the default is auto-detected from the OS
(`~/.config/google-chrome/Default` on Linux, `~/Library/Application Support/Google/Chrome` on macOS).

---

## 2. Zoom Viewer Transcript Scraping

**Decision**: Playwright DOM observation via a periodic poll of the transcript panel
container, collecting new lines since the last poll.

**Rationale**: The Zoom web recording player renders transcript text in a scrollable
`div` that grows as playback progresses. Polling every `frame_sample_rate_seconds`
(same cadence as frame capture) is sufficient because transcript lines accumulate
rather than replace, and missed polls just push lines into the next batch.

**CSS selectors** (Zoom web player as of 2025–2026; encapsulated in `zoom.py`):
- Slide/video element: `.vjs-tech` (VideoJS player element)
- Transcript container: `.transcript-panel__content` (scrollable transcript list)
- Individual transcript line: `.transcript-panel__content li` or similar

**Timestamp extraction**: Each transcript line in the Zoom viewer carries a visible
timestamp (e.g., "00:02:15 John Doe: Hello everyone"). The scraper parses this
using a regex, converting `HH:MM:SS` to `start_seconds`. End time is inferred as
the start of the next line.

**Fallback**: If the transcript panel selector is not found, the adapter logs a
`WARN` and continues with frame capture only. `transcript.json` is written as
`{"schema_version": "1.0", "utterances": [], "transcript_unavailable": true}`.

**Fragility risk**: Zoom can change CSS selectors. This is accepted and mitigated
by isolating all selectors in `zoom.py` and documenting the update procedure in
`quickstart.md`.

---

## 3. Slide Change Detection

**Decision**: Perceptual hashing using `imagehash.phash()` (64-bit pHash), with
Hamming distance threshold of 8 (configurable as `slide_change_threshold`).

**Rationale**: pHash is robust to JPEG compression artifacts, minor rendering
differences, and frame-to-frame antialiasing noise — all common in browser
screenshots. A Hamming distance of 8 on a 64-bit hash means ≤12.5% of bits differ,
which empirically distinguishes "same slide with minor rendering variation" (distance
< 5) from "new slide content" (distance ≥ 15) with a comfortable margin.

**Alternatives considered**:
- SSIM (Structural Similarity Index via `scikit-image`): More accurate for subtle
  changes, but 10–20× slower per comparison. For 14,400 frames (4-hour recording at
  1 fps), SSIM would add 30–60 minutes of processing. Rejected.
- Simple pixel difference (mean absolute difference): Too sensitive to JPEG encoding
  artifacts and slight timing differences in rendering. Rejected.
- MD5/SHA hash of raw pixels: Zero tolerance for any rendering variation; would
  produce false positives on every re-render. Rejected.

**De-duplication**: The `frame_hash` stored in `SlideOccurrence` is the pHash hex
string. When a second occurrence of a slide is detected (same pHash within
threshold), the new occurrence references the same `slide_id` from the first
occurrence. The SHA-256 of the frame image bytes (not the pHash) is the cache key
for vision model calls, since SHA-256 gives exact-match guarantees needed for
billing correctness.

---

## 4. Vision LLM for Slide Content Extraction

**Decision**: `claude-haiku-4-5-20251001` as the default vision model (fast, low
cost); `claude-sonnet-4-6` available via config for complex visuals.

**Rationale**: Most corporate presentation slides are text-heavy. Haiku handles
text extraction and simple chart descriptions well at a fraction of Sonnet's cost.
Sonnet is available as a config upgrade for recordings with complex diagrams or
dense infographics.

**Prompt structure** (structured JSON output requested):

```
You are extracting structured content from a presentation slide screenshot.

Return JSON with exactly these fields:
- title: the slide title (string, empty string if none)
- bullets: list of bullet point texts, preserving nesting as " • " prefixes (string[])
- visual_description: plain-language description of any charts, diagrams, images,
  or non-text content (string, empty string if text-only)
- raw_ocr: all text visible on the slide, in reading order (string)

Slide image attached.
```

**Response validation**: Response is parsed as JSON and validated against
`SlideContent` Pydantic model before caching. If validation fails (malformed JSON
or missing fields), the slide falls back to OCR.

**Cost tracking**: Tokens from each API response are summed into a running
`cumulative_cost_usd` counter. When this exceeds `budget_ceiling_usd`, the
`understanding` stage switches to OCR mode for all remaining slides.

**Alternatives considered**:
- GPT-4V / GPT-4o: Capable but outside the Anthropic SDK stack already required for
  synthesis. Rejected for consistency.
- Local vision model (LLaVA, Qwen-VL): Would eliminate API cost but requires GPU
  hardware not guaranteed on user's machine. Rejected.

---

## 5. OCR Fallback

**Decision**: `pytesseract` (Python wrapper for Tesseract 4+).

**Rationale**: Tesseract 4 with LSTM engine is accurate for clean, high-contrast
slide text. Tesseract is available on all target platforms via package manager.
`pytesseract` has no additional runtime dependencies beyond the Tesseract binary.

**Post-processing**: Raw OCR output is split into lines. First non-empty line is
treated as the title; subsequent lines become bullets. `visual_description` is
always empty string for OCR-processed slides (Tesseract cannot describe images).

**Alternatives considered**:
- EasyOCR: Better for non-Latin scripts and low-quality scans, but adds a ~500 MB
  PyTorch dependency. Out of proportion for English corporate slides. Rejected.
- AWS Textract / Google Vision OCR: API cost and network dependency; defeats the
  purpose of the fallback. Rejected.

---

## 6. Configuration Format

**Decision**: TOML via Python 3.11's built-in `tomllib`.

**Rationale**: TOML supports inline comments (unlike JSON), is less error-prone
than YAML (no implicit type coercion), and requires no external dependency in
Python 3.11+. The `config.toml` file committed to the repo documents all defaults;
users override in `~/.config/notetaker/config.toml`.

**Loading order**:
1. Compiled-in defaults (Python dataclass defaults in `config.py`)
2. Repo-root `config.toml` (if present)
3. `~/.config/notetaker/config.toml` (user overrides)
4. Environment variables `NOTETAKER_<SECTION>_<KEY>` (CI/CD or secrets)
5. CLI flags (`--budget-ceiling`, `--debug`, etc.)

---

## 7. URL-Keyed Cache

**Decision**: `~/.local/share/notetaker/cache/<url_sha256>/` with per-stage
subdirectories.

**URL normalisation**: Strip query-string tracking parameters before hashing to
avoid cache misses on the same recording URL with different tracking tokens.
Canonical form: scheme + host + path only.

**Cache layout**:
```
cache/<url_sha256>/
├── meta.json              # {url, captured_at, schema_versions}
├── capture/
│   ├── frames/            # <timestamp_ms>.jpg files
│   ├── frames_manifest.json
│   └── transcript.json    # schema v1
├── extraction/
│   └── slide_timeline.json
├── understanding/
│   └── slide_content.json
└── synthesis/
    ├── aligned_segments.json
    ├── summary.md
    └── summary.json
```

**Re-run logic**: Each stage checks for its output file's existence and schema
version match before executing. If present and version matches, the stage is
skipped. `--force` flag bypasses the check for the specified stage and all
downstream stages.

**Retention**: On each pipeline run, a cleanup pass removes cache directories
whose `meta.json` `captured_at` is older than `retention_days`. Cleanup runs
after the main pipeline completes, not before (to avoid deleting the current run).

---

## 8. Structured Logging

**Decision**: `structlog` with JSON renderer for `format = "json"` and
`ConsoleRenderer` for `format = "console"` (default).

**Context binding**: At stage entry, a `structlog.contextvars.bind_contextvars()`
call adds `stage`, `recording_url_hash`, and `run_id` to all log records produced
within that stage, without threading them through every function signature.

**Log levels**:
- `DEBUG`: Frame-by-frame decisions, pHash values, individual API calls
- `INFO`: Stage start/end, slide counts, cost summary
- `WARNING`: OCR fallback activated, transcript panel not found
- `ERROR`: Unrecoverable stage failure with exception traceback

---

## 9. Retry Mechanism

**Decision**: Custom `@retry(attempts: int, delay: float)` decorator wrapping any
function that calls an external API or network resource.

**Behaviour**: On exception, waits `retry_delay_seconds` (fixed, not exponential)
and retries up to `retry_count` times. After exhausting retries, re-raises the
original exception. Each retry is logged at DEBUG level.

**Fixed vs exponential backoff**: Fixed delay is appropriate here. The primary
failure mode is a brief API rate-limit or network blip, not resource contention
that benefits from spread-out backoff. Exponential backoff adds complexity without
measurable benefit for retry counts of 1–5.

**Scope**: Applied to `vision.py` (Anthropic API calls) and the Playwright HTTP
fetch inside the Zoom adapter. Not applied to local file operations.
