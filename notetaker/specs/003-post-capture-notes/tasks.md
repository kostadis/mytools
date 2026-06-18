---

description: "Task list for feature 003: post-capture notes (slides + transcript → notes.md)"
---

# Tasks: Post-Capture Notes (Slides + Transcript → Notes)

**Input**: Design documents from `/specs/003-post-capture-notes/`
**Prerequisites**: plan.md (✓), spec.md (✓), research.md (✓), data-model.md (✓), contracts/ (✓), quickstart.md (✓)

**Tests**: Required by Constitution Articles VII.1 (stage-level tests), VII.2 (golden fixtures), and VII.3 (mocked LLM calls). Tests are first-class tasks here, not optional.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

Single project layout (per plan.md "Structure Decision"):

- Source: `src/notetaker/` at repository root
- Tests: `tests/` at repository root
- Config: `config.toml` at repository root
- Docs: `HOWTO.md` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project skeleton for the new module and fixture directory; baseline config keys.

- [X] T001 [P] Create new module directory `src/notetaker/notes/` with an empty `src/notetaker/notes/__init__.py` placeholder (will be populated in T014)
- [X] T002 [P] Create new fixture directory `tests/fixtures/notes/` (empty; populated in T006)
- [X] T003 [P] Add a documented `[notes]` section to `config.toml` with the six keys defined in `data-model.md` (`model`, `max_output_tokens`, `retention_days`, `working_doc_filename`, `notes_filename`, `cost_warn_threshold_usd`); follow the inline-comment convention used elsewhere in the file (Article IV.3)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared code that every user story depends on — config loading, transcript parsing, golden fixture, and the retention-purge plumbing FR-018 needs.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 [P] Add `NotesConfig` dataclass in `src/notetaker/config.py` with the six fields from `data-model.md`, wire it into the existing `Config` dataclass, and extend `load_config()` to populate it from a `[notes]` table (mirror the `LoggingConfig` wiring at `src/notetaker/config.py:120-123`). Resolve `model = None` to `synthesis.summary_model` at read time (research.md D5).
- [X] T005 [P] Implement the transcript parser dispatcher and three format parsers in `src/notetaker/stages/capture/adapters/zoom_transcript_parsers.py` per `contracts/transcript_input.md`. Public surface: `parse_transcript_file(path: Path) -> TranscriptSchema` plus three private parsers (`_parse_block`, `_parse_vtt`, `_parse_transcript_json`). Detection rules from research.md D3. Refusal message verbatim per the contract.
- [X] T006 [P] Hand-author the synthetic golden fixture in `tests/fixtures/notes/`: `slide_content.json` (5 slides covering normal / empty-title-only-raw-OCR / bullets-only / visual-only / all-fields), three transcript files encoding the SAME 12-utterance conversation (`transcript_block.txt`, `transcript.vtt`, `transcript.json`), and the byte-stable `working_doc.expected.md` that the assembly test will compare against (Article VII.2)
- [X] T007 Add unit tests at `tests/unit/test_zoom_transcript_parsers.py` covering the six cases enumerated in `contracts/transcript_input.md` (3 shapes → identical TranscriptSchema; block continuation inheritance; VTT no-speaker fallback; detection precedence under misnamed extension; refusal message; trailing whitespace tolerance). Depends on T005 and T006.
- [X] T008 Implement FR-018 retention behaviour: locate the existing cache retention purge (currently driven by `[cache] retention_days`), modify it to skip any `notes/` subdirectory inside a recording cache root, and add a new purge that respects `[notes] retention_days` (with `0` meaning indefinite, default 365 days per plan.md Constitution Check). Depends on T004.

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 — Recover from missed live transcript (Priority: P1)

**Goal**: When the live transcript scrape returns zero utterances, the run still exits successfully with slide artifacts intact, emits exactly one clearly-flagged warning pointing at the documented recovery procedure, and the user can produce useful notes from the same cache without re-running capture.

**Independent Test**: Take a notetaker cache directory whose `transcript.json` is empty (or simulate it by running the capture stage in an environment where the transcript panel selector cannot match), confirm the run exits 0, confirm the new structured `capture.transcript_unavailable` warning appears in the run log with `selector_used` and `recovery_hint` fields, and confirm `notetaker notes <cache-id> <transcript-file>` then produces a populated `notes.md` (depends on US2 implementation for the second half of the test).

- [X] T009 [US1] Modify `src/notetaker/stages/capture/adapters/zoom.py:259` to emit the renamed `capture.transcript_unavailable` warning record per `contracts/render_log_records.md`: rename event from `capture.transcript_panel_not_found`, add `event_category: "warning"`, add `selector_used` (the timed-out selector) and `recovery_hint` (literal string `"See HOWTO.md 'Obtaining a transcript' to recover via post-capture procedure."`)
- [X] T010 [US1] Add a unit test at `tests/unit/test_zoom_capture_transcript_unavailable.py` that mocks the Playwright page locator to raise a timeout, drives `_scrape_transcript()`, and asserts the new warning record is emitted with the documented fields and that `_transcript_unavailable` is `True`. Use `caplog` or `structlog`'s capture helper consistent with feature 002's existing tests at `tests/unit/test_logging.py`.
- [X] T011 [US1] Add a section "Obtaining a transcript" to `HOWTO.md` documenting the post-capture browser snippet procedure (FR-016): open recording in Chrome → open transcript panel → DevTools Inspect a row → paste `mytools/scrape.js` and `mytools/download.js` → save as `zoom_chat.txt`. Reference the `recovery_hint` text from T009 verbatim so the warning and the doc agree.

**Checkpoint**: A run that misses the live transcript now ends in a recoverable state with clear instructions, *and* the structured warning is asserted by a test.

---

## Phase 4: User Story 2 — One command to combine transcript and slides (Priority: P1) 🎯 MVP

**Goal**: `notetaker notes <recording-url-or-cache-id> <transcript-path>` produces `<cache>/<hash>/notes/notes.md` from the existing `slide_content.json` and the supplied transcript via one LLM render call. Working doc, log records, retry, and cost reporting are all covered.

**Independent Test**: Against the synthetic golden fixture cache, run the CLI with a mocked Anthropic client; confirm `working_doc.md` matches the expected fixture byte-for-byte, confirm the mocked render output is written to `notes.md`, and confirm the four documented log records (`command_start`, `transcript_format_detected`, `working_doc_written`, `render_attempt`, `render_complete`) appear with the documented fields.

- [X] T012 [P] [US2] Implement `build_working_doc(slide_content: SlideContentSchema, transcript: TranscriptSchema, config: NotesConfig) -> str` in `src/notetaker/notes/working_doc.py` per `contracts/working_doc.md`. Honour all 8 invariants — including FR-006 raw-OCR fallback and the speaker-header collapsing rule. Pure function, deterministic.
- [X] T013 [P] [US2] Implement `render_notes(working_doc_text: str, config: NotesConfig, client=None, logger=None) -> RenderResult` in `src/notetaker/notes/render.py`. One LLM call per `contracts/notes_file.md`; retry via the existing `notetaker.utils.retry.retry` decorator using `[api] retry_count` and `[api] retry_delay_seconds`; emit `notes.render_attempt` per attempt and `notes.render_complete` once, with exact field shapes from `contracts/render_log_records.md`. Return a `RenderResult` carrying `text`, `total_attempts`, `total_cost_usd`, `outcome`. The `client=None` default lazy-imports `anthropic.Anthropic()` (mirrors the pattern at `src/notetaker/stages/synthesis/summarizer.py:58-62`).
- [X] T014 [US2] Implement the orchestrator in `src/notetaker/notes/__init__.py` exposing `run_notes(recording_arg: str, transcript_path: Path | None, mode: NotesMode, config: Config) -> NotesRunResult`. Resolves recording URL or cache-id to the cache root via the existing helpers in `src/notetaker/cache.py`; invokes `parse_transcript_file` (T005) → `build_working_doc` (T012) → `render_notes` (T013); writes `working_doc.md` and `notes.md` into `<cache>/<hash>/notes/`; emits `notes.command_start`, `notes.transcript_format_detected`, `notes.working_doc_written` records. Refuses to overwrite an existing notes file unless `force=True` (FR-014); refuses if `slide_content.json` is missing (FR-003). Falls back to a non-empty cached `<cache>/<hash>/capture/transcript.json` when `transcript_path is None` and the file is non-empty (per the updated edge case in spec).
- [X] T015 [US2] Add the `notes` Typer subcommand to `src/notetaker/cli.py`: positional args `recording` and optional `transcript_path`; flags `--force`, `--re-render`, `--dry-run`, `--output`; loads `Config` via `load_config()`; delegates to `run_notes`; prints the absolute notes path on success and the cost summary line per `quickstart.md`. (US3 wires `--re-render` and `--dry-run` behaviour; this task only adds the flag definitions and console plumbing so US3 has hooks to fill in.)
- [X] T016 [P] [US2] Unit tests at `tests/unit/test_notes_working_doc.py` covering the 5 invariants from `contracts/working_doc.md`: byte-for-byte match against `tests/fixtures/notes/working_doc.expected.md`; idempotence (call twice, identical bytes); raw-OCR fallback present when expected; consecutive same-speaker utterances share one header; final newline. Depends on T012 and T006.
- [X] T017 [P] [US2] Unit tests at `tests/unit/test_notes_render.py` (mocked Anthropic client per Article VII.3): verbatim write of mocked text; `assert_notes_file_valid` helper enforces the 5 properties from `contracts/notes_file.md`; refusal-on-existing without `--force`; overwrite with `--force`; transient failure → 2 attempts → success path emits exactly two `notes.render_attempt` records with outcomes `retryable` then `success`; persistent failure → no notes file written, working doc preserved, three `notes.render_attempt` records with the third outcome `persistent_failure`. Depends on T013.
- [X] T018 [US2] Integration test at `tests/integration/test_notes_command.py` exercising the full `notetaker notes` CLI against the fixture cache with a mocked render. Asserts: notes file at the documented path; cost-summary line printed to stdout matching the format in quickstart.md; the four `notes.*` log records emitted in order; FR-003 refusal when `slide_content.json` is absent. Depends on T014, T015, T016, T017.
- [X] T019 [US2] Verify cost-reporting console output (FR-011) matches the format documented in `quickstart.md` step 2 (`input_tokens=…  output_tokens=…  cost=$…`). Adjust either the code (T015) or the doc until they agree byte-for-byte; lock the format in a small unit test inside `tests/unit/test_notes_render.py`.

**Checkpoint**: The MVP works end-to-end against the fixture. Combined with US1's HOWTO update, this is the documented happy path.

---

## Phase 5: User Story 3 — Cheap re-render (Priority: P2)

**Goal**: `notetaker notes <recording-url-or-cache-id> --re-render --force` reads the existing `working_doc.md` and re-runs only the LLM render call. `--dry-run` reports projected cost without making the API call. Both flags exist in T015 but have no logic yet.

**Independent Test**: Produce a notes file via US2; tweak `[notes] model` in the user's config; re-invoke with `--re-render --force`; confirm no `notes.transcript_format_detected` or `notes.working_doc_written` records are emitted, confirm the working doc is read from disk verbatim, and confirm the new notes file is written. Separately, invoke with `--dry-run` and confirm the `notes.dry_run_estimate` record is emitted and no LLM call is made.

- [X] T020 [US3] Wire the `--re-render` mode in `src/notetaker/notes/__init__.py`: skip parsing and assembly; read `<cache>/<hash>/notes/working_doc.md` from disk; refuse with the documented message if the file is absent (FR-013). The transcript argument is ignored in this mode. Suppress the `notes.transcript_format_detected` and `notes.working_doc_written` records (per `contracts/render_log_records.md`).
- [X] T021 [US3] Wire the `--dry-run` mode in `src/notetaker/notes/__init__.py`: assemble the working doc as normal but skip the render call; emit a single `notes.dry_run_estimate` record with `working_doc_bytes`, `estimated_input_tokens` (= `len(working_doc) // 4`, the documented heuristic), `model`, and `projected_cost_usd_floor` (input-only projection at the resolved model's input price). Print a one-line console summary.
- [X] T022 [P] [US3] Unit/integration tests covering both modes in `tests/integration/test_notes_command.py` (extending the file from T018): `--re-render` against an existing fixture working doc with a mocked render; `--re-render` against a missing working doc raises with the documented message; `--dry-run` emits exactly one `notes.dry_run_estimate` record and zero render attempts. Depends on T020 and T021.

**Checkpoint**: Iterating on prompt or model is now cheap and quiet.

---

## Phase 6: User Story 4 — Inspect the working doc (Priority: P2)

**Goal**: The deterministic input to the LLM render call is a first-class artifact at a documented, predictable path inside the cache, the user can open it in any editor, and editing it manually + running `--re-render` produces notes from the edited content. This is mostly verification + docs; T012/T014 already place the file correctly.

**Independent Test**: After running `notetaker notes` on the fixture, list `<cache>/<hash>/notes/`, confirm `working_doc.md` is present alongside `notes.md`, open it, edit one slide title, run `--re-render --force`, and confirm the new `notes.md` reflects the edit (mocked render is fine here — assert that the input passed to the mocked client contains the edited title).

- [X] T023 [US4] Add a test in `tests/integration/test_notes_command.py` (extending T018) that asserts after a successful `notes` invocation the cache directory contains both `<cache>/<hash>/notes/working_doc.md` and `<cache>/<hash>/notes/notes.md` at the documented paths, and that the working doc contains every slide title from the fixture.
- [X] T024 [US4] Add a section "Inspect what the LLM saw" to `HOWTO.md` (alongside the section added in T011) documenting the working-doc location, what to look for when notes go wrong (slide missing → parsing/assembly bug; notes wrong but working doc right → prompt/model issue → use `--re-render`).
- [X] T025 [P] [US4] Add an integration test at `tests/integration/test_notes_command.py` that simulates the inspect-edit-rerender flow: copy the fixture working doc into a temp cache, modify one heading line in-place, run with `--re-render --force` against a mocked client, and assert the prompt sent to the mocked client contains the modified heading.

**Checkpoint**: All four user stories work and have independent tests.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Remove the prototype scripts now that the real modules exist; add the live-API smoke test; ensure quickstart actually walks through cleanly.

- [X] T026 [P] Remove `scripts/build_working_doc.py` and `scripts/render_notes.py`. Their logic now lives in `src/notetaker/notes/working_doc.py` and `src/notetaker/notes/render.py`. Per plan.md project structure, keeping two parallel implementations is forbidden (Article VIII.2). `scripts/recover_slide_content.py` is *kept* — it serves a different one-off purpose (recovering caches written before the fenced-JSON parser fix).
- [X] T027 [P] Add `tests/integration/test_notes_command_live.py` with a single test marked `@pytest.mark.live_api` that runs the full `notes` command against the fixture cache and a real Anthropic client (one real API call, ~$0.05). The test asserts only the structural invariants from `contracts/notes_file.md` (≥200 bytes, starts with `#`, valid UTF-8, no prompt-echo strings). Excluded from the default `pytest` run by the existing `addopts = "-m 'not live_api'"` setting (Article VII.3).
- [X] T028 Update `CLAUDE.md` (or whichever agent context file applies) to reference the new `notetaker notes` subcommand alongside the existing `run`, `capture`, `extract`, `understand`, `synthesise` subcommands. The plan-pointer between the SPECKIT markers was already updated in `/speckit-plan`; this task adds a one-paragraph note about the post-capture flow as the supported path.
- [X] T029 Run the procedure in `quickstart.md` end-to-end against a real recovered cache (the `1aafdeee55635a82` cache from this session, or a fresh capture). Verify the documentation matches reality byte-for-byte; fix any drift in `quickstart.md`. This is the final acceptance gate before declaring the feature complete.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — can start immediately.
- **Phase 2 (Foundational)**: Requires Phase 1. **Blocks** every user story phase.
- **Phase 3 (US1)**: Requires Phase 2 (specifically T005's parser dispatcher exists, but US1 only touches capture-side and HOWTO; the actual hard dependency is on T008's retention plumbing for completeness).
- **Phase 4 (US2)**: Requires Phase 2. The MVP. Independent of US1's capture-side change.
- **Phase 5 (US3)**: Requires Phase 4 (re-render reads a working_doc that US2's orchestrator writes; dry-run reuses the assembly path).
- **Phase 6 (US4)**: Requires Phase 4 and Phase 5 (US4's inspect-edit-rerender test exercises Phase 5's `--re-render` path).
- **Phase 7 (Polish)**: Requires all prior phases.

### User Story Independence

- **US1 ↔ US2**: Independently testable. US1 is verified via the structured warning record (T010); US2 is verified end-to-end with a mocked render (T018). The user-visible promise that US1 makes ("recoverable cache") is *demonstrated* end-to-end only when US2's code also exists, but the implementation work is independent.
- **US3 builds on US2**: `--re-render` requires a working doc that US2 produces. This is intrinsic to the feature shape, not a deficiency in story decomposition.
- **US4 builds on US2 + US3**: similarly intrinsic — the inspect-edit-rerender promise needs both the artifact and the re-render path.

### Within Each User Story

- Tests for a story may be authored in parallel with its implementation (Article VII.1 — tests *exist*, ordering test-vs-impl is not constitutionally fixed). The constitution's only ordering rule is no-merge without tests, not test-first.
- Models / data shapes (here: `NotesConfig`) precede services (here: `working_doc.py`, `render.py`).
- Services precede orchestration (`__init__.py`).
- Orchestration precedes CLI surface.

### Parallel Opportunities

- Setup tasks T001/T002/T003 are all `[P]`.
- Foundational `[P]` tasks T004/T005/T006 can run in parallel; T007 and T008 sequence after their respective dependencies.
- Within US2, the two modules `working_doc.py` (T012) and `render.py` (T013) are `[P]` — different files, no shared state.
- Tests for US2 (T016, T017) are `[P]` once their implementation tasks land.

---

## Parallel Example: Phase 2 Foundational

```bash
# Three independent foundational starts:
Task: "T004 NotesConfig in src/notetaker/config.py"
Task: "T005 Transcript parsers in src/notetaker/stages/capture/adapters/zoom_transcript_parsers.py"
Task: "T006 Golden fixture under tests/fixtures/notes/"

# Then sequence the dependents:
Task: "T007 Parser tests (depends on T005, T006)"
Task: "T008 Retention purge change (depends on T004)"
```

## Parallel Example: User Story 2 (MVP)

```bash
# Two independent module starts:
Task: "T012 build_working_doc in src/notetaker/notes/working_doc.py"
Task: "T013 render_notes in src/notetaker/notes/render.py"

# Tests follow each in parallel:
Task: "T016 Working-doc unit tests"
Task: "T017 Render unit tests (mocked)"

# Then orchestration + CLI sequentially:
Task: "T014 Orchestrator __init__.py"
Task: "T015 CLI subcommand"
Task: "T018 Integration test"
Task: "T019 Cost-reporting format lock"
```

---

## Implementation Strategy

### MVP First — Ship US2 (with US1 prerequisites)

1. Phase 1 (Setup) — directory + config skeleton.
2. Phase 2 (Foundational) — config, parsers, fixture, retention plumbing.
3. Phase 3 (US1) — fix the warning + write the recovery doc.
4. Phase 4 (US2) — the actual command.
5. **STOP and VALIDATE**: run the command against the recovered cache from this session. This is the MVP.

### Incremental Delivery After MVP

1. Add Phase 5 (US3) — cheap iteration via `--re-render` and `--dry-run`.
2. Add Phase 6 (US4) — inspect-edit-rerender verification + docs.
3. Phase 7 (Polish) — remove prototype scripts, add live-API smoke test, walk quickstart.

### Parallel Team Strategy

Single-developer execution is the realistic case here. If two developers were available:

- Dev A: Phase 2 T005 + T006 + T007 (transcript parsers + fixture + tests).
- Dev B: Phase 2 T004 + T008 (config + retention purge).
- Both converge on Phase 4 with Dev A taking T012/T016 and Dev B taking T013/T017, then either picks up T014/T015/T018/T019.

---

## Notes

- `[P]` tasks = different files, no dependencies on incomplete work.
- `[Story]` label maps task to a specific user story for traceability.
- Each user story should be independently completable and testable. US3/US4 explicitly build on US2 by design (re-render and inspect both need a working_doc to operate on).
- Tests must pass before merge per Constitution Article VII.1.
- Commit after each task or logical group (Article VIII.2).
- Stop at any checkpoint to validate story independently.
- Avoid: vague tasks, same-file conflicts in parallel-marked tasks, cross-story dependencies that break independence.
