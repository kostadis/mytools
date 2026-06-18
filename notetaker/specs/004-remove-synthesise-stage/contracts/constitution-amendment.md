# Contract: Constitution Amendment (v1.0.0 → v1.1.0)

This feature requires a coordinated amendment to
`.specify/memory/constitution.md` so the constitution does not name
artifacts the codebase no longer contains. Per Article IX.2, an amendment
requires (a) written rationale, (b) impact assessment, (c) migration plan.
This document provides all three; the amendment lands in the same change
set as the code deletion.

## Version bump

`1.0.0 → 1.1.0` (MINOR).

**Why MINOR**:
- No principle is removed.
- No principle is backward-incompatibly redefined.
- The names of one of four stages and two of five named example contracts
  change. The principles those names appear in (Stage Isolation, Versioned
  Contracts, Phased Delivery) survive verbatim.

**Why not MAJOR**: IX.2's MAJOR criterion is "backward-incompatible
removals or redefinitions of principles". No principle is removed or
redefined. The list of named contracts in I.3 is illustrative
("(Transcript, Slide Timeline, ...)"), not normative.

**Why not PATCH**: PATCH is "clarifications and wording fixes". One stage
name and two contract names change in normative-adjacent text. That is
more than a wording fix.

## Diff

### Article I.1 — Stage Isolation

**Before**:
> The pipeline consists of four stages: Capture, Slide Extraction, Slide
> Understanding, and Synthesis. Each stage MUST be independently
> runnable, independently testable, and independently replaceable. No
> stage may import implementation details from another stage; stages
> communicate only through documented data contracts.

**After**:
> The pipeline consists of four stages: Capture, Slide Extraction, Slide
> Understanding, and Notes. Each stage MUST be independently
> runnable, independently testable, and independently replaceable. No
> stage may import implementation details from another stage; stages
> communicate only through documented data contracts.

### Article I.3 — Data Contracts Are Versioned

**Before**:
> The contracts between stages (Transcript, Slide Timeline, Slide
> Content, Aligned Segment, Final Summary) are versioned schemas.
> Breaking changes require a version bump and a documented migration
> path. Stages MUST validate inputs against the contract before
> processing.

**After**:
> The contracts between stages (Transcript, Slide Timeline, Slide
> Content) are versioned schemas. Breaking changes require a version
> bump and a documented migration path. Stages MUST validate inputs
> against the contract before processing.

(Aligned Segment and Final Summary are removed from the example list
because the schemas they refer to are deleted by spec 004 — neither is
a contract crossing stage boundaries any more.)

### Article VIII.1 — Phased Delivery

**Before**:
> The four stages are delivered in phase order: Capture → Extraction →
> Understanding → Synthesis. Each phase MUST produce user-visible value
> on its own. Phase 1 (Capture) alone must yield clean transcripts even
> before slide extraction exists.

**After**:
> The four stages are delivered in phase order: Capture → Extraction →
> Understanding → Notes. Each phase MUST produce user-visible value on
> its own. Phase 1 (Capture) alone must yield clean transcripts even
> before slide extraction exists.

### SYNC IMPACT REPORT (header comment)

Append a new entry above the existing one:

```text
Version change: 1.0.0 → 1.1.0
Bump type: MINOR (renames within existing principles; no principle added,
removed, or backward-incompatibly redefined)

Modified principles:
  - I.1 Stage Isolation — fourth stage renamed Synthesis → Notes.
  - I.3 Versioned Data Contracts — example list shrinks: Aligned Segment
    and Final Summary removed (schemas deleted by spec 004).
  - VIII.1 Phased Delivery — fourth phase renamed Synthesis → Notes.

Added sections: None.
Removed sections: None.

Templates reviewed:
  ✅ .specify/templates/plan-template.md — no synthesis-named references.
  ✅ .specify/templates/spec-template.md — no synthesis-named references.
  ✅ .specify/templates/tasks-template.md — no synthesis-named references.

Migration plan: spec 004 (this feature). The codebase deletion lands in
the same change set as this amendment, so no version of the repo exists
in which the constitution and the code disagree.

Deferred items: None.
Follow-up TODOs: None.
```

## Impact assessment

- **Existing specs**:
  - `specs/001-slide-extractor/spec.md` — references the four-stage
    pipeline by name. NOT edited (spec history preserved per the spec's
    own Assumption section).
  - `specs/002-observability-logging/spec.md` — may reference
    `Stage.SYNTHESISE`. NOT edited (spec history preserved).
  - `specs/003-post-capture-notes/spec.md` — explicitly anticipates this
    feature ("A subsequent feature may decide to remove the old
    synthesis stage"). NOT edited.
- **Existing code**: covered by the rest of this plan.
- **Existing tests**: covered by the rest of this plan.
- **External tooling**: none documented.

## Migration plan

Spec 004 IS the migration. The amendment is a deliverable in this
feature's task list (Phase 2), to be applied in the same commit (or
adjacent commits) as the code deletion. After this feature lands, no
version of the repo exists in which the constitution names artifacts the
code does not have.

## Verification

Post-implementation, the following must all be true:

- `.specify/memory/constitution.md` line containing `**Version**:` reads
  `**Version**: 1.1.0`.
- `grep -i 'Synthesis\|Aligned Segment\|Final Summary' .specify/memory/constitution.md`
  returns only matches in the SYNC IMPACT REPORT (which records the
  rename) — no matches in the normative article text.
- The SYNC IMPACT REPORT comment contains the new entry above.
