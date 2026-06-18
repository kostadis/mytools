<!--
SYNC IMPACT REPORT
==================
Version change: 1.0.0 → 1.1.0
Bump type: MINOR (renames within existing principles; no principle added,
removed, or backward-incompatibly redefined)

Modified principles:
  - I.1 Stage Isolation — fourth stage renamed Synthesis → Notes.
  - I.3 Versioned Data Contracts — example list shrinks: Aligned Segment
    and Final Summary removed (schemas deleted by spec 004).
  - I.4 Re-runnability — example "Synthesis run" rephrased to "fourth-stage
    (Notes) run" to match the rename.
  - VIII.1 Phased Delivery — fourth phase renamed Synthesis → Notes.

Added sections: None.
Removed sections: None.

Templates reviewed:
  ✅ .specify/templates/plan-template.md — no synthesis-named references.
  ✅ .specify/templates/spec-template.md — no synthesis-named references.
  ✅ .specify/templates/tasks-template.md — no synthesis-named references.

Migration plan: spec 004 (specs/004-remove-synthesise-stage/). The codebase
deletion of the legacy slide-by-slide summariser lands in the same change
set as this amendment, so no version of the repo exists in which the
constitution names artifacts the code does not have.

Deferred items: None.
Follow-up TODOs: None.

----- Prior amendment -----

Version change: (none — initial population) → 1.0.0
Bump type: MINOR (new complete constitution replacing blank template)

Modified principles: N/A — first-time population from blank template
Added sections: All 9 Articles (I through IX) derived from user input
Removed sections: None (template placeholders replaced in full)

Templates reviewed:
  ✅ .specify/templates/plan-template.md
     — Constitution Check gate at line 31 is a per-feature placeholder; no
       update needed. Gates should reference Articles I–IX when filled.
  ✅ .specify/templates/spec-template.md
     — No constitution references; II.1 (spec vs. plan separation) already
       aligns with the spec-only scope of spec-template.md.
  ✅ .specify/templates/tasks-template.md
     — Phased structure (Phase 1 → Phase N) aligns with Article VIII.1
       (Phased Delivery). No changes required.
  ✅ .specify/templates/commands/ — directory not present; N/A.

Deferred items: None. All placeholders resolved.
Follow-up TODOs: None.
-->

# Meeting Recording Slide Extractor Constitution

## Preamble

This constitution governs all specifications, plans, and implementations for
the Meeting Recording Slide Extractor project. These principles are
non-negotiable. When a spec, plan, or task conflicts with the constitution,
the constitution wins and the artifact MUST be revised.

## Article I — Architectural Principles

### I.1 Stage Isolation (NON-NEGOTIABLE)

The pipeline consists of four stages: Capture, Slide Extraction, Slide
Understanding, and Notes. Each stage MUST be independently runnable,
independently testable, and independently replaceable. No stage may import
implementation details from another stage; stages communicate only through
documented data contracts.

### I.2 Platform Adapters Are Isolated

Platform-specific logic (Zoom, Gong, Chorus, etc.) lives only in capture
adapters. Once data leaves the Capture stage, no downstream code may contain
platform-specific branches. Adding a new platform MUST require changes only in
the adapter layer.

### I.3 Data Contracts Are Versioned

The contracts between stages (Transcript, Slide Timeline, Slide Content) are
versioned schemas. Breaking changes require a version bump and a documented
migration path. Stages MUST validate inputs against the contract before
processing.

### I.4 Re-runnability

Every stage MUST be re-runnable from cached intermediate artifacts without
re-executing expensive earlier stages. A failed fourth-stage (Notes) run MUST
NOT require re-capturing the video.

## Article II — Documentation Discipline

### II.1 Separation of Concerns (NON-NEGOTIABLE)

- `spec.md` describes WHAT and WHY. It MUST remain technology-agnostic. No
  frameworks, libraries, or implementation patterns. Audience: product and
  domain stakeholders.
- `plan.md` describes HOW. All technical decisions, framework choices, and
  architectural patterns live here. Audience: implementers.

Mixing these is grounds for rejecting the artifact.

### II.2 Every Stage Documents Its Contract

Each stage's spec MUST explicitly declare its input contract, output contract,
side effects, and failure modes. "Obvious" contracts still get written down.

## Article III — Cost and Resource Discipline

### III.1 Vision LLM Calls Are Expensive — Treat Them As Such

Vision model calls on slide images MUST be cached by content hash (perceptual
or cryptographic, as appropriate). The same slide image MUST NEVER be sent to
a vision model twice across runs. Cache invalidation rules MUST be explicit.

### III.2 Cost Controls Are First-Class

Every feature that consumes paid API calls MUST support a budget ceiling and a
degraded-mode fallback (e.g., OCR-only mode when vision LLM budget is
exhausted). Cost MUST be observable per run.

### III.3 No Hidden Real-Time Capture Without Consent

Screen-capture sessions MUST be initiated by explicit user action and MUST
surface clearly that capture is in progress. No silent recording.

## Article IV — Configuration and Tunability

### IV.1 No Magic Numbers

Thresholds, sample rates, model identifiers, retry counts, timeouts, and
similar tunables MUST live in configuration, not in code. Code MUST read them
by name, not by hardcoded literal.

### IV.2 Sensible Defaults

Default configuration MUST work end-to-end on a typical Zoom Cloud Recording
without modification. The user's first run should succeed; tuning should be
optional.

### IV.3 Configuration Is Documented

Every configurable parameter MUST have an inline description, a default value,
and a stated effect on output. Undocumented config is treated as a bug.

## Article V — Observability

### V.1 Every Stage Logs Its Decisions

Each stage MUST log inputs received, outputs produced, key decisions made
(e.g., "merged 3 frames as duplicates of slide 7"), elapsed time, and resource
cost. Logs are structured, not free text.

### V.2 Debug Mode Preserves Intermediates

A debug flag MUST cause each stage to preserve all intermediate artifacts
(extracted frames, OCR output, raw vision LLM responses, alignment tables) on
disk for inspection. Production mode may discard them.

### V.3 Failures Are Diagnosable Without Re-running

A failed run's logs and preserved artifacts MUST be sufficient to diagnose the
failure without re-executing the pipeline.

## Article VI — Security and Privacy

### VI.1 Credentials Are Never Logged or Persisted in Plain Text

Authentication cookies, session tokens, and API keys MUST be handled through a
secrets mechanism. They MUST NOT appear in logs, error messages, or committed
files. Test fixtures use redacted or synthetic credentials.

### VI.2 Captured Content Has a Retention Policy

Captured videos, frames, and transcripts are sensitive corporate content. The
system MUST have an explicit retention policy with automatic cleanup. Indefinite
retention is forbidden by default.

### VI.3 Scope to User-Entitled Content

The system operates on recordings the user is entitled to access. The pipeline
MUST NOT attempt to bypass authentication, DRM, or platform access controls.
When a recording cannot be accessed through normal user credentials, the
pipeline fails clearly rather than escalating.

## Article VII — Testing Discipline

### VII.1 Stage-Level Tests Are Required

Each stage MUST have tests that verify its contract: given valid input X,
produces valid output Y. Stages cannot be merged without these.

### VII.2 Golden Fixtures for the Full Pipeline

At least one end-to-end fixture (a known recording with known expected slides
and summary structure) MUST exist and pass. Adding platforms or major features
requires a new golden fixture.

### VII.3 Cost-Sensitive Tests Are Mocked by Default

Tests MUST NOT call paid APIs in the default test run. Live API tests are
opt-in via a separate marker and run on demand.

## Article VIII — Workflow

### VIII.1 Phased Delivery

The four stages are delivered in phase order: Capture → Extraction →
Understanding → Notes. Each phase MUST produce user-visible value on its
own. Phase 1 (Capture) alone must yield clean transcripts even before slide
extraction exists.

### VIII.2 Task-Sized Commits

Each completed task gets its own commit with a structured message referencing
the task ID and the spec it implements. Large grab-bag commits are rejected in
review.

### VIII.3 Spec Drift Is Reconciled, Not Ignored

When implementation diverges from the spec, the spec MUST be updated in the
same change, or the implementation MUST be brought back in line. Silent drift
is forbidden.

## Governance

### IX.1 Constitution Supersedes Other Practices

When this constitution conflicts with team habit, tooling defaults, or
convenience, the constitution wins.

### IX.2 Amendments Require Documentation

Changing this constitution requires (a) a written rationale, (b) an assessment
of impact on existing specs and code, and (c) a migration plan for any
artifacts the amendment invalidates. Version MUST be incremented per semantic
versioning: MAJOR for backward-incompatible removals or redefinitions; MINOR
for new principles or materially expanded guidance; PATCH for clarifications
and wording fixes.

### IX.3 Reviews Verify Constitutional Compliance

Every spec, plan, and PR review MUST explicitly confirm compliance with the
relevant articles. "Looks good" is not a sufficient review.

**Version**: 1.1.0 | **Ratified**: 2026-05-08 | **Last Amended**: 2026-05-09
