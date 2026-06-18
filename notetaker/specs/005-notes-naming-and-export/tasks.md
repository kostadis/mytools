---

description: "Task list for spec 005 — human-readable notes filenames, export, and cache delete"
---

# Tasks: Human-readable notes filenames, export, and cache delete

**Input**: Design documents from `specs/005-notes-naming-and-export/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/recording-meta.md`, `contracts/cli-surface.md`, `contracts/notes-naming.md`, `quickstart.md` (all present).

**Tests**: This feature adds new modules and behaviour, so per Article VII.1 ("each stage must have tests that verify its contract") and VII.2 ("at least one end-to-end fixture must exist and pass") test tasks are included alongside the implementation tasks. Tests are mocked-by-default per VII.3.

**Organization**: Tasks are grouped by user story (US1 / US2 / US3 from `spec.md`) so each story is independently completable, testable, and demoable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Different file from siblings in the same phase, no dependency on incomplete tasks → can run in parallel.
- **[Story]**: User story tag (`[US1]`, `[US2]`, `[US3]`). Setup, Foundational, and Polish phases have no story label.
- All file paths are repository-relative.

## Path Conventions

Single-project Python layout: `src/notetaker/...`, `tests/...` at repo root. Confirmed in `plan.md → Project Structure`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Capture the pre-feature pytest baseline so the polish phase can verify "all prior tests still pass plus the new ones added by this feature" (Article VII.1).

- [X] T001 Capture pytest baseline by running `pytest --collect-only -q 2>&1 | tail -5` from the repo root and `pytest -q 2>&1 | tail -3` to record both the collected and the passing test counts. Note the numbers in a temporary scratch file (cross-checked in T031). Do not modify any source files. **Baseline: 128 passing.**

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Land the shared building blocks that all three user stories depend on: the versioned `meta.json` schema, the new config knobs, the pure-logic naming module, and the `Cache` API extensions. Each block ships with full unit-test coverage so the user-story phases can compose against verified primitives.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 [P] Add the new configuration fields in `src/notetaker/config.py`. In `NotesConfig`, append: `summary_model: str = "claude-haiku-4-5-20251001"`, `summary_max_chars: int = 50`, `summary_input_token_price_per_million: float = 0.80`, `summary_output_token_price_per_million: float = 4.00`, `filename_max_chars: int = 200`, `filename_collision_suffix_chars: int = 8`. In `CaptureConfig`, append: `recording_title_selector: str = ".recording-topic, .topic-name, h1"`. Update the corresponding entries in `config.toml` (project root) with inline comments explaining the effect of each knob per Article IV.3. Reference values: see `data-model.md → Configuration additions`.

- [X] T003 [P] Create the `RecordingMetaSchema` Pydantic model at `src/notetaker/contracts/recording_meta.py` with fields, defaults, and validation rules per `contracts/recording-meta.md`. Implement two helpers on the model: `RecordingMetaSchema.from_path(path: Path) -> RecordingMetaSchema` (lenient v1 read — treat absent `schema_version` as `"1"`, populate missing v2 fields with `None`) and `model.write(path: Path) -> None` (always serialises with `schema_version="2"`). Module-level constant `CURRENT_SCHEMA_VERSION = "2"`.

- [X] T004 [P] Write unit tests at `tests/unit/test_recording_meta.py` covering: (a) lenient read of a legacy file containing only `{recording_url, created_at}` returns a model with `schema_version="1"` and the new fields all `None`; (b) round-trip of a v2 file preserves every field; (c) `write()` after a lenient read upgrades the on-disk file to `schema_version="2"`; (d) bad `schema_version` (`"3"`) raises a clear validation error; (e) malformed `recording_date` (`"2026/04/15"`) raises; (f) empty `meeting_title` is normalised to `None`. Depends on T003.

- [X] T005 [P] Write a contract test at `tests/contract/test_recording_meta_contract.py` asserting that `RecordingMetaSchema().model_dump()` always emits `schema_version="2"`, that `recording_url` and `created_at` are required, and that the lenient v1 read path is the only mode where `schema_version` may be absent on input. Depends on T003.

- [X] T006 Create `src/notetaker/notes/naming.py` implementing the public surface from `contracts/notes-naming.md`: `derive_notes_filename(meta: RecordingMetaSchema, *, max_chars: int, summary_max_chars: int, collision_suffix: str | None = None) -> str` and `sanitize_component(raw: str | None, *, max_chars: int, fallback: str) -> str`. Implement the sanitization pipeline (steps 1–7 from `contracts/notes-naming.md → Sanitization pipeline`) and the composition rules (steps 1–6 from `contracts/notes-naming.md → Composition rules`). Pure functions — no IO, no logging. Depends on T003.

- [X] T007 [P] Write unit tests at `tests/unit/test_notes_naming.py` covering: (a) the edge-case examples table from `contracts/notes-naming.md → Edge-case examples` (one assertion per row); (b) `test_filename_under_cap_for_pathological_titles` — a 500-character meeting title still produces a filename ≤ `filename_max_chars + len(".md")`; (c) collision-suffix mode produces a deterministic disambiguated name when `collision_suffix` is provided; (d) `recording_date=None` falls back to `meta.created_at[:10]`; (e) both date sources missing → `"undated"` prefix and a single warning is logged. Depends on T006.

- [X] T008 Edit `src/notetaker/cache.py`. (a) In `Cache.initialise()`, replace the ad-hoc `meta = {...}` dict with a `RecordingMetaSchema(...)` instance and write via `model.write(meta_path)`. The capture-stage caller will populate `meeting_title` later (US1); for now `Cache.initialise()` writes `meeting_title=None` and `recording_date=None`. (b) Add `Cache.notes_file_path(self) -> Path | None` that reads `meta.json` (returning `None` if missing or if no human-readable file is present yet), derives the human-readable filename via `notes.naming.derive_notes_filename(...)`, and returns `<cache>/<hash>/notes/<derived-name>.md`. (c) Add classmethod `Cache.iter_entries(cache_root: Path) -> Iterator[tuple[str, RecordingMetaSchema]]` that walks `cache_root`, skips entries without a valid `meta.json`, and yields `(url_hash, meta)` for each surviving entry. Depends on T003 and T006.

- [X] T009 [P] Extend `tests/unit/test_cache.py` with cases for the new surface from T008: (a) `Cache.iter_entries` against a synthetic cache root containing three valid entries, one entry missing `meta.json` (must be skipped), one entry with malformed `meta.json` (must be skipped with a debug log); (b) `Cache.notes_file_path` returns `None` when `meta.json` is absent, returns the derived path when present and the file exists, returns the derived path even when the file does not yet exist (caller is responsible for creation); (c) `Cache.initialise` writes a v2 meta.json that round-trips through `RecordingMetaSchema.from_path`. Depends on T008.

**Checkpoint**: All foundational tests green. The on-disk cache layout is now governed by a versioned schema; the naming pipeline and the cache walker are unit-tested. User story phases can begin.

---

## Phase 3: User Story 1 — Notes files have human-readable names (Priority: P1) 🎯 MVP

**Goal**: Running `notetaker notes <url>` writes the notes file under a human-readable composite name (`<YYYY-MM-DD>--<meeting>--<summary>.md`) inside the cache. The Zoom recording's meeting title is scraped during capture; a small Haiku call after the main render produces the ≤50-char summary; legacy `notes.md` files are renamed lazily on next access.

**Independent Test**: From `quickstart.md → Step 1–3`: run a full capture/extract/understand/notes pipeline against any Zoom recording. Verify (a) `meta.json` is v2 with `meeting_title`, `recording_date` and `summary` populated, (b) the `notes/` subdirectory contains a single Markdown file whose name matches the human-readable convention and contains the recording date, (c) `working_doc.md` is unchanged, (d) `--re-render --force` produces the same filename when the summary is stable. From a fixture-only path: `pytest tests/integration/test_notes_command.py tests/integration/test_full_pipeline.py` is green with the new assertions.

### Implementation for User Story 1

- [X] T010 [US1] Create `src/notetaker/notes/summary.py` exposing `generate_summary(notes_text: str, config: Config, *, client=None) -> SummaryResult`. The `SummaryResult` dataclass matches the fields in `data-model.md → SummaryResult`. The function makes a single Anthropic API call to `config.notes.summary_model` with a JSON-shaped prompt (`{"summary": "<text>"}`) asking for a ≤50-char one-line summary of the supplied notes. Wrap the call in the existing `[api]` retry policy (mirror `notes/render.py`'s retry handling). Defensive truncation: if the parsed `summary` exceeds `config.notes.summary_max_chars`, truncate at the last word boundary and log `notes.summary_overlong` at debug level. On any uncaught exception or JSON parse error, return `SummaryResult(text="no-summary", outcome="fallback", ...)` and log `notes.summary_fallback` with `reason` set to one of `"api_error"`, `"parse_error"`, `"over_length"`. Cost computation uses `config.notes.summary_input_token_price_per_million` / `summary_output_token_price_per_million`. Depends on T002.

- [X] T011 [P] [US1] Write unit tests at `tests/unit/test_notes_summary.py`: (a) success path — mocked client returns `{"summary": "Roadmap, headcount, OKRs"}` → `SummaryResult.outcome=="success"` and `text` equals the input; (b) over-length response — mocked client returns a 90-char summary → result is truncated to ≤ `summary_max_chars` and `notes.summary_overlong` logged; (c) malformed JSON response → `outcome=="fallback"`, `text=="no-summary"`, `reason=="parse_error"`; (d) Anthropic API exception → `outcome=="fallback"`, `reason=="api_error"`, retry-policy attempt count reflects retries; (e) cost calculation matches `(input_tokens / 1e6) * input_price + (output_tokens / 1e6) * output_price` to 4 decimal places. Depends on T010.

- [X] T012 [US1] Edit `src/notetaker/stages/capture/adapters/zoom.py` to add a meeting-title scrape. After `_open_browser` returns successfully (around line 149, before the `_PROMPT_PLAYBACK_STARTED` prompt), call a new helper `_scrape_meeting_title(page) -> str | None` that (1) tries `await page.title()` and returns it if the result is non-empty and not equal to one of the known generic Zoom titles (`"Zoom"`, `"Zoom Meetings"`, `"Zoom — Recording"`); (2) falls back to `page.locator(self.config.capture.recording_title_selector).first.text_content()` and returns the first non-empty match; (3) returns `None` on any exception. Persist the result by extending `Cache.initialise()`'s call site so the title is passed into `RecordingMetaSchema(meeting_title=...)` at write time. Log success as `capture.meeting_title_scraped` with `selector_used`, `title_len`, `title_truncated_for_log` (first 80 chars only — Article VI.1 redaction discipline); log absence as `capture.meeting_title_unavailable` with a `recovery_hint` directing the user to the `--debug` raw artifact. With `--debug`, write the raw `page.title()` and the selector chain attempted to `<cache>/<hash>/capture/raw/title_scrape.json` per Article V.2. Depends on T002, T003, T008.

- [X] T013 [P] [US1] Write unit tests at `tests/unit/test_zoom_title_scrape.py` using a Playwright `Page` mock (do not start a real browser): (a) `page.title()` returns `"Q2 Planning Sync"` → scrape returns `"Q2 Planning Sync"` and the locator-fallback is not invoked; (b) `page.title()` returns `"Zoom"` → scrape falls back to the locator and returns the locator's text; (c) `page.title()` raises → scrape returns `None`; (d) the scrape never raises (any exception is swallowed and surfaces as `None`). Use the existing `tests/unit/test_zoom_capture_transcript_unavailable.py` mocking style as a template. Depends on T012.

- [X] T014 [US1] Update the notes orchestrator at `src/notetaker/notes/__init__.py` end-to-end. (a) Replace the `_notes_paths(cache, config)` helper's hard-coded `notes_filename` lookup with a new helper `_resolve_notes_path(cache, config, summary)` that loads `meta.json`, applies `summary` to the in-memory model (without writing yet), calls `notes.naming.derive_notes_filename(...)`, and returns the resolved path. (b) After the existing `render_notes(...)` call (around line 197), import `notes.summary.generate_summary` and call it on `result.text`, then assign the resulting summary string to `meta.summary` and write the upgraded `meta.json` via `model.write(...)`. Roll the summary call's `total_cost_usd` into the run's `result.cost_usd` and emit a `notes.summary_render` log record with `input_tokens`, `output_tokens`, `cost_usd`, `model`, `attempt`, and `outcome`. (c) Detect the legacy filename: if `<cache>/<hash>/notes/notes.md` exists and the human-readable target does not, rename `notes.md` → `<derived>.md` (atomic rename within the same directory) and emit `notes.legacy_renamed` with `from`/`to` paths before writing new content. (d) When the human-readable target already exists with content matching `result.text`, no rewrite is needed (idempotent re-render). When it exists with different content, the existing collision logic (`--force` gate) applies. (e) When the derived name collides with a different existing file (not produced by this run), re-derive with `collision_suffix=cache._hash[:config.notes.filename_collision_suffix_chars]` and use that. Depends on T006, T008, T010.

- [X] T015 [P] [US1] Edit `tests/integration/test_notes_command.py` to update the existing assertions that hardcode `notes.md`. Lines 111–112, 131, 174, 204, 233, 253, 314 currently assert `(cache_dir / "notes" / "notes.md")`; replace each with a derivation of the expected filename via `notes.naming.derive_notes_filename(meta)` from the test's prepared `meta.json` content. Add two new test cases: (a) `test_notes_writes_human_readable_filename` — given a populated meta.json with `meeting_title="Test Meeting"` and a mocked summary call returning `"summary text"`, the produced file is named `2026-05-10--Test Meeting--summary text.md`; (b) `test_legacy_notes_md_is_renamed_in_place` — pre-create `<cache>/notes/notes.md` with stale content, run notes with `--re-render --force`, assert the legacy file is gone, the human-readable file exists with the new content, and `notes.legacy_renamed` was logged. Mock `notes.summary.generate_summary` exactly the way `notes.render.render_notes` is currently mocked. Depends on T014.

- [X] T016 [P] [US1] Edit `tests/integration/test_full_pipeline.py` (the Article VII.2 golden fixture). At line 151 (`assert result.notes_path is not None and result.notes_path.exists()`), append assertions that the resolved `result.notes_path.name` matches the human-readable convention (regex `r"^\d{4}-\d{2}-\d{2}--.+--.+\.md$"`) and that `meta.json` on disk after the run is `schema_version="2"` with `summary` non-null. Mock both `notes.render.render_notes` and `notes.summary.generate_summary`. Depends on T014.

- [X] T017 [P] [US1] Update `HOWTO.md → "Where output lives"` (around line 196) so the cache-tree diagram shows a `<YYYY-MM-DD>--<meeting>--<summary>.md` example instead of `notes.md`, and add a one-paragraph note above it explaining that the filename is derived deterministically from `meta.json`. Update the example output line near `notes:` (around line 134) to show a representative human-readable path. No content changes outside this section.

- [X] T018 [P] [US1] Run `pytest -q tests/unit/test_notes_naming.py tests/unit/test_notes_summary.py tests/unit/test_zoom_title_scrape.py tests/unit/test_recording_meta.py tests/integration/test_notes_command.py tests/integration/test_full_pipeline.py`. Confirm all green. Then run the full `pytest -q` and confirm only the changes you intended (the notes-command and full-pipeline assertions are now stricter; nothing else regresses).

**Checkpoint**: User Story 1 is fully functional. The notes file produced by `notetaker notes <url>` lives at the human-readable path; legacy caches are migrated lazily; meta.json is v2.

---

## Phase 4: User Story 2 — Export all cached notes into a user-specified directory (Priority: P2)

**Goal**: Running `notetaker export <directory>` copies every rendered notes file from the cache into `<directory>` under its human-readable name, preserving the cache originals. Collisions skip-and-report by default; `--overwrite` replaces. Legacy `notes.md` files in the cache are exported under a computed human-readable name without mutating the cache.

**Independent Test**: From `quickstart.md → Step 4`: populate the cache with three captures, run `notetaker export ~/notetaker-archive`. Confirm three files in the target directory with human-readable names; cache copies still present; second invocation reports `copied=0 skipped_collision=3`. From a fixture-only path: `pytest -q tests/integration/test_export_command.py tests/unit/test_cache_ops.py` is green.

### Implementation for User Story 2

- [X] T019 [US2] Create `src/notetaker/cache_ops.py` with the `ExportSummary` dataclass (fields per `data-model.md → ExportSummary`) and the public function `export_notes(cache_root: Path, target_dir: Path, *, overwrite: bool = False) -> ExportSummary`. Behaviour: `mkdir(target_dir, parents=True, exist_ok=True)`; iterate `Cache.iter_entries(cache_root)`; for each entry, locate the notes file (prefer the human-readable file, fall back to legacy `notes.md` and re-derive the destination name via `notes.naming.derive_notes_filename`); skip with `export.entry_skipped_no_notes` if no notes file present; compute destination path; if exists and not `overwrite`, skip with `export.entry_skipped_collision`; else `shutil.copy2` and log `export.entry_copied`. Track `legacy_resolved` count for entries whose source was `notes.md`. Emit `export.summary` at end with the full counter set. Depends on T006, T008.

- [X] T020 [P] [US2] Write unit tests at `tests/unit/test_cache_ops.py` (new file) for `export_notes`. Use a `tmp_path` fixture to synthesise a cache root with three entries: (a) one fully-modern entry (v2 meta.json, human-readable notes file present); (b) one legacy entry (v1-shaped meta.json, only `notes.md` present); (c) one partial entry (v2 meta.json, no notes file). Assert: a successful run copies (a) and (b) under their derived names, skips (c) with `skipped_no_notes`, and the cache copies are intact. Add a collision case: pre-create one of the destination files with different content; run without `--overwrite` → `skipped_collision==1`; run with `overwrite=True` → file is replaced. Add an idempotency case: two runs in a row → second run reports `copied=0`. Depends on T019.

- [X] T021 [US2] Register the `notetaker export` Typer subcommand in `src/notetaker/cli.py` between the existing `notes` and `run` subcommands. Signature: `export(directory: str = typer.Argument(...), overwrite: bool = typer.Option(False, "--overwrite"), debug: bool = typer.Option(False, "--debug"))`. Body: call `_setup(debug, force=False, config_path=None)` for logging parity, resolve `Path(directory).expanduser().resolve()` (NOT yet creating the dir — `cache_ops.export_notes` does that), call `cache_ops.export_notes(cfg.cache_dir_path, target, overwrite=overwrite)`, and `typer.echo` the user-facing summary per `contracts/cli-surface.md → notetaker export <directory>` stdout shape. Map hard errors to exit code 1; the skipped-counters case stays at exit code 0. Depends on T019.

- [X] T022 [P] [US2] Write the integration test at `tests/integration/test_export_command.py`. Use the typer `CliRunner` (or `subprocess` via the existing test conventions in `test_notes_command.py`). Cases: (a) export against a populated synthetic cache root (use the same test fixture style as `test_full_pipeline.py`) — assert exit code 0 and the expected stdout summary line; (b) export against an empty cache root — exit 0, `copied=0`, no error; (c) export with a pre-existing target file at a colliding destination — without `--overwrite` exit 0 with `skipped_collision=1`, with `--overwrite` the file is replaced; (d) export with a target directory that does not exist — directory is created and the export succeeds. Depends on T021.

- [X] T023 [P] [US2] Update `HOWTO.md` to document `notetaker export <directory>`: add a new section "Exporting your notes" between "When things go wrong" and "Reference" with a worked example, the collision-skip behaviour, the `--overwrite` flag, and a one-line pointer to the spec. Also extend the "CLI subcommands" list (around line 215) to include `export` in the `notetaker export <dir>` form.

**Checkpoint**: User Story 2 is fully functional. The user can pull every rendered notes file out of the cache into a directory of their choosing, with safe collision behaviour and a clear summary report.

---

## Phase 5: User Story 3 — Delete the cache (Priority: P3)

**Goal**: Running `notetaker purge` removes every per-recording entry under the cache root after explicit confirmation (or `--yes` for non-interactive use), reports the count and bytes reclaimed, and leaves siblings (logs/, exported notes elsewhere) untouched.

**Independent Test**: From `quickstart.md → Step 6`: populate the cache, run `notetaker purge`, confirm the prompt, observe the cache root is emptied and `~/.local/share/notetaker/logs/` is preserved. Cancellation path: run `notetaker purge` and decline the prompt → cache untouched. Non-interactive path: `notetaker purge --yes` skips the prompt. From a fixture-only path: `pytest -q tests/integration/test_purge_command.py tests/unit/test_cache_ops.py` is green.

### Implementation for User Story 3

- [X] T024 [US3] Extend `src/notetaker/cache_ops.py` (the file created in T019) with the `PurgeSummary` dataclass (fields per `data-model.md → PurgeSummary`) and the public function `purge_cache(cache_root: Path, *, confirmed: bool) -> PurgeSummary`. Behaviour: if `cache_root` does not exist, return `PurgeSummary(cache_root=cache_root, entries_removed=0, bytes_reclaimed=0, cancelled=False)`; if `not confirmed`, return `PurgeSummary(..., cancelled=True)`; otherwise iterate `Cache.iter_entries(cache_root)`, sum each entry's recursive size before `shutil.rmtree(entry_dir, ignore_errors=False)`, accumulate counters, and emit `purge.entry_removed` (with `cache_id`, `bytes`) per entry plus `purge.summary` at the end. Per FR-022, the function MUST NOT touch sibling directories (`logs/` etc.) — it scopes `shutil.rmtree` to entries yielded by `Cache.iter_entries`. The cache_root directory itself is preserved. Stray non-entry files at the cache root (no `meta.json`) are removed at debug level only. Depends on T008, T019 (file co-location).

- [X] T025 [P] [US3] Extend `tests/unit/test_cache_ops.py` (file created in T020) with `purge_cache` cases: (a) confirmed purge against a populated synthetic cache → all entries removed, `entries_removed` and `bytes_reclaimed` correct, the `logs/` sibling directory created in the test fixture is untouched; (b) `confirmed=False` → no files removed, `cancelled=True`; (c) missing cache root → no-op, returns zero counters, no error; (d) the cache root directory itself survives the purge (only its children are removed). Depends on T024.

- [X] T026 [US3] Register the `notetaker purge` Typer subcommand in `src/notetaker/cli.py` (the file edited in T021) immediately after `export`. Signature: `purge(yes: bool = typer.Option(False, "--yes"), debug: bool = typer.Option(False, "--debug"))`. Body: call `_setup(debug, force=False, config_path=None)`; pre-flight by walking `Cache.iter_entries(cfg.cache_dir_path)` to compute the entry count and total bytes; print a one-line preview (`Cache: <abs path> ; entries=<N> ; total_size=<bytes>`); resolve `confirmed` per `contracts/cli-surface.md → notetaker purge → Behaviour` (TTY check via `sys.stdin.isatty()`, prompt with `typer.confirm`); call `cache_ops.purge_cache(cfg.cache_dir_path, confirmed=confirmed)`; print the final summary per the cli-surface contract. Map non-TTY-without-yes to exit 1 with the documented error message. Depends on T008, T024.

- [X] T027 [P] [US3] Write the integration test at `tests/integration/test_purge_command.py`. Cases: (a) confirmed purge via simulated `y` input → cache emptied, exit 0; (b) cancelled purge via simulated `n` input → cache intact, exit 0, output contains `purge cancelled`; (c) `--yes` flag against populated cache → exit 0, no prompt, cache emptied; (d) non-TTY without `--yes` → exit 1 with the documented error message; (e) missing cache root → exit 0, summary reports zero; (f) sibling-directory safety: pre-create a `logs/` sibling under the test's notetaker-data root and assert it is intact after the purge. Depends on T026.

- [X] T028 [P] [US3] Update `HOWTO.md` to document `notetaker purge`: extend the "Exporting your notes" section (added in T023) into a "Exporting and purging" section, add a worked example of the end-to-end workflow (capture → notes → export → purge), and warn that purge is destructive and should follow an export. Extend the "CLI subcommands" list (around line 215) to include `purge`.

**Checkpoint**: User Story 3 is fully functional. All three user stories deliver independently; the cache lifecycle (capture → notes → export → purge) is now a complete user-facing flow.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Cross-cutting documentation and the final regression sweep that ties the three user stories together.

- [X] T029 [P] Update `CLAUDE.md` (project file at repo root). Bump the CLI subcommand count from "five" to "seven" in the "## CLI subcommands" section; add bullet points for `export` and `purge` describing their purpose in one line each. The `<!-- SPECKIT START -->` block was already updated to point at this plan during the planning phase.

- [ ] T030 [P] Run the full `quickstart.md` walkthrough manually against a real (or synthetic-fixture) recording. Confirm steps 1–7 produce the documented outputs. Note: Step 5 (legacy `notes.md` rename) requires a cache entry from before this feature shipped; if no such entry exists locally, manually create one (`mkdir -p ~/.local/share/notetaker/cache/legacycafebabe1234/notes && touch ~/.local/share/notetaker/cache/legacycafebabe1234/notes/notes.md && cp <a-meta.json> ~/.local/share/notetaker/cache/legacycafebabe1234/meta.json`) before testing. **DEFERRED — requires real Zoom recording; out of scope for autonomous execution. Run before merge.** against a real (or synthetic-fixture) recording. Confirm steps 1–7 produce the documented outputs. Note: Step 5 (legacy `notes.md` rename) requires a cache entry from before this feature shipped; if no such entry exists locally, manually create one (`mkdir -p ~/.local/share/notetaker/cache/legacycafebabe1234/notes && touch ~/.local/share/notetaker/cache/legacycafebabe1234/notes/notes.md && cp <a-meta.json> ~/.local/share/notetaker/cache/legacycafebabe1234/meta.json`) before testing.

- [X] T031 Run the final regression check. **Result: 212 passing (baseline 128 → +84 tests). Seven CLI subcommands listed by `notetaker --help`. Zero regressions.** Execute `pytest -q` from repo root; compare collected and passing test counts to the baseline captured in T001. Expected delta: `+ N collected, + N passing` where `N` equals the count of new test functions added across `test_recording_meta.py`, `test_notes_naming.py`, `test_notes_summary.py`, `test_zoom_title_scrape.py`, `test_cache_ops.py` (new files), `test_recording_meta_contract.py` (new file), `test_export_command.py` (new file), `test_purge_command.py` (new file), `test_notes_command.py` (added cases), `test_full_pipeline.py` (added assertions only, not new test functions), `test_cache.py` (added cases). No existing tests should be removed. Confirm zero failures, zero errors. Run `notetaker --help` and confirm the listed subcommands are exactly seven: `capture, extract, understand, notes, run, export, purge`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup (T001 baseline). BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational completion.
- **User Story 2 (Phase 4)**: Depends on Foundational completion. Independent of US1.
- **User Story 3 (Phase 5)**: Depends on Foundational completion. Shares `src/notetaker/cache_ops.py` and `src/notetaker/cli.py` with US2 → sequential edits within those files when both stories run in the same change set.
- **Polish (Phase 6)**: Depends on whichever user stories are being shipped.

### User Story Dependencies

- **US1 (P1)**: Standalone after Foundational. Provides the human-readable filename infrastructure that US2 also reads from disk, but US2 does not import US1's orchestrator code; the contract is the on-disk filename, not Python symbols.
- **US2 (P2)**: Standalone after Foundational. Reads the human-readable filename if present, computes it from `meta.json` if not (legacy resolution). Therefore US2 can ship before US1 for the legacy-resolution path; in practice both ship together because US1 is the higher-priority story.
- **US3 (P3)**: Standalone after Foundational. Does not read notes filenames at all (purge only counts entries and rmtree's them).

### Within Each User Story

- Tests adjacent to their target module (per `[P]` markers) can run in parallel after the implementation task completes.
- Within a single file (e.g., `notes/__init__.py` orchestrator, `cache_ops.py`, `cli.py`), edits are sequential within and across stories.

### Parallel Opportunities

- **Phase 2 Foundational**: T002, T003 in parallel; then T004, T005, T006, T008 in parallel after T003; then T007, T009 in parallel after T006/T008.
- **Phase 3 US1**: T010, T012 in parallel after foundational; T011 depends on T010; T013 depends on T012; T014 depends on T010 + T008 + T006; T015, T016 in parallel after T014; T017, T018 in parallel after T016.
- **Phase 4 US2**: T019 first; T020 in parallel with T021 after T019; T022 depends on T021; T023 in parallel with T022.
- **Phase 5 US3**: T024 first (extends T019's file); T025 in parallel with T026 after T024; T027 depends on T026; T028 in parallel with T027.
- **Different team members**: After Phase 2, one developer can take US1 (T010–T018) while another takes US2 (T019–T023) and a third takes US3 (T024–T028). The shared-file edits in `cache_ops.py` (T019/T024) and `cli.py` (T021/T026) need a brief merge coordination but each edit is small.

---

## Parallel Example: Phase 2 Foundational

```bash
# After T001 lands, run T002 and T003 in parallel (different files):
Task: "Add new NotesConfig + CaptureConfig fields in src/notetaker/config.py"
Task: "Create RecordingMetaSchema at src/notetaker/contracts/recording_meta.py"

# After T003 lands, run T004, T005, T006, T008 in parallel:
Task: "Write tests/unit/test_recording_meta.py — lenient v1 read, v2 round-trip"
Task: "Write tests/contract/test_recording_meta_contract.py"
Task: "Create src/notetaker/notes/naming.py — derive_notes_filename + sanitize_component"
Task: "Edit src/notetaker/cache.py — Cache.initialise v2, notes_file_path, iter_entries"

# After T006 and T008 land, run T007 and T009 in parallel:
Task: "Write tests/unit/test_notes_naming.py — sanitization edge cases + truncation"
Task: "Extend tests/unit/test_cache.py with iter_entries + notes_file_path cases"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1: Setup (T001).
2. Complete Phase 2: Foundational (T002–T009). CRITICAL — blocks all stories.
3. Complete Phase 3: User Story 1 (T010–T018).
4. **STOP and VALIDATE**: Run quickstart Steps 1–3 against a real recording. Confirm the human-readable filename is produced and `meta.json` is v2.
5. Ship US1 alone if needed — the user can already browse the cache by name. Export and purge ship in a follow-up if scope is tight.

### Incremental Delivery

1. Setup + Foundational → green test suite, no user-visible change.
2. Add US1 → user sees human-readable filenames in the cache (MVP). Ship.
3. Add US2 → user can copy the cache out into an archive. Ship.
4. Add US3 → user can reclaim cache disk space safely. Ship.

Each story is independently demoable.

### Parallel Team Strategy

After Phase 2 lands, three developers can split the user-story phases:
- Dev A: US1 (T010–T018) — most complex; touches capture, notes orchestrator, and config.
- Dev B: US2 (T019–T023) — pure cache walking + new CLI subcommand.
- Dev C: US3 (T024–T028) — pure cache walking + new CLI subcommand.

Devs B and C coordinate on the shared `cache_ops.py` and `cli.py` edits (small surface).

---

## Notes

- `[P]` tasks = different files, no dependency on incomplete tasks in the same phase.
- `[Story]` label maps task to specific user story for traceability and PR scoping.
- Each user story should be independently completable, testable, and shippable.
- Constitution gates were checked in `plan.md → Constitution Check` and re-verified post-design; no amendment is required by this feature.
- Commit after each task or logical group per Article VIII.2.
- Stop at any checkpoint to validate story independently.
- Avoid: vague tasks, parallel edits to the same file, cross-story dependencies that compromise independence.
