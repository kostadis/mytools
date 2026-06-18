# Phase 1 Data Model: Remove the Legacy Synthesise Stage

This is a deletion feature. There are no new entities. The data model
delta is **two contracts removed, one enum value removed, one config
dataclass removed, one cache subdirectory key removed**, and the rest
of the codebase's data shape unchanged.

## Removed entities

### `SummarySchema` (and its `PerSlideSummary`) — DELETED

**Source**: `src/notetaker/contracts/summary.py`

**What it was**: The Pydantic model describing the legacy stage's on-disk
output (`<cache>/<hash>/synthesis/summary.json`). Carried `recording_url`,
`generated_at`, `overall_summary`, a list of `PerSlideSummary` records
(slide_id, slide_title, summary text, key_points), `action_items`, and
`decisions`.

**Why removed**: The only producer (`stages/synthesis/summarizer.py`) and
the only consumer (`stages/synthesis/__init__.py` writing
`summary.json`/`summary.md`) are both deleted by this feature. The notes
path produces a Markdown file, not a JSON-validated structured object, so
nothing surviving needs this schema.

**Migration**: None. Existing on-disk `synthesis/summary.json` files in
user caches become orphan files; the existing cache retention sweep removes
them on its normal schedule (FR-012).

### `AlignedSegmentsSchema` (and its `AlignedSegment`, `SlideContentRef`) — DELETED

**Source**: `src/notetaker/contracts/aligned_segments.py`

**What it was**: The Pydantic model describing the time-aligned join of the
slide timeline and the transcript that the legacy aligner produced. Each
segment carried slide_id, occurrence_index, an inlined SlideContentRef,
transcript_text, duration_seconds, start_seconds.

**Why removed**: The only producer (`stages/synthesis/aligner.py`) and the
only consumers (`stages/synthesis/__init__.py` writing
`aligned_segments.json` and the optional CSV; `stages/synthesis/summarizer.py`
reading `AlignedSegmentsSchema` as input to the per-slide LLM call) are all
deleted. The notes path does not time-align — it concatenates extracted
slides and parsed transcript utterances independently into a deterministic
working doc. No surviving code consumes `AlignedSegment`.

**Migration**: None. Existing on-disk `synthesis/aligned_segments.json` and
`synthesis/aligned_segments.csv` become orphans; cache retention sweep
collects them.

### `Stage.SYNTHESISE` enum value — DELETED

**Source**: `src/notetaker/contracts/log_record.py:46`

**What it was**: The `Stage` closed-set enum value `"synthesise"`. Emitted
on `stage_start` and `stage_end` log records by the legacy stage's
`stage_lifecycle("synthesise", ...)` context manager.

**Why removed**: After this feature, no producer emits it; FR-011 requires
removing dead values from the structured-log contract. The closed-set
nature of the enum (per the docstring on `EventCategory`) means consumers
rely on absent values being absent. Keeping a never-emitted value is
misleading.

**Schema version impact**: `LogRecord.SCHEMA_VERSION` bumps from `"1.0.0"`
to `"1.1.0"`. The change is restrictive (one fewer permitted value) but
backward-compatible for any consumer that was filtering by emitted values.
Update the schema docstring with the changelog line:

> 1.1.0 — Removed `Stage.SYNTHESISE`. The legacy slide-by-slide
> summariser stage was deleted (spec 004); no producer emits this value.

### `SynthesisConfig` dataclass and `[synthesis]` section — DELETED

**Source**: `src/notetaker/config.py:32-34` (dataclass), `:76` (field on
Config), `:176` (section loader), `:83` (`resolved_notes_model` fallback);
`config.toml:51-53` (config file section).

**What it was**: The configuration dataclass holding `summary_model =
"claude-sonnet-4-6"`, the only knob the legacy stage exposed.

**Why removed**: FR-004 / FR-005. After deletion, `[synthesis]` sections in
existing user config files are silently ignored by the existing TOML
loader (FR-005); the bundled default model name moves into
`NotesConfig.model` per Decision 1 in `research.md`.

**Migration**: None. The TOML loader's existing behaviour of ignoring
unknown sections is sufficient. No deprecation warning, no shim.

### `STAGE_SUBDIRS["synthesis"]` cache layout entry — DELETED

**Source**: `src/notetaker/cache.py:21-26`

**What it was**: The mapping from logical stage name `"synthesis"` to its
on-disk subdirectory name `"synthesis"`. Used by `Cache.stage_dir` and
`Cache.artifact_path`.

**Why removed**: After deletion, no surviving caller passes `"synthesis"`
to `Cache.stage_dir` or `Cache.artifact_path`. Removing the mapping turns
an accidental future call into a `KeyError` rather than a silent
directory creation, which is the right failure mode for dead code paths.

**Migration**: None. Existing on-disk `synthesis/` subdirectories are not
read or referenced; cache retention sweep handles them (FR-012).

## Modified entities

### `NotesConfig.model` — default value changes from `""` to `"claude-sonnet-4-6"`

**Source**: `src/notetaker/config.py:62`

**Before**:
```python
model: str = ""  # empty means "fall back to synthesis.summary_model"
```

**After**:
```python
model: str = "claude-sonnet-4-6"  # bundled default for the notes render call
```

**Why**: Per Decision 1 in `research.md`. The user-visible default model
the notes call uses is preserved (FR-006 / SC-007); the runtime fallback
chain through the deleted `[synthesis]` section is replaced with a static
default in the surviving section.

**Behavioural impact**:
- A user with no `notes.model` override → sees `"claude-sonnet-4-6"`
  (unchanged).
- A user with `notes.model = "claude-opus-4-7"` set → sees their override
  (unchanged).
- A user with `notes.model = ""` set explicitly → previously fell back to
  `synthesis.summary_model`; after this feature, an empty-string value is
  honoured literally and the SDK call would fail with a "model required"
  error. The shipped `config.toml` no longer ships `model = ""` (Decision
  8 in `research.md`), so a user only hits this if they hand-set the
  empty string, which is unambiguously their own override of a sensible
  default.

### `Config.resolved_notes_model()` — fallback chain shortened

**Source**: `src/notetaker/config.py:82-83`

**Before**:
```python
def resolved_notes_model(self) -> str:
    return self.notes.model or self.synthesis.summary_model
```

**After**:
```python
def resolved_notes_model(self) -> str:
    return self.notes.model
```

The function survives as the chokepoint per Decision 1.

## Unchanged entities (called out for explicit re-review)

These entities were inspected and confirmed unaffected by this feature:

- `TranscriptSchema` (`contracts/transcript.py`) — consumed by the notes
  path. Untouched.
- `SlideTimelineSchema` (`contracts/slide_timeline.py`) — produced by the
  extraction stage; consumed only by the (deleted) aligner. After this
  feature it is consumed only by tests and by direct readers; it is NOT
  consumed by the notes path (which reads the slide-content artifact
  directly). It remains a versioned inter-stage contract because the
  extraction stage still produces it as its on-disk output and a future
  consumer (or a future debugging session) may read it. Not deleted.
- `SlideContentSchema` (`contracts/slide_content.py`) — produced by the
  understanding stage, consumed by the notes path. Untouched.
- `FramesManifestSchema` (`contracts/frames_manifest.py`) — produced and
  consumed by the capture/extraction stages. Untouched.
- `LogRecord` and `EventCategory` (`contracts/log_record.py`) — only
  `Stage.SYNTHESISE` is removed; the rest of the schema is untouched.
- `Cache` class (`cache.py`) — only the `STAGE_SUBDIRS["synthesis"]` entry
  is removed. The notes-aware retention logic (`purge_stale` with its
  `notes_retention_days` parameter) is untouched.

## State transitions

Not applicable. This feature has no state machines, no lifecycle, no
transitions. It is a pure removal.
