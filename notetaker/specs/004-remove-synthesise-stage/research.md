# Phase 0 Research: Remove the Legacy Synthesise Stage

This is a deletion feature in a codebase whose author has already done the
hard architectural work in spec 003. The "research" here is mostly **decision
recording with rationale** for the dozen judgment calls that fall out of the
spec's functional requirements. There were no NEEDS CLARIFICATION markers in
`spec.md`; nothing here is open.

## Decision 1 — Where the Notes default model name lives after the legacy section is deleted

**Decision**: Bake the literal `"claude-sonnet-4-6"` into `NotesConfig.model` as its
default-factory value. Delete `Config.resolved_notes_model()`'s fallback to
`synthesis.summary_model`. The function still exists and still honours an
explicit `notes.model` override; it just no longer chains to a removed sibling.

**Rationale**:
- FR-006 / SC-007 require the user-visible default model name to stay the
  same. The only place that name lives today is `SynthesisConfig.summary_model`
  (default `"claude-sonnet-4-6"`); the notes config has `model = ""` and falls
  back. After deleting `SynthesisConfig`, the literal has to land somewhere or
  the user's behaviour silently changes.
- Lifting the literal into `NotesConfig.model` is the most local change and
  matches Article IV.1 ("no magic numbers in code; thresholds and model
  identifiers live in configuration"). The notes section already exists; the
  literal moves into it without introducing a new section or knob.
- Keeping `resolved_notes_model()` (rather than inlining `cfg.notes.model`
  everywhere) preserves the single chokepoint for "which model does the notes
  call use?". Future overrides (env var, per-cache override) can land there
  without touching every call site.

**Alternatives considered**:
- *Keep an empty default and require the user to set `notes.model` explicitly.*
  Rejected — violates IV.2 ("default configuration must work end-to-end on a
  typical Zoom Cloud Recording without modification") and breaks SC-007.
- *Keep `[synthesis]` in the config.toml as a deprecated alias.* Rejected —
  defeats the spec's User Story 3 ("the configuration surface no longer offers
  a knob you can't use"). Also adds maintenance burden (two paths to test).
- *Move the literal into a separate `[models]` section and have `[notes]`
  reference it.* Rejected as scope creep — the spec does not ask for a
  cross-feature model registry, and inventing one to handle a single migration
  is an architectural decision that belongs in its own spec.

## Decision 2 — What `notetaker run` does after the legacy stage is gone

**Decision**: `run` chains `capture → extract → understand` and exits. On
success it prints two lines: (1) the cache root path, and (2) the literal
next-step command `notetaker notes <url> [transcript-path]` so the user can
copy it. It does NOT auto-invoke the notes path.

**Rationale**:
- FR-002 requires `run` to do only the unattended stages. The notes path needs
  a transcript file the user supplies after pulling it from their browser
  (HOWTO.md "Obtaining a transcript") — `run` cannot supply that argument.
- Auto-invoking notes with `[transcript-path]` defaulted to the cached
  `transcript.json` would silently produce notes from a transcript that may be
  empty (the original problem spec 003 was written to fix). The spec's
  Edge Case "Live transcript scraper still ran in this cache" already
  documents that `notetaker notes` falls back to a cached non-empty
  `transcript.json` when called without a path; making `run` opaque about that
  fallback is a worse UX. Better: `run` always prints the next command and the
  user always sees what they're invoking.
- VIII.1 ("each phase must produce user-visible value on its own") is already
  satisfied by capture/extract/understand independently; the user sees the
  cache populated and is told the exact next step.

**Alternatives considered**:
- *Delete `notetaker run` entirely.* Rejected — breaks the most-used entry
  point for a fresh recording without any user benefit. The spec's User
  Story 2 explicitly preserves `run`.
- *Have `run` auto-chain into `notes` when a non-empty `transcript.json`
  exists in the cache.* Rejected — silent behaviour. The user can't tell from
  `run`'s output whether the live scrape worked. Better to have one obvious
  next step the user types explicitly.
- *Have `run` print the next command and refuse to run if `transcript.json`
  is missing.* Rejected — `transcript.json` is normally only present *after*
  capture's live scrape completes successfully; refusing on absence would
  collapse most invocations. The transcript is post-capture, optional, and
  user-supplied; `run` shouldn't know about it.

## Decision 3 — Whether to delete `tests/integration/test_full_pipeline.py` or rewrite it

**Decision**: Rewrite. The test stays as the Article VII.2 golden end-to-end
fixture but its synthesis assertions are replaced with notes assertions:
chain `extract → understand → notes`, mock the notes LLM call (single call),
assert the notes file was written and the working doc is populated.

**Rationale**:
- VII.2 ("at least one end-to-end fixture must exist and pass") is a hard
  requirement. Deleting the only end-to-end test would silently lose that
  coverage even if every unit test passes.
- The existing test file already imports the synthesis path's mocks at lines
  127–155; rewriting it to mock the notes path is a like-for-like swap, not a
  new fixture. The synthetic fixture data (slide_timeline, slide_content,
  transcript JSON) remains valid input for the notes path.
- Deletion would also fail SC-005's "test count drop equals exactly the
  removed-by-FR-009 count" requirement, because the integration test does not
  fall under FR-009 (its purpose is end-to-end coverage, not coverage of the
  removed module).

**Alternatives considered**:
- *Delete the file and add a separate `test_full_pipeline_notes.py`.*
  Rejected — same coverage with churn. The existing file's name is right;
  only its mocked stage chain changes.
- *Keep the synthesis assertions and add notes assertions alongside.*
  Rejected — leaves dead `from notetaker.stages.synthesis import …` imports
  that won't collect after the module is deleted.

## Decision 4 — Whether to delete `Stage.SYNTHESISE` from the log-record enum or retain as a stable-but-unused value

**Decision**: Delete. After this feature, no producer emits `stage="synthesise"`,
so the value's continued presence in the closed-set enum would be dead surface
area.

**Rationale**:
- FR-011 explicitly requires removing legacy entries from the structured-log
  contracts. The whole point of a closed-set enum (per the docstring on
  `EventCategory`) is that consumers can rely on the absence of values that
  aren't emitted; keeping a never-emitted value misleads consumers about what
  to expect.
- The log-record schema is at `SCHEMA_VERSION = "1.0.0"`. Changing the closed
  set is a contract change; per Article I.3 it requires a version bump. The
  bump is `1.0.0 → 1.1.0` (additive on the producer side, restrictive on the
  consumer side — a consumer that filters `stage in {capture, extract,
  understand, synthesise, cli}` keeps working; a consumer that switches on
  `Stage.SYNTHESISE` would have already been dead code). Document the bump in
  the schema's docstring.

**Alternatives considered**:
- *Retain `SYNTHESISE` as a stable value with a comment "do not emit".*
  Rejected — violates the closed-set principle and adds permanent confusion.
- *Rename to `NOTES`.* Rejected as scope creep — the notes path doesn't
  emit stage_start/stage_end records keyed on `Stage.NOTES` today (the notes
  CLI command runs synchronously inside the CLI shell, not as a `stage_lifecycle`
  context). Adding such records would be a separate feature. If the notes
  path later wants stage-lifecycle records, the value can be added then.

## Decision 5 — How to handle existing on-disk `synthesis/` cache subdirectories

**Decision**: Do nothing in code. The existing `Cache.purge_stale` already
walks every cache root and `shutil.rmtree`s the entire entry once it's stale
(or partially purges, preserving `notes/`). Stale `synthesis/` subdirectories
are removed by that same sweep with no special-case code.

**Rationale**:
- FR-012 forbids migration code and forbids special-casing. The reasoning in
  the spec was right: the cost of a migration script (test surface, edge
  cases, the user wondering why notetaker is touching their cache the first
  time they upgrade) vastly exceeds the cost of letting the existing
  retention sweep handle it on its normal 30-day schedule.
- A user who wants the `synthesis/` directories gone immediately can `rm -rf`
  them; the behaviour of every surviving subcommand against a cache containing
  orphan `synthesis/` files is unchanged (nothing reads them after this
  feature; nothing crashes on their presence).

**Alternatives considered**:
- *Add a one-time "migrate v003 → v004" script.* Rejected — see above.
- *Add a deprecation warning when `synthesis/` is present.* Rejected — emits
  a noisy warning every run for every cache touched, for no user benefit.

## Decision 6 — Constitution amendment scope and version bump

**Decision**: Amend Articles I.1, I.3, and VIII.1 in the same change set as
the code deletion. Bump version 1.0.0 → 1.1.0. Update the `SYNC IMPACT REPORT`
header at the top of `constitution.md` with the diff, the rationale, the
impact assessment, and the migration plan.

**Rationale**:
- IX.2 requires (a) written rationale, (b) impact assessment, (c) migration
  plan. The rationale is "the named stage and the named contracts no longer
  exist after spec 004"; the impact is on Articles I.1, I.3, VIII.1 only
  (re-reviewed in Constitution Check); the migration plan IS spec 004 itself.
- IX.3 ("Reviews verify constitutional compliance") would fail every future
  PR review if the constitution still named "Synthesis" as a stage that the
  code no longer has. Doing the amendment in a follow-up feature would land
  the codebase in a known-violating state.
- MINOR (1.1.0) was chosen because: no principle is removed (none are added
  either); the *names* in the example list of I.3 contracts and the *name*
  of one of four stages in I.1/VIII.1 change. The principles themselves
  (stage isolation, contract versioning, phased delivery) survive verbatim.
  MAJOR was rejected because no principle is backward-incompatibly redefined;
  PATCH was rejected because more than typo-level wording changes.

**Alternatives considered**:
- *Defer the amendment.* Rejected — leaves the codebase non-compliant with
  no tracking.
- *MAJOR bump to 2.0.0.* Considered. Rejected because IX.2's MAJOR criterion
  is "backward-incompatible removals or redefinitions of principles" — and
  no principle is removed or redefined. The list of named example contracts
  in I.3 is illustrative ("(Transcript, Slide Timeline, …)"), not normative.

## Decision 7 — `pyproject.toml` dependencies

**Decision**: No changes. Every listed dependency
(`playwright`, `imagehash`, `Pillow`, `pytesseract`, `anthropic`, `pydantic`,
`structlog`, `typer`) is consumed by at least one surviving stage:
- `playwright` — capture stage
- `imagehash`, `Pillow` — extraction stage
- `pytesseract`, `anthropic` — understanding stage (and `anthropic` is also
  used by the surviving notes path)
- `pydantic` — every contract module
- `structlog` — logging utility
- `typer` — CLI

**Rationale**: FR-014 requires removing dependencies whose only consumer was
the removed stage. Verified by inspection: nothing in the legacy stage
imported a unique dependency.

**Alternatives considered**: None — the inspection is conclusive.

## Decision 8 — Documentation diff scope

**Decision**: Edit `HOWTO.md`, `CLAUDE.md`, and `config.toml`'s inline
comments only. Do NOT edit `specs/003-post-capture-notes/spec.md`,
`specs/001-slide-extractor/spec.md`, or `specs/002-observability-logging/spec.md`.
Spec history is preserved as-written.

**Rationale**:
- Per the spec's Assumption "Spec history under `specs/` is preserved
  unchanged. The `specs/003-post-capture-notes/spec.md` document explicitly
  anticipates this feature and is not edited as part of this work."
- 003's spec already says "A subsequent feature may decide to remove the old
  synthesis stage" — that feature is this one, and 003 reading the future
  correctly is a good record to preserve.
- `HOWTO.md`, `CLAUDE.md`, `config.toml` are *active* documentation that the
  user reads to understand the *current* system, so they must reflect the
  current system after this feature. The edit list:
  - `HOWTO.md` line 32 — `--help` should print 5 subcommands, not 6.
  - `HOWTO.md` line 207 — drop the `synthesis/` row from the cache layout.
  - `HOWTO.md` lines 224–225 — drop `notetaker synthesise` and the "legacy"
    sentence from the CLI table.
  - `HOWTO.md` line 241 — drop "synthesis output" from the retention table.
  - `HOWTO.md` line 254 — drop the `synthesis/aligned_segments.csv` debug note.
  - `HOWTO.md` lines 318–326 — delete the entire "Legacy synthesise stage"
    section.
  - `HOWTO.md` line 331 — update the test count comment if it changes after
    test removals (`pytest # all non-live, ~138 tests` → adjust).
  - `CLAUDE.md` line 11 — replace "four-stage pipeline" listing.
  - `CLAUDE.md` line 12 — `run` no longer chains synthesise.
  - `CLAUDE.md` line 16 — drop the "older synthesise stage remains" sentence.
  - `config.toml` line 6 — rewrite the `[notes].model` comment to name the
    bundled default and remove the "inherit synthesis.summary_model" mention.
  - `config.toml` lines 51–53 — delete the `[synthesis]` section.

**Alternatives considered**:
- *Add a CHANGELOG entry.* Out of scope — the project does not ship a
  changelog file today; introducing one is its own feature.
- *Edit the 003 spec to mark the "synthesise stage remains" assumption as
  superseded.* Rejected per Assumption above. Spec history is not edited.

## Open questions

None. All decisions resolved by the spec's own Assumptions section, by the
constitution, or by inspection of the existing codebase.
