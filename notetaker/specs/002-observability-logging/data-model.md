# Phase 1 Data Model: Pipeline Progress Logging

The feature introduces three runtime entities and one on-disk artifact. None of them participates in the stage data-flow pipeline (capture → extract → understand → synthesise); they are observability-only.

## Entities

### 1. `LogRecord` — one line in a run log file

The atomic unit. Defined as a Pydantic model in `src/notetaker/contracts/log_record.py`. Serialised to JSON, one record per line. See `contracts/log_record.py` for the authoritative schema.

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | `str` | yes | `"1.0.0"`. Bumped per Article I.3 if the schema breaks. |
| `ts` | `str` (ISO-8601 UTC) | yes | Provided by structlog's `TimeStamper(fmt="iso")`. |
| `level` | `str` | yes | One of `debug`, `info`, `warning`, `error`. |
| `event` | `str` | yes | Dotted name, e.g. `capture.heartbeat`, `understand.stage_start`. Free-form within stage namespace. |
| `event_category` | `str` (enum) | yes | One of: `stage_start`, `stage_end`, `heartbeat`, `waiting_for_input`, `resumed_from_input`, `warning`, `error`, `unhandled_exception`, `info`. Drives downstream tooling and tests. |
| `stage` | `str` | sometimes | One of `capture`, `extract`, `understand`, `synthesise`, `cli` (for top-level setup/teardown), or `null` for pre-stage events. |
| `recording_url_hash` | `str` (16 hex) | sometimes | Same hash used by `Cache`. Always set once we know which recording the run is about. |
| `elapsed_seconds` | `float` | sometimes | On `stage_end` records, wall-clock duration of the stage. |
| `payload` | `dict[str, Any]` | yes | Free-form structured fields specific to the event (e.g., `{"frames": 42}` on a capture heartbeat, `{"unique_slides": 18, "vision_count": 12, "ocr_count": 6, "total_cost_usd": 1.23}` on understand.stage_end). |

**Validation rules**:
- `event_category=stage_start` ⇒ `stage` must be one of the four pipeline stages.
- `event_category=stage_end` ⇒ `stage` set, `elapsed_seconds` set.
- `event_category=heartbeat` ⇒ `stage` set, `payload` non-empty.
- `event_category=waiting_for_input` and `resumed_from_input` ⇒ `stage` set, `payload.prompt` set (the message shown to the user).
- `event_category=unhandled_exception` ⇒ `payload.exc_type` and `payload.traceback` set; `stage` may be null if the crash was before any stage entered.

**State transitions** (per stage, per run):

```
            ┌──── stage_end (success or warning)
stage_start ┤
            └──── unhandled_exception (crash)

(during stage)
        ┌── heartbeat ──┐
        │               │
        ▼               ▼
   waiting_for_input  warning
        │
        ▼
   resumed_from_input
```

A well-formed completed run produces exactly one `stage_start` and one `stage_end` for each of the four stages (SC-006). A crashed run produces a `stage_start` without a matching `stage_end` for the dying stage, plus a single `unhandled_exception` (SC-003).

### 2. `RunLogFile` — one JSON-lines file per invocation

Path: `<log_dir>/<UTC-iso-basic>-<url_hash>.log`
Example: `/home/kroussos/.local/share/notetaker/logs/20260509T143022Z-3f7a91c8b2d0e1f4.log`

**Naming rules**:
- Timestamp prefix is `strftime("%Y%m%dT%H%M%SZ")` of run start in UTC. Sortable lexicographically.
- URL hash is the same `hashlib.sha256(url).hexdigest()[:16]` already used by `Cache`.
- Filename component for the URL hash is omitted only for invocations that never resolve a recording URL (e.g., `notetaker --help`, never logged anyway).

**Lifecycle**:
1. Created at the top of `cli._setup()` after config loads.
2. `latest.log` symlink is atomically replaced to point at this file.
3. The CLI prints `[notetaker] Logging to <absolute path>` once.
4. Records stream to the file as the run proceeds; each record is flushed.
5. On clean exit, the file is closed by `logging.shutdown()` in an `atexit` handler.
6. Files older than `logging.retention_days` are unlinked at the next invocation's `_setup()` call.

**Failure modes**:
- Log directory not writable → CLI prints one warning to stderr (`[notetaker] WARNING: cannot write to <log_dir> (<reason>); continuing without file log`) and the run proceeds with stderr-only logging. (FR-012, SC-007.)
- Symlink not supported (Windows without dev mode) → `latest.log` is silently skipped; the rest works. (FR-009 degraded.)
- Disk fills mid-run → next write raises `OSError`; the file handler logs an internal warning to stderr and disables itself. The run continues.

### 3. `HeartbeatTracker` — in-memory throttle (not persisted)

Location: `src/notetaker/utils/heartbeat.py`.

| Field | Type | Notes |
|---|---|---|
| `interval_seconds` | `float` | From `config.logging.heartbeat_interval_seconds`. |
| `last_emit_at` | `dict[tuple[str, str], float]` | Keyed by `(stage, key)`. Value is `time.monotonic()` of the last emission for that key. |

**API**:
- `tick(stage: str, key: str, **payload) -> None` — emit a `heartbeat` LogRecord if `monotonic() - last_emit_at[(stage,key)] >= interval_seconds`, else no-op. On emit, update `last_emit_at`.
- `stage_lifecycle(stage: str) -> AbstractAsyncContextManager` — emits `stage_start` on enter, `stage_end` on exit, captures elapsed time, sets a `current_stage` `ContextVar`, and exposes `tick(...)` bound to that stage.

**Semantics**:
- `tick()` with the same `(stage, key)` more than once per `interval_seconds` collapses to one record. Different keys in the same stage do not collapse — e.g. `tick("capture", "frames")` and `tick("capture", "transcript")` independently throttled, allowing fine-grained progress without crowding the file.
- The tracker is process-local. Two parallel runs each have their own.

### 4. `LatestLogPointer` — the discoverability handle

Location: `<log_dir>/latest.log` (a symlink, not a regular file). Updated atomically at the start of each invocation. Its target is the current run's `RunLogFile` absolute path.

**Validation**:
- Replaced via `os.symlink` to a temp name + `os.replace` to `latest.log` to avoid a window where the link is missing or dangling.
- Test asserts that `Path("<log_dir>/latest.log").resolve() == <expected run log path>` immediately after `_setup()` runs.

## Naming notes

- **`synthesise` (Stage enum) vs `synthesis` (directory)**: The `Stage` enum value is `synthesise` — it matches the user-facing CLI subcommand name. The implementation directory is `src/notetaker/stages/synthesis/`. The mismatch is intentional and stable; do **not** rename either side. The Stage enum is the public log-record contract; the directory name is an internal Python module path.

## Out-of-scope entities (called out so they don't sneak in)

- **Aggregated metrics across runs**: cumulative cost, total runtime, success rate. Useful, but a separate feature; this one is per-run only.
- **Remote shipping**: no syslog, no journald, no HTTP. Local file is the contract.
- **Structured query API over the log dir**: users grep / jq / `tail` directly. We do not build a search tool.
- **Live-update web UI**: out of scope. The "second terminal + tail" workflow is the supported observability surface.
