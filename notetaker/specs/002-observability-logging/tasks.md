---

description: "Task list for feature 002-observability-logging — Pipeline Progress Logging"
---

# Tasks: Pipeline Progress Logging

**Input**: Design documents from `/specs/002-observability-logging/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/log_record.py, quickstart.md

**Tests**: This project ships with a pytest suite (53 tests green at HEAD). Article VII.1 requires stage-level tests; this feature is itself a cross-cutting infrastructure addition, so unit tests are interleaved into each phase rather than gated to the end. No live-API tests are needed (Article VII.3 is N/A here — no paid API calls touched).

**Organization**: Tasks are grouped by user story (US1 = P1 hang detection, US2 = P2 discoverability, US3 = P3 post-mortem reconstruction). Each story can be implemented and shipped independently on top of the foundational phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are absolute repo-relative and exact

## Path Conventions

Single-project Python CLI. All source under `src/notetaker/`, tests under `tests/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the new configuration surface that every later task reads. No code logic yet.

- [X] T001 [P] Add the four new keys under `[logging]` in `config.toml` with inline comments per Article IV.3: `heartbeat_interval_seconds = 15`, `log_dir = "~/.local/share/notetaker/logs"`, `file_format = "json"`, `retention_days = 30`. Each comment must state the default and its observable effect on the run log. The `retention_days` comment MUST explicitly note that `0 = keep forever` (matching the convention used by `cache.retention_days` — a value of `0` does NOT mean "purge all"), so the two retention values are independent but follow the same semantics.
- [X] T002 [P] Extend `LoggingConfig` in `src/notetaker/config.py` with the four new fields (`heartbeat_interval_seconds: float = 15.0`, `log_dir: str = "~/.local/share/notetaker/logs"`, `file_format: str = "json"`, `retention_days: int = 30`). Add a `log_dir_path` property analogous to `cache_dir_path` that returns `Path(self.log_dir).expanduser()`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Land the contract, the redaction helper, the log-store machinery, the multi-sink structlog wiring, and the CLI plumbing that activates them. After this phase, every CLI invocation writes a JSON-lines file to disk — even though no stage emits stage_start/stage_end yet, the file exists and receives the existing logger.info() calls. This is the prerequisite for US1, US2, and US3.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 [P] Copy the contract from `specs/002-observability-logging/contracts/log_record.py` to `src/notetaker/contracts/log_record.py` verbatim. The implementation copy must remain byte-identical to the spec copy (Article I.3).
- [X] T004 [P] Implement `redact_url(url: str) -> str` in `src/notetaker/utils/redact.py`. Use `urllib.parse.urlsplit`/`urlunsplit`; replace any query-parameter value whose key is in `{"pwd","password","tk","token","access_token","auth","authorization","signature","sig"}` (case-insensitive) with `***`; replace `user:pass@host` userinfo with `***@host`; preserve scheme/host/path/fragment.
- [X] T005 [P] Add unit tests for `redact_url` in `tests/unit/test_redact.py`: known Zoom share-recording URL with `?pwd=`, URL with `?access_token=&pwd=`, URL with userinfo, URL with no credentials (must round-trip unchanged), URL with non-credential params (must not be touched), case-insensitive key matching.
- [X] T006 Implement `LogStore` in `src/notetaker/utils/log_store.py` with: `__init__(log_dir, retention_days)`; `start_run(recording_url_hash: str | None) -> Path` returning `<log_dir>/<UTC-iso-basic>-<hash>.log` (or `<UTC-iso-basic>.log` when hash is None), creating parent dir as needed; `purge_stale()` that unlinks log files older than `retention_days` (mtime-based, mirroring `Cache.purge_stale` semantics in `src/notetaker/cache.py`; `retention_days=0` means *keep forever* per the cache convention) **and emits exactly one structlog INFO record `event="log_store.purge_stale"` with `removed=<n>, kept=<n>` payload at the end of the call**; a stub `update_latest_pointer(target: Path)` that does nothing (filled in by T018). All filesystem operations must be defensive — `OSError` returns a `Path` of `os.devnull` and surfaces a one-line warning to stderr (FR-012).
- [X] T007 [P] Add unit tests for `LogStore` in `tests/unit/test_log_store.py`: filename format with and without URL hash; directory autocreate; `purge_stale` removes files older than the threshold and keeps newer ones; `start_run` returns a writable path under `tmp_path`.
- [X] T008 Refactor `configure_logging()` in `src/notetaker/utils/logging.py` to set up a stdlib `logging.Logger` with two handlers via `structlog.stdlib.ProcessorFormatter`: (a) `StreamHandler(sys.stderr)` with `ConsoleRenderer(colors=sys.stderr.isatty())`, (b) `FileHandler(<run_log_path>, encoding="utf-8")` with `JSONRenderer()`. The structlog processor chain stays as today (contextvars, level, ISO timestamp, positional args, stack info, exception renderer), with a final `ProcessorFormatter.wrap_for_formatter` step. Add a new parameter `file_path: Path | None`; when None, the file handler is omitted (degraded mode). Make the file handler line-buffered and call `handler.flush()` after each `emit()` so SIGKILL leaves the latest record on disk.
- [X] T009 [P] Extend `tests/unit/test_logging.py` with: a test that `configure_logging(file_path=tmp_path/"x.log")` causes a `logger.info()` call to land in the file as a single JSON object with the expected `event`, `level`, and `ts` fields; a test that bound contextvars (e.g., `bind_contextvars(stage="capture")`) appear in the file record; a test that omitting `file_path` does NOT create a file and does NOT raise; a test that an unwritable `file_path` does not raise from `configure_logging` and falls back to stderr-only.
- [X] T010 Wire `LogStore` + the new `configure_logging` signature into `_setup()` in `src/notetaker/cli.py`. Order: load config → instantiate `LogStore(cfg.logging.log_dir_path, cfg.logging.retention_days)` → call `store.purge_stale()` → call `store.start_run(recording_url_hash=None)` to obtain `run_log_path` (URL hash is filled in later by stage code via contextvars) → call `configure_logging(level=cfg.logging.level, fmt=cfg.logging.format, file_path=run_log_path)` → call `Cache.purge_stale(...)` (existing line, kept). On `OSError` from any of these, log one stderr warning and continue with `file_path=None`.

**Checkpoint**: A `notetaker run <url>` invocation now writes a JSON-lines file under `~/.local/share/notetaker/logs/`. The file receives every existing `logger.info()` call (e.g., `capture.cache_hit`, `capture.complete`, `understanding.cache_hit`). It does not yet have stage-start/stage-end markers or heartbeats — those land in US1.

---

## Phase 3: User Story 1 - Confirm a long-running pipeline is alive (Priority: P1) 🎯 MVP

**Goal**: A user tailing the run log file from a second terminal sees a heartbeat record at least every 15 seconds during any long-running stage, and a stage-transition record whenever the pipeline moves between capture/extract/understand/synthesise. Sustained silence (no new line for substantially longer than 15s) reliably means the run is hung.

**Independent Test**: Start `notetaker run <url>`. From another terminal, `tail -f <run-log-path>`. Confirm: (1) `stage_start` for `capture` appears within seconds of pressing Enter at the playback prompt; (2) heartbeats with `stage="capture"` appear at ≤15s cadence while the capture loop runs; (3) `stage_end` for `capture` appears when the user presses Enter to finish; (4) `stage_start`/`stage_end` for `extract`, `understand`, `synthesise` each appear in turn. Kill the process mid-`understand`; confirm the file contains `stage_start: understand` with no matching `stage_end`.

### Implementation for User Story 1

- [X] T011 [P] [US1] Implement `HeartbeatTracker` and `stage_lifecycle` in `src/notetaker/utils/heartbeat.py`. `HeartbeatTracker(interval_seconds: float)` exposes `tick(stage: str, key: str, **payload)` which emits `logger.info(f"{stage}.heartbeat", event_category="heartbeat", **payload)` only if `monotonic() - last_emit_at[(stage,key)] >= interval_seconds`. `interval_seconds` is **passed in via the constructor** (no module-level singleton — keeps the heartbeat module decoupled from logging-config init order and makes T012 trivially testable without any global setup). `stage_lifecycle(stage: str, recording_url_hash: str | None = None, *, tracker: HeartbeatTracker)` is an `@contextlib.asynccontextmanager` (async only — every pipeline stage's `run(...)` is an `async def`, so the sync form has no caller). It: binds `stage` and `recording_url_hash` to contextvars on enter; emits `logger.info(f"{stage}.stage_start", event_category="stage_start")`; records `t0 = monotonic()`; yields a small object exposing the bound tracker (`life.tick(key, **payload)`) and a mutable `life.end_payload: dict`; on clean exit emits `logger.info(f"{stage}.stage_end", event_category="stage_end", elapsed_seconds=monotonic()-t0, **life.end_payload)`; on exception, emits NO `stage_end` and re-raises (per data-model.md state diagram and SC-003). The cli wires up a single `HeartbeatTracker(cfg.logging.heartbeat_interval_seconds)` and passes it into each stage's `run(...)` call (via existing `cfg` plumbing — add a `tracker` kwarg or stash it on `cfg` at runtime; the latter is lower-churn).
- [X] T012 [P] [US1] Add unit tests for the heartbeat machinery in `tests/unit/test_heartbeat.py`: 10 calls to `tick(stage, key)` within 1ms emit exactly 1 record; 2 calls separated by `interval_seconds + 0.1` emit 2 records; different `(stage, key)` tuples are throttled independently; `stage_lifecycle` emits `stage_start` then `stage_end` with positive `elapsed_seconds` on clean exit; `stage_lifecycle` emits `stage_start` only (no `stage_end`) when the body raises, and the exception propagates; `end_payload` set in the body appears in the `stage_end` record.
- [X] T013 [P] [US1] Wrap the extraction stage in `stage_lifecycle("extract")` in `src/notetaker/stages/extraction/__init__.py`. Inside the per-frame loop in `slide_detector.py` (or wherever the dominant loop lives — see `src/notetaker/stages/extraction/slide_detector.py`), call `life.tick(key="frames", processed=i, total=n)` once per iteration so SC-002 (≤30s gap during *any* long-running stage) holds even on long captures with many frames. Populate `life.end_payload` with `{"total_slides": result.total_slides, "unique_slides": result.unique_slides, "output_path": str(result.output_path)}` so SC-006 (matches console summary) holds.
- [X] T014 [P] [US1] Wrap the synthesis stage in `stage_lifecycle("synthesise")` in `src/notetaker/stages/synthesis/__init__.py`. Populate `life.end_payload` with `{"synthesis_cost_usd": result.synthesis_cost_usd, "summary_md_path": str(result.summary_md_path), "summary_json_path": str(result.summary_json_path)}`.
- [X] T015 [US1] Wrap the understanding stage in `stage_lifecycle("understand")` in `src/notetaker/stages/understanding/__init__.py`. Inside the per-slide loop, call `life.tick(key="slides", processed=i, unique_total=n)` so a long understand stage emits a heartbeat at most every 15s during vision/OCR work. Populate `life.end_payload` with `{"vision_count": result.vision_count, "ocr_count": result.ocr_count, "total_cost_usd": result.total_cost_usd, "output_path": str(result.output_path)}`.
- [X] T016 [US1] Wrap the capture stage in `stage_lifecycle("capture")` in `src/notetaker/stages/capture/adapters/zoom.py`. Replace the existing `if frame_count % 30 == 0: logger.info("capture.progress", frames=frame_count)` block in `_capture_frames` with `life.tick(key="frames", frames=frame_count)`. Add `life.tick(key="transcript", utterances=len(self._utterances))` inside the `_scrape_transcript` polling loop. Populate `life.end_payload` with `{"frames": len(self._frames), "utterances": len(self._utterances), "transcript_unavailable": self._transcript_unavailable}`. Pass the URL hash through `stage_lifecycle("capture", recording_url_hash=hashlib.sha256(url.encode()).hexdigest()[:16])` so US3's filename and contextvar story can rely on it being set as soon as capture begins. **Article VI.1 mitigation**: in the same edit, replace the two existing raw-URL log calls — `logger.info("capture.cache_hit", url=url)` (currently at zoom.py:91) and `logger.debug("capture.browser_open", profile=profile_path, url=url)` (currently at zoom.py:138) — with `url=redact_url(url)`. These are the only call sites in the codebase today that pass a raw recording URL to a logger (verified by grep). Import `redact_url` from `notetaker.utils.redact`.

**Checkpoint**: User Story 1 is complete. A user can `tail -f` the run log and see: `stage_start: capture` → heartbeats with frame counts → `stage_end: capture` → `stage_start: extract` → `stage_end: extract` (with metrics) → `stage_start: understand` → per-slide heartbeats → `stage_end: understand` (with cost) → `stage_start: synthesise` → `stage_end: synthesise` (with summary path). The MVP can ship here.

---

## Phase 4: User Story 2 - Find the log without hunting (Priority: P2)

**Goal**: A user opening a fresh shell can locate the active run's log file in under 10 seconds without copying any path from the original terminal.

**Independent Test**: Start a run. From a separate fresh shell, run `tail -f ~/.local/share/notetaker/logs/latest.log` and confirm it streams the active run. The original terminal must have printed the absolute log path once on startup.

### Implementation for User Story 2

- [X] T017 [US2] Print `"[notetaker] Logging to <abs-path>"` to stderr at the top of `_setup()` in `src/notetaker/cli.py`, immediately after `configure_logging` returns and the run-log path is known. One line, prefixed `[notetaker]` to match the existing capture-stage prompts. When file logging fell back to stderr-only, print `"[notetaker] WARNING: cannot write to <log_dir> (<reason>); continuing without file log"` instead.
- [X] T018 [US2] Implement `LogStore.update_latest_pointer(target: Path)` in `src/notetaker/utils/log_store.py`. Algorithm: write a temp symlink at `<log_dir>/.latest.log.tmp.<pid>` pointing at `target`, then `os.replace(tmp, <log_dir>/latest.log)` for atomicity. On `OSError` (Windows without dev mode, exotic FS) emit one structlog WARNING (`event="log_store.symlink_unsupported"`) and return cleanly. Call this from `start_run()` immediately after the run log path is created.
- [X] T019 [P] [US2] Extend `tests/unit/test_log_store.py` with: `update_latest_pointer` creates a symlink whose `readlink` matches the target absolute path; calling it twice points at the second target (atomic replace); when `os.symlink` raises `OSError`, the call returns without raising and writes one warning record.

**Checkpoint**: A user can find the active log via `latest.log` in any fresh shell. The original terminal prints the absolute path once. P2 ships independently of US3.

---

## Phase 5: User Story 3 - Reconstruct what happened after the fact (Priority: P3)

**Goal**: After a run completes (success or crash), the log file contains everything needed to reconstruct timing, cost, OCR fallback events, intentional pauses, and crash details — without re-running the pipeline. Old logs are pruned per retention.

**Independent Test**: (a) Run a pipeline to completion; `jq -c 'select(.event_category=="stage_end")' latest.log` returns 4 records with the same metrics shown in the console summary. (b) Crash a run mid-stage; the file's last meaningful record is an `unhandled_exception` with stage and traceback. (c) Pause for 60s at the "Press Enter when playback has started…" prompt; the log shows `waiting_for_input` then `resumed_from_input` with `wait_seconds≈60`. (d) Touch a stale log file's mtime to 60 days in the past (`touch -d '60 days ago' ~/.local/share/notetaker/logs/<old>.log`); run notetaker once with the default `retention_days=30`; confirm the stale file has been unlinked. (Convention matches `cache.retention_days`: `0` means *keep forever*, not *purge all*.)

### Implementation for User Story 3

- [X] T020 [US3] Wrap `app()` in `cli.main()` in `src/notetaker/cli.py` with `try / except BaseException as exc: logger.error("unhandled_exception", event_category="unhandled_exception", exc_type=type(exc).__name__, traceback=traceback.format_exc(), message=str(exc)); raise`. The log handler's flush-on-emit (T008) guarantees the record reaches disk before re-raise. Catch `BaseException` (not `Exception`) so KeyboardInterrupt is captured per research R-006. The active stage is read by structlog from contextvars set by `stage_lifecycle` (T011); no manual stage tagging needed at this layer.
- [X] T021 [US3] Wrap the two `input()` calls in `src/notetaker/stages/capture/adapters/zoom.py` (in `capture()` and `_wait_for_stop_signal()`) with explicit lifecycle markers. Before `input()`: `logger.info("capture.waiting_for_input", event_category="waiting_for_input", prompt=<the prompt string>)` and capture `t = monotonic()`. After `input()` returns: `logger.info("capture.resumed_from_input", event_category="resumed_from_input", prompt=<same string>, wait_seconds=monotonic()-t)`. The two prompts must be the same strings the existing `print(...)` calls show — keep the strings as module-level constants and reuse them in the print and the log.
- [X] T022 [US3] Verification-only task (no production code changes — all production behaviour is delivered by T006 + T010). Confirm that running the synthetic-fixture pipeline once produces exactly one `event=log_store.purge_stale` record per invocation in the run log, and that the record's `removed` + `kept` payload sums to the actual file count under `log_dir`. If verification fails, the bug is in T006; fix there.
- [X] T023 [P] [US3] Extend `tests/unit/test_log_store.py` with: a test that creates 5 dummy log files with mtimes spanning 0 to 60 days ago, calls `purge_stale(retention_days=30)`, and asserts only files newer than 30 days remain. Mark file mtimes via `os.utime`.
- [X] T024 [P] [US3] Add a unit test in `tests/unit/test_logging.py` (or new `tests/unit/test_unhandled_exception.py`, scoped to one file) that invokes a small typer `app` whose subcommand raises `RuntimeError("boom")`, calls `cli.main()` inside `pytest.raises(RuntimeError)`, and asserts the configured log file contains exactly one record with `event_category=="unhandled_exception"` and `payload.exc_type=="RuntimeError"`.

**Checkpoint**: All three user stories now work independently. The feature is complete. Polish phase tightens it.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end validation, documentation, and the integration test that ties US1 + US2 + US3 together.

- [X] T025 [P] Add an integration test in `tests/integration/test_run_log_file.py`. The test reuses the existing synthetic-fixture pipeline harness (see `tests/integration/test_pipeline_e2e.py` for the pattern) but redirects `cfg.logging.log_dir` to `tmp_path` and supplies a credential-bearing recording URL such as `https://zoom.us/rec/play/abc?pwd=SECRETSECRET&access_token=TOKENTOKEN`. After the run completes, the test asserts: (a) `tmp_path/latest.log` exists and is a symlink; (b) reading the file produces ≥ 4 `stage_start` and 4 `stage_end` records, one per stage, in pipeline order; (c) zero `unhandled_exception` records; (d) every `stage_end` has positive `elapsed_seconds` and a non-empty `payload`; (e) every record validates against `LogRecord.model_validate(...)`; (f) **Article VI.1 leak check**: the raw bytes of the log file contain neither `SECRETSECRET` nor `TOKENTOKEN` (i.e. `redact_url` is genuinely applied at every call site, not merely available as a helper).
- [X] T026 [P] Update `HOWTO.md` with a new section "How do I know notetaker is running?" placed before the "Common problems" table. Reference `~/.local/share/notetaker/logs/latest.log`, the `tail -f` pattern, and what a healthy heartbeat cadence looks like. Keep the section under 20 lines — the file is for users, not for the spec.
- [X] T027 Run `pytest` from the repo root; confirm the previous green count plus all new tests (T005, T007, T009, T012, T019, T023, T024, T025) pass. Total should be ≥ 53 + ~10 new ≥ 63 green. No live-API tests opted in.
- [ ] T028 (deferred — requires real Zoom recording + interactive Playwright session) Walk the manual verification steps in `specs/002-observability-logging/quickstart.md` (SC-001 through SC-007 plus FR-006 and the URL-redaction check) against a real Zoom recording. Required because the integration test (T025) cannot exercise the real Playwright + browser interactive path. Constitutes the per-Article-VII.2 "golden fixture" extension for this feature.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies. Can start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1 (config keys must exist before code reads them). Blocks all user-story phases.
- **Phase 3 (US1, P1)**: Depends on Phase 2. The MVP slice — alone delivers user-visible value.
- **Phase 4 (US2, P2)**: Depends on Phase 2. Independent of US1. Can ship before US1 if a team chooses (the banner + symlink work even with no heartbeats), but P1 priority means US1 should land first.
- **Phase 5 (US3, P3)**: Depends on Phase 2 and on `stage_lifecycle` from T011 (US1) so the contextvar `stage` is set when the unhandled-exception handler reads it. Practically: do US1 first, then US3.
- **Phase 6 (Polish)**: Depends on US1, US2, US3 all complete.

### Within-Phase Dependencies

**Phase 2**:
- T003, T004, T005 are all independent ([P] within Phase 2).
- T006 has no code dependency on T003/T004 but conceptually fits after them.
- T007 depends on T006 (tests of `LogStore`).
- T008 depends on T006 (uses `LogStore.start_run()` indirectly through the `file_path` it produces — though the wiring lives in T010).
- T009 depends on T008.
- T010 depends on T006 + T008.

**Phase 3 (US1)**:
- T011 (heartbeat module) and T012 (its tests) are independent of T013–T016.
- T013, T014, T015, T016 each touch a different stage file → all marked [P], can land in any order once T011 is in.

**Phase 5 (US3)**:
- T020, T021, T022 each touch a different file → all sequential because they share `cli.py` indirectly through wiring.
- T023 and T024 are test-only [P].

### Parallel Opportunities

- Phase 1: T001 || T002.
- Phase 2: T003 || T004 || T005 — three [P] tasks in parallel. Then T006 → T007 [P]. Then T008 → T009 [P]. Then T010.
- Phase 3 after T011 lands: T013 || T014 || T015 || T016 — four stages can be wrapped in parallel by four developers.
- Phase 6: T025 || T026.

---

## Parallel Example: User Story 1

```bash
# Once T011 (heartbeat machinery) is merged, four stage wrappers are independent:
Task: "Wrap extraction stage with stage_lifecycle in src/notetaker/stages/extraction/__init__.py"
Task: "Wrap synthesis stage with stage_lifecycle in src/notetaker/stages/synthesis/__init__.py"
Task: "Wrap understanding stage with stage_lifecycle + per-slide tick in src/notetaker/stages/understanding/__init__.py"
Task: "Wrap capture stage with stage_lifecycle and tick() in src/notetaker/stages/capture/adapters/zoom.py"
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Phase 1 (Setup) — T001, T002. ~15 minutes.
2. Phase 2 (Foundational) — T003 through T010. The bulk of plumbing. Each task is one focused commit.
3. Phase 3 (US1) — T011 through T016. The visible MVP behaviour.
4. **STOP and VALIDATE**: Run the pipeline. From a second terminal, `tail -f ~/.local/share/notetaker/logs/<latest>.log`. Confirm heartbeats and stage transitions. The user's original "how do I know it's running?" question is now answered.
5. Optionally cut a release / merge to main.

### Incremental Delivery

1. Setup + Foundational → file logging exists, no stage markers. (Limited value alone.)
2. + US1 → MVP. Heartbeats and stage tagging. (Ships.)
3. + US2 → discoverability. Banner + `latest.log`. (Ships.)
4. + US3 → post-mortem reconstruction. Crash capture + waiting_for_input + retention. (Ships.)
5. + Polish → integration test, HOWTO, real-Zoom verification. (Ships.)

### Single-Developer Strategy (likely here)

Tasks are sized for one commit each per Article VIII.2. Suggested order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15 → 16 → 17 → 18 → 19 → 20 → 21 → 22 → 23 → 24 → 25 → 26 → 27 → 28. The [P] markers identify safe parallel branches if a second contributor or a worktree is available, but a serial walk is fine.

---

## Notes

- [P] tasks = different files, no incomplete-task dependencies.
- [Story] label maps task to a user story (US1/US2/US3) for traceability and for shipping a partial feature.
- The contract file at `specs/002-observability-logging/contracts/log_record.py` and the runtime copy at `src/notetaker/contracts/log_record.py` MUST stay byte-identical. Any drift is an Article I.3 violation.
- The 30-frame `capture.progress` log line removed by T016 is replaced 1-for-1 by `tick("capture", "frames")`; no observability is lost, only generalised.
- No new third-party dependencies. structlog and typer are already pinned.
- Tests do not call any paid API. Article VII.3 untouched.
- The Article VI.1 mitigation (`redact_url`) is in T004 + T005. Quickstart includes a manual leak check (T028).
