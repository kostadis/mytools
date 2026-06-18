# Data Model — Human-readable notes filenames, export, and cache delete

**Feature**: 005-notes-naming-and-export
**Date**: 2026-05-10

This feature does not introduce any new inter-stage data contracts (Article I.3 is unaffected). It does formalise one previously-informal per-cache-entry file (`meta.json`) into a versioned Pydantic schema, and it introduces two pure-data dataclasses used internally by the new CLI commands. Two filesystem-level entities (the human-readable notes filename and the export target directory) are described as field-level invariants rather than schemas.

---

## Entities

### Promoted to a schema — `RecordingMetaSchema` (was: informal `meta.json` dict)

The per-cache-entry metadata file at `<cache-root>/<url-hash>/meta.json`. Today it is written by `Cache.initialise()` as an ad-hoc dict with two keys (`recording_url`, `created_at`). This feature promotes it to a Pydantic schema with a `schema_version` field and two new fields populated by capture, plus one populated by notes.

**File path**: `<cache-root>/<url-hash>/meta.json`
**Module**: `src/notetaker/contracts/recording_meta.py` (new)

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `schema_version` | `str` | Yes (v2) | `"2"` | Absent on legacy reads; the lenient reader treats absence as `"1"`. The next write upgrades to `"2"`. |
| `recording_url` | `str` | Yes | n/a | Existing field; carries through unchanged. |
| `created_at` | `str` (ISO-8601 UTC) | Yes | n/a | Existing field; the cache entry's creation timestamp. Used as the fallback for `recording_date`. |
| `meeting_title` | `str \| None` | No | `None` | Scraped during capture from the Zoom recording page (Decision 1). `None` if scrape failed. The notes step uses it (or the fallback `"untitled"`) as the meeting-title component of the filename. |
| `recording_date` | `str \| None` (ISO date `YYYY-MM-DD`) | No | `None` | The recording's own date if it can be determined cheaply from the page; otherwise `None`, in which case the notes step derives it from `created_at`. (See Decision 7.) |
| `summary` | `str \| None` | No | `None` | Populated by the notes step after the Haiku summary call (Decision 2). Bounded by `summary_max_chars` (default 50). `None` until the first successful notes run; `"no-summary"` if the call has been attempted and consistently fallen back. |

**Validation rules** (enforced by Pydantic and by the small wrapper that loads it):

- `schema_version` MUST be one of `"1"` or `"2"` on read; on write it MUST be `"2"`.
- `meeting_title`, when non-null, has length ≥ 1 (empty string treated as `None`).
- `recording_date`, when non-null, MUST match `^\d{4}-\d{2}-\d{2}$`.
- `summary`, when non-null, has length ≤ `NotesConfig.summary_max_chars` (defensive client-side cap, in addition to the prompt-side instruction to Haiku).

**Lenient v1 read**: If `schema_version` is missing, the reader sets it to `"1"` and treats every new field as `None`. The next write performs the v1→v2 upgrade transparently — any caller that loads-then-saves migrates the file. No standalone migration runs.

**State transitions** (on a single cache entry's `meta.json`):

```text
[no file]                    initial state
   │
   │ capture stage runs
   ▼
{schema_version="2",         after Cache.initialise() during capture
 recording_url, created_at,
 meeting_title, recording_date,
 summary=None}
   │
   │ notes stage runs (any mode)
   ▼
{… , summary=<≤50-char string>}    after summary call
```

A legacy `meta.json` (written by an older notetaker build) starts in the implicit v1 state; the next read-then-write upgrades it.

---

### New (internal dataclass) — `SummaryResult`

The return value of the Haiku summary call. Lives in `src/notetaker/notes/summary.py`.

| Field | Type | Notes |
|---|---|---|
| `text` | `str` | The summary string, ≤ `summary_max_chars`. On fallback: `"no-summary"`. |
| `outcome` | `Literal["success", "fallback"]` | `"success"` only when the API call returned a parseable JSON-shaped response within the length cap; otherwise `"fallback"`. |
| `model` | `str` | Resolved Haiku model id (from `NotesConfig.summary_model`). |
| `total_attempts` | `int` | Number of API attempts (uses the existing `[api]` retry policy). |
| `total_input_tokens` | `int` | Across all attempts. |
| `total_output_tokens` | `int` | Across all attempts. |
| `total_cost_usd` | `float` | Computed from token counts and the new `summary_input_token_price_per_million` / `summary_output_token_price_per_million` config knobs. |

This object exists for parity with the existing `RenderResult` (returned by the main Sonnet call) so the notes orchestrator can roll its cost into the per-run total and emit a parallel structured log record.

---

### New (internal dataclass) — `ExportSummary`

The return value of `cache_ops.export_notes(...)`. Lives in `src/notetaker/cache_ops.py`. Used by `cli.py` to format the user-facing report.

| Field | Type | Notes |
|---|---|---|
| `target_dir` | `pathlib.Path` | The resolved (absolute) target directory after creation. |
| `copied` | `int` | Number of cache entries whose notes file was successfully copied. |
| `skipped_no_notes` | `int` | Cache entries whose `notes/` did not contain a notes file. |
| `skipped_collision` | `int` | Cache entries whose destination filename already existed in the target directory and `--overwrite` was not passed. |
| `legacy_resolved` | `int` | Cache entries whose source was a legacy `notes.md` and whose destination filename was computed at export time. (Subset of `copied`.) |

---

### New (internal dataclass) — `PurgeSummary`

The return value of `cache_ops.purge_cache(...)`. Lives in `src/notetaker/cache_ops.py`.

| Field | Type | Notes |
|---|---|---|
| `cache_root` | `pathlib.Path` | The resolved cache root that was operated on. |
| `entries_removed` | `int` | Number of per-recording entries removed (each is one `<url-hash>/` subdirectory). |
| `bytes_reclaimed` | `int` | Total bytes freed; computed by walking each entry before removal. |
| `cancelled` | `bool` | `True` if the user cancelled the confirmation prompt. When `True`, the other counters are zero. |

---

### Filesystem-level entity — Notes filename (composite, per cache entry)

Not a serialised schema. The naming function `notes.naming.derive_notes_filename(meta) -> str` constructs it by composition. The composition rule and the sanitization pipeline are documented under `contracts/notes-naming.md`. Summary of invariants:

- Components: `<YYYY-MM-DD>` + `--` + `<sanitized-meeting-title>` + `--` + `<sanitized-summary>` + `.md`.
- Date component: `meta.recording_date` if set; otherwise the date portion of `meta.created_at`.
- Meeting-title component: `meta.meeting_title` after sanitization (Decision 4); empty result → `"untitled"`.
- Summary component: `meta.summary` after sanitization; empty or `None` → `"no-summary"`.
- Total length (excluding `.md`) ≤ `NotesConfig.filename_max_chars` (default 200). If the per-component sums exceed this, the meeting-title component is truncated.
- Within a single cache entry's `notes/` subdirectory, deterministic per recording: same URL hash + same `meta.json` always produces the same filename. Re-render with a new summary changes the filename, in which case the orchestrator renames the existing file to the new name (atomic rename within the same directory).
- Cross-entry collisions are not the concern of this entity; they are handled by the export step (Decision 5(B)).

---

### Filesystem-level entity — Export target directory

Not a serialised schema. Specified by FR-010 through FR-016. Summary of invariants:

- Path resolution: relative paths are resolved against the user's `cwd` at command time (typer's default).
- Created if missing, including parents (`Path.mkdir(parents=True, exist_ok=True)`).
- Permissions: inherited from the parent directory (no chmod).
- Files written with `shutil.copy2` (preserves mtime; permission preservation is best-effort).
- The export command does not write any files outside `target_dir`. In particular, it does not create a `meta.json` or any sidecar files.

---

## Configuration additions

The following fields are added to `NotesConfig` in `src/notetaker/config.py`. All ship with inline comments in `config.toml` per Article IV.3.

| Field | Type | Default | Effect |
|---|---|---|---|
| `summary_model` | `str` | `"claude-haiku-4-5-20251001"` | Model for the summary call (Decision 2). |
| `summary_max_chars` | `int` | `50` | Defensive client-side cap on the summary length (Decision 2). |
| `summary_input_token_price_per_million` | `float` | `0.80` | Mirrors `UnderstandingConfig`'s Haiku pricing knob; used for cost reporting on the summary call. |
| `summary_output_token_price_per_million` | `float` | `4.00` | Same. |
| `filename_max_chars` | `int` | `200` | Total filename cap excluding `.md` (Decision 4). |
| `filename_collision_suffix_chars` | `int` | `8` | Length of the URL-hash-prefix disambiguator used inside a single cache entry on within-entry collisions (Decision 5(A)). |

Capture-side addition to `CaptureConfig`:

| Field | Type | Default | Effect |
|---|---|---|---|
| `recording_title_selector` | `str` | `".recording-topic, .topic-name, h1"` | CSS selector(s) for the Zoom recording-topic element, used as a fallback when `page.title()` returns the generic Zoom document title (Decision 1). |

No removals.

---

## Out-of-scope (explicit non-changes)

- The transcript, slide-timeline, slide-content, and frames-manifest contracts are untouched.
- The notes' `working_doc.md` filename and content are untouched.
- The retention machinery (`Cache.purge_stale`) is untouched: it still keys on directory mtimes, which the rename does not alter.
- The `[notes] cost_warn_threshold_usd` knob is untouched: the summary call's cost is added to the existing per-run total and the existing threshold continues to apply.
