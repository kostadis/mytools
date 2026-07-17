# Batch conversion pipeline

How to convert a whole directory tree of PDFs to 5etools JSON, unattended and
resumably — and how to recover when individual docs fail. This covers the four
batch scripts (`batch/batch_convert.py`, `batch/batch_mistral_ocr.py`,
`batch/batch_marker.py`, `lib/batch_state.py`) and their working data, which
now lives alongside them in `batch/`; for the single-PDF converter itself see
`README.md`.

---

## The shape of it

Conversion is split into three phases so the cheap, fast, deterministic work
(structure extraction) is separated from the expensive, slow, ML/network work
(OCR and LLM encoding). Each phase is independently resumable and writes its
progress to a shared SQLite **state DB** (`batch/dmsguild-state.db`), so a kill,
reboot, or dropped endpoint never loses work.

```
                 ┌─────────────────────────────────────────────┐
                 │  batch_convert.py --phase extract            │
                 │  fast PyMuPDF structural pass (parallel)      │
                 │  • bookmarked digital PDF → <stem>-extract.json
                 │  • everything else        → deferred (needs OCR)
                 └───────────────┬─────────────────────────────┘
                                 │  docs with no <stem>-extract.json
                 ┌───────────────▼─────────────────────────────┐
                 │  OCR the rest — pick ONE:                    │
                 │   batch_mistral_ocr.py   (cloud, best output)│
                 │   batch_marker.py        (local GPU/ML)      │
                 │  both write <stem>-extract.json (kind=lines) │
                 └───────────────┬─────────────────────────────┘
                                 │  every content doc now has an extract
                 ┌───────────────▼─────────────────────────────┐
                 │  batch_convert.py --phase encode             │
                 │  in-process LLM conversion → <stem>.json     │
                 └─────────────────────────────────────────────┘
```

`--phase all` (the default) runs extract→encode in one invocation. Use it only
when **no** docs need OCR; otherwise run the phases by hand so the OCR step can
slot in between, as above.

### Per-PDF artifacts (all land next to the source PDF)

| File | Written by | Meaning |
|---|---|---|
| `<stem>-extract.json` | extract / OCR pass | structural extract the encode pass consumes (`kind="lines"`) |
| `<stem>.json` | encode pass | the finished 5etools adventure JSON — its existence means **done** |
| `<stem>-mistral.md` | `batch_mistral_ocr` | raw OCR markdown (for cleanup in `editors/markdown_editor.py`) |
| `<stem>-mistral-images/` | `batch_mistral_ocr` | decoded page images, links rewritten in the `.md` |
| `<stem>-mistral-raw.json` | `batch_mistral_ocr` | complete raw OCR response (enables free re-render) |
| `<stem>-responses/` | encode pass | per-chunk LLM responses (enables free resume) |

Resumability is **artifact-driven**: every phase skips a doc that already has
its output file. Delete the artifact (or pass `--force`) to redo just that doc.

---

## State DB and bookkeeping

`lib/batch_state.py` owns `batch/dmsguild-state.db`. The `docs` table has one row per PDF
with a `status` and a `reason`:

| status | meaning |
|---|---|
| `done` | `<stem>.json` exists; nothing more to do |
| `skipped` | classified as non-content (art/map/token), image-only/scan failure, or `.extract_skip` |
| `pending` | content doc, not yet (successfully) converted |
| `failed` | attempted and errored (timeout, too-big, bad request, partial) |

Two flat files are written alongside for eyeballing:
- `batch/dmsguild-skiplist.tsv` — every `skipped` doc with its `reason`, page count, text size.
- `batch/dmsguild-logs/` — per-doc conversion logs.

Inspect counts directly when you want ground truth:

```bash
sqlite3 batch/dmsguild-state.db \
  "SELECT status, count(*) FROM docs GROUP BY status;"
sqlite3 batch/dmsguild-state.db \
  "SELECT rel, reason, exit FROM docs WHERE status='failed';"
```

---

## Common runs

```bash
# 0. Dry plan: scan, classify, write state DB + skiplist, then stop.
python3 batch/batch_convert.py --list

# 1. Fast structural pass over the whole tree.
python3 batch/batch_convert.py --phase extract

# 2a. OCR the deferred docs with Mistral (preferred — better output).
export MISTRAL_API_KEY=...
python3 batch/batch_mistral_ocr.py --no-profile --limit 10   # free tier caps a job at 10
#    ...repeat until the list is empty (already-extracted docs auto-skip):
python3 batch/batch_mistral_ocr.py --list                    # how many are left?

# 2b. ...or OCR locally with Marker instead (GPU, no API key).
python3 batch/batch_marker.py

# 3. Encode everything that now has an extract on disk.
python3 batch/batch_convert.py --phase encode --plan reuse
```

### `--plan` (fresh vs reuse vs ask)

`batch/batch_convert.py` decides up front what to do with the existing state DB:
- `--plan reuse` — continue from the DB as-is (the normal resume; what you want
  after an interruption or between phases).
- `--plan fresh` — re-plan from a clean scan.
- `--plan ask` (default) — prompt interactively. **Pass `reuse` or `fresh`
  explicitly in any unattended/scripted run** so it never blocks on a prompt.

---

## `batch/batch_mistral_ocr.py` — the OCR pass in detail

```bash
python3 batch/batch_mistral_ocr.py [--list] [--limit N] [--no-profile] [--force]
                             [--no-images] [--rebuild-from-raw]
                             [--resume-job JOB_ID] [--poll-interval SEC] [--verbose]
```

It selects PDFs that lack `<stem>-extract.json` and route to OCR, uploads them +
a JSONL manifest to the Mistral **Batch API** as one job (≈50% cheaper, async),
polls to completion, then for each doc renders the markdown/images/tables and
writes `<stem>-extract.json`.

| flag | use |
|---|---|
| `--list` | show the docs that would be submitted, then exit |
| `--limit N` | submit at most N this run (Mistral free tier caps a job at **10**); re-run for the next N |
| `--no-profile` | skip the per-PDF routing check. Sound **after** `--phase extract` has run — a doc with neither `<stem>.json` nor `<stem>-extract.json` is OCR-bound by construction. Cuts startup on a slow mount from minutes to ~5s |
| `--no-images` | text-only; don't download page image base64 (keeps results small for art-heavy books) |
| `--force` | re-OCR even if `<stem>-extract.json` already exists |
| `--rebuild-from-raw` | re-render `.md` / images / extract from saved `<stem>-mistral-raw.json` with **no API calls** — use after a parsing fix to refresh every already-OCR'd doc for free |
| `--resume-job ID` | a job was submitted but the script died before download; skip upload/submit and go straight to polling (see below) |

Key comes from `MISTRAL_API_KEY` or `--mistral-api-key`.

---

## Failure handling

The pipeline is built to make progress on the healthy docs and let you remediate
the broken ones separately, rather than failing the whole run.

### A doc died mid-encode (timeout / dropped endpoint / reboot)

Just re-run the encode phase. Cached per-chunk responses in `<stem>-responses/`
are reused automatically, so only the missing chunks re-bill:

```bash
python3 batch/batch_convert.py --phase encode --plan reuse
```

### Skip known-bad docs and make progress on the rest

After a run leaves some `failed`, carry those failures forward and let the next
run work the never-attempted docs instead of re-failing the known-bad ones:

```bash
python3 batch/batch_convert.py --phase encode --plan reuse --skip-failed
```

### Remediation pass — re-run ONLY the failures

Later, on a faster / less-contended box, attempt just the `failed` docs (cached
chunks still reused), e.g. with a smaller pool:

```bash
python3 batch/batch_convert.py --phase encode --plan reuse --only-failed --pool 2
```

### A doc failed over a size cap (`chunk_too_big` / `prompt_too_big`)

These are auto-skipped on a verbatim re-run (it would fail identically). Either
raise the matching cap (which re-queues them automatically):

```bash
python3 batch/batch_convert.py --phase encode --plan reuse --chunk-token-cap 28000
```

…or force a re-attempt at the same caps with `--retry-too-big`.

### Docs that will *never* convert — `.extract_skip`

Drop a `.extract_skip` file at the **top of the PDF's own directory** listing the
exact filename(s) to skip, one per line (`#` comments and blank lines ignored):

```
# Storm King's Thunder - Complete DM's Bundle/.extract_skip
193137-Yartar.pdf          # map-only, no text to convert
193137-poster-back.pdf
```

Matched docs are marked `skipped` (`reason=extract_skip`) and never queued — no
doc slot burned. The filter runs at dispatch, so it applies on both `--plan
fresh` and `--plan reuse`, and the count surfaces in the plan summary and
skiplist. Matching is on basename, so the same filename across different title
directories is handled per-directory.

### A Mistral OCR job submitted but the script died before download

The job ID is saved automatically to `batch/mistral-ocr-map.json`. Re-poll the
already-running (or already-SUCCESS) job and run the result handler without
re-submitting — and **without** spending fresh quota:

```bash
python3 batch/batch_mistral_ocr.py \
  --resume-job <JOB_ID> --resume-map batch/mistral-ocr-map.json --verbose
```

### A Mistral job came back not-`SUCCESS` (`FAILED` / `TIMEOUT_EXCEEDED` / `CANCELLED`)

The poller treats all of these as terminal. On anything but `SUCCESS` the tool
prints `job did not succeed; check Mistral dashboard`, writes **no** extracts,
and exits non-zero — results are not processed. Check the dashboard for the
cause (commonly an oversized PDF or a quota/tier limit), then just re-run the
normal command to resubmit. Docs that already have a `<stem>-extract.json` from
an earlier run auto-skip, so only the unfinished ones go back through.

### A job succeeded but some docs inside it failed (partial batch)

A `SUCCESS` job can still contain per-doc failures (a non-200 response for one
PDF). The succeeded docs get their `<stem>-extract.json`; the run prints
`FAIL <stem>: status …` for each bad one and ends with
`extracted N, failed M` (and exits non-zero if `M > 0`). The failed docs simply
have no extract, so the **next** `batch/batch_mistral_ocr.py` run re-selects and
re-OCRs them in a fresh job. Note `--rebuild-from-raw` does **not** rescue these
— a raw response is only saved for docs that returned a body, so a failed doc
has nothing to rebuild from; it must be re-submitted.

### A parsing bug dropped data (e.g. empty stat-block tables)

The complete raw OCR response is kept in `<stem>-mistral-raw.json`. After fixing
the renderer, refresh every already-OCR'd doc offline for free:

```bash
python3 batch/batch_mistral_ocr.py --rebuild-from-raw
```

### Force a clean redo of one doc

Delete its artifact and re-run the phase, or pass `--force`:

```bash
rm "Some Title/123-doc.json"            # redo encode for one doc
rm "Some Title/123-doc-extract.json"    # redo extract/OCR for one doc
```

---

## Quick reference — which flag, which situation

| situation | command |
|---|---|
| Plan only, don't convert | `batch/batch_convert.py --list` |
| Normal resume after interruption | `batch/batch_convert.py --phase encode --plan reuse` |
| Make progress, ignore prior failures | `… --plan reuse --skip-failed` |
| Re-run only the failures | `… --plan reuse --only-failed --pool 2` |
| Re-queue size-cap failures | `… --plan reuse --chunk-token-cap N` (or `--retry-too-big`) |
| OCR next 10 (free tier) | `batch/batch_mistral_ocr.py --no-profile --limit 10` |
| Resume a submitted OCR job | `batch/batch_mistral_ocr.py --resume-job ID --resume-map batch/mistral-ocr-map.json` |
| Re-render OCR docs after a parse fix | `batch/batch_mistral_ocr.py --rebuild-from-raw` |
| Never convert specific files | add them to `<pdf-dir>/.extract_skip` |
| Redo one doc | `rm <stem>.json` (or `<stem>-extract.json`) then re-run the phase |
