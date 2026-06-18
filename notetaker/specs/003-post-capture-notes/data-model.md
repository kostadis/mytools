# Data Model — Post-Capture Notes

**Feature**: 003-post-capture-notes
**Date**: 2026-05-09

This feature does not introduce new persistent data schemas. It re-uses one
existing schema and produces two new Markdown artifacts whose structures are
documented (not validated by Pydantic). It also adds one configuration
dataclass.

---

## Entities

### Reused — `TranscriptSchema` (already defined in `src/notetaker/contracts/transcript.py`)

The internal canonical representation of a parsed transcript. All three
input shapes (browser-scrape blocks, WebVTT, `transcript.json`) are
normalised to this. No changes to the schema.

Relevant fields (existing):

| Field | Type | Notes |
|---|---|---|
| `recording_url` | `str` | Set from the cache lookup, not the transcript file. |
| `transcript_unavailable` | `bool` | Always `False` for files produced by this feature (we have a transcript by definition). |
| `utterances` | `list[Utterance]` | Ordered, chronological. |

`Utterance` (existing): `start_seconds: float`, `end_seconds: float`,
`speaker: str`, `text: str`. WebVTT cues without an explicit speaker label
default to `speaker = "Unknown"` (per FR-004). `start_seconds` and
`end_seconds` are derived from the source format's timestamp:

- Block format: `start_seconds` = parsed `HH:MM:SS`; `end_seconds` =
  `start_seconds + 5.0` (estimate, mirrors the existing live-scrape
  fallback behaviour at `zoom.py:280`).
- WebVTT: `start_seconds` and `end_seconds` come directly from the cue.
- `transcript.json`: pass through unchanged.

---

### New (Markdown only) — Working Doc

A Markdown file at `<cache-root>/<url-hash>/notes/working_doc.md`. The
deterministic concatenation of slide content and parsed transcript. Sole
input to the LLM render call.

Structure (informally enforced by the builder; documented in
`contracts/working_doc.md`):

```text
# Working Doc — slides + transcript

[1-paragraph header explaining what this file is and that it is the input
 to the LLM render call]

- Slides: <N> unique, in extraction order
- Utterances: <M>
- Transcript span: <HH:MM:SS> → <HH:MM:SS>

## Slides

### Slide 1 (`s001`): <title>

- <bullet 1>
- <bullet 2>

_Visual:_ <visual_description>

### Slide 2 (`s002`): <title or "(no title)">

[For slides with empty title and bullets but populated raw_ocr,
 _Visual:_ is omitted and the raw OCR is surfaced under
 _Raw text on slide:_ as a fenced block.]

…

## Transcript

**<Speaker> [HH:MM:SS]**

<utterance text>
<utterance text continued>

**<Next speaker> [HH:MM:SS]**

<utterance text>

…
```

Invariants (tested in `tests/unit/test_notes_working_doc.py`):

1. Every slide in `slide_content.json["slides"]` appears exactly once,
   in the order given.
2. Every utterance in the parsed transcript appears exactly once, in
   `utterances` order.
3. A slide whose `title`, `bullets`, and `visual_description` are all
   empty but whose `raw_ocr` is non-empty MUST have its `raw_ocr` rendered
   in the working doc (FR-006).
4. Identical inputs produce a byte-identical working doc (deterministic).

---

### New (Markdown only) — Notes File

A Markdown file at `<cache-root>/<url-hash>/notes/notes.md`. Output of the
LLM render call. Structure is *suggested* by the prompt but not strictly
enforced; the contract is "valid Markdown, starts with a `#` heading, no
trailing prose outside the rendered notes."

Documented expectations (FR-009 + spec User Story 2 acceptance scenario 3):
- Meeting overview
- Named participants taken from transcript speakers
- Per-topic narrative sections (slide titles used as section headings when
  topical match is clear)
- Decisions with attribution
- Action items
- Open questions

These are described in `contracts/notes_file.md` as expectations rather
than as a schema. The file is for human review, not for downstream
automation.

---

### New — `NotesConfig` (dataclass in `src/notetaker/config.py`)

| Field | Type | Default | Effect |
|---|---|---|---|
| `model` | `str \| None` | `None` | LLM model for the render call. `None` falls back to `synthesis.summary_model`. |
| `max_output_tokens` | `int` | `8192` | Output cap for the render call. |
| `retention_days` | `int` | `365` | How long `working_doc.md` and `notes.md` survive automatic cleanup. `0` opts into indefinite retention (constitution-compliant via Article VI.2 only when explicitly set). |
| `working_doc_filename` | `str` | `"working_doc.md"` | Filename inside the cache `notes/` subdirectory. |
| `notes_filename` | `str` | `"notes.md"` | Filename inside the cache `notes/` subdirectory. |
| `cost_warn_threshold_usd` | `float` | `0.50` | If projected (dry-run) or actual cost exceeds this, emit a warning record. Does not block. |

Wired into `Config` exactly the way `LoggingConfig` was wired in feature
002 (per `config.py:120-123` pattern).

---

### New (run log records — emitted by the new module, not stored as data)

Three new structured log events, all consumed by the existing run log
sink from feature 002 and documented in
`contracts/render_log_records.md`:

1. `notes.transcript_format_detected` — `format` (one of `block`, `vtt`,
   `transcript_json`), `path`, `utterance_count`.
2. `notes.working_doc_written` — `path`, `slide_count`, `utterance_count`,
   `bytes`.
3. `notes.render_attempt` — `attempt`, `model`, `input_tokens`,
   `output_tokens`, `elapsed_seconds`, `cost_usd`, `outcome` (one of
   `success`, `retryable`, `persistent_failure`).
4. `notes.render_complete` — `model`, `total_attempts`, `total_cost_usd`,
   `notes_path`, `outcome`.

These records satisfy FR-007a and Article V.1.

---

## Lifecycle / state transitions

The `notes` command is a single one-shot invocation. There is no
multi-call lifecycle. Within one invocation, the artifacts move through:

```text
                    ┌─ working_doc.md exists?
no transcript path ─┤
                    └─ no  → ERROR (FR-013 refuse) ──┐
                                                     │
                    ┌─ working_doc.md exists?        │
re-render mode    ──┤                                │
                    └─ yes → render → notes.md       │
                                                     │
                                                     ▼
explicit transcript → parse(detect format) → assemble → render → notes.md
                                                ↓ (on persistent render failure)
                                            working_doc.md preserved; exit non-zero
```

`working_doc.md` is rewritten on every non-re-render invocation (the
deterministic builder produces the same bytes given the same inputs, so
this is idempotent). `notes.md` is written only on render success and
refuses to overwrite an existing file unless `--force` is passed (FR-014).

---

## Validation rules

- **Cache layout**: `notes/` subdirectory must be inside an existing
  recording cache root (resolved by URL hash). The command refuses if the
  recording's `understanding/slide_content.json` is missing (FR-003).
- **Transcript file**: must match exactly one of the three documented
  shapes (FR-004). Refusal (FR-004a) names all three shapes in the error.
- **Output file**: refuse to overwrite an existing `notes.md` unless
  `--force` (FR-014).
- **Re-render mode**: requires an existing `working_doc.md`; transcript
  argument is ignored (FR-013).

---

## Relationships

```text
TranscriptSchema (existing)        NotesConfig (new)
        ▲                                  ▲
        │ produced by                      │ read by
        │                                  │
   parse_transcript_file ───────►   notes/__init__.py (orchestrator)
        ▲                                  │
        │ consumes                         │ writes
        │                                  ▼
   user-supplied transcript file     <cache>/<hash>/notes/working_doc.md
   OR cached transcript.json                │
                                            │ consumed by
                                            ▼
                                     notes/render.py ──► <cache>/<hash>/notes/notes.md
                                            ▲
                                            │ reads
                                            │
                                     <cache>/<hash>/understanding/slide_content.json (existing)
```
