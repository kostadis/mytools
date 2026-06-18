# Feature Specification: Meeting Recording Slide Extractor

**Feature Branch**: `001-slide-extractor`
**Created**: 2026-05-08
**Status**: Draft
**Input**: User description: "Meeting Recording Slide Extractor — extract slides with
timestamps from streamed meeting recordings and combine with transcripts for richer
summaries"

## Clarifications

### Session 2026-05-08

- Q: How does the pipeline authenticate and retrieve video/transcript from Zoom? → A: Screen capture during playback — the pipeline cannot download the video. Instead, the user plays the Zoom recording in their browser; the pipeline screen-records frames during playback to detect slide transitions and scrapes the transcript from the Zoom viewer's transcript panel.
- Q: What is the expected source and quality bar for the transcript? → A: Scraped from the Zoom viewer's transcript panel during playback; no video/audio download or ASR is in scope.
- Q: How long is acceptable for post-capture processing (slide extraction + understanding + synthesis)? → A: Under 10 minutes for a typical 1-hour meeting with 20–40 slides; meetings commonly run 2–4 hours, so the target scales approximately linearly with unique slide count.
- Q: How should the pipeline identify and relate runs of the same recording? → A: URL-keyed — each unique Zoom viewer URL has one cached run; re-running the same URL overwrites the prior cached artifacts.
- Q: When a transient failure occurs during post-capture processing, should the pipeline retry automatically or fail fast? → A: Auto-retry with a configurable fixed limit (default: 3 attempts per call) before failing the stage.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Captured Transcript from Recording Playback (Priority: P1)

A user opens a Zoom Cloud Recording URL in their browser, starts playback, and
triggers the pipeline's Capture stage. The pipeline screen-records the playback
session, scraping the Zoom viewer's live transcript panel as the recording plays.
At the end of playback, the user has a clean, timestamped `transcript.json` they
can search, share, or feed into downstream stages — without any slides extracted yet.

**Why this priority**: The scraped transcript is the minimum viable product. It
delivers value independently and is the foundation every downstream stage depends on.
Phase 1 must stand alone.

**Independent Test**: With a known Zoom recording playing in the browser, run the
Capture stage and verify it produces a `transcript.json` containing speaker turns and
timestamps. No slide content or summary is required for this story to pass.

**Acceptance Scenarios**:

1. **Given** the user opens a valid Zoom viewer URL and starts playback,
   **When** the pipeline's Capture stage runs alongside the playback session,
   **Then** it produces a `transcript.json` containing all transcript lines visible
   in the Zoom viewer panel, with timestamps accurate to within 5 seconds.

2. **Given** a Zoom recording whose transcript panel is not available or empty,
   **When** the Capture stage completes,
   **Then** the pipeline continues with a slide-only capture and notes clearly in
   all downstream outputs that no transcript was available.

3. **Given** a URL the user is not authorized to view (Zoom shows an access error),
   **When** the pipeline attempts capture,
   **Then** it fails immediately with a clear error identifying the access problem;
   it does not attempt to bypass Zoom's access controls.

---

### User Story 2 - Slide Timeline from Recorded Meeting (Priority: P2)

A user who already has a transcript (or runs the full pipeline) receives a slide
timeline: a list of unique slides that appeared in the meeting, each with the time
range during which it was displayed.

**Why this priority**: The slide timeline is the core artifact that differentiates this
pipeline from transcript-only tools. Without it, the summary stage cannot use slides
as scaffolding.

**Independent Test**: Given a pre-captured frame sequence from Story 1, run only the
Slide Extraction stage against it and verify it produces a slide timeline file with
at least one unique slide entry containing a start time, end time, and a reference to
the slide image. No transcript alignment or summary is required.

**Acceptance Scenarios**:

1. **Given** a captured frame sequence,
   **When** the Slide Extraction stage runs,
   **Then** it produces a slide timeline listing each unique slide with its start and
   end timestamps, and duplicate or near-duplicate frames are merged rather than
   listed separately.

2. **Given** a meeting where the same slide is shown twice (e.g., an agenda slide
   displayed at the start and revisited mid-meeting),
   **When** slide extraction completes,
   **Then** each occurrence is recorded as a separate timeline entry, but the slide
   content is de-duplicated (processed once, referenced twice).

3. **Given** a recording where the entire meeting was conducted without any shared
   screen or slides,
   **When** slide extraction runs,
   **Then** the pipeline produces an empty slide timeline and continues to the
   summary stage, which produces a transcript-only summary.

---

### User Story 3 - Slide Content Extraction (Priority: P3)

For each unique slide in the timeline, the pipeline extracts the slide's content:
its text, logical structure (headings, bullets, tables), and a description of key
non-text visuals. This enriched content is stored alongside the slide image for use
in summary generation.

**Why this priority**: Content extraction is required before the summary stage can
attribute meaning to slides. Without it, the summary can only say "a slide was shown"
rather than what the slide contained.

**Independent Test**: Given a slide timeline produced by Story 2, run only the Slide
Understanding stage and verify it produces a content record for each unique slide
containing at least extracted text and a structural description. No summary is
required.

**Acceptance Scenarios**:

1. **Given** a slide timeline with N unique slides,
   **When** the Slide Understanding stage runs,
   **Then** it produces a content record for each unique slide containing extracted
   text (via OCR or vision model), a structural summary, and any identified key visuals.

2. **Given** a slide image that was already processed in a prior run (content hash
   matches a cached result),
   **When** the Slide Understanding stage encounters that image,
   **Then** it uses the cached content record and does not invoke the vision model
   again.

3. **Given** the vision LLM budget has been exhausted for the current run,
   **When** additional slides require processing,
   **Then** remaining slides are processed using OCR only, the output clearly notes
   which slides used OCR fallback, and the pipeline does not fail.

---

### User Story 4 - Slide-Scaffolded Meeting Summary (Priority: P4)

A user receives a structured meeting summary where each slide anchors a section of
the narrative. Each section contains the slide's key content followed by the relevant
discussion from the transcript — giving a complete picture of what was presented and
what was said about it.

**Why this priority**: This is the end-to-end value proposition. Stories 1–3 are
infrastructure; this story is what the user actually wanted when they started the
pipeline.

**Independent Test**: Given pre-produced slide content records and an aligned
transcript from Stories 2–3, run only the Synthesis stage and verify it produces a
structured summary document where each slide corresponds to a named section containing
slide content and related transcript excerpts.

**Acceptance Scenarios**:

1. **Given** slide content records and a timestamped transcript,
   **When** the Synthesis stage runs,
   **Then** it produces a structured summary document where each unique slide anchors
   a section, and each section contains the slide's extracted content alongside the
   transcript segments spoken while the slide was displayed.

2. **Given** a prior failed Synthesis run (cached slide content and transcripts are
   intact),
   **When** Synthesis is re-run,
   **Then** it completes without re-running the Capture stage or re-processing slides,
   using only the cached artifacts.

3. **Given** a meeting with both slides and transcript segments that do not align to
   any slide (e.g., discussion before the first slide),
   **When** the summary is generated,
   **Then** unanchored transcript segments appear in a "General Discussion" section
   rather than being dropped.

---

### Edge Cases

- Recording URL is invalid or expired → pipeline fails at Capture with a clear error
  identifying the URL as the problem; no intermediate artifacts are written.
- User is not logged into Zoom in their browser → pipeline detects the Zoom login
  screen rather than the viewer and fails with a clear error instructing the user to
  log in first; it does not attempt authentication on their behalf.
- User pauses or stops playback mid-capture → pipeline notes the gap in the frame
  sequence and resumes scraping when playback resumes; it does not fail.
- Zoom transcript panel is hidden or not populated → pipeline captures frames only
  and produces a slide-only summary; the absence of transcript is noted in output.
- Transcript is unavailable (no captions) → pipeline continues; summary notes
  absence of transcript in each slide section.
- Entire meeting is a single shared slide → one unique slide entry with full-meeting
  timestamps; summary has one slide section.
- Recording is very short (under 2 minutes) → pipeline completes with a warning that
  the summary may be sparse; no failure.
- Recording exceeds 4 hours → pipeline warns the user that behavior beyond 4 hours
  is best-effort and continues; it does not refuse to run.
- Vision budget exhausted mid-run → OCR fallback for remaining slides; summary
  clearly marks which slides used OCR-only extraction.
- Intermediate artifact from a prior run is corrupt → the affected stage re-runs
  from its last valid predecessor rather than propagating corrupt data.
- User has no disk space for intermediate artifacts → Capture stage fails early with
  a space estimate and a clear message; no partial artifacts are left behind.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST accept a Zoom viewer URL as input. The Capture stage
  operates by screen-recording the user's browser while the recording plays: it
  captures timestamped frames of the presentation area to detect slide transitions,
  and simultaneously scrapes the Zoom viewer's transcript panel to produce a
  structured `transcript.json`. No video file is downloaded; the outputs of the
  Capture stage are a sequence of timestamped screen frames and `transcript.json`.
  If the Zoom transcript panel is absent or empty, the pipeline continues without a
  transcript and notes this clearly in all downstream outputs.

- **FR-002**: The system MUST identify unique slides from the captured frame sequence
  and produce a slide timeline listing each unique slide with its start and end
  timestamps.

- **FR-003**: The system MUST extract the text content, structural layout, and key
  visual descriptions from each unique slide.

- **FR-004**: The system MUST align each slide's time range with the corresponding
  segments of the transcript to produce a set of aligned segments.

- **FR-005**: The system MUST produce a structured summary document that uses slides
  as section anchors and includes relevant transcript content for each slide.

- **FR-006**: The system MUST support a pluggable capture adapter model: adding a new
  recording platform (e.g., Gong, Chorus) MUST require changes only within the Capture
  stage adapter, with no modifications to Slide Extraction, Slide Understanding, or
  Synthesis.

- **FR-007**: The system MUST cache all stage outputs keyed by the Zoom viewer URL.
  A second invocation of the pipeline on the same URL MUST reuse cached intermediate
  artifacts (captured frames, transcript, slide timeline, slide content) rather than
  re-running expensive earlier stages, unless the user explicitly requests a full
  re-capture. Slide content is additionally de-duplicated by image content hash so
  that visually identical slides across different recordings are never sent to the
  vision model more than once.

- **FR-008**: The system MUST make each stage independently re-runnable against
  cached intermediate artifacts from a prior run of the same URL.

- **FR-009**: The system MUST report the cost of each run, including the number of
  vision model calls made and an estimated spend in the currency configured.

- **FR-010**: The system MUST enforce a configurable per-run budget ceiling for paid
  API calls and fall back to OCR-only slide processing when the ceiling is reached.

- **FR-011**: The system MUST provide a debug mode that preserves all intermediate
  artifacts (extracted frames, OCR output, raw vision model responses, alignment
  tables) on disk for inspection after the run.

- **FR-012**: Captured frames and transcripts MUST be subject to a
  configurable retention policy; the system MUST automatically delete artifacts older
  than the configured retention period.

- **FR-013**: The system MUST produce structured, machine-parseable logs for every
  stage, recording inputs, outputs, key decisions, elapsed time, and resource cost.

- **FR-014**: The system MUST use the user's own platform credentials to access
  recordings; it MUST NOT attempt to bypass authentication, DRM, or platform access
  controls.

- **FR-015**: The system MUST automatically retry failed API or network calls during
  post-capture processing up to a configurable limit (default: 3 attempts) before
  failing the stage. Retry count MUST be a named configuration parameter per
  Article IV.1. Transient failures within the retry limit MUST be logged but MUST
  NOT surface as errors to the user.

### Key Entities

- **Recording**: A past meeting recording identified by a Zoom viewer URL. The
  pipeline does not download the recording; it captures data from the recording
  during user-initiated browser playback.

- **CaptureSession**: The process of screen-recording frames and scraping the
  transcript panel during one complete playback of a Recording. Produces a
  FrameSequence and a raw transcript as its outputs. Each Recording URL has at most
  one active CaptureSession cache; a new capture overwrites the prior one.

- **Transcript**: A time-ordered sequence of utterances, each with a speaker
  identifier, start time, end time, and spoken text.

- **SlideTimeline**: An ordered list of slide occurrences, each linking to a unique
  slide and carrying a start time and end time.

- **UniqueSlide**: A distinct slide image (de-duplicated across the recording),
  identified by a content hash, with a reference to its source frames.

- **SlideContent**: The extracted information for a unique slide: verbatim text, a
  structural summary (headings, bullets, tables), and descriptions of key non-text
  visuals.

- **AlignedSegment**: The pairing of a slide occurrence with the transcript utterances
  that overlapped its display window.

- **MeetingSummary**: The final output document structured as a sequence of sections,
  each anchored to a slide (or to unanchored discussion), containing slide content
  and relevant transcript excerpts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can go from a valid meeting recording URL to a structured summary
  by running a single command with no manual intermediate steps.

- **SC-002**: Re-running the Synthesis stage alone after a completed run (unchanged
  recording and slides) finishes without downloading any video or re-processing any
  slide image.

- **SC-003**: Adding a new recording platform requires changes only within the Capture
  adapter layer and no modifications to any other stage's code.

- **SC-004**: A failed run's log output and preserved artifacts are sufficient to
  identify the failing stage and the cause of failure without re-executing any stage.

- **SC-005**: For a typical 1-hour Zoom recording presenting 20–40 slides, the system
  produces a slide timeline where every distinct slide visible in the recording is
  represented and no duplicate slides appear as separate entries.

- **SC-006**: When the per-run vision model budget is reached, the pipeline continues
  to completion using OCR fallback for remaining slides and clearly identifies which
  slides used each method in the output.

- **SC-007**: Post-capture processing (Slide Extraction + Slide Understanding +
  Synthesis) completes in under 10 minutes for a 1-hour recording with 20–40 unique
  slides, scaling approximately linearly with unique slide count for longer meetings
  (e.g., under 30 minutes for a 3-hour recording with ~80 unique slides).

## Assumptions

- The user must be logged into Zoom in their browser before starting the pipeline.
  The pipeline screen-records the browser during playback and does not manage logins
  or MFA — it requires an already-authenticated, already-open browser session.

- The initial supported platform is Zoom Cloud Recordings. Gong and Chorus support is
  planned but is out of scope for this specification.

- Recordings are available on the platform for at least the duration of the pipeline
  run (typically under 30 minutes); the pipeline does not handle recordings that
  expire or are revoked mid-run.

- Meetings typically run 1–4 hours. The pipeline MUST handle recordings up to 4
  hours without degradation. Recordings over 4 hours are out of scope for v1 and
  behavior for them is best-effort.

- The user's machine has sufficient local disk space to hold intermediate artifacts
  (captured frames + transcript JSON), estimated at 100–500 MB per recording depending
  on frame capture rate and meeting length — significantly less than a video download.

- Internet connectivity and an open, logged-in browser session are required during
  the Capture stage. Stages 2–4 (Slide Extraction, Understanding, Synthesis) can
  run fully offline against the captured frames and transcript.

- The Capture stage duration is bounded by playback speed. A 1-hour recording takes
  approximately 1 hour to capture unless the user plays it at increased speed (e.g.,
  1.5× or 2× on platforms that support it). Capture time is not a pipeline
  optimization target; it is inherent to the approach.

- The Zoom viewer's transcript panel displays auto-generated captions in real time
  during playback. The pipeline treats the scraped panel text as the authoritative
  transcript; it does not generate speech-to-text from audio.
- Summary output is delivered as a Markdown document. Structured JSON export is a
  future enhancement and is out of scope for v1.
