# HOWTO: Run notetaker on a Zoom recording

Practical end-to-end walkthrough. Spec-level docs live under `specs/`.

## One-time setup

Already done in this checkout (venv at `./venv/`, deps installed, Playwright Chromium installed). To start fresh:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

System-level prereqs (not pip-installable):

- **Tesseract 4+** for the OCR fallback path: `sudo apt install tesseract-ocr` (or `brew install tesseract` on macOS).
- **Google Chrome** installed and logged in to Zoom — Playwright reuses your real Chrome profile so the recording loads with your existing session.

## Each session

```bash
cd ~/src/notetaker
source venv/bin/activate
export ANTHROPIC_API_KEY=sk-ant-...   # required for Steps 3 and 5
```

Verify:

```bash
notetaker --help            # should print 5 subcommands (capture/extract/understand/run/notes)
pytest                      # 127 should pass; 1 (live_api) deselected
```

---

# End-to-end walkthrough

You have a Zoom Cloud Recording URL. Run these five steps in order.

## Step 1 — Capture frames (interactive, ≈ length of the meeting, free)

```bash
notetaker capture "<zoom-recording-url>"
```

What happens:

1. A headed Chrome window opens at the recording URL using your existing Chrome profile (so your Zoom session is already logged in).
2. **Before you press Enter in the terminal**, in the Chrome window:
   - Click play in the Zoom web player.
   - Open the **Audio Transcript** panel (right-side panel toggle). Even though the live transcript scrape is unreliable, it's worth letting it try — if it succeeds you skip Step 4.
3. Return to the terminal. Press Enter at `Press Enter when playback has started…`.
4. Notetaker now records ~1 frame/second from the player area for the entire playback duration.
5. When the recording finishes, press Enter at `Press Enter when playback is complete…`.

Output: `~/.local/share/notetaker/cache/<hash>/capture/`.

If the live transcript scrape couldn't find the panel you'll see this in the log (Step 4 covers it):

```
capture.transcript_unavailable  selector_used=.transcript-panel__content
recovery_hint=See HOWTO.md "Obtaining a transcript" to recover via post-capture procedure.
```

The slide artifacts (frames, slide_timeline.json, slide_content.json) are unaffected — only the transcript is missing.

## Step 2 — Detect unique slides (≈ 5–10 seconds, free)

```bash
notetaker extract "<same-url>"
```

Dedupes the captured frames into unique slides. Output: `~/.local/share/notetaker/cache/<hash>/extraction/slide_timeline.json`.

## Step 3 — Vision pass on each unique slide (≈ $0.001 per unique slide)

```bash
notetaker understand "<same-url>"
```

Sends each unique slide image to Claude Haiku and parses the response into structured slide content. For a 1-hour meeting expect 100–150 unique slides ≈ **$0.15–$0.25**. Final cost printed on completion. Output: `~/.local/share/notetaker/cache/<hash>/understanding/slide_content.json`.

If you see `vision.json_parse_error` warnings here, the parser already strips ` ```json … ``` ` fences automatically — those warnings would only appear for genuinely malformed responses.

## Step 4 — Get the transcript (free, manual)

**Skip this step if Step 1's live scrape succeeded** — i.e. the cache has a non-empty `<hash>/capture/transcript.json` and you didn't see a `transcript_unavailable` warning.

Otherwise, in Chrome on the same recording URL:

1. Open the **Audio Transcript** panel.
2. **Right-click any utterance row → Inspect.** Chrome DevTools opens with that node selected.
3. Open the **Console** tab. (Don't click anywhere else first — DevTools needs to keep `$0` pointing at the row you inspected.)
4. Paste the contents of [`mytools/scrape.js`][1] and press Enter. A red-bordered textarea appears at the top-left of the page containing the harvested transcript. Click into it, `Ctrl+A`, `Ctrl+C` if you want it on the clipboard.
5. To get a file instead, paste [`mytools/download.js`][2] in the same Console — it triggers a normal browser download of `zoom_chat.txt`.
6. Move the file somewhere convenient: `mv ~/Downloads/zoom_chat.txt ~/src/notetaker/`.

Alternative shapes `notetaker notes` accepts directly without conversion:

- **WebVTT (`.vtt`)** — if Zoom Cloud Recording offers a "Download Audio Transcript" button on the recording, take that file directly.
- **Notetaker `transcript.json`** — produced by a successful Step 1 live scrape; used automatically when no transcript path is supplied to Step 5.

[1]: https://github.com/kostadis/mytools/blob/main/scrape.js
[2]: https://github.com/kostadis/mytools/blob/main/download.js

## Step 5 — Produce the notes (≈ $0.10–$0.20)

With a transcript file in hand:

```bash
notetaker notes "<same-url>" path/to/zoom_chat.txt
```

Or, if Step 4 was skipped because Step 1's live scrape worked:

```bash
notetaker notes "<same-url>"
```

What it does:

1. Resolves the recording argument to the cache directory (URL hash convention used elsewhere in notetaker).
2. Sniffs the transcript file format (block / VTT / `transcript.json`) and parses it into the canonical schema. Falls back to the cached `transcript.json` if no path is supplied.
3. Concatenates `slide_content.json` (Step 3) and the parsed transcript into `<cache>/<hash>/notes/working_doc.md` — deterministic and inspectable.
4. Makes exactly **one** Sonnet call against the working doc, retrying on transient failure per the existing `[api]` retry policy.
5. Writes `<cache>/<hash>/notes/notes.md` and prints the absolute path plus a `input_tokens=… output_tokens=… cost=$…` summary line.

The last two lines of stdout name the file:

```
input_tokens=…  output_tokens=…  cost=$…
notes: /home/<you>/.local/share/notetaker/cache/<hash>/notes/<YYYY-MM-DD>--<meeting>--<summary>.md
```

The notes filename is composed deterministically from the meeting title (scraped
during capture), the recording date, and a one-line summary produced by a small
Haiku call after the main render. See `specs/005-notes-naming-and-export/` for
the full derivation rules.

Open it via the path the command printed, or browse the cache directly:

```bash
ls ~/.local/share/notetaker/cache/<hash>/notes/
# → <YYYY-MM-DD>--<meeting>--<summary>.md
# → working_doc.md
```

## Total cost expectation

For a typical 1-hour technical meeting:

| Step | Cost |
|---|---|
| 1 Capture | $0 |
| 2 Extract | $0 |
| 3 Understand (~150 unique slides × Haiku) | ~$0.15–$0.25 |
| 4 Transcript scrape | $0 |
| 5 Notes (one Sonnet render) | ~$0.10–$0.20 |
| **Total** | **~$0.25–$0.45** |

Re-running Step 5 with a different prompt or model is independently cacheable — see "Iterating cheaply" below.

---

# When things go wrong

## Notes are wrong

- **A specific slide's content is missing or garbled in the notes** → open `~/.local/share/notetaker/cache/<hash>/notes/working_doc.md` and search for the slide's title/bullets there. If the slide is wrong in the working doc, the bug is upstream (vision pass) — re-run Step 3 with `--force`. If the slide is correct in the working doc but missing from the notes, the LLM render dropped it.
- **Utterance attributed to the wrong speaker** → check the `**Speaker [HH:MM:SS]**` headers in the working doc. Wrong there → transcript parser bug. Right there → LLM render mistake.
- **Wording / structure of the rendered notes is off** → tweak `[notes] model` or the prompt in code, then re-render cheaply (no parse, no API spend on assembly):

  ```bash
  notetaker notes "<url>" --re-render --force
  ```

- **Want to test prompt changes by hand-editing the working doc** → edit `~/.local/share/notetaker/cache/<hash>/notes/working_doc.md` directly, then `--re-render --force`. The edited content goes straight into the LLM call.

- **Preview the spend before committing** → `--dry-run` reports projected cost without making the API call:

  ```bash
  notetaker notes "<url>" path/to/zoom_chat.txt --dry-run
  ```

## Live capture issues

| Symptom | Fix |
|---|---|
| `Zoom login wall detected` | Open Chrome manually, sign in to Zoom, close it, re-run Step 1. |
| `capture.transcript_unavailable` warning | Expected if the transcript panel wasn't open or Zoom changed CSS classes. Continue to Step 4 (manual transcript pull). The slide artifacts are intact. |
| `frames_manifest.json` has 0 frames | The slide CSS selector didn't match. Open the recording in Chrome DevTools, find the presentation `<video>` element, update `SLIDE_SELECTOR` in `src/notetaker/stages/capture/adapters/zoom.py`. |
| `vision.json_parse_error` warnings | The fenced-JSON stripper handles ` ```json ``` ` wrappers automatically; persistent failures indicate genuinely malformed Haiku output. Re-run Step 3 with `--debug` and inspect `understanding/raw/<sha256>.raw.json`. |
| Cache grew large | `cache.retention_days` (default 30) auto-purges old URL hashes at the start of every CLI invocation. The `notes/` subdirectory inside each cache is exempt and follows `[notes] retention_days` (default 365 days). |

---

# Reference

## Where output lives

```
~/.local/share/notetaker/cache/<url-hash>/
├── meta.json                            # v2 schema: recording_url, created_at,
│                                        # meeting_title, recording_date, summary
├── capture/
│   ├── frames/<ms>.jpg                  # Step 1: ~1 frame/sec
│   ├── frames_manifest.json
│   └── transcript.json                  # only if Step 1's live scrape succeeded
├── extraction/
│   └── slide_timeline.json              # Step 2: dedup + timeline
├── understanding/
│   └── slide_content.json               # Step 3: vision-extracted titles/bullets
└── notes/                               # Step 5 outputs
    ├── working_doc.md                   # deterministic input to the LLM render
    └── <YYYY-MM-DD>--<meeting>--<summary>.md   # ← read this
```

The notes filename is composed from the meeting title (scraped during capture
into `meta.json`), the recording date, and a generated summary (≤50 chars). It
is derived deterministically — the same recording always lands at the same
filename across re-runs, modulo summary changes.

The 16-character hash is computed from the recording URL (with tracking params stripped), so the same recording always lands in the same cache directory across runs.

## CLI subcommands

```bash
notetaker capture     "<url>"   # Step 1: interactive browser + frame capture
notetaker extract     "<url>"   # Step 2: slide-change detection (free)
notetaker understand  "<url>"   # Step 3: vision LLM per unique slide ($)
notetaker notes       "<url>" [transcript-path]  # Step 5: combine + render ($)

notetaker run         "<url>"   # convenience: chains capture → extract → understand,
                                # then prints the next-step `notetaker notes` command

notetaker export      "<dir>"   # copy every cached notes file into <dir>
                                # under its human-readable name (--overwrite to replace)
notetaker purge                 # delete the entire cache (with confirmation; --yes for scripts)
```

## Exporting and purging the cache

Once you have notes you care about, copy them out of the throwaway cache into a
directory you control (your personal archive, an Obsidian vault, a shared drive):

```bash
notetaker export ~/notetaker-archive
# → exported to: /home/<you>/notetaker-archive
# → copied=12  skipped_no_notes=1  skipped_collision=0  legacy_resolved=2
```

The export is non-destructive: the cache copies remain in place. By default a
collision in the target directory (a file with the same human-readable name
already exists, perhaps because you edited it) is preserved; pass `--overwrite`
to replace. Re-running the same command twice is idempotent in steady state.

When you're ready to reclaim disk space, purge the cache:

```bash
notetaker purge
# → Cache: /home/<you>/.local/share/notetaker/cache  ;  entries=12  total_size=4321 MB
# → Proceed? [y/N]:
```

`notetaker purge --yes` skips the prompt for non-interactive use. Purge removes
every cached recording (frames, transcripts, slide content, notes) but does NOT
touch logs, exported notes, or any directory outside the configured cache root.

Add `--force` to any stage to re-run even if cached. Add `--debug` to keep raw artifacts.

## `notetaker notes` modes

- **default** — parse → assemble → render → write `notes.md`. Refuses to overwrite an existing `notes.md` unless `--force`.
- **`--re-render`** — skip parse + assembly; reuse the existing `working_doc.md`; run only the LLM call. Requires `--force` to overwrite.
- **`--dry-run`** — parse + assemble, then report projected cost and exit without making the API call.
- **`--output <path>`** — override the default output path inside the cache.

## Retention

| Artifact | Knob | Default |
|---|---|---|
| Frames, slide_timeline, slide_content | `[cache] retention_days` | 30 days |
| `notes/working_doc.md`, `notes/notes.md` | `[notes] retention_days` | 365 days (`0` = forever) |
| Run logs (`~/.local/share/notetaker/logs/`) | `[logging] retention_days` | 30 days |

A purge runs at the top of every CLI invocation. The notes retention is a separate knob (per FR-018) so you don't lose user-facing output when the bulky frame cache turns over.

## Debug mode

```bash
notetaker capture "<url>" --debug
```

- `understanding/raw/<sha256>.raw.json` — the raw Claude vision response per unique slide. Useful when `vision.json_parse_error` warnings appear.
- Logging flips to DEBUG level.

## Cost control

The understanding stage calls the vision API once per **unique** slide (not per occurrence). The default ceiling lives in `config.toml`:

```toml
[understanding]
budget_ceiling_usd = 2.00
```

When the running total reaches this number, remaining slides fall back to Tesseract OCR. The CLI prints a yellow warning if any slide used OCR fallback. Raise the ceiling and re-run `notetaker understand <url>` (without `--force`, the already-billed slides are cached and won't be re-billed).

`budget_ceiling_usd = 0.0` forces OCR for every slide (no API spend, lower-quality content).

The notes stage doesn't have a hard ceiling because it's a single ~$0.15 call. `[notes] cost_warn_threshold_usd` (default $0.50) emits a warning record if exceeded but does not block.

## How do I know it's running?

The first thing every invocation prints — before any interactive prompt — is the absolute path of this run's log file:

```
[notetaker] Logging to /home/you/.local/share/notetaker/logs/20260509T161254Z.log
```

Then every stage logs to stderr in colorized human-readable form, plus the same events as JSON-lines on disk. Open a **second terminal** to tail without disturbing the interactive run:

```bash
tail -f ~/.local/share/notetaker/logs/latest.log | jq -c '{ts: .timestamp, cat: .event_category, stage, event}'
```

The heartbeat interval is **15 seconds by default** (`[logging] heartbeat_interval_seconds`). So:

- New line in the last 15 seconds → healthy.
- No new line for 30+ seconds → likely hung. Check the last `stage_start` to see which stage froze.
- Last record is `waiting_for_input` → blocked on you. Press Enter.
- Last record is `unhandled_exception` → the run died; the `traceback` field shows where.

### Useful one-liners

```bash
# Stage transitions only:
jq -c 'select(.event_category | IN("stage_start","stage_end","unhandled_exception"))' \
   ~/.local/share/notetaker/logs/latest.log

# Cost breakdown of the last completed run:
jq -c 'select(.event_category=="stage_end") | {stage, elapsed_seconds, total_cost_usd}' \
   ~/.local/share/notetaker/logs/latest.log

# Notes-command events of the last run:
jq -c 'select(.event | startswith("notes."))' \
   ~/.local/share/notetaker/logs/latest.log
```

## Iterating cheaply

The cache is layered. Re-running an upstream stage requires `--force`; downstream stages re-pick up the new artifacts on their next run.

- Tweak the notes prompt or model → `notetaker notes <url> --re-render --force` (Step 5 only, ~$0.15).
- Re-detect slide boundaries with a different threshold → `notetaker extract <url> --force` (Step 2 + downstream).
- Re-run vision on a specific slide set → `notetaker understand <url> --force` (Step 3 + Step 5 downstream).
- Re-capture from the browser → `notetaker capture <url> --force` (everything from Step 1).

## Tests

```bash
pytest                                            # all non-live, ~127 tests, ~2s
pytest tests/integration                          # synthetic-fixture pipeline tests
pytest -m live_api                                # opt in to real Claude API (costs money)
```
