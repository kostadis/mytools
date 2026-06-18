# Implementation Plan: Pipeline Progress Logging

**Branch**: `002-observability-logging` | **Date**: 2026-05-09 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-observability-logging/spec.md`

## Summary

Add a per-invocation file log alongside the existing console (stderr) stream so a user can confirm — at any time, from a second terminal — what stage notetaker is in, when it last made progress, and (if it died) where. The implementation reuses the existing `structlog` foundation: introduce a multi-sink configuration that fans every event out to (a) the current console renderer on stderr and (b) a JSON-lines renderer writing to a per-run file under `~/.local/share/notetaker/logs/`. A small `tick()` helper enforces a bounded heartbeat cadence in long-running stage loops; explicit `waiting_for_input` records bracket the two `input()` blocks in the capture stage. A `latest.log` symlink and a startup banner make the active log file trivially discoverable. Retention mirrors the existing 30-day cache policy.

## Technical Context

**Language/Version**: Python 3.11+ (matches existing project; uses `tomllib`, PEP 604 unions, `asyncio.run`).
**Primary Dependencies**: `structlog` (already pinned, configured in `src/notetaker/utils/logging.py`); Python stdlib `logging` (used via `structlog.stdlib.ProcessorFormatter` to drive two handlers from one structlog pipeline); `typer` (CLI, unchanged). No new third-party dependencies.
**Storage**: Local filesystem only. Run logs land in `~/.local/share/notetaker/logs/<YYYYMMDDTHHMMSSZ>-<url-hash>.log`. A `latest.log` symlink in the same directory points at the most recently started run.
**Testing**: `pytest` (unit + integration; existing 53-test green baseline). New tests under `tests/unit/test_logging.py` (extend existing file) and `tests/integration/test_run_log_file.py`. No live API needed.
**Target Platform**: Linux + macOS CLI (matches existing). Symlink behaviour is POSIX; on platforms without symlink support the implementation degrades to "no `latest.log`" with a single-warning console message.
**Project Type**: Single-project Python CLI (`src/notetaker/`). No layout change.
**Performance Goals**: Heartbeat lines emitted no more than once every 15 seconds per stage (config-tunable). One run log under 5 MB for a 60-minute capture (SC-005). File writes are line-buffered + flushed per record so a `kill -9` mid-stage still leaves the most recent state on disk.
**Constraints**: Must not regress the existing interactive flow (the two `input()` prompts in `ZoomAdapter.capture` and `_wait_for_stop_signal` are user-facing; their stdout/stderr behaviour cannot change). Must not log secrets — the recording URL is logged today and may contain access tokens; this plan adds a redaction step before any URL goes to the log file (Article VI.1). Must not abort the pipeline if the log file is unwritable (FR-012).
**Scale/Scope**: One user, one machine, typically one concurrent run. Two parallel runs supported via per-run filenames keyed by URL-hash + timestamp. Log directory retention defaults to 30 days, matching `cache.retention_days`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Article | Compliance assessment |
|---|---|
| **I.1 Stage Isolation** | PASS. Logging is cross-cutting infrastructure in `utils/logging.py`. No stage imports another stage. The `tick()` helper and heartbeat machinery live in `utils/`, used by each stage independently. |
| **I.2 Platform Adapters Are Isolated** | PASS. No platform-specific log fields. The Zoom adapter's existing event names (`capture.transcript_panel_not_found`, etc.) remain inside `stages/capture/adapters/zoom.py`. |
| **I.3 Data Contracts Are Versioned** | PASS. The run-log JSON-line schema is added at `contracts/log_record.py` with a `schema_version` field, same pattern as the existing stage contracts. |
| **I.4 Re-runnability** | PASS. Logs are diagnostic only; they are never an input to a downstream stage. A stage rerun produces a new log file, never reads an old one. |
| **II.1 Spec/Plan Separation** | PASS. `spec.md` is technology-agnostic ("a log file at a stable location"); this plan introduces structlog, JSON-lines, symlinks. |
| **II.2 Every Stage Documents Its Contract** | PASS. The new log-record contract is documented in `contracts/log_record.py` with allowed `event_category` values, required fields, and version semantics. |
| **III.1 Vision LLM Caching** | N/A. No vision calls added or changed. |
| **III.2 Cost Controls** | N/A. No paid API calls added. |
| **III.3 No Hidden Capture** | PASS. The startup banner ("Logging to …") makes file-write-back-to-disk visible — strengthens, not weakens, this principle. |
| **IV.1 No Magic Numbers** | PASS. Heartbeat interval, log directory path, log retention days, JSON-vs-console file format are all added to `[logging]` in `config.toml` and `LoggingConfig`. |
| **IV.2 Sensible Defaults** | PASS. Defaults: 15s heartbeat interval, `~/.local/share/notetaker/logs/`, 30-day retention, JSON file format. First run requires zero config to gain the feature. |
| **IV.3 Configuration Is Documented** | PASS. Each new `[logging]` key gets an inline comment + default in `config.toml`. |
| **V.1 Every Stage Logs Decisions** | DIRECTLY ADVANCED. This is the article the feature implements. Each stage already emits structured events; this plan ensures they all reach disk. |
| **V.2 Debug Mode Preserves Intermediates** | PASS. Existing `--debug` already lifts log level to DEBUG and preserves stage intermediates. The file sink inherits the DEBUG level when `--debug` is set, so all DEBUG events land in the file. The closed-set `event_category` field on every record (FR-015 revised) lets users `jq` stage transitions and heartbeats out of the noisy DEBUG stream with a one-line filter. |
| **V.3 Failures Diagnosable Without Re-running** | DIRECTLY ADVANCED. The CLI gains a top-level `try/except` that records an `unhandled_exception` event with full traceback to the file before re-raising — making post-mortems possible from the log alone (FR-008, SC-003). |
| **VI.1 Credentials Never Logged** | RISK → MITIGATED. The recording URL is currently logged in plain at two sites (`zoom.py:91`, `zoom.py:138` — verified by grep; `cli.py` does not log URLs). Plan adds `redact_url()` (T004 + T005), applies it at both call sites in T016, and asserts no leakage end-to-end via the credential-bearing-URL fixture in T025(f). |
| **VI.2 Captured Content Retention** | PASS. Logs may contain transcript snippets in DEBUG mode and event metadata, so they fall under retention. `LogStore.purge_stale()` mirrors `Cache.purge_stale()` and uses the same `cache.retention_days` value (or a separate `logging.retention_days` if the user wants to differ). |
| **VI.3 Scope to User-Entitled Content** | N/A. No new access boundaries. |
| **VII.1 Stage-Level Tests** | PASS. New unit tests for: file-sink wiring, heartbeat throttling, URL redaction, `waiting_for_input` records, log-rotation/retention. |
| **VII.2 Golden Fixtures** | PASS. The existing synthetic-fixture integration test (`tests/integration/test_pipeline_e2e.py`) is extended to assert on the run log produced by the run. |
| **VII.3 Cost-Sensitive Tests Mocked** | N/A. No paid API calls touched. |
| **VIII.1 Phased Delivery** | PASS. This feature is itself an independently shippable enhancement; capture/extract/understand/synthesise phases keep their value. |
| **VIII.2 Task-Sized Commits** | PLANNED. Tasks in `tasks.md` (next phase) will be sized for one commit each. |
| **VIII.3 Spec Drift** | PASS. Spec and plan are paired in this change; no drift introduced. |

**Gate result**: PASS. No violations. The Article VI.1 risk (URL token leakage) is acknowledged and mitigated in design, not deferred. Complexity Tracking is not required.

## Project Structure

### Documentation (this feature)

```text
specs/002-observability-logging/
├── plan.md                      # This file (/speckit-plan output)
├── spec.md                      # Feature spec (already written)
├── research.md                  # Phase 0 output — decisions log
├── data-model.md                # Phase 1 output — runtime entities
├── quickstart.md                # Phase 1 output — how to verify the feature
├── contracts/
│   └── log_record.py            # JSON-line schema for one log entry
├── checklists/
│   └── requirements.md          # Spec-quality checklist (already written)
└── tasks.md                     # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
src/notetaker/
├── utils/
│   ├── logging.py               # MODIFIED — multi-sink configure_logging()
│   ├── heartbeat.py             # NEW — Tick throttle + waiting_for_input ctx mgr
│   ├── log_store.py             # NEW — LogStore (path resolution, latest symlink, purge)
│   └── redact.py                # NEW — redact_url() and helpers
├── contracts/
│   └── log_record.py            # NEW — Pydantic schema: LogRecord, EventCategory enum
├── config.py                    # MODIFIED — LoggingConfig gains heartbeat_interval_seconds,
│                                #            log_dir, file_format, retention_days
├── cli.py                       # MODIFIED — _setup() resolves log path, prints banner,
│                                #            wraps app() in unhandled-exception capture
└── stages/
    ├── capture/adapters/zoom.py # MODIFIED — emit waiting_for_input around the two input()
    │                            #            calls; tick() during _capture_frames /
    │                            #            _scrape_transcript loops
    ├── extraction/__init__.py   # MODIFIED — stage_start / stage_end via context manager
    ├── understanding/__init__.py# MODIFIED — stage_start / stage_end + per-slide tick()
    └── synthesis/__init__.py    # MODIFIED — stage_start / stage_end

tests/
├── unit/
│   ├── test_logging.py          # MODIFIED — add: file sink writes JSON; URL redaction;
│   │                            #            ProcessorFormatter wiring
│   ├── test_heartbeat.py        # NEW — tick() throttle, waiting_for_input ctx mgr
│   ├── test_log_store.py        # NEW — path naming, latest symlink, retention purge
│   └── test_redact.py           # NEW — token / cookie / Authorization-header redaction
└── integration/
    └── test_run_log_file.py     # NEW — run synthetic-fixture pipeline; assert per-stage
                                 #        records and crash record appear in log file

config.toml                      # MODIFIED — new [logging] keys with inline comments
```

**Structure Decision**: Single-project Python CLI, unchanged. The feature is a cross-cutting addition to `utils/`, a contract addition under `contracts/`, and small per-stage edits to insert lifecycle records and `tick()` calls. No new top-level package.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. Section intentionally empty.
