# Quickstart: Pipeline Progress Logging

How to verify the feature works once it ships. Each section maps to one or more numbered Success Criteria from `spec.md`.

## Prerequisites

You're in `~/src/notetaker` on branch `002-observability-logging` after implementation lands. The venv exists, deps are installed, you have a Zoom recording URL handy. Two terminals open side-by-side.

## Verify SC-001 / SC-002 (live progress + hang detection)

**Terminal A** — start a long-running run:

```bash
source venv/bin/activate
export ANTHROPIC_API_KEY=sk-ant-...
notetaker run "https://zoom.us/rec/play/<id>"
```

You should see one new line near the top of the output, before the "Press Enter when playback has started…" prompt:

```
[notetaker] Logging to /home/<you>/.local/share/notetaker/logs/20260509T143022Z-3f7a91c8b2d0e1f4.log
```

Copy that path. Click play in the Zoom browser. Press Enter in Terminal A.

**Terminal B** — without copying anything else from Terminal A:

```bash
tail -f ~/.local/share/notetaker/logs/latest.log
```

You should see the same file scroll. Within 15 seconds you should see a line whose `event_category` is `heartbeat` and whose `stage` is `capture`:

```json
{"schema_version":"1.0.0","ts":"2026-05-09T14:33:11Z","level":"info","stage":"capture","event":"capture.heartbeat","event_category":"heartbeat","recording_url_hash":"3f7a91c8b2d0e1f4","payload":{"frames":15,"utterances":3}}
```

✅ **SC-001 passes** if the most recent line tells you the active stage at a glance.
✅ **SC-002 passes** if you see a new line at least every 15 seconds while the capture is healthy.

## Verify SC-003 (crash leaves a usable log)

While capture is running in Terminal A, simulate a crash from Terminal B:

```bash
pkill -KILL -f "notetaker run"
```

Open the log in Terminal B (`less` not `tail` — the file's done):

```bash
less ~/.local/share/notetaker/logs/latest.log
```

The last record in the file should be either a final `heartbeat` or a final `stage_end`. There must NOT be a `stage_end` for `capture` (since you killed it mid-stage) — that's the signal that the pipeline died with `capture` active.

For a *graceful* crash test (e.g., raised exception), modify a stage to `raise RuntimeError("test")`, run again, and confirm the file contains:

```json
{"event_category":"unhandled_exception","stage":"capture","payload":{"exc_type":"RuntimeError","traceback":"...","message":"test"}, ...}
```

✅ **SC-003 passes**.

## Verify SC-004 (find the active log without copying paths)

Start a run in Terminal A. In a fresh shell (Terminal C — close and reopen if needed):

```bash
ls -lah ~/.local/share/notetaker/logs/
```

You should see two files: a timestamped run log and `latest.log` symlinked at it.

```bash
readlink ~/.local/share/notetaker/logs/latest.log
tail -f ~/.local/share/notetaker/logs/latest.log
```

Time yourself: opening a fresh shell, navigating to the log dir, running `tail -f`, and seeing live updates should take well under 10 seconds.

✅ **SC-004 passes**.

## Verify SC-005 (log-file size is bounded)

After a real-world ~60-minute capture:

```bash
ls -lh ~/.local/share/notetaker/logs/
```

The largest run log should be well under 5 MB. With the default 15-second heartbeat:
- ~240 capture heartbeats ≈ 36 KB
- 4 × stage_start + 4 × stage_end ≈ 2 KB
- Per-slide events from understand (one tick per ~5–10 unique slides during a meeting) ≈ 5 KB
- Per-occurrence synthesis events ≈ 5 KB

Total well under 100 KB for a 60-minute meeting. The 5 MB ceiling is generous.

✅ **SC-005 passes**.

## Verify SC-006 (post-hoc reconstruction)

After a successful run completes, in any terminal:

```bash
jq -c 'select(.event_category == "stage_start" or .event_category == "stage_end")' \
   ~/.local/share/notetaker/logs/latest.log
```

You should see exactly 8 lines: 4 starts and 4 ends, in order: capture, extract, understand, synthesise. Each `stage_end` should carry `elapsed_seconds` and the headline metrics that match what was printed to the terminal at the end of the run.

✅ **SC-006 passes**.

## Verify SC-007 (degraded mode when log dir is unwritable)

```bash
chmod 000 ~/.local/share/notetaker/logs
notetaker run "https://zoom.us/rec/play/<id>"
```

You should see exactly one stderr warning near the top:

```
[notetaker] WARNING: cannot write to /home/<you>/.local/share/notetaker/logs (PermissionError); continuing without file log
```

The pipeline should otherwise proceed normally — interactive prompts work, stderr console output appears as before.

Restore:

```bash
chmod 755 ~/.local/share/notetaker/logs
```

✅ **SC-007 passes**.

## Verify FR-006 (interactive pause is not a hang)

In Terminal A, start a run but do NOT press Enter at the first prompt for ~60 seconds. In Terminal B, watch the log:

```bash
tail -f ~/.local/share/notetaker/logs/latest.log
```

You should see, before the heartbeats begin:

```json
{"event_category":"waiting_for_input","stage":"capture","payload":{"prompt":"Press Enter when playback has started..."}, ...}
```

…and then no new lines until you press Enter, at which point a `resumed_from_input` record appears (with `wait_seconds` payload). Crucially, the `waiting_for_input` record makes it obvious the gap is intentional.

✅ **FR-006 verified**.

## Run the unit + integration tests

```bash
pytest tests/unit/test_logging.py
pytest tests/unit/test_heartbeat.py
pytest tests/unit/test_log_store.py
pytest tests/unit/test_redact.py
pytest tests/integration/test_run_log_file.py
```

All must pass. The integration test runs the synthetic-fixture pipeline and asserts the exact 8 stage-lifecycle records appear in the run log.

```bash
pytest                # full suite — should remain at 53+ tests, all green
```

## Verify URL redaction (Article VI.1)

Pass a URL with credential-bearing query parameters whose values are distinctive sentinels (so the grep below cannot be fooled by partial matches inside paths or hashes):

```bash
notetaker run "https://zoom.us/rec/play/abc?pwd=SECRETSECRET&access_token=TOKENTOKEN"
```

Then:

```bash
grep -E "SECRETSECRET|TOKENTOKEN" ~/.local/share/notetaker/logs/latest.log && echo "LEAK" || echo "redacted ok"
```

Expected: `redacted ok`. The log should contain `pwd=***` and `access_token=***` (or omit those parameters entirely), never the original values. The unit-level guarantee is `tests/unit/test_redact.py`; the end-to-end guarantee is `tests/integration/test_run_log_file.py` clause (f) — both must be in place for this manual check to be redundant rather than load-bearing.

✅ Article VI.1 risk mitigation verified.
