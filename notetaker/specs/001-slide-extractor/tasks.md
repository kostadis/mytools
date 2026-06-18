---
description: "Task list for Meeting Recording Slide Extractor"
---

# Tasks: Meeting Recording Slide Extractor

**Input**: Design documents from `specs/001-slide-extractor/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: Contract tests (T014, T022, T029, T035) and golden fixture (T048) are
included as constitutionally required (Articles VII.1 and VII.2). Vision API calls
are mocked by default; use `--live-api` marker to run against the real API.

**Organization**: Tasks are grouped by user story to enable independent
implementation and delivery of each phase.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (no dependencies on incomplete tasks, different files)
- **[Story]**: Which user story this task belongs to (US1–US4)
- Paths are relative to repository root (`src/notetaker/` prefix assumed throughout)

---

## Phase 1: Setup

**Purpose**: Project scaffold and shared infrastructure.

- [X] T001 Create pyproject.toml with project metadata and all dependencies: playwright, imagehash, Pillow, pytesseract, anthropic, pydantic>=2, structlog, typer, pytest, pytest-asyncio
- [X] T002 Create src/notetaker/__init__.py and the package directory tree: stages/capture/adapters/, stages/extraction/, stages/understanding/, stages/synthesis/, contracts/, utils/
- [X] T003 [P] Create config.toml at repo root with all tunables, inline descriptions, and defaults per plan.md Configuration Schema section
- [X] T004 [P] Create src/notetaker/config.py: Config dataclass with nested sections; load order: compiled defaults → config.toml → ~/.config/notetaker/config.toml → env vars → CLI flags
- [X] T005 [P] Create src/notetaker/utils/logging.py: structlog setup with JSON and ConsoleRenderer modes; bind_contextvars helper for stage/recording_url_hash/run_id
- [X] T006 [P] Create src/notetaker/utils/retry.py: @retry(attempts, delay) decorator; logs each retry at DEBUG; re-raises after exhaustion
- [X] T007 [P] Create src/notetaker/cache.py: URL normalisation (strip tracking params → sha256), per-stage subdirectory layout, cache hit check (output file present + schema version match), --force bypass

---

## Phase 2: Foundational — Contract Models

**Purpose**: Pydantic v2 models for all five inter-stage contracts. These are the
only cross-stage imports permitted (Article I.1). Must be complete before any stage
implementation begins.

**⚠️ CRITICAL**: No stage work can begin until all contract models exist.

- [X] T008 [P] Create src/notetaker/contracts/transcript.py: Utterance and TranscriptSchema Pydantic models matching transcript.schema.json; schema_version = "1.0"
- [X] T009 [P] Create src/notetaker/contracts/slide_timeline.py: SlideOccurrence and SlideTimelineSchema Pydantic models matching slide_timeline.schema.json; schema_version = "1.0"
- [X] T010 [P] Create src/notetaker/contracts/slide_content.py: SlideContent and SlideContentSchema Pydantic models matching slide_content.schema.json; ExtractionMethod enum ("vision" | "ocr"); schema_version = "1.0"
- [X] T011 [P] Create src/notetaker/contracts/aligned_segments.py: AlignedSegment, SlideContentRef, and AlignedSegmentsSchema Pydantic models matching aligned_segments.schema.json; schema_version = "1.0"
- [X] T012 [P] Create src/notetaker/contracts/summary.py: PerSlideSummary and SummarySchema Pydantic models matching summary.schema.json; schema_version = "1.0"
- [X] T012a [P] Create src/notetaker/contracts/frames_manifest.py: FrameEntry and FramesManifestSchema Pydantic models matching frames_manifest.schema.json; schema_version = "1.0"
- [X] T013 Create src/notetaker/cli.py: Typer app with five subcommand stubs (capture, extract, understand, synthesise, run); each accepts a url: str argument and --debug/--force flags; loads Config; configures logging

**Checkpoint**: All contract models exist. Stage implementation can begin in parallel.

---

## Phase 3: User Story 1 — Captured Transcript from Recording Playback (Priority: P1) 🎯 MVP

**Goal**: `notetaker capture <url>` opens a headed Playwright browser, screen-records
frames and scrapes the Zoom transcript panel during user-initiated playback, and
writes `transcript.json` + `frames_manifest.json` to the URL-keyed cache.

**Independent Test**: `notetaker capture <zoom-url>` against a known recording
produces a `transcript.json` with non-empty `utterances` and a `frames_manifest.json`
listing timestamped frame files. No slide processing required.

### Contract Test for User Story 1

- [X] T014 [P] [US1] Create tests/contract/test_transcript_contract.py: verify TranscriptSchema round-trips valid JSON; verify validation rejects missing fields, end_seconds ≤ start_seconds, empty text

### Implementation for User Story 1

- [X] T015 [P] [US1] Create src/notetaker/stages/capture/base.py: CaptureAdapter ABC with abstract method capture(url: str, config: Config) -> tuple[Path, Path] (frames_manifest, transcript)
- [X] T016 [P] [US1] Create src/notetaker/stages/capture/adapters/zoom.py: ZoomAdapter class skeleton extending CaptureAdapter; define SLIDE_SELECTOR, TRANSCRIPT_PANEL_SELECTOR, TRANSCRIPT_LINE_SELECTOR constants at top of file
- [X] T017 [US1] Implement ZoomAdapter._open_browser() in src/notetaker/stages/capture/adapters/zoom.py: Playwright launch_persistent_context() using config.capture.browser_profile_path; headed mode; navigate to url; wait for Zoom player to load; detect login-wall and raise CaptureAuthError if found
- [X] T018 [US1] Implement ZoomAdapter._capture_frames() in src/notetaker/stages/capture/adapters/zoom.py: async loop calling page.locator(SLIDE_SELECTOR).screenshot() every frame_sample_rate_seconds; save to cache/capture/frames/<timestamp_ms>.jpg; handle playback pause (log gap, resume on DOM change)
- [X] T019 [US1] Implement ZoomAdapter._scrape_transcript() in src/notetaker/stages/capture/adapters/zoom.py: poll transcript panel for new li elements each frame_sample_rate_seconds; parse "HH:MM:SS Speaker: text" pattern; accumulate Utterance list; handle missing panel (set transcript_unavailable=True, log WARN)
- [X] T020 [US1] Implement ZoomAdapter.capture() in src/notetaker/stages/capture/adapters/zoom.py: orchestrate _open_browser + concurrent _capture_frames + _scrape_transcript; on completion write frames_manifest.json (FramesManifest schema) and transcript.json (TranscriptSchema) to cache; validate outputs against Pydantic models before writing
- [X] T021 [US1] Wire capture subcommand in src/notetaker/cli.py: call ZoomAdapter.capture(); print live progress (frame count, transcript line count); surface CaptureAuthError with actionable message; show cache output path on success

**Checkpoint**: `notetaker capture <url>` works end-to-end. US1 is independently deliverable.

---

## Phase 4: User Story 2 — Slide Timeline from Recorded Meeting (Priority: P2)

**Goal**: `notetaker extract <url>` reads the captured frame sequence, computes pHash
per frame, detects slide transitions by Hamming distance, de-duplicates recurring
slides, and writes `slide_timeline.json` to the cache.

**Independent Test**: Given a populated `frames_manifest.json` from US1, `notetaker
extract <url>` produces a `slide_timeline.json` with at least one SlideOccurrence
containing valid start/end timestamps, frame_path, frame_hash, and frame_sha256.

### Contract Test for User Story 2

- [X] T022 [P] [US2] Create tests/contract/test_slide_timeline_contract.py: verify SlideTimelineSchema round-trips valid JSON; verify frame_sha256 pattern validation; verify end_seconds > start_seconds

### Implementation for User Story 2

- [X] T023 [P] [US2] Create src/notetaker/stages/extraction/frame_sampler.py: load frames_manifest.json from cache; validate against FramesManifestSchema Pydantic model before processing; yield FrameEntry records at sample_every_n_frames cadence
- [X] T024 [P] [US2] Create src/notetaker/stages/extraction/slide_detector.py: SlideDetector class; compute imagehash.phash() per frame; compare consecutive hashes with Hamming distance; emit SlideOccurrence on transition; assign slide_id by matching to prior occurrences within threshold; compute frame_sha256 for cache key
- [X] T025 [US2] Implement SlideDetector.detect() in src/notetaker/stages/extraction/slide_detector.py: full detection loop returning SlideTimelineSchema; handle empty frame sequence (return empty slides list with log WARN); log each transition decision at DEBUG (frame path, hash, distance)
- [X] T026 [US2] Write slide_timeline.json to cache in src/notetaker/stages/extraction/__init__.py: validate against SlideTimelineSchema before writing; log slide count, unique slide count, transition timestamps at INFO
- [X] T027 [US2] Add unit tests for SlideDetector in tests/unit/test_slide_detector.py: identical frames → no transition; different frames → transition recorded; same slide reappearing → reuses slide_id; empty input → empty timeline
- [X] T028 [US2] Wire extract subcommand in src/notetaker/cli.py: call extraction stage; print slide count and unique slide count; show cache output path

**Checkpoint**: `notetaker extract <url>` works end-to-end. US2 independently deliverable.

---

## Phase 5: User Story 3 — Slide Content Extraction (Priority: P3)

**Goal**: `notetaker understand <url>` iterates unique slides from the slide timeline,
sends each to Claude Haiku (or falls back to pytesseract when budget is exhausted),
and writes `slide_content.json` to the cache. Identical slides across runs are never
re-processed.

**Independent Test**: Given a populated `slide_timeline.json` from US2, `notetaker
understand <url>` produces a `slide_content.json` where every unique slide_id has a
SlideContent record with non-empty raw_ocr and an extraction_method value. A second
run with the same URL skips all API calls (uses cache).

### Contract Test for User Story 3

- [X] T029 [P] [US3] Create tests/contract/test_slide_content_contract.py: verify SlideContentSchema round-trips valid JSON; verify extraction_method enum; verify budget/cost fields are non-negative

### Implementation for User Story 3

- [X] T030 [P] [US3] Create src/notetaker/stages/understanding/vision.py: extract_slide_vision(frame_path, frame_sha256, config) -> SlideContent; build structured extraction prompt; call anthropic client with vision; parse JSON response; validate against SlideContent; apply @retry decorator; mock-friendly (accept client as dependency)
- [X] T031 [P] [US3] Create src/notetaker/stages/understanding/ocr.py: extract_slide_ocr(frame_path) -> SlideContent; run pytesseract.image_to_string(); heuristic split (first line = title, remainder = bullets); extraction_method = "ocr"; estimated_cost_usd = 0.0
- [X] T032 [US3] Implement understanding stage orchestration in src/notetaker/stages/understanding/__init__.py: load slide_timeline.json and validate against SlideTimelineSchema Pydantic model; for each unique slide_id check frame_sha256 cache; if miss → call vision (if budget remains) or ocr; accumulate total_cost_usd; log budget status at INFO after each call; log OCR fallback activation at WARNING
- [X] T033 [US3] Write slide_content.json to cache in src/notetaker/stages/understanding/__init__.py: validate against SlideContentSchema before writing; log total cost, vision count, OCR count
- [X] T034 [US3] Wire understand subcommand in src/notetaker/cli.py: call understanding stage; display per-slide extraction method and running cost; warn clearly if OCR fallback was triggered

**Checkpoint**: `notetaker understand <url>` works end-to-end. US3 independently deliverable.

---

## Phase 6: User Story 4 — Slide-Scaffolded Meeting Summary (Priority: P4)

**Goal**: `notetaker synthesise <url>` aligns slides with transcript utterances by
timestamp, generates a per-slide summary via Claude Sonnet, then compiles an overall
summary with action items and decisions. Writes `summary.json` and `summary.md`.
`notetaker run <url>` executes all four stages in sequence.

**Independent Test**: Given populated `slide_content.json` and `transcript.json`,
`notetaker synthesise <url>` produces a `summary.md` where each slide has a named
section with transcript content. Unanchored discussion appears under "General
Discussion". A second run with unchanged inputs uses cached output without API calls.

### Contract Tests for User Story 4

- [X] T035 [P] [US4] Create tests/contract/test_aligned_segments_contract.py: verify AlignedSegmentsSchema round-trips; verify null slide_id allowed (general_discussion); verify duration_seconds ≥ 0

### Implementation for User Story 4

- [X] T036 [P] [US4] Create src/notetaker/stages/synthesis/aligner.py: Aligner class; align_segments(timeline: SlideTimelineSchema, transcript: TranscriptSchema) -> AlignedSegmentsSchema; validate both input schemas via Pydantic before processing; overlap detection by [start, end) interval intersection; collect unanchored utterances before first slide and after last slide into general_discussion segments
- [X] T037 [P] [US4] Create src/notetaker/stages/synthesis/summarizer.py: Summarizer class; summarise_segment(segment: AlignedSegment, config) -> PerSlideSummary using Claude claude-sonnet-4-6; compile_summary(segments, per_slide, config) -> SummarySchema with overall_summary, action_items, decisions; accumulate synthesis_cost_usd per API call; apply @retry; mock-friendly
- [X] T038 [US4] Implement Aligner.align_segments() in src/notetaker/stages/synthesis/aligner.py: full interval-overlap algorithm; validate AlignedSegmentsSchema output against Pydantic model before returning; handle transcript_unavailable=True (empty transcript_text for all segments); log segment count and total anchored vs. unanchored duration at INFO
- [X] T039 [US4] Implement Summarizer.summarise() orchestration in src/notetaker/stages/synthesis/summarizer.py: iterate AlignedSegments; call summarise_segment per segment; single compile_summary call; accumulate and log total synthesis_cost_usd at INFO; validate SummarySchema before returning
- [X] T040 [US4] Add unit tests for Aligner in tests/unit/test_aligner.py: slide with overlapping utterances → correct transcript_text; unanchored utterances → general_discussion segments; no transcript (transcript_unavailable) → empty transcript_text on all segments
- [X] T041 [US4] Write aligned_segments.json and summary.json to cache in src/notetaker/stages/synthesis/__init__.py: validate both against schemas before writing
- [X] T042 [US4] Write summary.md from SummarySchema in src/notetaker/stages/synthesis/__init__.py: one H2 section per per_slide_summary (title = slide_title); include key_points as bullets; append ## Action Items and ## Decisions sections at end
- [X] T043 [US4] Wire synthesise and run subcommands in src/notetaker/cli.py: synthesise calls synthesis stage only; run calls all four stages in order (capture → extract → understand → synthesise); both print final summary.md path on success

**Checkpoint**: `notetaker run <url>` produces summary.md. Full pipeline end-to-end deliverable.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Hardening, observability, retention, and the constitutional golden fixture.

- [X] T044 [P] Add unit tests for cache URL normalisation and retention in tests/unit/test_cache.py: URL with tracking params normalises to same hash as clean URL; cache dirs older than retention_days are deleted; --force bypasses cache hit check
- [X] T045 [P] Add unit tests for @retry decorator in tests/unit/test_retry.py: succeeds on first try (no retry); retries on transient exception up to limit; raises after exhaustion; logs each retry
- [X] T046 Implement cache retention cleanup in src/notetaker/cache.py: after pipeline completion, scan cache root for meta.json files older than retention_days; delete those directories; log count of purged entries at INFO
- [X] T047 Add --debug flag implementation across all stages: when debug=True, skip frame and intermediate artifact cleanup; write raw API response JSON alongside slide_content.json; write alignment table CSV alongside aligned_segments.json
- [X] T048 [P] Create tests/integration/test_full_pipeline.py: golden fixture scaffold with synthetic frames_manifest.json + transcript.json fixture; run extraction, understanding (mocked vision), and synthesis; assert summary.json contains expected slide titles and at least one action item
- [X] T049 [P] Update specs/001-slide-extractor/quickstart.md with finalized Zoom selector values, common troubleshooting entries, and instructions for running the integration test with --live-api

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — begin immediately; T003–T007 all parallel
- **Foundational (Phase 2)**: Depends on Phase 1 completion — T008–T012, T012a all parallel; T013 depends on T004
- **User Stories (Phase 3–6)**: All depend on Phase 2 completion (contracts must exist)
  - US1 (Phase 3): No story dependencies; delivers standalone transcript MVP
  - US2 (Phase 4): Depends on Phase 3 completion (reads frames_manifest.json)
  - US3 (Phase 5): Depends on Phase 4 completion (reads slide_timeline.json)
  - US4 (Phase 6): Depends on Phase 5 completion (reads slide_content.json + transcript.json)
- **Polish (Phase 7)**: Depends on all user story phases

### Within Each User Story

- Contract test [P] can run alongside base/skeleton tasks
- Base/adapter skeleton tasks [P] can run in parallel
- Orchestration tasks depend on their component implementations
- CLI wiring is always last within a story

### Parallel Opportunities

```bash
# Phase 1 — all parallel after T001, T002:
T003  T004  T005  T006  T007

# Phase 2 — all parallel after Phase 1:
T008  T009  T010  T011  T012  T012a
then T013

# Phase 3 (US1) — parallel start:
T014  T015  T016
then T017 → T018, T019 (parallel) → T020 → T021

# Phase 4 (US2) — parallel start:
T022  T023  T024
then T025 → T026 → T027 (parallel with T026) → T028

# Phase 5 (US3) — parallel start:
T029  T030  T031
then T032 → T033 → T034

# Phase 6 (US4) — parallel start:
T035  T036  T037
then T038, T039 (parallel) → T040 (parallel with T039) → T041 → T042 → T043

# Phase 7 — all parallel:
T044  T045  T046  T047  T048  T049
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational contract models (T008–T013)
3. Complete Phase 3: User Story 1 (T014–T021)
4. **STOP AND VALIDATE**: `notetaker capture <url>` produces transcript.json
5. Deploy/share if transcript-only value is sufficient

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 complete → transcript from recording URL (**working pipeline**)
3. US2 complete → slide timeline with timestamps
4. US3 complete → enriched slide content (vision + OCR)
5. US4 complete → full slide-scaffolded summary (**full value delivered**)
6. Polish → hardened, tested, documented

---

## Notes

- `[P]` tasks have no dependencies on incomplete tasks in the same phase and touch different files
- `[Story]` label maps every task to a specific user story for traceability
- Vision API calls in tests are mocked by default; pass `--live-api` pytest marker to call the real API
- Zoom CSS selectors in `zoom.py` are the only Zoom-specific code in the entire codebase (Article I.2)
- All numeric thresholds read from config — no hardcoded literals in stage code (Article IV.1)
