# Quickstart — Verify the human-readable notes + export + purge feature

A short, manual sanity-check walkthrough for someone who has just merged this feature. The full automated coverage lives under `tests/` and runs via `pytest`; this file is for the "does the new UX feel right end-to-end" eyeball check.

## Prerequisites

- Working notetaker checkout, venv active (`source venv/bin/activate`).
- `ANTHROPIC_API_KEY` exported (the summary call needs it).
- A Zoom recording URL you have access to (the existing `notetaker capture` workflow). For a smoke test, any recording ≥ 2 minutes is fine.

## Step 1 — Capture against a real recording

```bash
notetaker capture "<zoom-url>"
```

After capture finishes, check the cache entry's `meta.json`:

```bash
ls ~/.local/share/notetaker/cache/
# → one or more <16-hex>/ directories
cat ~/.local/share/notetaker/cache/<hash>/meta.json
```

Expected: `schema_version` is `"2"`, `meeting_title` is the recording's topic (or `null` if Zoom's page title scrape didn't resolve), `recording_date` is `null` or an ISO date, `summary` is `null`.

If you see `capture.meeting_title_unavailable` in the run log, the title scrape's CSS fallback didn't match the page; Zoom may have rotated its DOM. The cache entry is still usable; the filename derivation will fall back to `"untitled"`.

## Step 2 — Run extract + understand + notes

```bash
notetaker extract     "<zoom-url>"
notetaker understand  "<zoom-url>"
notetaker notes       "<zoom-url>" path/to/transcript.txt
```

Watch the final lines of `notes` output. Where you used to see:

```text
notes: /home/you/.local/share/notetaker/cache/<hash>/notes/notes.md
```

You should now see:

```text
notes: /home/you/.local/share/notetaker/cache/<hash>/notes/2026-04-15--Q2 Planning Sync--Roadmap, headcount, OKR rollovers.md
```

The exact title and summary will reflect your recording. The filename should:
- start with a `YYYY-MM-DD` date,
- contain the meeting title between `--` separators,
- contain the LLM-generated summary between `--` separators,
- end with `.md`,
- be ≤ ~200 characters total before `.md`.

Verify the cache:

```bash
ls ~/.local/share/notetaker/cache/<hash>/notes/
# → 2026-04-15--Q2 Planning Sync--Roadmap, headcount, OKR rollovers.md
# → working_doc.md
```

The `working_doc.md` filename is unchanged (FR-008).

`meta.json` should now have `summary` populated:

```bash
cat ~/.local/share/notetaker/cache/<hash>/meta.json
```

## Step 3 — Verify --re-render still works

```bash
notetaker notes "<zoom-url>" --re-render --force
```

Expected: same human-readable filename (deterministic from the same `meta.json`); content overwritten.

If the summary call returns a different summary on this run, the orchestrator renames the existing file to the new human-readable name. You should see `notes.legacy_renamed` records (or `notes.filename_changed` — check the logs).

## Step 4 — Export to a directory

Run a few captures so the cache has multiple entries, then:

```bash
notetaker export ~/notetaker-archive
```

Expected output:

```text
exported to: /home/you/notetaker-archive
copied=<N>  skipped_no_notes=0  skipped_collision=0  legacy_resolved=0
```

Verify:

```bash
ls ~/notetaker-archive/
# → one .md file per cached recording, each named per the human-readable convention
```

The cache copies are still in place:

```bash
ls ~/.local/share/notetaker/cache/<hash>/notes/
# → still contains the same .md file
```

Re-run export:

```bash
notetaker export ~/notetaker-archive
```

Expected: `copied=0  skipped_no_notes=0  skipped_collision=<N>` — the second run is a no-op (SC-005).

To force replacement:

```bash
notetaker export ~/notetaker-archive --overwrite
```

## Step 5 — Test the legacy `notes.md` rename

If you have an old cache entry produced before this feature shipped, find one with a literal `notes.md`:

```bash
find ~/.local/share/notetaker/cache -name notes.md
```

Run notes against its URL (or just export):

```bash
notetaker notes "<the-old-url>" --re-render --force
# OR
notetaker export ~/notetaker-archive
```

Expected: the legacy `notes.md` is renamed in place to the human-readable name (when `notes` runs), or exported under the human-readable name with the cache copy untouched (when `export` runs). The log records the rename / resolution.

## Step 6 — Purge the cache (optional; destructive)

After exporting everything you care about:

```bash
notetaker purge
```

Expected: a summary of what would be deleted, then a `Proceed? [y/N]:` prompt.

- Decline (`n` or Enter): output `purge cancelled`; cache untouched.
- Confirm (`y`): the cache root is emptied; the directory itself stays.

To bypass the prompt (e.g., from a script):

```bash
notetaker purge --yes
```

Verify:

```bash
ls ~/.local/share/notetaker/cache/
# → empty (or the directory is recreated empty)
ls ~/.local/share/notetaker/logs/
# → still populated (logs are NOT touched)
ls ~/notetaker-archive/
# → still populated (exports are NOT touched)
```

## Step 7 — Run the test suite

```bash
pytest                   # all non-live tests, ~2s
pytest -m live_api       # opt-in live API smoke tests (cost: a few cents)
```

Expected: green. New tests in scope:
- `tests/unit/test_notes_naming.py`
- `tests/unit/test_recording_meta.py`
- `tests/unit/test_notes_summary.py`
- `tests/unit/test_cache_ops.py`
- `tests/unit/test_zoom_title_scrape.py`
- `tests/contract/test_recording_meta_contract.py`
- `tests/integration/test_export_command.py`
- `tests/integration/test_purge_command.py`

Edited:
- `tests/integration/test_full_pipeline.py` (asserts the human-readable filename)
- `tests/integration/test_notes_command.py` (asserts the summary write to `meta.json`)

## What "good" looks like

- A user who hasn't read the code can find any meeting's notes by browsing the cache directory in their file manager.
- `notetaker export ~/Documents/MeetingNotes` produces a directory the user could share with another human without further explanation.
- `notetaker purge --yes` reclaims the cache's disk usage and leaves logs and exported notes in place.
