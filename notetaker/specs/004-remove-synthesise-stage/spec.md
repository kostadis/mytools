# Feature Specification: Remove the Legacy Synthesise Stage

**Feature Branch**: `004-remove-synthesise-stage`
**Created**: 2026-05-09
**Status**: Draft
**Input**: User description: "let's get rid of the old synthesize phase which I don't want to use any more"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The deprecated subcommand is gone (Priority: P1)

A user opens a fresh shell, runs `notetaker --help`, and sees only the subcommands that the project actually wants them to use. The legacy slide-by-slide summariser — which has been documented as "kept for backwards compatibility" since the post-capture notes feature shipped — is no longer listed, no longer invokable, and no longer surfaces in tab-completion. A user who follows the printed help cannot accidentally run a code path that the project owner has stated they no longer want to use.

**Why this priority**: The whole point of this feature is the user's stated intent: stop offering a path you don't want people to take. Leaving a deprecated subcommand listed in `--help` is the most visible violation of that intent. Every other change in this feature flows downstream from this one.

**Independent Test**: From a clean checkout, install the package and run `notetaker --help`. Confirm the legacy summariser subcommand is absent. Then attempt to invoke it directly by name; confirm the CLI returns a "no such command" error rather than executing it.

**Acceptance Scenarios**:

1. **Given** the user has installed the project, **When** they run `notetaker --help`, **Then** the legacy summariser subcommand does not appear in the listed subcommands and the count of listed subcommands is reduced by exactly one relative to before this feature.
2. **Given** the user types the legacy subcommand name explicitly, **When** they invoke it, **Then** the CLI returns a clear "unknown command" error and a non-zero exit code, and no part of the legacy summariser code runs.
3. **Given** the user inspects the project's user-facing documentation, **When** they search for the legacy subcommand name or for "legacy synthesise stage" headings, **Then** no live references remain — only at most a single line in a changelog or migration note pointing at this feature's number.

---

### User Story 2 - The `run` chain stops at understanding and points at notes (Priority: P1)

A user invokes the chained convenience command (`notetaker run <url>`) expecting it to do everything the project still supports in a single shot. Today that command chains capture → extract → understand → the legacy summariser. After this feature, the chain stops at the understanding stage — because the documented happy path for producing notes is the post-capture notes subcommand, which requires a transcript file the user supplies from their browser. The chained command finishes successfully, prints the cache directory it produced, and prints exactly the next command the user should run to turn that cache into notes.

**Why this priority**: `notetaker run` is the most-used entry point for a fresh recording — losing it would surprise users. Rewiring it to end where the supported pipeline now ends preserves the convenience while honouring the user's intent. Skipping this rewire would either leave `run` calling the removed code (a build break) or quietly remove `run` (a UX regression).

**Independent Test**: Invoke `notetaker run <url>` against a recording for which capture, extract, and understand can all complete. Confirm the command exits successfully, that no legacy-summariser artifacts are produced in the cache, and that the final printed line tells the user exactly what to type next to produce notes.

**Acceptance Scenarios**:

1. **Given** the user runs `notetaker run <url>`, **When** the command completes successfully, **Then** capture, extract, and understand have produced their normal cache artifacts AND no `synthesis/` subdirectory or summary file is created in the cache.
2. **Given** the user runs `notetaker run <url>`, **When** the command finishes, **Then** the final two lines of console output state (a) the cache path and (b) the exact next command to invoke to produce notes — including the placeholder for the transcript file path.
3. **Given** the user runs `notetaker run --help`, **When** they read its description, **Then** the description names only the stages the command actually runs (no mention of a fourth/synthesis stage), so help text matches behaviour.

---

### User Story 3 - The configuration surface no longer offers a knob you can't use (Priority: P2)

A user opens the shipped `config.toml`. They see configuration sections only for the stages and features the project actually supports. There is no `[synthesis]` section, no `summary_model` knob, and no comment telling them "this is the fallback for the notes model." The notes feature's model knob is self-contained — it carries its own default and does not point at a removed sibling. A user editing the file to swap models for the notes call only needs to look in one place.

**Why this priority**: Configuration is documentation. Leaving a `[synthesis]` section in the shipped config (or a "fall back to synthesis.summary_model" comment in the notes section) tells the user this stage is alive and supported when, after this feature, it is not. Removing it eliminates a confusing self-contradiction. Lower priority than P1 because nobody crashes if it's left in — but it is a finish-the-job item.

**Independent Test**: After this feature, run `grep -i 'synthes\|summary_model' config.toml`. Confirm the result is empty. Load the configuration in a fresh process and confirm the notes feature still resolves a model and still produces the same default model name as it did before this feature.

**Acceptance Scenarios**:

1. **Given** the shipped `config.toml` is opened in an editor, **When** the user searches for the legacy stage name or the legacy model knob, **Then** no matches are found.
2. **Given** a user's existing `config.toml` (predating this feature) still contains a `[synthesis]` section, **When** the CLI loads it, **Then** the load succeeds without error, the unknown section is silently ignored, and behaviour is identical to a config file without that section. (No migration script required.)
3. **Given** the user wants to change which model the notes call uses, **When** they read the notes section's comment in the shipped `config.toml`, **Then** the comment names a concrete default model and does not redirect them to a removed section.

---

### User Story 4 - The codebase no longer carries two competing implementations (Priority: P3)

A new contributor (or returning maintainer) opens the project's source tree to find where notes are produced from a transcript. They find exactly one implementation: the post-capture notes path. There is no parallel `stages/synthesis/` directory containing a slide-aligner, a slide-by-slide summariser, and a contracts module describing a `Summary` schema. There is no test directory full of fixtures for that aligner. The cognitive load of "which of these two paths is the real one?" is gone.

**Why this priority**: This is the maintenance payoff. Lower priority than P1/P2 because no end-user behaviour depends on it — but leaving the dead code in place re-creates the original problem (two competing paths) the next time someone reads the tree. The P1 stories are necessary; this story is what makes the cleanup actually durable.

**Independent Test**: From a clean checkout after this feature, run a recursive search for the legacy stage name across `src/`, `tests/`, and the user-facing docs. Confirm the only matches are in changelog/spec history files. Run the full test suite and confirm no test asserts on the legacy stage's behaviour.

**Acceptance Scenarios**:

1. **Given** the source tree is searched for the legacy stage's module name, **When** the search completes, **Then** no live source file under `src/` references it, no test under `tests/` exercises it, and no shipped documentation file (`HOWTO.md`, `CLAUDE.md`, `README.md` if present) describes it as a supported path.
2. **Given** the test suite is run, **When** it completes, **Then** every test that previously exercised the legacy stage has either been removed (because its only purpose was to test the removed code) or rewritten to target the surviving path it covered.
3. **Given** the project's structured-log contracts are inspected, **When** the legacy stage's event names are searched for, **Then** they are absent from the contract (no orphan log-record types referring to a stage that no longer exists).

---

### Edge Cases

- **Existing caches contain `synthesis/` subdirectories.** A user who ran `notetaker run` before this feature has a `synthesis/` directory inside one or more cache entries, containing a `summary.md`, a `summary.json`, and an `aligned_segments.csv`. After this feature, those files are orphans: nothing reads them, nothing writes to them. The system MUST NOT crash when it encounters them, MUST NOT attempt to migrate them, and MUST allow the existing cache-retention purge to remove them on its normal schedule along with the rest of the recording's cache. No special migration is required.
- **User's `config.toml` still has `[synthesis]`.** Many users have a hand-edited `config.toml` containing `[synthesis] summary_model = "..."`. After this feature, the loader MUST silently ignore unknown sections and unknown keys (the existing TOML loader already does this) and the run MUST proceed normally with the notes model defaulting to the bundled default. The CLI MUST NOT print a deprecation warning every run for a removed knob — the user already saw the help text and the documentation.
- **User scripts call `notetaker synthesise` directly.** A user may have a shell script or makefile that pipes through the legacy subcommand. After this feature, that script will fail with a clear "no such command" message from the CLI parser. The project does not undertake to detect or shim such callers — the legacy stage was already documented as legacy, and the failure is loud rather than silent.
- **`notetaker run` previously printed a synthesis cost line.** The console output of `run` will lose its final "Pipeline complete. Summary: …" line. The replacement final line MUST be unambiguous about what was produced and what to do next, so a user grepping CI logs for the old line will see a clearly different (not silently absent) signal.
- **Logging records that referenced the legacy stage.** The structured-log `event_category` enum or equivalent contract MUST NOT keep dead values for the removed stage's lifecycle events. Any log-analysis pipeline keyed on the old `stage="synthesis"` value will see those events disappear; this is acceptable and expected.
- **The `[notes] model = ""` empty-string fallback.** Today an empty `notes.model` falls back to `synthesis.summary_model`. After this feature, an empty `notes.model` MUST instead resolve to the bundled default model name baked into the notes configuration's own default. The user-visible default model for the notes call MUST NOT change as a result of this feature unless the user has explicitly overridden it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The CLI MUST NOT expose the legacy slide-by-slide summariser subcommand. After this feature, invoking the CLI with that subcommand name MUST produce a "no such command" error from the CLI parser and exit non-zero.
- **FR-002**: The chained convenience command (`notetaker run`) MUST run only the capture, extract, and understand stages. It MUST NOT invoke the legacy summariser. On success, it MUST print the cache path it populated and the exact next-step command (the notes subcommand, with a placeholder for the transcript path) so the user can copy it.
- **FR-003**: The chained command's `--help` description MUST accurately enumerate the stages it runs. It MUST NOT mention a fourth or synthesis stage.
- **FR-004**: The shipped `config.toml` MUST NOT contain a `[synthesis]` section, MUST NOT contain a `summary_model` knob, and MUST NOT contain a comment in the `[notes]` section that points at the removed knob.
- **FR-005**: The configuration loader MUST silently ignore an unknown `[synthesis]` section if present in a user's existing `config.toml`. Loading such a file MUST succeed and MUST NOT emit a warning every run.
- **FR-006**: The notes feature's model resolution MUST remain self-contained. An empty `notes.model` MUST resolve to a default model name that lives inside the notes configuration itself. The user-visible default model name produced by this resolution MUST equal the default model name produced before this feature (no silent model change).
- **FR-007**: The legacy summariser's source files MUST be removed from the source tree. After this feature, no live source file under `src/` (excluding spec history under `specs/`) MUST import from or reference the legacy stage's module path.
- **FR-008**: The legacy summariser's data contract (the `Summary` schema and any sibling contracts that exist solely to describe its output) MUST be removed from the contracts module unless the same schema is independently used by the surviving notes path.
- **FR-009**: Tests whose sole purpose is exercising the legacy summariser MUST be removed. Tests that exercise the legacy summariser only as a side-effect of testing a shared component (e.g., the configuration loader, the cache layout) MUST be rewritten to target the surviving path so the underlying coverage is preserved.
- **FR-010**: User-facing documentation (`HOWTO.md`, `CLAUDE.md`, and any other Markdown the project ships at the repository root) MUST NOT describe the legacy summariser as a supported path. Where the documentation today lists the legacy subcommand, that line MUST be removed. Where it carries a "Legacy synthesise stage" section, that section MUST be deleted (not merely re-flagged).
- **FR-011**: Structured-logging contracts (the `event_category` enumeration and any per-stage log-record types) MUST NOT retain entries that exist only to describe the removed stage's lifecycle events.
- **FR-012**: The cache retention behaviour for legacy `synthesis/` subdirectories MUST follow the existing cache retention policy unchanged. The system MUST NOT crash on encountering a legacy `synthesis/` subdirectory, MUST NOT attempt to migrate or rename it, and MUST NOT special-case it. The existing cache purge MUST remove it on the same schedule as the rest of the cache entry.
- **FR-013**: The full project test suite MUST pass after this feature, with the test count reduced by the number of tests removed under FR-009 and not by any other amount. No previously-green non-`live_api` test MUST become red as a side effect of this removal.
- **FR-014**: The `pyproject.toml` (or equivalent build metadata) MUST NOT continue to ship dependencies whose only consumer was the removed legacy stage. Dependencies shared with the surviving notes path MUST remain.

### Key Entities

- **Legacy summariser subcommand**: The CLI entry point for the slide-by-slide summariser path (`notetaker synthesise`). After this feature: gone.
- **Legacy summariser module**: The package under `src/notetaker/stages/synthesis/` containing the aligner, the slide-by-slide summariser, and any internal helpers used only by them. After this feature: removed.
- **Legacy summary contract**: The data schema describing the legacy summariser's output (the per-slide and overall summary structure and its on-disk JSON shape). After this feature: removed unless reused by the notes path.
- **Notes model resolution**: The single function used by the notes feature to decide which model name to call the LLM with. After this feature: continues to exist, continues to honour an explicit `notes.model` override, but no longer falls back to a removed sibling section.
- **Existing cache `synthesis/` subdirectories**: Orphaned files left over from previous runs. After this feature: not read, not written, and removed by the existing retention purge on its normal schedule.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After this feature, `notetaker --help` lists exactly one fewer subcommand than before, and the missing one is the legacy summariser. A reader of the help text cannot tell that the legacy summariser ever existed.
- **SC-002**: After this feature, `grep -ri 'stages\.synthesis\|notetaker synthesise\|synthesis\.summary_model' src/ tests/ HOWTO.md CLAUDE.md config.toml pyproject.toml` returns zero matches.
- **SC-003**: After this feature, a user running `notetaker run <url>` against a recording that successfully completes capture/extract/understand sees a successful exit and a final printed line that names the next command to invoke. They can copy that command, supply the transcript path, and produce notes — without consulting documentation.
- **SC-004**: After this feature, a user whose existing `config.toml` still contains a `[synthesis]` section can invoke any subcommand without error and without a deprecation warning printed every run.
- **SC-005**: After this feature, the project's full non-`live_api` pytest suite passes with no skips introduced by this change. The test count is reduced by exactly the number of tests removed under FR-009.
- **SC-006**: After this feature, a user whose cache contains a legacy `synthesis/` subdirectory from a prior run can invoke any current subcommand against that cache without crash, without warning, and without attempted migration.
- **SC-007**: After this feature, the default model the notes feature uses for its LLM call (with no user override) is the same model name it used before this feature. A user who has not set `notes.model` sees no change in the model their next notes invocation calls.

## Assumptions

- The post-capture notes feature (spec 003) has shipped and is the documented happy path. Removing the legacy summariser does not require a fallback during a transition window — the transition has already happened.
- The user has accepted that `notetaker run` will no longer end with a fully-rendered summary file, because the supported notes path requires a transcript file the user supplies from their browser. The convenience trade-off is: `run` does the unattended steps, the user runs the notes step explicitly.
- The default model name used by the notes feature is preserved by lifting the existing default value from the legacy `[synthesis]` config section into the notes config section as the new bundled default. No model name change is intended by this feature.
- Existing users' `config.toml` files in the wild may still contain `[synthesis]` sections. The TOML loader's existing behaviour of silently ignoring unknown sections is sufficient — no migration script and no per-run deprecation warning is in scope.
- Existing on-disk caches with `synthesis/` subdirectories are not re-processed or migrated. The existing cache retention purge is sufficient to clean them up on its normal schedule.
- Spec history under `specs/` is preserved unchanged. The `specs/003-post-capture-notes/spec.md` document explicitly anticipates this feature and is not edited as part of this work.
- The structured-log contract changes (FR-011) are acceptable to any downstream log consumers. There is no external consumer of these logs that requires the legacy event categories to remain present as dead-but-stable values.
