---

description: "Task list for spec 004 — remove the legacy synthesise stage"
---

# Tasks: Remove the Legacy Synthesise Stage

**Input**: Design documents from `specs/004-remove-synthesise-stage/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md` (all present)

**Tests**: This is a deletion feature, not new development. No new test code is generated; existing tests are preserved, edited, or deleted as required by FR-009 and FR-013. The polish phase contains a regression-test task that asserts the test-count delta exactly matches the deleted test files (SC-005).

**Organization**: Tasks are grouped by user story (US1–US4 from `spec.md`) so each story is independently completable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks in the same phase)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- All file paths are repository-relative

## Path Conventions

Single-project Python layout: `src/notetaker/...`, `tests/...` at repo root. Confirmed in `plan.md → Project Structure`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Capture the pre-feature pytest baseline so SC-005 ("test count drop equals exactly the count of removed-by-FR-009 tests") is mechanically verifiable in the polish phase.

- [ ] T001 Capture pytest baseline by running `pytest --collect-only -q 2>&1 | tail -5` from the repo root; record the collected test count in a temporary note (it will be cross-checked in T022). Do not modify any files.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Land the constitution amendment that authorises the rest of this feature. Per Article IX.1 the constitution wins over implementation; the amendment must precede or accompany the code deletion so no commit lands the codebase in a known-violating state.

**⚠️ CRITICAL**: No user story work can begin until T002 is complete.

- [ ] T002 Amend `.specify/memory/constitution.md` per `specs/004-remove-synthesise-stage/contracts/constitution-amendment.md`: rewrite Article I.1 (rename "Synthesis" → "Notes" in the four-stage list), rewrite Article I.3 (drop "Aligned Segment, Final Summary" from the named contract examples), rewrite Article VIII.1 (rename fourth phase "Synthesis" → "Notes"), append the new SYNC IMPACT REPORT entry above the existing one, and bump the footer line to `**Version**: 1.1.0 | **Ratified**: 2026-05-08 | **Last Amended**: 2026-05-09`.

**Checkpoint**: Constitution and code now disagree; the rest of this feature reconciles them.

---

## Phase 3: User Story 1 — The deprecated subcommand is gone (Priority: P1) 🎯 MVP

**Goal**: After this phase, `notetaker --help` lists five subcommands (not six), and invoking `notetaker synthesise <url>` produces a CLI-parser "no such command" error and a non-zero exit code.

**Independent Test**: From a fresh shell, install the package and run `notetaker --help`; expect five subcommands and no `synthesise` entry. Run `notetaker synthesise "https://example/recording"`; expect non-zero exit and a "no such command" message.

### Implementation for User Story 1

- [ ] T003 [US1] Delete the `synthesise()` Typer subcommand from `src/notetaker/cli.py` (currently lines 117–134, including its `@app.command()` decorator, the `from notetaker.stages.synthesis import run as run_synthesis` lazy import inside its body, and its `typer.echo(...)` summary block). Do NOT yet edit the `run()` command — that is US2.

- [ ] T004 [US1] Verify the help surface: run `notetaker --help` and confirm the listed subcommands are exactly `capture, extract, understand, notes, run` (count: 5). Run `notetaker synthesise "https://example/recording"` and confirm a non-zero exit code with a Typer/Click "no such command" message. Run `pytest -q` and confirm all collected tests still pass (no test currently asserts the presence of the `synthesise` subcommand, so the existing suite must stay green).

**Checkpoint**: User Story 1 is fully functional. The `synthesise` CLI surface is gone; the legacy module remains on disk and is still reached via `notetaker run` (US2 territory).

---

## Phase 4: User Story 2 — `notetaker run` stops at understanding and points at notes (Priority: P1)

**Goal**: After this phase, `notetaker run <url>` chains `capture → extract → understand` only, exits zero on success, and prints two final lines: the cache directory path and a copy-pasteable `notetaker notes <url> [transcript-file]` next-step command.

**Independent Test**: Invoke `notetaker run <url>` against a recording for which the three remaining stages can complete (use the synthetic-fixture path from `tests/integration/test_full_pipeline.py` if a real recording is unavailable). Confirm the cache directory contains `capture/`, `extraction/`, and `understanding/` subdirectories but NOT a `synthesis/` subdirectory. Confirm the final two console lines match the spec.

### Implementation for User Story 2

- [ ] T005 [US2] Rewrite the `run()` Typer subcommand in `src/notetaker/cli.py` (currently lines 219–242). Remove the `from notetaker.stages.synthesis import run as run_synthesis` import line and the `result = asyncio.run(run_synthesis(url, cfg, force=force, debug=debug))` call. Update the docstring/`help=` text so it names only `capture → extract → understand`. After the `run_understanding` call, replace the existing final `typer.echo` with two lines: (1) the cache root path (use `Cache(cfg.cache_dir_path, recording_url=url).root` to compute it) and (2) the literal `Next: notetaker notes "{url}" <transcript-file>` line followed by a parenthetical noting that `<transcript-file>` may be omitted when the live transcript scrape succeeded. Reference `contracts/cli-surface.md` for exact wording requirements.

- [ ] T006 [P] [US2] Edit `tests/integration/test_run_log_file.py` lines 164–165: change both expected lists `["extract", "understand", "synthesise"]` to `["extract", "understand"]`. Confirm by reading the file that no other assertion in it references `synthesise`.

- [ ] T007 [US2] Run `pytest tests/integration/test_run_log_file.py -q` and confirm green. If `tests/integration/test_full_pipeline.py` runs `notetaker run` (rather than calling the stages directly), it will start failing at this point because it still expects a `synthesise` step — that failure is expected and is fixed by T011 in US4. Document this in the polish-phase regression check (T022) so it is not mistaken for an unrelated regression.

**Checkpoint**: User Story 2 is fully functional. `notetaker run` no longer reaches into `stages/synthesis`. Both Typer subcommands now leave the legacy module unreferenced from the CLI surface.

---

## Phase 5: User Story 3 — Configuration surface no longer offers a knob you can't use (Priority: P2)

**Goal**: After this phase, the shipped `config.toml` contains no `[synthesis]` section, no `summary_model` knob, and no comment in `[notes]` redirecting to a removed sibling. The notes-model default is preserved (still `claude-sonnet-4-6`) by lifting it into `NotesConfig.model` as a literal default. Existing user configs that still contain `[synthesis]` load silently without warning.

**Independent Test**: Run `grep -i 'synthes\|summary_model' config.toml` and confirm empty output. Run `python -c "from notetaker.config import load_config; print(load_config().resolved_notes_model())"` and confirm the output is `claude-sonnet-4-6`. Simulate an old user config (a temp `config.toml` containing only `[synthesis]\nsummary_model = "claude-opus-4-1"`), point `NOTETAKER_CONFIG` at it, run `notetaker --help`, and confirm exit zero with no warning about the unknown section.

### Implementation for User Story 3

- [ ] T008 [US3] Edit `src/notetaker/config.py`: (a) delete the `SynthesisConfig` dataclass at lines 32–34 (the `@dataclass` decorator and the class body); (b) delete the `synthesis: SynthesisConfig = field(default_factory=SynthesisConfig)` field from `Config` at line 76; (c) delete the `synthesis=_section(raw, "synthesis", SynthesisConfig),` argument from the `load_config` return statement at line 176; (d) change the `NotesConfig.model` default at line 62 from `""` to `"claude-sonnet-4-6"` and rewrite the inline comment to read `# Default model for the post-capture notes render call. Override here to swap models.`; (e) simplify `Config.resolved_notes_model()` at lines 82–83 to `return self.notes.model` (single line return). Reference `contracts/config-surface.md` for the contract checklist.

- [ ] T009 [P] [US3] Edit `config.toml`: delete the `[synthesis]` section at lines 51–53 (three lines including the section header, the comment, and the `summary_model` assignment). Rewrite lines 5–7 (the `[notes]` section opening) so the comment names the bundled default and removes the "inherit synthesis.summary_model" mention, and so `model = ""` becomes `model = "claude-sonnet-4-6"`. Reference `contracts/config-surface.md` for exact wording.

- [ ] T010 [US3] Verify the configuration surface: (a) `grep -i 'synthes\|summary_model' config.toml` returns empty; (b) `python -c "from notetaker.config import load_config; print(load_config().resolved_notes_model())"` outputs `claude-sonnet-4-6`; (c) write a temp file `/tmp/old-cfg.toml` containing `[synthesis]\nsummary_model = "claude-opus-4-1"\n` and run `NOTETAKER_CONFIG=/tmp/old-cfg.toml notetaker --help` — confirm exit zero with no per-run warning about the unknown section; (d) run `pytest tests/unit/test_cache.py tests/unit/test_notes_render.py tests/unit/test_notes_working_doc.py -q` and confirm green.

**Checkpoint**: User Story 3 is fully functional. The configuration surface is consolidated; the default model name is preserved; existing user configs still load silently.

---

## Phase 6: User Story 4 — The codebase no longer carries two competing implementations (Priority: P3)

**Goal**: After this phase, `src/notetaker/stages/synthesis/` is gone, the two synthesis-only contracts are gone, the `Stage.SYNTHESISE` log enum value is gone, the cache `STAGE_SUBDIRS` mapping no longer accepts `"synthesis"`, the synthesis-only test files are gone, the integration golden-fixture test chains into notes instead, and all user-facing documentation references are removed (excluding spec history).

**Independent Test**: Run the codebase-cleanliness grep from `quickstart.md` step 5: `grep -ri 'stages\.synthesis\|notetaker synthesise\|synthesis\.summary_model' src/ tests/ HOWTO.md CLAUDE.md config.toml pyproject.toml` — confirm empty output. Run `pytest -q` and confirm green. Confirm `ls src/notetaker/stages/` shows exactly `capture extraction understanding` (no `synthesis`).

### Implementation for User Story 4

**Test rewrite first** (must precede the source deletions to avoid pytest collection errors):

- [ ] T011 [US4] Rewrite `tests/integration/test_full_pipeline.py` to chain `extract → understand → notes` instead of `extract → understand → synthesise`. Specifically: (a) update the module docstring at line 4 to name the new chain; (b) replace the `from notetaker.contracts.summary import SummarySchema` import (line 25) and the `from notetaker.stages.synthesis import run as run_synthesis` / `from notetaker.stages.synthesis.summarizer import Summarizer` imports (lines 146–147) with the corresponding notes-path imports (`from notetaker.notes import run_notes, NotesMode`); (c) replace the `Mock Claude for synthesis` block (lines 127–155) with a notes-path mock — patch the notes LLM call so it returns a fixed Markdown string and assert `result.notes_path` exists and contains the expected fixture text. The test must continue to satisfy Article VII.2 (golden end-to-end fixture). Use `tests/integration/test_notes_command.py` as a reference for how the notes path is exercised in tests.

**Test deletions** (parallel — different files):

- [ ] T012 [P] [US4] Delete `tests/unit/test_aligner.py`.

- [ ] T013 [P] [US4] Delete `tests/contract/test_aligned_segments_contract.py`. If `tests/contract/` has no remaining files after this deletion, also remove the now-empty `tests/contract/` directory.

**Source deletion** (must follow T011/T012/T013 so no test still imports what's being deleted):

- [ ] T014 [US4] Delete the directory `src/notetaker/stages/synthesis/` and its three files (`__init__.py`, `aligner.py`, `summarizer.py`). Use `rm -rf src/notetaker/stages/synthesis/`. After deletion, run `python -c "import notetaker.cli"` and confirm no import error (the CLI no longer references the deleted module after T003 and T005).

**Edits to surviving source files** (parallel — different files, all independent of each other):

- [ ] T015 [P] [US4] Edit `src/notetaker/cache.py`: delete the `"synthesis": "synthesis",` line from the `STAGE_SUBDIRS` dict (currently line 25). Update the docstring at lines 51–61 (the `Layout under cache_root:` block) to drop the `synthesis/ — summary.json, summary.md, aligned_segments.json` line.

- [ ] T016 [P] [US4] Edit `src/notetaker/contracts/log_record.py`: delete the `SYNTHESISE = "synthesise"` line from the `Stage` enum (currently line 46). Bump `SCHEMA_VERSION` at line 23 from `"1.0.0"` to `"1.1.0"`. Add a changelog entry to the module docstring (above line 14): `Schema 1.1.0 — removed Stage.SYNTHESISE (legacy summariser stage deleted by spec 004; no producer emits this value).`

- [ ] T017 [P] [US4] Delete `src/notetaker/contracts/summary.py`.

- [ ] T018 [P] [US4] Delete `src/notetaker/contracts/aligned_segments.py`.

**Documentation edits** (parallel — different files):

- [ ] T019 [P] [US4] Edit `HOWTO.md` per the edit list in `research.md → Decision 8`. Specifically: (a) line 32 — change `should print 6 subcommands (capture/extract/understand/synthesise/run/notes)` to `should print 5 subcommands (capture/extract/understand/run/notes)`; (b) line 207 — drop the `├── synthesis/  # legacy — see "Legacy synthesise stage" below` row from the cache layout diagram; (c) lines 224–225 — drop the `notetaker synthesise` row and the `notetaker run` "legacy — chains capture/extract/understand/synthesise" comment, replacing the `run` row with one that says `chains capture → extract → understand`; (d) line 241 — drop "synthesis output" from the `[cache] retention_days` row in the retention table; (e) line 254 — delete the `synthesis/aligned_segments.csv` debug bullet; (f) lines 318–326 — delete the entire "## Legacy synthesise stage" section; (g) line 331 — update the `~138 tests` count comment to match the post-feature collected count (cross-check with T022's measurement).

- [ ] T020 [P] [US4] Edit `CLAUDE.md` (the project root file, not the user-global one): rewrite the "## CLI subcommands" section (currently lines 7–18). New text: `notetaker exposes five subcommands: capture, extract, understand, run, notes. capture/extract/understand are the chained pipeline stages. run chains capture → extract → understand and prints the next-step notetaker notes command. notes combines the slide content from understand with a transcript file (obtained via the post-capture browser snippet documented in HOWTO.md "Obtaining a transcript") and renders polished Markdown via a single LLM call.` Drop the standalone "older synthesise stage remains in the codebase" sentence.

**Verification**:

- [ ] T021 [US4] Verify codebase cleanliness: (a) `grep -ri 'stages\.synthesis\|notetaker synthesise\|synthesis\.summary_model\|SummarySchema\|AlignedSegment' src/ tests/ HOWTO.md CLAUDE.md config.toml pyproject.toml` returns zero matches (excluding `__pycache__/` directories); (b) `ls src/notetaker/stages/` lists exactly `capture extraction understanding`; (c) `ls src/notetaker/contracts/` does not list `summary.py` or `aligned_segments.py`; (d) `python -c "from notetaker.cli import app"` succeeds (no broken imports).

**Checkpoint**: User Story 4 is fully functional. The legacy stage's source, contracts, tests, and documentation references are gone. Constitution amendment from T002 now matches the codebase reality.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final regression verification, end-to-end walkthrough, and constitutional consistency check. These tasks confirm the feature meets every Success Criterion in `spec.md`.

- [ ] T022 Run the full test regression: `pytest -q`. Confirm: (a) exit code 0; (b) collected test count equals (baseline from T001) minus (the count of tests in `tests/unit/test_aligner.py` plus the count of tests in `tests/contract/test_aligned_segments_contract.py`); (c) no skips were introduced by this feature; (d) no test that was green before this feature is now red. If the count delta is wrong, identify which other tests dropped and either restore them or document why their removal is justified by FR-009. SC-005 fails until this check passes.

- [ ] T023 Run the `quickstart.md` walkthrough end-to-end against a local cache directory (use any existing cache from a prior `notetaker run`, or create a synthetic one). Steps 1–8 must all pass. Record any discrepancy as a follow-up task.

- [ ] T024 Manual CLI smoke test: (a) `notetaker --help` lists exactly `capture, extract, understand, run, notes`; (b) `notetaker synthesise "https://example/recording"` exits non-zero with a "no such command" message; (c) `notetaker run --help` describes only the three chained stages and does not mention "synthesis" or "summary"; (d) `notetaker run <real-or-mocked-url>` exits zero and prints two final lines naming the cache and the next-step `notetaker notes` command per `contracts/cli-surface.md`.

- [ ] T025 [P] Verify constitutional consistency: (a) `grep -E '^\*\*Version\*\*:' .specify/memory/constitution.md` outputs `**Version**: 1.1.0 | ...`; (b) `grep -i 'Synthesis\|Aligned Segment\|Final Summary' .specify/memory/constitution.md` outputs matches only inside the SYNC IMPACT REPORT comment block at the top of the file (no matches in the normative Article text). If the second grep finds matches in normative text, return to T002 and fix.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1, T001)**: No dependencies. Run first to establish the baseline.
- **Foundational (Phase 2, T002)**: Depends on T001. BLOCKS all user-story phases.
- **US1 (Phase 3, T003–T004)**: Depends on Foundational. Independent of US2/US3/US4.
- **US2 (Phase 4, T005–T007)**: Depends on Foundational. Independent of US1/US3/US4 *for code correctness* — `synthesise()` and `run()` are separate functions in `cli.py` with separate lazy imports. Order with US1 only matters because both edit `cli.py` (no parallel safety on the same file).
- **US3 (Phase 5, T008–T010)**: Depends on Foundational. Independent of US1/US2/US4 — the `[synthesis]` config section has no other readers.
- **US4 (Phase 6, T011–T021)**: Depends on US1, US2, AND US3. Specifically:
  - T011 (rewrite `test_full_pipeline.py`) depends on US3's `Config.resolved_notes_model()` simplification (T008) so the test can construct a notes-mode config naturally.
  - T014 (delete `stages/synthesis/`) depends on US1 (T003) and US2 (T005) having removed every `cli.py` reference to the module.
  - T016 (drop `Stage.SYNTHESISE` enum value) depends on T014 because `stages/synthesis/__init__.py` is the only producer of the value.
- **Polish (Phase 7, T022–T025)**: Depends on all user-story phases.

### Within each phase

- US2 internal: T005 → T006 (T006 [P] only against T005 conceptually, but T006 is in a different file from T005 so they CAN be parallel as long as T005's `cli.py` rewrite doesn't change the test's behavioural assumptions). T007 (verification) runs last.
- US3 internal: T008 (config.py) and T009 (config.toml) are in different files and can run in parallel; T010 (verification) runs after both.
- US4 internal: T011 (test rewrite) MUST precede T014 (delete the source the test imports from). T012 and T013 (test file deletions) can run in parallel with T011. T014 (delete source dir) MUST follow T011/T012/T013. T015–T018 (edits/deletes to surviving source files) can run in parallel after T014. T019 and T020 (doc edits) can run in parallel anytime after T002 (foundational). T021 (verification) runs last.

### Parallel opportunities

- Within US4: T012 + T013 (test deletions, parallel); T015 + T016 + T017 + T018 (post-T014 source edits/deletes, all parallel — different files); T019 + T020 (doc edits, parallel — different files).
- Across phases — once US1, US2, US3 are independently complete, a single developer with three terminals could split T011/T012/T013/T015/T016/T017/T018/T019/T020 across them.

---

## Parallel Example: User Story 4

```bash
# After T002 lands, three doc edits and four post-T014 source edits/deletes can be issued in parallel:
Task: "Edit src/notetaker/cache.py per T015"
Task: "Edit src/notetaker/contracts/log_record.py per T016"
Task: "Delete src/notetaker/contracts/summary.py per T017"
Task: "Delete src/notetaker/contracts/aligned_segments.py per T018"
Task: "Edit HOWTO.md per T019"
Task: "Edit CLAUDE.md per T020"
```

The two test deletions in US4 can also be issued in parallel with each other (and with T011, the test rewrite, since they touch different files):

```bash
Task: "Rewrite tests/integration/test_full_pipeline.py per T011"
Task: "Delete tests/unit/test_aligner.py per T012"
Task: "Delete tests/contract/test_aligned_segments_contract.py per T013"
```

---

## Implementation Strategy

### MVP (User Story 1 only)

1. Complete Phase 1 (T001 — baseline).
2. Complete Phase 2 (T002 — constitution amendment).
3. Complete Phase 3 (T003–T004 — `synthesise` subcommand gone).
4. **STOP and VALIDATE**: `notetaker --help` shows 5 subcommands; `pytest -q` is green. The user's stated intent ("get rid of the old synthesize phase which I don't want to use any more") is materially achieved at this point. The legacy module is still on disk and `notetaker run` still chains it, but the deprecated entry point is gone.

### Incremental delivery

- **Increment 1 (MVP)**: Setup + Foundational + US1 → 4 tasks → deprecated subcommand gone.
- **Increment 2**: + US2 → 7 tasks total → `notetaker run` rewired.
- **Increment 3**: + US3 → 10 tasks total → config surface clean.
- **Increment 4**: + US4 → 21 tasks total → codebase clean.
- **Increment 5**: + Polish → 25 tasks total → fully verified.

Each increment leaves the codebase in a working, test-green state. A reviewer can stop at any increment and the project remains shippable.

### Single-developer strategy

Run the increments serially in priority order: T001 → T002 → T003 → T004 (verify) → T005 → T006 → T007 (verify) → T008 → T009 → T010 (verify) → T011/T012/T013 (parallel) → T014 → T015/T016/T017/T018/T019/T020 (parallel) → T021 (verify) → T022 → T023 → T024 → T025. Commit per VIII.2 ("Task-Sized Commits") after each task or each verification checkpoint.

---

## Notes

- **Article VIII.2 (Task-Sized Commits)**: Each task above is a commit-sized unit. Combine T015–T018 into a single commit if desired (they're conceptually one cleanup), but T011 (test rewrite) and T014 (source deletion) should be separate commits so the test rewrite is reviewable on its own merits.
- **Article VII.3 (Cost-Sensitive Tests Are Mocked)**: T011's rewrite of `test_full_pipeline.py` MUST mock the notes LLM call. The existing test mocks the synthesis LLM call; the same mocking pattern applies. This is non-negotiable per VII.3.
- **Spec history under `specs/`**: Not edited. Per `spec.md` Assumptions and `research.md` Decision 8, `specs/001-`, `specs/002-`, and `specs/003-` are preserved verbatim. Only `.specify/memory/constitution.md`, `HOWTO.md`, `CLAUDE.md`, and active source/config files are touched.
- **No new tests written**: This is a deletion feature; FR-013 requires the test count to *drop* by the count of removed tests, not stay flat. Adding new tests would mask the SC-005 measurement. The polish-phase regression check (T022) is not a test; it's a verification command.
- **The constitution amendment (T002) is in the foundational phase, not in US4**: It is foundational because every subsequent code change depends on the amended principle text being authoritative. Doing it last would mean the entire user-story phase landed code that violated the unamended constitution.

---

## Task ID Index (for cross-reference)

| Phase | IDs | Story | Files touched |
|-------|-----|-------|---------------|
| 1 Setup | T001 | — | (read-only baseline) |
| 2 Foundational | T002 | — | `.specify/memory/constitution.md` |
| 3 US1 | T003, T004 | US1 | `src/notetaker/cli.py` |
| 4 US2 | T005, T006, T007 | US2 | `src/notetaker/cli.py`, `tests/integration/test_run_log_file.py` |
| 5 US3 | T008, T009, T010 | US3 | `src/notetaker/config.py`, `config.toml` |
| 6 US4 | T011–T021 | US4 | `tests/integration/test_full_pipeline.py`, `tests/unit/test_aligner.py`, `tests/contract/test_aligned_segments_contract.py`, `src/notetaker/stages/synthesis/`, `src/notetaker/cache.py`, `src/notetaker/contracts/log_record.py`, `src/notetaker/contracts/summary.py`, `src/notetaker/contracts/aligned_segments.py`, `HOWTO.md`, `CLAUDE.md` |
| 7 Polish | T022, T023, T024, T025 | — | (verification only) |

**Total tasks**: 25.
