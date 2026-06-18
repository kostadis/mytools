# Feature Specification: Post-Capture Notes (Slides + Transcript → Notes)

**Feature Branch**: `003-post-capture-notes`
**Created**: 2026-05-09
**Status**: Draft
**Input**: User description: "Notetaker today tries to do everything in one `run`: capture frames, scrape the transcript live from the Zoom playback page, extract slides, run vision, and synthesise notes. The live transcript scrape is brittle (depends on an internal Zoom CSS class, gives up after 10s, polls a virtualized list during playback) and silently degrades the entire run when it misses. We propose splitting the transcript out of the live capture entirely. The supported flow becomes: (1) notetaker captures and understands the slides only, (2) the user pulls the transcript from the Zoom playback page using a small DevTools console snippet that already works reliably, (3) a new `notetaker notes` subcommand combines the two and produces polished Markdown notes via a single LLM render call."

## Clarifications

### Session 2026-05-09

- Q: When the single LLM call fails after the working doc has been assembled, what should the command do? → A: Retry with existing project retry policy; exit non-zero on persistent failure; leave working doc in place; log every attempt and the final outcome to the run log file.
- Q: Should the working doc and the notes file be subject to the existing 30-day cache retention purge? → A: No — both are exempt. Frames and slide-content artifacts continue to follow the existing cache retention policy; the working doc and notes file persist until the user removes them.
- Q: For v1 of `notetaker notes`, which transcript shapes does the parser have to accept? → A: Three shapes — the `scrape.js` block format, Zoom-downloaded WebVTT, and the existing `transcript.json` written by a successful live scrape. Format is auto-detected from the file content (with file extension as a hint).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Recover useful output when the live transcript scrape misses (Priority: P1)

The user has just finished a notetaker run on a long meeting recording. The pipeline reports success and writes a `summary.md`, but every section says "no transcript available for this segment" because the live transcript scraper failed to find the Zoom transcript panel. The user does not want to re-run an 80-minute capture. Instead, they want to obtain the transcript from the Zoom recording in their browser, hand it to notetaker, and get a useful set of meeting notes that combine the slides notetaker already extracted with the transcript they just pulled.

**Why this priority**: This is the failure-recovery path for the most common observed failure of the existing pipeline. Without it, an 80-minute capture produces no useful narrative output and the user has wasted a meeting's worth of time and a meaningful slice of API spend on the vision pass. With it, the same capture becomes recoverable in minutes.

**Independent Test**: Take a completed notetaker cache directory whose `transcript.json` is empty (or whose `summary.md` reports the transcript was unavailable), supply a separately-obtained transcript text file, and confirm a single command produces a polished `notes.md` whose section structure reflects the slide titles and whose narrative reflects the transcript content.

**Acceptance Scenarios**:

1. **Given** a notetaker cache directory exists for a recording, the cache contains populated slide content from the understanding stage, but the cache contains no transcript (or an empty transcript), **When** the user invokes the new notes command pointing at the cache and a transcript file they obtained from their browser, **Then** the command produces a Markdown notes file whose top-level structure uses slide titles as section anchors and whose body discusses what was actually said in the transcript.
2. **Given** the user has a transcript file but does not remember which cache directory matches their recording, **When** they invoke the command with the recording URL instead of a cache directory path, **Then** the command resolves the URL to the correct cache directory using the same convention notetaker already uses elsewhere, and proceeds.
3. **Given** a notetaker run completed but the live transcript scrape returned zero utterances, **When** the user reads the run's console output or its log file, **Then** they see a clearly-flagged warning that explains the live transcript was not captured and points them at the documented post-capture transcript-pull procedure, rather than seeing the run report unqualified "success".

---

### User Story 2 - One command to combine transcript and slides into polished notes (Priority: P1)

The user has the two inputs in hand — a notetaker cache (with extracted slide content) and a transcript text file. They do not want to read the slides JSON, hand-edit a working document, run separate scripts, or know the path conventions inside the cache. They want one command that takes the two inputs and produces notes that read like meeting minutes: an executive summary, sections organised by topic, named decisions and action items, and named open questions.

**Why this priority**: Without this, the feature is a developer-only workflow ("run script A, then script B"). Promoting it to a single subcommand makes it the documented happy path and brings it within reach of a user who has not opened the codebase.

**Independent Test**: From a fresh shell with only a transcript file and a recording URL, invoke a single notetaker subcommand and confirm a polished Markdown notes file is produced and its path is printed to the console.

**Acceptance Scenarios**:

1. **Given** a slide-content artifact exists in the cache for a recording and a transcript text file exists on disk, **When** the user runs the notes subcommand with those two inputs, **Then** a polished Markdown notes file is written to a stable, conventional location inside the cache and its absolute path is printed to the console.
2. **Given** the user has not specified an explicit output location, **When** the notes subcommand completes, **Then** the notes file is written next to the slide-content artifact inside the same cache directory (so future invocations and inspections find it without remembering a new path).
3. **Given** the notes subcommand has just produced a notes file, **When** the user opens the notes file in a plain text editor, **Then** they see at minimum: a meeting overview, named participants taken from transcript speakers, per-topic narrative sections that use slide titles as section headings, a list of decisions with attribution, a list of action items, and a list of open questions.
4. **Given** the LLM render call succeeded, **When** the command exits, **Then** the user sees a single line summarising the input and output token counts and the estimated cost of the call, so they can budget future runs.

---

### User Story 3 - Re-render without paying for re-capture or re-assembly (Priority: P2)

The user is unhappy with the rendered notes — the prompt could be tweaked, the model bumped, the structure changed. They want to re-render the notes from the *same* slide content and the *same* transcript without redoing slide assembly and without re-running the vision pass.

**Why this priority**: Iterating on prompt and structure is the natural way the user will tune output quality. If each iteration costs an 80-minute re-capture or even a 10-minute re-render of the working doc, the user will iterate less, and the resulting notes will be worse. Cheap iteration is what makes the feature actually usable for tuning.

**Independent Test**: After producing a notes file once, invoke the same subcommand in a re-render mode without supplying the transcript again, and confirm the LLM is called with the cached working doc as input (no re-assembly) and a new notes file is produced.

**Acceptance Scenarios**:

1. **Given** a notes file and its working-doc input both already exist in the cache, **When** the user invokes the notes subcommand in re-render mode without supplying a transcript, **Then** the working-doc step is skipped, the LLM call runs against the existing working doc, and the notes file is overwritten or written to a new path according to the user's flag choice.
2. **Given** the user invokes a re-render but the cache contains no working doc (e.g., only the slide content), **When** the command runs, **Then** it refuses with a message telling the user to first run the full notes command (with a transcript) to produce the working doc.

---

### User Story 4 - Inspect the working doc that was handed to the LLM (Priority: P2)

The user wants to verify what the LLM saw before it rendered, so they can attribute any rendering error to either bad input (slide extraction, transcript parsing) or bad rendering (prompt, model). They expect to be able to open a single Markdown file in any editor that contains every recovered slide and every parsed transcript utterance.

**Why this priority**: The LLM call is the only step in this feature whose output is non-deterministic. Making the input to that call a first-class, inspectable artifact is what lets the user trust the output and debug it when wrong.

**Independent Test**: After running the notes subcommand, open the working-doc artifact in a plain text editor and confirm it contains all slide titles in order and the full set of parsed transcript utterances with speakers and timestamps.

**Acceptance Scenarios**:

1. **Given** the notes subcommand has produced a notes file, **When** the user lists the cache directory, **Then** they see a working-doc artifact next to the notes file and the slide-content artifact, all under predictable filenames.
2. **Given** the user opens the working-doc artifact, **When** they scroll through it, **Then** they find every slide that was extracted (in order, with title, bullets, and visual description) followed by every transcript utterance (in chronological order, with speaker and HH:MM:SS timestamp).
3. **Given** the working-doc artifact has just been written, **When** the user inspects its size and structure, **Then** the input to the LLM call is reproducible from this artifact alone — running re-render against this file produces the same kind of notes the original run produced.

---

### Edge Cases

- **Transcript file format drift.** The supported transcript text format uses block separators between utterances and a three-line "speaker / HH:MM:SS / text" header followed by zero or more single-line continuation blocks attributed to the same speaker. The parser must handle both new-speaker and continuation blocks, and must not fail on a trailing blank block at end of file.
- **Slides with no extracted structure.** Some slides come back from the vision stage with empty title and bullets but a populated raw OCR string (typical for full-bleed diagrams or code dumps). The working doc must surface the raw OCR for these slides so the content is not silently dropped, and the LLM render must be told to treat raw-OCR-only slides as content rather than noise.
- **Slide capture longer than the meeting.** The slide capture window may extend past the end of the meeting transcript (the user kept playback rolling). The renderer must not require strict per-slide time alignment between transcript and slides; slides shown but never discussed must be either omitted from the narrative or surfaced in a closing "shown but not discussed" section, never silently dropped.
- **Repeated slides.** A single unique slide may appear multiple times in the recording. The working doc lists each unique slide once in extraction-first-appearance order; the renderer is told that the transcript may revisit earlier slides and to weave discussion accordingly.
- **Missing transcript argument.** If the user invokes the notes subcommand without supplying a transcript path and re-render mode is not active, the command falls back to a non-empty cached `transcript.json` in the recording's cache directory if one exists. If neither a path is given nor a usable cached transcript is present, the command refuses with a clear message that names the three supported transcript shapes and points at the documented procedure for obtaining one from the Zoom recording.
- **Cost-aware invocation.** The command must report estimated input/output tokens and dollar cost of the LLM call after the call completes. A dry-run mode reports the assembled working-doc size and the projected cost without making the LLM call, so the user can confirm the spend before committing.
- **Existing notes file.** If the notes file already exists at the target output path, the command refuses to overwrite it unless an explicit force flag is passed, so a re-render does not silently clobber a copy the user has been editing.
- **Live transcript scraper still ran in this cache.** If the cache already contains a non-empty transcript artifact from a successful live scrape, the notes subcommand prefers the user-supplied transcript file when one is given (so the post-capture path is always available), but uses the cached one when no file is provided.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a single CLI subcommand that takes a recording identifier (URL or cache directory) and a transcript text file path and produces a Markdown notes file as its primary output.
- **FR-002**: System MUST resolve a recording URL argument to its cache directory using the same convention used elsewhere in notetaker, so the user does not need to know or type the cache layout.
- **FR-003**: System MUST refuse to run the notes subcommand if the cache directory contains no slide-content artifact, and MUST surface a clear message naming the missing prerequisite (i.e., that the understanding stage has not yet completed for this recording).
- **FR-004**: System MUST accept a transcript file in any of the following three shapes and produce the same internal representation (an ordered list of utterances, each with speaker, start time, and text):
  - **Browser-scrape block format** — blocks separated by a documented separator, with each new-speaker block carrying a "speaker / HH:MM:SS / text" header and continuation blocks attributed to the previous speaker. This is the format produced by the documented post-capture browser snippet.
  - **WebVTT (`.vtt`)** — Zoom Cloud Recording's downloadable transcript format. The parser MUST extract cue start time, speaker (when the cue payload prefixes `<v Speaker>` or equivalent), and text. Cues without a speaker label MUST default to a single "Unknown" speaker rather than failing.
  - **Notetaker `transcript.json`** — the schema written by a successful live scrape and already validated against `TranscriptSchema`.
- **FR-004a**: System MUST detect the format from file content, with file extension (`.vtt`, `.json`, `.txt`) used only as a tiebreaker. The parser MUST tolerate trailing blank blocks, MUST not fail on encoding artifacts that do not affect content, and MUST refuse with a clear, actionable error (naming all three supported shapes) when the file matches none of them.
- **FR-005**: System MUST produce a working-doc artifact, written to a stable path inside the cache directory, that is the deterministic concatenation of (a) every unique extracted slide in extraction order, with title, bullets, and visual description, and (b) every parsed utterance in chronological order, with speaker and timestamp. The working-doc artifact MUST be human-readable as Markdown.
- **FR-006**: System MUST surface raw-OCR content for any slide whose title and bullets are both empty but whose raw OCR is non-empty, so that no extracted content is silently lost in the working doc.
- **FR-007**: System MUST make at most one *successful* LLM render call per notes invocation. The call's input MUST be the working-doc artifact and a fixed rendering prompt; the call's output MUST be the contents of the notes file. No additional LLM calls may be chained from this output. Transient failures MAY trigger retries per FR-017.
- **FR-007a**: System MUST emit a structured record to the run log file for each LLM render attempt — including attempt number, model name, input/output token counts (when available), elapsed time, estimated cost, and outcome (success / retryable failure / persistent failure) — and a final per-invocation record summarising the overall outcome and total cost. This is in addition to the console summary required by FR-011.
- **FR-008**: System MUST instruct the renderer that slide order is first-appearance order and that the transcript may revisit earlier slides, so the renderer does not assume strict one-to-one alignment between contiguous transcript and a single slide.
- **FR-009**: System MUST instruct the renderer to attribute decisions, statements, and questions to named speakers when the transcript provides that attribution, and MUST instruct it to flag uncertainty rather than fabricate when an attribution is not clear.
- **FR-010**: System MUST write the notes file to a stable, predictable path inside the cache directory by default, and MUST print the absolute path of the notes file to the console on success.
- **FR-011**: System MUST report the actual input token count, output token count, and estimated dollar cost of the LLM call to the console on success.
- **FR-012**: System MUST support a dry-run mode that reports the assembled working-doc size and projected cost without making the LLM call.
- **FR-013**: System MUST support a re-render mode that skips working-doc assembly and reuses an existing working-doc artifact in the cache. In this mode the transcript argument is not required. If no working-doc artifact exists, the system MUST refuse and tell the user to run the full notes command first.
- **FR-014**: System MUST refuse to overwrite an existing notes file at the target path unless an explicit force flag is provided.
- **FR-015**: System MUST treat the live transcript scrape inside the existing capture stage as best-effort. When the live scrape captures zero utterances, the run MUST exit successfully with the slide artifacts intact, MUST emit a single clearly-labelled warning to the console and to the run log, and MUST point the user at the documented post-capture transcript-pull procedure.
- **FR-016**: System MUST document the post-capture transcript-pull procedure (how to obtain the transcript text file from the Zoom recording in the browser) in user-facing documentation that ships with the project, so the user can perform the recovery flow without reading source code.
- **FR-017**: System MUST retry a failed LLM render call using the existing project retry policy (the same `retry_count` and `retry_delay_seconds` settings that govern the vision and synthesis stages). On persistent failure (all retries exhausted), the command MUST exit with a non-zero status, MUST leave the working-doc artifact in place so the user can re-invoke without rebuilding it, and MUST NOT write a notes file.
- **FR-018**: Working-doc and notes-file artifacts produced by this feature MUST be exempt from the existing automatic cache retention purge (the policy currently governed by `[cache] retention_days`). Frames, slide-timeline, slide-content, and synthesis artifacts continue to follow the existing retention policy unchanged. The user remains free to delete the working doc or notes file manually.

### Key Entities

- **Slide-content artifact**: The output of the existing understanding stage, already written to the cache. Lists every unique slide extracted from the recording, in first-appearance order, with title, bullets, visual description, and raw OCR. This feature consumes it; it does not change its shape.
- **Transcript text file**: A user-supplied text file containing the meeting transcript, obtained from the Zoom recording's browser-side transcript panel. Block-separated; each first block in a turn carries a speaker name, an HH:MM:SS timestamp, and the spoken text; continuation blocks contain only text and inherit the previous speaker.
- **Working doc**: The deterministic Markdown concatenation of the slide-content artifact and the parsed transcript text file. Written to a stable path inside the cache directory. The sole input to the LLM render call. Human-readable; reproducible from its two source inputs.
- **Notes file**: The Markdown output of the LLM render call. Contains a meeting overview, identified speakers, per-topic narrative sections anchored on slide titles, decisions with attribution, action items, and open questions. Intended for human review and editing. Written to a stable path inside the cache directory by default.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user with a completed notetaker cache and a separately-obtained transcript text file can produce a polished notes file in a single command in under one minute of user activity (excluding the LLM call's wall-clock time).
- **SC-002**: For a one-hour meeting recording the LLM call cost stays under thirty cents at the project's default model.
- **SC-003**: A user can re-render the notes from the cached working doc, with a tweaked prompt or model, in under fifteen seconds of user activity (again excluding the LLM call's wall-clock time) and without re-running any earlier stage.
- **SC-004**: The notes file produced for a one-hour technical meeting names every speaker present in the transcript, uses at least seventy percent of the slide titles as section anchors when there is a clear topical match, and lists at least one decision and at least one action item or open question — without fabricating content not present in the transcript.
- **SC-005**: When a notetaker run's live transcript scrape captures zero utterances, the run exits successfully (slide artifacts intact), emits exactly one clearly-flagged warning, and the user can produce useful notes from the same cache without re-running capture.
- **SC-006**: Inspecting the working-doc artifact for a one-hour meeting reveals every unique extracted slide and every parsed utterance, in their respective natural orders — no silent drops, no truncation.
- **SC-007**: A notes file produced today is still present after a subsequent notetaker run that triggers the cache retention purge against the same recording's cache, while the run's frame directory has been purged on schedule.

## Assumptions

- The user already runs a notetaker cache at the conventional location (i.e., `~/.local/share/notetaker/cache/<recording-url-hash>/`) and has run at least the capture, extract, and understand stages successfully for the recording in question. This feature does not introduce a new cache layout.
- The post-capture transcript-pull procedure is performed by the user in their own browser, against the Zoom recording. The notetaker process does not control that browser. The transcript text file the user supplies is treated as authoritative.
- A single LLM render call producing a few thousand output tokens is sufficient for a meeting of up to roughly one hour. Longer meetings may need a chunked or multi-pass strategy in a future iteration; a chunking strategy is out of scope for this feature.
- The default LLM for this feature is the same model the existing synthesis stage uses, configurable through the same configuration mechanism. This feature does not introduce a new model selection surface.
- The existing slide-by-slide synthesis stage and its `summary.md` output remain in the codebase but are no longer the documented happy path. Documentation is updated to recommend the new notes subcommand. A subsequent feature may decide to remove the old synthesis stage or repurpose it; that decision is out of scope here.
- Live remote monitoring, real-time notes generation, and recordings from platforms other than Zoom Cloud Recording are out of scope for this feature.
