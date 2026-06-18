# Implementation Plan: Post-Capture Notes (Slides + Transcript → Notes)

**Branch**: `003-post-capture-notes` | **Date**: 2026-05-09 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-post-capture-notes/spec.md`

## Summary

Add a new `notetaker notes` subcommand that combines an already-extracted
slide-content artifact with a user-supplied transcript file (in any of three
shapes: browser-scrape blocks, WebVTT, or notetaker `transcript.json`) to
produce polished Markdown meeting notes via a single LLM render call.

The implementation is two deterministic steps surrounding one LLM call:

1. **Parse + assemble** — detect the transcript format, parse it into the
   existing `TranscriptSchema`, and concatenate slide content + parsed
   utterances into a `working_doc.md` written into the recording's cache
   directory.
2. **Render** — make exactly one Sonnet call against `working_doc.md` with a
   fixed prompt; retry on transient failure per the existing retry policy;
   log every attempt and the final outcome to the run log; write `notes.md`
   on success.

A `--re-render` mode skips the parse+assemble step and reuses an existing
`working_doc.md`, so iterating on prompt/model is cheap. A `--dry-run` mode
reports projected cost without making the API call. Both `working_doc.md`
and `notes.md` live under a per-recording sub-path inside the cache and are
exempt from the existing 30-day cache retention purge (see Constitution
Check note on VI.2).

The existing `synthesise` stage and its `summary.md` output stay in the
codebase but are no longer the documented happy path; documentation steers
users to `notetaker notes`. Demoting the live transcript scrape to
non-blocking best-effort is part of this feature (FR-015) so a missed live
scrape exits successfully with the slide artifacts intact.

## Technical Context

**Language/Version**: Python 3.12 (existing project; `requires-python = ">=3.11"`)
**Primary Dependencies**: `anthropic` (LLM calls), `structlog` (existing logging from feature 002), `pydantic` (existing contracts), `typer` (existing CLI)
**Storage**: Filesystem only — `~/.local/share/notetaker/cache/<url-hash>/notes/{working_doc.md, notes.md}`. No new database or external store.
**Testing**: `pytest`, `pytest-mock`. The LLM call is mocked by default (Article VII.3); a single `live_api`-marked test exercises the real API on demand.
**Target Platform**: Linux / macOS / WSL CLI (matches existing project)
**Project Type**: CLI tool (single project; existing `src/notetaker/` layout)
**Performance Goals**: Working-doc assembly ≤ 2s for 200 slides + 1000 utterances. LLM render wall-clock ≤ 60s for a 1-hour meeting. Re-render path skips assembly entirely.
**Constraints**: One LLM render call, model defaults to `config.synthesis.summary_model` (currently `claude-sonnet-4-6`). Working doc must fit Sonnet's 200K-token context window; current measured size for a 1-hour meeting is ~35K input tokens — well inside the budget. Default cost ≤ $0.30 per render at Sonnet pricing (matches SC-002).
**Scale/Scope**: Up to ~1-hour meetings; ~200 unique slides max; ~1000 utterances max. Longer meetings would need chunking; explicitly out of scope per spec Assumptions.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Article | Status | Notes |
|---|---|---|
| I.1 Stage Isolation | PASS | `notes` is not a fifth stage; it is a top-level command consuming existing stage outputs (`slide_content.json`, optionally `transcript.json`). It does not import stage internals. |
| I.2 Platform Adapters Are Isolated | PASS | The three transcript parsers (`scrape.js` blocks, WebVTT, `transcript.json`) live under `src/notetaker/stages/capture/adapters/zoom_transcript_parsers.py` — keeping platform/format-specific logic in the adapters layer. The `notes` orchestrator calls a single `parse_transcript_file(path) -> TranscriptSchema` dispatcher and contains no format branches. |
| I.3 Data Contracts Are Versioned | PASS | The internal transcript representation re-uses the existing versioned `TranscriptSchema`. Two new artifacts (working doc, notes file) are Markdown documents with documented structures (see Phase 1 contracts) — they are not strict JSON schemas, but their shape is captured in `contracts/working_doc.md` and `contracts/notes_file.md` so consumers (test fixtures, future re-renderers) can rely on them. |
| I.4 Re-runnability | PASS | Re-render mode (FR-013) is the explicit constitutional answer: failed render does not require re-running understand or capture. |
| II.1 Spec/Plan separation | PASS | Spec carries no framework names; this plan owns all technical decisions. |
| II.2 Every stage documents its contract | PASS | Phase 1 produces `contracts/transcript_input.md`, `contracts/working_doc.md`, `contracts/notes_file.md`, `contracts/render_log_records.md`. |
| III.1 Vision LLM caching | N/A | This feature makes no vision calls; it consumes the cached `slide_content.json` written by understanding. |
| III.2 Cost controls first-class | PASS | FR-011 reports cost per call; FR-012 supports dry-run; FR-007a logs cost per attempt. Hard ceiling not enforced because cost ceiling for a single ~$0.20 call would be theatre; the dry-run + console summary delivers the same behaviour. |
| III.3 No hidden capture | N/A | Feature does not capture. |
| IV.1 No magic numbers | PASS | New tunables (`render.max_tokens`, `notes.retention_days`, output filenames) all live in `config.toml` under a new `[notes]` section; the prompt itself is a string constant in code with rationale comments. |
| IV.2 Sensible defaults | PASS | Default model = `synthesis.summary_model`. Default retention = 365 days (see VI.2 note). Default output filename = `notes.md`. Default working doc filename = `working_doc.md`. |
| IV.3 Configuration documented | PASS | Every new key gets an inline comment in `config.toml` per the project convention. |
| V.1 Stages log decisions | PASS | FR-007a covers per-attempt and per-invocation render records. The dispatcher logs which transcript shape was detected. The working-doc builder logs slide / utterance counts. |
| V.2 Debug mode preserves intermediates | PASS | `working_doc.md` is *always* preserved (not gated on debug) because it is the cheap-re-render input. |
| V.3 Failures diagnosable without re-running | PASS | FR-017 leaves working doc in place on persistent failure; FR-007a logs token counts and error per attempt. |
| VI.1 Credentials not logged | PASS | Anthropic key handled via SDK env var; no credential surfaces in logs. |
| **VI.2 Retention policy** | **PASS WITH NOTE** | Spec FR-018 says working doc + notes are "exempt from automatic cache retention purge" with a user-clarified intent of "persist until the user removes them." The constitution forbids indefinite retention *by default*. This plan reconciles by introducing a separate `[notes] retention_days` config knob with a **default of 365 days** (long enough to honour the user's intent — surviving normal cache churn — without making indefinite retention the default). Setting this to 0 explicitly opts into indefinite retention; `0` is *not* the default. Frames, slide content, and synthesis artifacts continue to follow the existing 30-day `[cache] retention_days`. |
| VI.3 User-entitled content | N/A | Feature consumes only locally-cached content the user already produced. |
| VII.1 Stage-level tests | PASS | New unit tests: transcript-parser dispatcher (3 shapes + refusal), working-doc builder, render module with mocked client. New integration test: CLI `notes` subcommand against a tiny golden fixture. |
| VII.2 Golden fixtures | PASS | New fixture under `tests/fixtures/notes/` containing a 5-slide synthetic `slide_content.json`, a 12-utterance synthetic transcript in each of the three shapes, and an expected `working_doc.md` for byte-for-byte assembly assertions. The render call is mocked. |
| VII.3 Cost-sensitive tests mocked | PASS | All render-call tests mock the `anthropic.Anthropic` client; a `live_api`-marked test exercises one real call and is excluded from the default `pytest` run per the existing `addopts = "-m 'not live_api'"`. |
| VIII.1 Phased delivery | PASS | This feature is itself one phased deliverable. The four user stories from the spec map to the implementation phases below; each delivers user-visible value alone. |
| VIII.2 Task-sized commits | Implementation discipline; not a planning artifact. |
| VIII.3 Spec drift reconciled | PASS | One reconciliation in this plan (VI.2 default retention vs. spec FR-018 wording). The spec wording is honoured in spirit; the plan documents the finite-default constraint. If a strict reading of FR-018 is required, the spec must be amended. |

**Verdict**: PASS. One reconciliation noted (VI.2 retention default) and addressed by introducing a separate `[notes] retention_days` config with a generous finite default. No constitutional violations require Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/003-post-capture-notes/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── transcript_input.md
│   ├── working_doc.md
│   ├── notes_file.md
│   └── render_log_records.md
├── checklists/
│   └── requirements.md  # Spec quality checklist (already produced by /speckit-specify)
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
src/notetaker/
├── cli.py                                    # ADD: new `notes` Typer subcommand
├── config.py                                 # ADD: NotesConfig dataclass + load wiring
├── notes/                                    # NEW MODULE — orchestrator + LLM render
│   ├── __init__.py                           # NEW: orchestrate(build_working_doc, render)
│   ├── working_doc.py                        # NEW: deterministic assembly (slide+transcript → markdown)
│   └── render.py                             # NEW: single LLM call with retry+log+cost reporting
├── stages/
│   └── capture/
│       └── adapters/
│           ├── zoom.py                       # MODIFY: demote live transcript scrape to non-blocking best-effort (FR-015)
│           └── zoom_transcript_parsers.py    # NEW: three-shape format detector + parsers, all returning TranscriptSchema
├── utils/
│   ├── llm_json.py                           # EXISTS (created earlier)
│   └── log_store.py                          # MODIFY: extend retention purge to skip the new {working_doc.md, notes.md}
└── contracts/
    └── transcript.py                         # EXISTS — TranscriptSchema reused as the canonical internal shape

config.toml                                   # MODIFY: add [notes] section
HOWTO.md                                      # MODIFY: document the post-capture flow as the supported path

tests/
├── fixtures/
│   └── notes/                                # NEW: tiny synthetic cache + 3 transcript shapes + expected working_doc.md
├── unit/
│   ├── test_zoom_transcript_parsers.py       # NEW: dispatcher + 3 shapes + refusal
│   ├── test_notes_working_doc.py             # NEW: assembly correctness, edge cases (empty title, raw_ocr-only)
│   └── test_notes_render.py                  # NEW: mocked Anthropic client; retry behaviour; log records emitted
└── integration/
    ├── test_notes_command.py                 # NEW: end-to-end CLI invocation against golden fixture, mocked render
    └── test_notes_command_live.py            # NEW: marked `live_api`; one real call, opt-in only

scripts/
├── recover_slide_content.py                  # EXISTS — keep, used to recover pre-fix caches
├── build_working_doc.py                      # REMOVE post-cutover (logic moves into src/notetaker/notes/working_doc.py)
└── render_notes.py                           # REMOVE post-cutover (logic moves into src/notetaker/notes/render.py)
```

**Structure Decision**: Single project, existing layout. The new `notes`
module is at `src/notetaker/notes/` rather than under `src/notetaker/stages/`
because per Article I.1 it is *not* a pipeline stage. The transcript parsers
live in the existing capture-adapters directory because Article I.2 says
platform/format-specific knowledge belongs there. The orchestrator and CLI
have zero format branches.

The two `scripts/` prototypes built earlier in this session are
intentionally not promoted as-is; they are the working seed for the real
modules and are removed once the modules and tests are in place
(Article VIII.2 — task-sized commits — and to avoid two parallel code paths
for the same job).

## Complexity Tracking

> No constitutional violations require justification. The VI.2 reconciliation
> (finite-but-generous retention default) is recorded in the Constitution
> Check table above and is implemented as a config default, not a code
> exception.
