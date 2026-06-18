# Implementation Plan: Human-readable notes filenames, export, and cache delete

**Branch**: `005-notes-naming-and-export` | **Date**: 2026-05-10 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/005-notes-naming-and-export/spec.md`

## Summary

Three additive changes to the notetaker CLI. (1) When `notetaker capture` runs, it scrapes the Zoom recording page title and persists it (along with a date) into a versioned `meta.json` schema. (2) When `notetaker notes` finishes rendering, a small follow-up Haiku call produces a ≤50-character one-line summary of the rendered notes, and the notes file is written under a human-readable composite name `<YYYY-MM-DD>--<meeting-title>--<summary>.md` instead of the literal `notes.md`. The summary call is safe under the LLM Pipeline Design Rule: the LLM renders a label from already human-reviewable content (the rendered notes themselves), and a 10%-wrong label only changes a filename — no downstream automated step inherits the error. (3) Two new CLI subcommands — `export <dir>` (copy-not-move every cached notes file into a user directory under its human-readable name) and `purge` (rmtree the configured cache root with explicit confirmation). Legacy caches whose notes are still named `notes.md` are handled lazily: any later access (notes re-run, export) recomputes the human-readable name from whatever metadata is available and renames the cache file in place. No standalone migration is shipped.

## Technical Context

**Language/Version**: Python 3.11+ (current dev tree on 3.12 per existing `__pycache__/*.cpython-312.pyc`).
**Primary Dependencies**: `typer` (CLI), `playwright` (Zoom page scrape, already in tree), `anthropic` (Claude SDK, already in tree), `pydantic` (schemas), `structlog` (logging), `tomllib` (stdlib). No new top-level dependencies.
**Storage**: Local filesystem cache at `~/.local/share/notetaker/cache/<url-hash>/`. This feature extends `meta.json` with `meeting_title`, `recording_date`, `summary`, and bumps its `schema_version` to `2`. Legacy meta.json files (no `schema_version`) are read with defaults; they are migrated lazily on the next write.
**Testing**: `pytest` with the existing `[tool.pytest.ini_options]` config and the `live_api` opt-in marker. New unit tests cover filename derivation, sanitization, collision handling, and legacy-cache rename. New integration tests cover `export` (multi-entry cache, collision behaviour, missing-notes skip) and `purge` (confirmed and `--yes` paths). The existing full-pipeline integration test is extended to assert the notes file lands at the human-readable path.
**Target Platform**: Linux CLI (developer machine; WSL2 in current dev tree). Filename sanitization MUST also be safe on macOS HFS+/APFS; Windows is out of scope per current HOWTO.
**Project Type**: Single-project Python package + Typer CLI. No new directories outside `src/notetaker/`, plus the new spec directory.
**Performance Goals**: Export ≤ 5 s per 100 cached notes files on a local SSD (per spec SC-008). Filename derivation MUST add < 50 ms to the notes step (Haiku call dominates, ≈ 1–2 s). Purge MUST run as a single best-effort `shutil.rmtree` per cache entry without locking.
**Constraints**:
- Existing `meta.json` files (schema_version absent or `"1"`) MUST keep loading. No breaking change to the on-disk cache layout.
- The existing `--re-render`, `--dry-run`, `--output`, and `--force` semantics on `notetaker notes` MUST continue to work.
- The existing `[notes] retention_days` knob and `Cache.purge_stale`'s notes-exemption logic MUST keep applying to the renamed files (retention is keyed on the `notes/` subdirectory, not the filename inside it).
- The summary call cost MUST stay well under the existing `[notes] cost_warn_threshold_usd` (default $0.50). Haiku at ~600 input tokens + ~30 output tokens ≈ $0.0006 per call. No new budget knob is introduced.
- Filenames MUST be filesystem-safe across Linux ext4 and macOS APFS, MUST be ≤ 200 chars (excluding `.md`), and MUST contain only graphemes that survive shell tab-completion (no leading dot, no whitespace at the boundaries).
**Scale/Scope**: ~10 source files touched and ~6 added.
- Edits: `src/notetaker/cli.py` (+2 subcommands, +1 helper), `src/notetaker/cache.py` (+`Cache.notes_file_path()`, +`Cache.iter_entries()`), `src/notetaker/config.py` (+`NotesConfig.summary_model`, +`NotesConfig.summary_max_chars`, +`NotesConfig.filename_max_chars`), `src/notetaker/notes/__init__.py` (filename derivation + legacy rename), `src/notetaker/stages/capture/adapters/zoom.py` (title scrape), `config.toml` (new keys + comments), `HOWTO.md` (rename + new commands documented), `CLAUDE.md` (subcommand list + plan reference).
- New: `src/notetaker/contracts/recording_meta.py` (Pydantic schema for meta.json), `src/notetaker/notes/naming.py` (filename derivation + sanitization), `src/notetaker/notes/summary.py` (Haiku summary call with retry), `src/notetaker/cache_ops.py` (export + purge implementations called from cli.py), plus matching unit tests.

## Constitution Check

Reviewed against `.specify/memory/constitution.md` v1.1.0 (ratified 2026-05-08, amended 2026-05-09). No article requires amendment.

| Article | Compliance | Notes |
|---------|-----------|-------|
| I.1 Stage Isolation (NON-NEGOTIABLE) | PASS | `export` and `purge` are cache-management commands, not pipeline stages. They read the cache layout (`meta.json` + `notes/` subdir) but do not import any stage's internals. The four-stage pipeline (Capture → Extraction → Understanding → Notes) is unchanged. |
| I.2 Platform Adapters Are Isolated | PASS | Meeting-title scraping lives in `stages/capture/adapters/zoom.py` alongside the existing slide and transcript selectors. The output (a string in `meta.json`) is platform-neutral. Adding a future Gong/Chorus adapter would set `meta.json.meeting_title` from its own page conventions; downstream code never branches on platform. |
| I.3 Versioned Data Contracts | PASS | `meta.json` is being formalised as `RecordingMetaSchema` (Pydantic) with `schema_version` bumped from implicit `"1"` to explicit `"2"`. Legacy reads (no version, fewer fields) succeed via lenient defaults. Future field additions follow the existing version-bump discipline. `meta.json` is per-cache-entry metadata, not an inter-stage data contract; the named contracts in I.3 (Transcript, Slide Timeline, Slide Content) are unaffected. |
| I.4 Re-runnability | PASS | The new summary call is a sub-step of the existing fourth stage (Notes). It runs after the main render call; on failure, the system falls back to a deterministic placeholder and proceeds. The notes file is still re-runnable via `--re-render --force`; the filename is re-derived from `meta.json` on each run. |
| II.1 Separation of Concerns (NON-NEGOTIABLE) | PASS | `spec.md` describes WHAT/WHY (filenames, export, delete) without naming Haiku, Pydantic, Playwright, or Typer. This `plan.md` is where those choices are recorded. |
| II.2 Every Stage Documents Its Contract | PASS | New contract documents under `contracts/`: `recording-meta.md` (the meta.json v2 schema), `cli-surface.md` (the new `export` and `purge` subcommands), `notes-naming.md` (filename derivation rules + sanitization spec). |
| III.1 Vision LLM Calls Are Expensive | N/A | No new vision calls. |
| III.2 Cost Controls Are First-Class | PASS | The summary call's cost is rolled into the notes-stage cost reporting and observable per-call via `notes.summary_render` log records (`input_tokens`, `output_tokens`, `cost_usd`). It is bounded by Haiku's per-call envelope (~$0.001) and the existing `cost_warn_threshold_usd` already covers it. Degraded-mode fallback: on any summary-call exception (rate limit, network, parse), the system uses the placeholder `"no-summary"` and proceeds — the notes file still gets written. |
| III.3 No Hidden Real-Time Capture Without Consent | N/A | No new capture surface. The title scrape happens during the existing user-initiated capture session. |
| IV.1 No Magic Numbers | PASS | `summary_max_chars=50`, `filename_max_chars=200`, `summary_model="claude-haiku-4-5-20251001"`, `summary_input_token_price_per_million`, `summary_output_token_price_per_million` all live in `NotesConfig`. The disambiguator hash length (8 chars) is also a config knob (`filename_collision_suffix_chars`). |
| IV.2 Sensible Defaults | PASS | Defaults produce working filenames out of the box for any Zoom recording whose page title scrapes cleanly. Untitled-fallback path is exercised via the existing scrape-failure code path. |
| IV.3 Configuration Is Documented | PASS | All new keys ship with inline comments in `config.toml` (effect on output, default, units). |
| V.1 Every Stage Logs Its Decisions | PASS | New structured log records: `capture.meeting_title_scraped` (selector_used, title_len), `capture.meeting_title_unavailable` (recovery_hint), `notes.summary_render` (input_tokens, output_tokens, cost_usd, model, attempt), `notes.summary_fallback` (reason), `notes.filename_derived` (notes_filename, components, sanitized_chars), `notes.legacy_renamed` (from, to), `export.entry_copied` (source, dest), `export.entry_skipped_no_notes` (cache_id), `export.entry_skipped_collision` (dest, source), `export.summary` (copied, skipped_no_notes, skipped_collision, target_dir), `purge.entry_removed` (cache_id, bytes), `purge.summary` (entries_removed, bytes_reclaimed, cache_root). |
| V.2 Debug Mode Preserves Intermediates | PASS | With `--debug`, the capture stage writes the raw `page.title()` and the meeting-title scrape selector path under `<cache>/<hash>/capture/raw/title_scrape.json`. The summary call's raw response is preserved at `<cache>/<hash>/notes/raw/summary.raw.json`. |
| V.3 Failures Are Diagnosable Without Re-running | PASS | All structured records above carry enough context that a failed run is diagnosable from the log file alone. `notes.summary_fallback` records the reason (`api_error`, `parse_error`, `over_length`), which is sufficient to root-cause without re-execution. |
| VI.1 Credentials Are Never Logged | PASS | No new credential flow. The Anthropic API key continues to be read from env. |
| VI.2 Captured Content Has a Retention Policy | PASS | Renaming the notes file does not change retention semantics — `[notes] retention_days` is keyed on the `notes/` subdirectory's mtime, not the inner filename. The new `purge` command is a user-driven override of retention, which is the user's stated intent (it's a cache-clear command). |
| VI.3 Scope to User-Entitled Content | PASS | Meeting title is content the authenticated user already sees on the Zoom recording page. No bypass. |
| VII.1 Stage-Level Tests Are Required | PASS | New unit tests: `tests/unit/test_notes_naming.py` (sanitization, truncation, collision suffix, fallback name), `tests/unit/test_recording_meta.py` (v1→v2 lenient read, v2 round-trip), `tests/unit/test_notes_summary.py` (Haiku call mocked, length-cap defence, fallback paths), `tests/unit/test_cache_ops.py` (`export` and `purge` against a synthesised cache root). New integration tests: `tests/integration/test_export_command.py` (multi-entry cache, target-dir creation, collision behaviour, legacy `notes.md` rename-on-export), `tests/integration/test_purge_command.py` (confirmed prompt, `--yes` flag, missing-cache no-op). New unit test for the title scrape: `tests/unit/test_zoom_title_scrape.py` (Playwright `page.title()` mocked). |
| VII.2 Golden Fixtures for the Full Pipeline | PASS | The existing `tests/integration/test_full_pipeline.py` is extended to assert the notes file lands at the human-readable path (not `notes.md`) and that `meta.json` v2 is on disk afterwards. |
| VII.3 Cost-Sensitive Tests Are Mocked by Default | PASS | The summary call is mocked in unit/integration tests exactly the way the existing notes render call is mocked. A `live_api`-marked smoke test for the summary call is added but opt-in. |
| VIII.1 Phased Delivery | PASS | The three user stories (P1 naming, P2 export, P3 purge) are independently testable per the spec. Phase 1 ships P1 alone (cache contains human-readable filenames); Phase 2 adds `export`; Phase 3 adds `purge`. P1 alone delivers user value. |
| VIII.2 Task-Sized Commits | PASS | Followed in `tasks.md` (Phase 2 of /speckit). |
| VIII.3 Spec Drift Is Reconciled, Not Ignored | PASS | This plan is explicitly tied to the spec; any divergence during implementation forces a spec or plan update in the same change. |
| IX.2 Amendments Require Documentation | N/A | No constitution amendment in this feature. The new commands are not stages and the new `meta.json` fields are not inter-stage contracts. |

**Gate verdict**: PASS. No unjustified violations; no constitution amendment required.

## Project Structure

### Documentation (this feature)

```text
specs/005-notes-naming-and-export/
├── plan.md                                  # This file
├── research.md                              # Phase 0 — decisions and rationale
├── data-model.md                            # Phase 1 — meta.json v2 schema, naming entities
├── quickstart.md                            # Phase 1 — verify-the-feature walkthrough
├── contracts/
│   ├── recording-meta.md                    # meta.json schema v2 (fields, defaults, lenient v1 read)
│   ├── cli-surface.md                       # `export` and `purge` subcommands (args, exit codes, output)
│   └── notes-naming.md                      # Filename derivation rules + sanitization spec
├── checklists/
│   └── requirements.md                      # Created by /speckit-specify
└── tasks.md                                 # Phase 2 output (NOT created by /speckit-plan)
```

### Source Code (repository root)

The project is a single-tree Python package; this feature adds modules and edits a handful of existing ones. No directory relocation.

```text
src/notetaker/
├── cli.py                                   # EDIT: add `export` and `purge` subcommands; thin
│                                            #       wrappers that delegate to cache_ops.py.
├── config.py                                # EDIT: add NotesConfig.summary_model,
│                                            #       summary_max_chars=50, filename_max_chars=200,
│                                            #       filename_collision_suffix_chars=8, plus the
│                                            #       summary_input_token_price_per_million and
│                                            #       summary_output_token_price_per_million pricing
│                                            #       knobs that mirror the existing render-call ones.
├── cache.py                                 # EDIT: add `Cache.notes_file_path()` (resolves the
│                                            #       human-readable filename, creating it from
│                                            #       meta.json if missing); add `Cache.iter_entries()`
│                                            #       classmethod that yields (hash, meta) pairs for
│                                            #       export/purge to walk the cache root.
├── cache_ops.py                             # NEW: pure functions `export_notes(cache_root, target,
│                                            #       overwrite)` and `purge_cache(cache_root,
│                                            #       confirmed)`. Both return structured result
│                                            #       dataclasses for cli.py to format.
├── contracts/
│   ├── recording_meta.py                    # NEW: Pydantic RecordingMetaSchema with
│                                            #       schema_version="2". Lenient read of legacy
│                                            #       (no version) meta.json by treating missing
│                                            #       fields as defaults; on next write, the schema
│                                            #       version is set and missing fields populated.
│   ├── log_record.py                        # untouched (no new event_category enum values needed —
│                                            #       all new records use existing categories).
│   ├── transcript.py                        # untouched
│   ├── slide_timeline.py                    # untouched
│   ├── slide_content.py                     # untouched
│   └── frames_manifest.py                   # untouched
├── notes/
│   ├── __init__.py                          # EDIT: after the render call, invoke summary.py to
│                                            #       generate the summary, persist it into
│                                            #       meta.json, derive the filename via naming.py,
│                                            #       and write notes under that name. On
│                                            #       --re-render, re-derive from current meta.json.
│                                            #       Detect legacy `notes.md` and rename to the new
│                                            #       human-readable path before writing.
│   ├── naming.py                            # NEW: filename derivation + sanitization. Pure
│                                            #       functions, fully unit-testable. Public surface:
│                                            #       `derive_notes_filename(meta) -> str` and
│                                            #       `sanitize_component(s, max_len) -> str`.
│   ├── summary.py                           # NEW: Haiku summary call with retry (uses the
│                                            #       existing api retry policy). Public surface:
│                                            #       `generate_summary(notes_text, config, client)
│                                            #       -> SummaryResult`. Defensive: caps the result
│                                            #       to summary_max_chars; on failure returns a
│                                            #       SummaryResult with `outcome="fallback"` and
│                                            #       text `"no-summary"` instead of raising.
│   ├── render.py                            # untouched
│   └── working_doc.py                       # untouched
├── stages/
│   ├── capture/
│   │   └── adapters/
│   │       └── zoom.py                      # EDIT: after _open_browser succeeds, scrape page
│   │                                        #       title via page.title() with a CSS-selector
│   │                                        #       fallback for the recording-topic element.
│   │                                        #       Persist into meta.json via the new
│   │                                        #       RecordingMetaSchema. On scrape failure,
│   │                                        #       record `capture.meeting_title_unavailable`
│   │                                        #       and write meta.json with `meeting_title=null`.
│   ├── extraction/                          # untouched
│   └── understanding/                       # untouched
└── utils/                                   # untouched

tests/
├── unit/
│   ├── test_notes_naming.py                 # NEW: derivation, sanitization, truncation,
│                                            #       collision-suffix, fallback name, ASCII-only
│                                            #       safety check, length cap.
│   ├── test_recording_meta.py               # NEW: v1 (legacy, missing version) lenient read,
│                                            #       v2 round-trip, write upgrades v1→v2.
│   ├── test_notes_summary.py                # NEW: mocked Haiku call, length-cap defence,
│                                            #       fallback on api_error / parse_error /
│                                            #       over_length.
│   ├── test_cache_ops.py                    # NEW: export against synthetic cache (3 entries,
│                                            #       1 missing notes, 1 collision), purge
│                                            #       against synthetic cache, both confirmed
│                                            #       and missing-cache cases.
│   ├── test_zoom_title_scrape.py            # NEW: mocked Playwright page; success + fallback.
│   ├── test_cache.py                        # untouched
│   └── (other unit tests untouched)
├── contract/
│   └── test_recording_meta_contract.py      # NEW: schema_version field is mandatory in v2;
│                                            #       legacy reads tolerate its absence.
└── integration/
    ├── test_full_pipeline.py                # EDIT: assert the notes file lands at the human-
    │                                        #       readable path; assert meta.json v2 round-trip.
    ├── test_export_command.py               # NEW: end-to-end export against a populated synthetic
    │                                        #       cache root, including collision and missing-
    │                                        #       notes cases and a legacy `notes.md` entry.
    ├── test_purge_command.py                # NEW: confirmed prompt path, `--yes` flag,
    │                                        #       missing-cache no-op, sibling-dir untouched
    │                                        #       (logs/ MUST survive purge).
    └── test_notes_command.py                # EDIT: add a case asserting the produced notes
                                             #       file matches the human-readable name and
                                             #       that meta.json gets the summary written.

config.toml                                  # EDIT: new [notes] keys with inline comments;
                                             #       no removals.
HOWTO.md                                     # EDIT: rename "notes.md" references to the
                                             #       human-readable form; document `notetaker
                                             #       export` and `notetaker purge`; update the
                                             #       "Where output lives" tree.
CLAUDE.md                                    # EDIT: bump CLI subcommand count from 5 to 7;
                                             #       update SPECKIT block to point at this plan.
pyproject.toml                               # untouched (no new dependencies).
.specify/memory/constitution.md              # untouched (no amendment required).
```

**Structure Decision**: Existing single-project layout retained. The two new pure-logic modules — `notes/naming.py` and `notes/summary.py` — sit under the existing `notes/` package because they are logically scoped to the notes step. `cache_ops.py` lives at package root rather than under `notes/` because `purge` is cache-wide, not notes-specific; placing it at root mirrors the existing `cache.py` and avoids a misleading directory hierarchy. `contracts/recording_meta.py` sits alongside the other Pydantic contract schemas. No new top-level directories are introduced.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

The Constitution Check passed without violations. The two design choices that warrant explicit tracking — both because a reviewer might reasonably ask why we chose them — are recorded here for accountability rather than because they violate any article.

| Item | Why Needed | Simpler Alternative Rejected Because |
|------|-----------|-------------------------------------|
| Separate Haiku summary call (rather than asking the main Sonnet render call to also emit a 50-char title line) | Two reasons: (a) Reliability — extracting a fixed-format header from free-form Markdown is brittle; the Sonnet output is optimised to be readable notes, not parseable metadata. A separate JSON-shaped Haiku call gives a structured response with a length cap built into the prompt. (b) The LLM Pipeline Design Rule (global CLAUDE.md): the summary call's output feeds a *filename* (a label on already human-reviewable content), not another LLM step. Keeping it as a discrete call makes it easy to fall back deterministically (`"no-summary"`) without contaminating the main render. | *Asking the Sonnet render to prepend a `# Title: <50-char summary>` line and parsing it out.* Rejected — every render-prompt change risks regressing the polished-notes output (the user's primary deliverable), and the parse step would need its own fallback path anyway. *Skipping the summary entirely and using only meeting title + date.* Rejected because the spec's User Story 1 explicitly asks for a one-line descriptive summary; meeting titles alone are too coarse when a user has many syncs with similar names ("Q2 Planning Sync" appears weekly). |
| Promote `meta.json` to a versioned Pydantic schema (`schema_version="2"`) instead of just adding loose fields | The cache layout is a long-lived contract; the codebase already treats inter-stage contracts as versioned. Formalising `meta.json` now (1) gives lenient-read-by-default semantics for existing caches, (2) makes future field additions follow an established pattern (Article I.3 discipline), and (3) catches malformed legacy meta.json files at read time with a clear error rather than at field-access time with an opaque `KeyError`. | *Reading `meta.json` as a raw dict with `.get(field, default)` everywhere.* Rejected — scatters defaults across call sites, makes future field additions risk silent breakage, and offers nothing for legacy reads that the schema doesn't already give us. The Pydantic dependency is already in the tree; the marginal cost is one small file. |
