# Contract — Run-Log Records Emitted by the Notes Command

**Feature**: 003-post-capture-notes
**Emitted by**: `src/notetaker/notes/__init__.py` and
`src/notetaker/notes/render.py`
**Consumed by**: the run-log file sink installed by feature 002, and any
`grep`/`jq` post-mortem tooling.

All records are structlog events keyed by `event` and routed through the
existing `notetaker.utils.logging.get_logger(__name__)` factory. The
`event_category` field for stage-style records mirrors the convention from
feature 002 (`stage_start`, `stage_end`, `heartbeat`). The `notes` command
is not a pipeline stage but it follows the same record shape so the
existing log tooling does not need to learn a new vocabulary.

---

## Records

### `notes.command_start`

Emitted once at the start of `notetaker notes` invocation, before any
work.

| Field | Type | Notes |
|---|---|---|
| `event_category` | `"command_start"` | constant |
| `recording_url_hash` | `str` | resolved from URL or cache-id arg |
| `mode` | `"full"` \| `"re_render"` \| `"dry_run"` | derived from CLI flags |
| `model` | `str` | resolved model (after the synthesis-default fallback) |

### `notes.transcript_format_detected`

Emitted by the parser dispatcher. Not emitted in `re_render` mode.

| Field | Type | Notes |
|---|---|---|
| `format` | `"block"` \| `"vtt"` \| `"transcript_json"` | |
| `path` | `str` | the transcript file path argument |
| `utterance_count` | `int` | count after parse |
| `speaker_count` | `int` | distinct speakers |

### `notes.working_doc_written`

Emitted after the deterministic builder writes the file. Not emitted in
`re_render` mode.

| Field | Type | Notes |
|---|---|---|
| `path` | `str` | absolute path to `working_doc.md` |
| `slide_count` | `int` | unique slides included |
| `utterance_count` | `int` | utterances included |
| `bytes` | `int` | file size on disk |

### `notes.render_attempt`

Emitted *once per attempt* of the LLM render call (on the first call AND
on every retry). Required fields per FR-007a.

| Field | Type | Notes |
|---|---|---|
| `attempt` | `int` | 1-indexed |
| `model` | `str` | the resolved model |
| `input_tokens` | `int` \| `None` | `None` only when the API call failed before usage was reported |
| `output_tokens` | `int` \| `None` | same |
| `elapsed_seconds` | `float` | wall-clock for this attempt |
| `cost_usd` | `float` | `0.0` if usage unavailable |
| `outcome` | `"success"` \| `"retryable"` \| `"persistent_failure"` | |
| `error` | `str` \| absent | populated for non-success outcomes |
| `level` | `"info"` for success, `"warning"` for retryable, `"error"` for persistent_failure | |

### `notes.render_complete`

Emitted *once*, after the retry loop terminates (whether success or
persistent failure). Pairs with `notes.command_start`.

| Field | Type | Notes |
|---|---|---|
| `event_category` | `"command_end"` | constant |
| `model` | `str` | |
| `total_attempts` | `int` | including the successful one |
| `total_cost_usd` | `float` | sum across all attempts that reported usage |
| `notes_path` | `str` \| `None` | `None` on persistent failure |
| `outcome` | `"success"` \| `"persistent_failure"` | |

### `notes.dry_run_estimate`

Emitted only in `dry_run` mode, in lieu of any `render_attempt` /
`render_complete` events.

| Field | Type | Notes |
|---|---|---|
| `working_doc_bytes` | `int` | size of the assembled working doc |
| `estimated_input_tokens` | `int` | crude estimator (chars / 4) |
| `model` | `str` | |
| `projected_cost_usd_floor` | `float` | input-only projection (output unknowable) |

### `capture.transcript_unavailable_warning` (UPDATED, owned by feature 002 + this feature)

Modification, not addition. The existing warning emitted at
`zoom.py:259` is changed from a one-line `transcript_panel_not_found` into
a structured `event_category: "warning"` record with these fields:

| Field | Type | Notes |
|---|---|---|
| `event` | `"capture.transcript_unavailable"` | renamed for clarity |
| `event_category` | `"warning"` | constant |
| `selector_used` | `str` | the selector that timed out |
| `recovery_hint` | `str` | a short pointer at HOWTO.md, e.g. `"See HOWTO.md 'Obtaining a transcript' to recover via post-capture procedure."` |

The change satisfies FR-015 and SC-005 (exactly one clearly-flagged
warning).

---

## Test coverage required

Unit tests in `tests/unit/test_notes_render.py` and
`tests/integration/test_notes_command.py`:

1. Each event listed above is emitted at least once during a successful
   end-to-end mocked run, in the correct order, with the documented fields.
2. On a transient failure followed by a success, exactly two
   `notes.render_attempt` records appear (outcomes `retryable` then
   `success`) followed by one `notes.render_complete` with
   `outcome = success` and `total_attempts = 2`.
3. On persistent failure, three `notes.render_attempt` records appear (all
   `retryable` except the last which is `persistent_failure`) followed by
   one `notes.render_complete` with `outcome = persistent_failure` and
   `notes_path = None`.
4. In `re_render` mode no `transcript_format_detected` /
   `working_doc_written` events appear.
5. In `dry_run` mode `notes.dry_run_estimate` is emitted and no
   `render_attempt` events occur.
