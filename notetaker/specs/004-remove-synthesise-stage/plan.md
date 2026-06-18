# Implementation Plan: Remove the Legacy Synthesise Stage

**Branch**: `004-remove-synthesise-stage` | **Date**: 2026-05-09 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/004-remove-synthesise-stage/spec.md`

## Summary

Delete the legacy slide-by-slide summariser pipeline path and consolidate the project around the post-capture notes path that has been the documented happy path since spec 003 shipped. The deletion is end-to-end: CLI subcommand, source module, two data contracts (`Summary`, `AlignedSegment`), config section, log-record enum value, two test files, and all user-facing documentation references. The chained convenience command (`notetaker run`) is rewired to stop at the understanding stage and print the exact next-step `notetaker notes` invocation. The notes feature's default model name is preserved by lifting `"claude-sonnet-4-6"` from the deleted `[synthesis]` section into the `[notes]` section as its explicit default. The constitution names "Synthesis" as one of four pipeline stages and names "Aligned Segment" and "Final Summary" among the inter-stage contracts; this plan amends those references in the same change set so the constitution and the code remain consistent (Article IX.2, IX.3).

## Technical Context

**Language/Version**: Python 3.11+ (current dev tree on 3.12 per `__pycache__/*.cpython-312.pyc`).
**Primary Dependencies**: `typer` (CLI), `anthropic` (Claude SDK — used by surviving notes path, not removed), `pydantic` (data contracts), `structlog` (logging), `tomllib` (stdlib). No dependency removals required by this feature.
**Storage**: Local filesystem cache at `~/.local/share/notetaker/cache/<url-hash>/`. Existing on-disk `synthesis/` subdirectories under that root become orphan files after this feature; the existing `Cache.purge_stale` retention sweep collects them on its normal schedule (no migration code).
**Testing**: `pytest` with the existing `[tool.pytest.ini_options]` config. The `live_api` marker stays untouched. Two test files are deleted (`tests/unit/test_aligner.py`, `tests/contract/test_aligned_segments_contract.py`); two are edited to drop synthesis assertions (`tests/integration/test_full_pipeline.py`, `tests/integration/test_run_log_file.py`).
**Target Platform**: Linux CLI (developer machine; WSL2 in current dev tree).
**Project Type**: Single-project CLI tool. No web/mobile split.
**Performance Goals**: N/A — pure deletion. The notes path's existing performance envelope is unchanged.
**Constraints**:
- Default model name produced by `Config.resolved_notes_model()` MUST equal what it produced before this feature (FR-006, SC-007).
- Loading a user's existing `config.toml` that still contains `[synthesis]` MUST succeed silently — no per-run deprecation warning (FR-005).
- The full non-`live_api` pytest suite MUST stay green; test count drop MUST equal exactly the count of removed-by-FR-009 tests, no other regressions (FR-013, SC-005).
**Scale/Scope**: ~12 source/doc/config files modified or deleted. Approximately:
- 1 directory deleted (`src/notetaker/stages/synthesis/`, 3 files).
- 2 contract files deleted (`contracts/summary.py`, `contracts/aligned_segments.py`).
- 2 test files deleted, 2 test files edited.
- 5 source files edited (`cli.py`, `config.py`, `cache.py`, `contracts/log_record.py`, plus the `notes/` model resolution in `__init__.py` if needed — verified at task time).
- 4 doc/config files edited (`config.toml`, `HOWTO.md`, `CLAUDE.md`, `.specify/memory/constitution.md`).

## Constitution Check

Reviewed against `.specify/memory/constitution.md` v1.0.0 (ratified 2026-05-08). Three articles reference the legacy stage by name and require coordinated amendment in the same change set:

| Article | Reference | Conflict | Resolution |
|---------|-----------|----------|------------|
| I.1 Stage Isolation | "The pipeline consists of four stages: Capture, Slide Extraction, Slide Understanding, and Synthesis." | Names "Synthesis" as the fourth stage. After this feature, the fourth stage in the codebase is "Notes" (the post-capture notes path). | Amend I.1 to name the fourth stage "Notes". The principle (four isolated stages, contract-only communication) is unchanged. |
| I.3 Versioned Data Contracts | "The contracts between stages (Transcript, Slide Timeline, Slide Content, Aligned Segment, Final Summary) are versioned schemas." | Names "Aligned Segment" and "Final Summary" as inter-stage contracts. Both are deleted by this feature; the surviving Notes path consumes its inputs (`SlideContentSchema`, `TranscriptSchema`) directly and emits a Markdown file plus a working-doc Markdown file, neither of which is a versioned inter-stage JSON contract. | Amend I.3 to drop "Aligned Segment, Final Summary" from the named example list. The principle (contracts are versioned, breaking changes bump the version) is unchanged; the example list shrinks. |
| VIII.1 Phased Delivery | "The four stages are delivered in phase order: Capture → Extraction → Understanding → Synthesis." | Names "Synthesis" as the fourth phase. | Amend VIII.1 to name the fourth phase "Notes". Phase ordering and "each phase must produce user-visible value" are unchanged. |

**Other articles re-checked**:
- I.2 Platform Adapters Are Isolated — no impact (notes path has no platform-specific branching).
- I.4 Re-runnability — preserved (notes `--re-render` mode already exists; understanding stage cache is unchanged).
- II.1 Documentation Discipline — this plan keeps all HOW out of `spec.md` and all WHAT/WHY out of `plan.md`.
- III.1, III.2 Cost Controls — preserved (the notes path already exposes `cost_warn_threshold_usd`, `--dry-run`, and per-run cost reporting; the understanding stage's `budget_ceiling_usd` is untouched).
- IV.1, IV.2, IV.3 Configuration — preserved. The `notes.model` default migrates from a runtime fallback (`notes.model or synthesis.summary_model`) to a baked-in default literal in `NotesConfig`, with the comment in `config.toml` updated to name the model explicitly. No magic numbers introduced; all knobs documented inline.
- V.1, V.2, V.3 Observability — preserved. Removing `Stage.SYNTHESISE` from the `event_category` enum is the only logging change; no records currently emit it (only the deleted module did).
- VI.1, VI.2, VI.3 Security/Privacy — no impact.
- VII.1 Stage-Level Tests — the surviving Notes path already has stage-level tests (`tests/unit/test_notes_working_doc.py`, `tests/unit/test_notes_render.py`, `tests/integration/test_notes_command.py`). Deleting tests for a removed stage does not violate VII.1.
- VII.2 Golden Fixtures for the Full Pipeline — `tests/integration/test_full_pipeline.py` is rewritten to assert on `capture → extract → understand → notes` instead of `→ synthesise`, preserving the end-to-end golden-fixture coverage VII.2 requires.
- VII.3 Cost-Sensitive Tests Are Mocked — preserved. The rewritten full-pipeline test mocks the notes LLM call exactly as the existing test mocks the synthesis LLM call.
- VIII.2 Task-Sized Commits — followed by Phase 2 task generation.
- VIII.3 Spec Drift Is Reconciled — the constitution amendment IS the reconciliation; constitution and code land together.
- IX.2 Amendments Require Documentation — provided in this Constitution Check section. Version bump: **1.0.0 → 1.1.0** (MINOR — clarifies/renames within an existing principle, does not remove or redefine a principle and does not add a new one). MAJOR was rejected because no principle is removed or backward-incompatibly redefined; PATCH was rejected because the changes are more than wording fixes (one stage name and two contract names change in normative text).

**Gate verdict**: PASS, conditional on the constitution amendment being delivered as part of this feature's task list. The amendment is a deliverable, not a blocker. Listed in Complexity Tracking below for explicit accountability.

## Project Structure

### Documentation (this feature)

```text
specs/004-remove-synthesise-stage/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions and rationale
├── data-model.md        # Phase 1 — contracts deleted, contracts retained
├── quickstart.md        # Phase 1 — verify-the-removal walkthrough
├── contracts/
│   ├── cli-surface.md   # Before/after CLI command set
│   ├── config-surface.md# Before/after config.toml schema
│   └── constitution-amendment.md  # Articles I.1, I.3, VIII.1 diff
├── checklists/
│   └── requirements.md  # Already created by /speckit-specify
└── tasks.md             # Phase 2 output (NOT created by /speckit-plan)
```

### Source Code (repository root)

The project is a single-tree Python package; this feature only deletes from and edits the existing tree. No new directories, no relocation of survivors.

```text
src/notetaker/
├── cli.py                              # EDIT: drop synthesise(); rewire run()
├── config.py                           # EDIT: drop SynthesisConfig; bake notes.model default
├── cache.py                            # EDIT: drop "synthesis" from STAGE_SUBDIRS
├── contracts/
│   ├── log_record.py                   # EDIT: drop Stage.SYNTHESISE enum value
│   ├── summary.py                      # DELETE
│   ├── aligned_segments.py             # DELETE
│   ├── transcript.py                   # untouched
│   ├── slide_timeline.py               # untouched
│   ├── slide_content.py                # untouched
│   └── frames_manifest.py              # untouched
├── stages/
│   ├── capture/                        # untouched
│   ├── extraction/                     # untouched
│   ├── understanding/                  # untouched
│   └── synthesis/                      # DELETE (entire directory)
│       ├── __init__.py
│       ├── aligner.py
│       └── summarizer.py
├── notes/                              # untouched (this is the surviving path)
│   ├── __init__.py
│   ├── working_doc.py
│   └── render.py
└── utils/                              # untouched

tests/
├── unit/
│   ├── test_aligner.py                 # DELETE
│   └── test_notes_working_doc.py       # untouched (false positive on grep — only mentions
│                                       #             "summary" in unrelated string assertions)
├── contract/
│   └── test_aligned_segments_contract.py  # DELETE
└── integration/
    ├── test_full_pipeline.py           # EDIT: chain ends at notes, not synthesise
    └── test_run_log_file.py            # EDIT: expected stages list drops "synthesise"

config.toml                             # EDIT: remove [synthesis]; rewrite notes.model comment
HOWTO.md                                # EDIT: drop "Legacy synthesise stage" + 6 inline refs
CLAUDE.md                               # EDIT: 3 lines naming the four-stage pipeline
pyproject.toml                          # untouched (no dependencies were exclusive to legacy stage)
.specify/memory/constitution.md         # EDIT: Articles I.1, I.3, VIII.1; SYNC IMPACT REPORT;
                                        #       version 1.0.0 → 1.1.0
```

**Structure Decision**: Existing single-project layout retained. This feature is a deletion; no new modules are introduced and no surviving modules are relocated. The Notes path (`src/notetaker/notes/`) was promoted to first-class status in spec 003 and remains in its current location.

## Complexity Tracking

The Constitution Check above queues a constitution amendment as a deliverable of this feature. That is the only item that warrants explicit tracking.

| Item | Why Needed | Simpler Alternative Rejected Because |
|------|-----------|-------------------------------------|
| Constitution amendment to Articles I.1, I.3, VIII.1 (1.0.0 → 1.1.0) | Articles name "Synthesis", "Aligned Segment", and "Final Summary" — all three are deleted by this feature. Without the amendment, the constitution names artifacts the codebase no longer contains, which is a self-contradiction the next reader will hit. | Leaving the constitution unchanged was rejected because IX.3 ("Reviews Verify Constitutional Compliance") would then fail every future PR review against this codebase. Doing the amendment in a separate follow-up feature was rejected because it would land the codebase in a known-violating state with no tracking of when the violation gets cleared. |
| Test rewrite of `tests/integration/test_full_pipeline.py` (rather than deletion) | VII.2 requires a golden end-to-end fixture. The current file IS that fixture; deleting it would lose Article VII.2 coverage. Rewriting it to chain into `notes` instead of `synthesise` preserves the coverage. | Deletion was rejected because it would silently lose VII.2 coverage with no replacement. Leaving the test referencing the deleted module was rejected because it would not collect. |

No other complexity items. The rest of this feature is straight removal.
