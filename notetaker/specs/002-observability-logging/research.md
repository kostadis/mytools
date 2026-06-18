# Phase 0 Research: Pipeline Progress Logging

All technical unknowns referenced in `plan.md` are resolved below. No `NEEDS CLARIFICATION` markers remain.

## R-001: How to fan one structlog event out to two sinks (console + file) with two different renderers

**Decision**: Use the documented `structlog.stdlib.ProcessorFormatter` bridge. structlog runs the shared processor chain (timestamp, contextvars, level, etc.); the final event dict is then handed to a stdlib `logging.Logger` with two `Handler`s — a `StreamHandler(sys.stderr)` whose formatter is `ProcessorFormatter(processor=ConsoleRenderer())` and a `FileHandler(<run_log_path>)` whose formatter is `ProcessorFormatter(processor=JSONRenderer())`. Each handler renders the same event dict in its preferred form.

**Rationale**:
- One processor pipeline → one source of truth for fields. We never hand-build the same record twice.
- `ProcessorFormatter` is structlog's official multi-sink mechanism; no custom logger factories needed.
- Each handler can have its own `level`, so the file sink can stay at `INFO` while console stays at whatever the user chose, or both move to `DEBUG` together when `--debug` is set.
- File handler uses `delay=False` and sets `stream.reconfigure(line_buffering=True)` (or wraps in `FlushingFileHandler`) so each record is flushed at write time — meeting FR-007 (post-crash inspection).

**Alternatives considered**:
1. Custom `LoggerFactory` that writes JSON to a file and a separate processor that writes console to stderr. Rejected — duplicates the pipeline and risks divergence between sinks.
2. Single sink (file only), then `tail -f` from a wrapper script. Rejected — regresses interactive UX (FR-011); the user already values seeing typer's prompts and stage summaries inline.
3. Append everything as JSON to stderr and let the user redirect. Rejected — destroys the human-readable console, fails FR-016 ("human-readable when opened in a plain text viewer" applies to the file, but the existing console UX is also non-negotiable).

## R-002: Where on disk to put run logs

**Decision**: `~/.local/share/notetaker/logs/` by default, configurable via `[logging] log_dir`. Each run writes to `<UTC-iso-basic>-<url-hash>.log` (e.g., `20260509T143022Z-3f7a91c8b2d0e1f4.log`). A POSIX symlink `latest.log` in the same directory is atomically replaced at the start of each run.

**Rationale**:
- Co-locates with `~/.local/share/notetaker/cache/` so a user inspecting the data root finds both. Matches existing project convention.
- Filename encodes both timestamp (sortable, unambiguous) and recording identity (URL hash, same one used by `Cache`). Satisfies FR-010 + SC-004.
- Symlink replacement is `os.replace(tmp_link, target)` against a temp link created with `os.symlink`, which is atomic on POSIX. Satisfies FR-009.
- On Windows / non-symlink filesystems we skip the symlink with a single `WARNING` and the rest of the feature still works.

**Alternatives considered**:
1. Inside the per-recording cache dir (`<cache>/<url-hash>/run.log`). Rejected — same recording can have multiple runs over weeks; we'd either overwrite (loses history) or have to re-implement the "latest" pointer per cache dir. Centralised log dir is simpler.
2. CWD (`./notetaker.log`). Rejected — interactive shells run from many places; logs would scatter and pollute repos.
3. `/tmp/notetaker/...`. Rejected — `/tmp` is reaped by the OS; logs would vanish during a long run. Also fails the post-mortem use case (P3).

## R-003: How to enforce a heartbeat without spawning a background task

**Decision**: A `tick()` helper in `utils/heartbeat.py` that throttles emissions to at most one record per `heartbeat_interval_seconds` per `(stage, key)` tuple. Stage loops call `tick(stage="capture", key="frames", payload={"frames": n})` on every iteration; the helper checks a monotonic clock and decides whether to emit. No threads, no asyncio tasks.

**Rationale**:
- Robust under SIGKILL / OOM — there is no background thread that could survive the main loop and corrupt state on shutdown.
- The capture stage already runs an `await asyncio.sleep(interval)` loop at 1Hz. Calling `tick()` each iteration is free (just a clock comparison) until the throttle window elapses.
- For stages without a natural loop (synthesis is a small handful of model calls), we use a `with stage_lifecycle("synthesise") as life:` context manager that emits `stage_start` on enter, `stage_end` on exit, and exposes `life.tick(...)` for the few intermediate beats — same throttle semantics.
- The interactive `input()` blocks in capture are a hole in the heartbeat ("the user might pause for 20 minutes before clicking play"). We solve that explicitly with a `waiting_for_input` event emitted once before the call and a `resumed_from_input` event after — these are not heartbeats; they are mode markers, so the user sees the gap is intentional. Satisfies FR-006.

**Alternatives considered**:
1. Async `Heartbeat` task that wakes every N seconds and emits independently. Rejected — extra moving part, harder to reason about during shutdown, and doesn't actually know what the stage is doing right now (would need a shared mutable state cell). The throttled-tick approach pulls live state from the call site.
2. Logging frame count every 30 frames (current capture behaviour). Rejected for general use — couples cadence to a sample rate that varies per stage. The capture stage's existing 30-frame log will be replaced by `tick()` for consistency.

## R-004: Default heartbeat interval

**Decision**: 15 seconds, configurable via `[logging] heartbeat_interval_seconds`.

**Rationale**:
- SC-002 requires "a user observing 60+ seconds of silence can confidently classify the run as hung." A 15s interval gives 4× margin against transient slowness (network blips, GC pauses) before the user's 60s threshold.
- For capture at 1 fps, 15s = one heartbeat every 15 frames. Over a 60-minute capture: 240 heartbeats × ~150 bytes/JSON-line ≈ 36 KB. Comfortably under the 5 MB SC-005 ceiling, leaving headroom for stage-start/end records, transcript-poll warnings, and DEBUG verbosity.
- Half of a 30s `capture.progress` cadence (which is what's there today) — strictly an improvement.

**Alternatives considered**:
- 30s: matches today's capture.progress but leaves only 2× margin against the 60s "hung" threshold. Rejected.
- 5s: nicer for live tailing but produces 720 heartbeats per 60-min capture. Tractable, but wastes user attention and grows DEBUG-mode files quickly. Rejected as default; users can tune down via config.

## R-005: Log-line format

**Decision**: JSON-lines (one JSON object per line) for the file sink; the existing `ConsoleRenderer` (human-readable, colorized when TTY) for stderr. The JSON file is "human-readable enough" for `tail -f` because each record is a single line with stable key order (timestamp, level, stage, event first), but tooling can also parse it.

**Rationale**:
- Article V.1: "Logs are structured, not free text." JSON satisfies this directly.
- structlog's built-in `JSONRenderer` is zero-cost.
- A user running `tail -f latest.log` sees lines like `{"ts":"2026-05-09T14:33:11Z","level":"info","stage":"capture","event":"heartbeat","frames":42}` — readable in a pinch, machine-parseable when needed (jq, grep).
- The console sink remains pretty-printed so the interactive UX is unaffected (FR-011).

**Alternatives considered**:
1. logfmt-style `key=value` pairs in the file. More immediately readable in `tail -f`, but tooling support is weaker, and structlog's logfmt processor is not part of the stable API. Rejected.
2. Pretty-print each event over multiple lines in the file. Trivial to break with `tail -F` watchers. Rejected.
3. Console renderer to file too. Loses the structured-data advantage, gains no readability that matters at scale. Rejected.

## R-006: Capturing unhandled exceptions

**Decision**: Wrap the typer `app()` invocation in `cli.main()` in a `try/except BaseException` block that calls `logger.exception("unhandled_exception", stage=current_stage_var.get())` and re-raises. `current_stage_var` is a `contextvars.ContextVar` set by `stage_lifecycle()` so the error record carries the active stage tag.

**Rationale**:
- The structlog `ExceptionRenderer` already serializes traceback into a single string field, which the JSON renderer emits intact.
- Catching `BaseException` (not just `Exception`) covers `KeyboardInterrupt` — important because Ctrl-C during a long capture is the *expected* way users abort, and a clean record of "user cancelled at stage capture, frames=4123" is exactly the post-mortem signal P3 wants.
- contextvars propagate correctly through `asyncio.run()` boundaries (Python ≥ 3.7 contract).

**Alternatives considered**:
1. `sys.excepthook` override. Rejected — typer/click already manipulate the exception path; an excepthook can be missed. A try/except in `main()` is explicit and testable.
2. Per-stage try/except with re-raise. Rejected — duplicates code across four stages, and we'd still want a top-level catch for non-stage errors (config parse, cache init).

## R-007: URL redaction for credential safety

**Decision**: Add `redact_url(url: str) -> str` in `utils/redact.py`. It parses the URL with `urllib.parse.urlsplit`, blanks any query parameter whose name is in a denylist (`pwd`, `password`, `tk`, `token`, `access_token`, `auth`, `Authorization`, `signature`, `sig`), and replaces userinfo (`user:pass@host`) with `***@host`. The path component is preserved. All log entries that today log a recording URL go through this helper first.

**Rationale**:
- Zoom share-recording URLs commonly contain `?pwd=<token>` for password-bearing recordings — this is a real, common credential-in-URL case in our exact domain. Article VI.1 directly applies.
- Redaction is at the call site of the logger (a single helper), not via a structlog processor, so it's explicit and easy to grep for in code review.
- A unit test asserts that known-bad URL shapes are scrubbed.

**Alternatives considered**:
1. Hash the URL. Rejected — destroys the operator's ability to disambiguate runs by reading the log.
2. Log only the URL hash (the 16-char one already used as cache key). Considered — and adopted as the *additional* identifier in record metadata. The redacted URL is logged once at stage_start; the hash is logged on every record. Best of both.
3. structlog processor that scans every value for URL-shaped strings. Rejected — fragile, blanket regexes catch unrelated fields and complicate debugging.

## R-008: Retention policy for log files

**Decision**: Reuse the existing `cache.retention_days` value by default (30 days). Allow override via `[logging] retention_days`. Run `LogStore.purge_stale()` at the top of `_setup()` in `cli.py`, immediately after `Cache.purge_stale()`.

**Rationale**:
- Logs may carry transcript fragments and slide titles in DEBUG mode → fall under Article VI.2 ("Captured content has a retention policy").
- Aligning with the existing cache TTL is the expected behaviour. Diverging would surprise users.
- The purge runs once per CLI invocation at startup — same model the cache already uses, no daemon needed.

**Alternatives considered**:
1. Never purge. Rejected — Article VI.2 forbids indefinite retention by default.
2. Delete on successful run completion. Rejected — destroys the post-hoc reconstruction use case (P3).
3. Size-based rotation (`logging.handlers.RotatingFileHandler`). Rejected — splits a single run across multiple files, breaking the "one run = one file" invariant that makes `latest.log` and the discoverability story work. Each run's volume is bounded by R-004's heartbeat throttle, not by rotation.

## R-009: How to test file logging without race conditions

**Decision**: Tests configure logging to a `tmp_path / "test.log"`, run the unit under test, then read the file and parse it line-by-line as JSON. For the integration test, the synthetic-fixture pipeline already exists; we add an assertion that `<log_dir>/latest.log` (resolved via the test's `tmp_path`-based `log_dir` override) contains exactly four `stage_end` records and zero `unhandled_exception` records.

**Rationale**:
- structlog's `cache_logger_on_first_use=True` is the only sticky-state concern. Tests reset it via a `caplog`-style fixture that calls `structlog.reset_defaults()` and re-runs `configure_logging()` per test.
- File handlers are flushed by an explicit `logging.shutdown()` call in the fixture teardown so reads don't race against buffered writes.

**Alternatives considered**:
1. Mock the file handler. Rejected — defeats the purpose; we want to confirm bytes hit disk.
2. Use `pytest-structlog`. Rejected — adds a dependency for one feature; the in-test reset pattern is six lines.
