# Independent Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task.

**Goal:** Remove source publication and manifest discovery from the coordinator's resolution/dispatch loop.

**Architecture:** One publication thread owns the existing Session and source journals, communicating through nonblocking request/result channels. The coordinator retains sole ledger/reservation ownership and ignores superseded results; a bounded read-only discovery thread reports its final directory set.

**Tech Stack:** Rust std threads/channels, existing SQLite and filesystem safeguards.

**Spec:** ../specs/2026-11-23-independent-publication-design.md

## Global Constraints

- Existing metadata process and two extraction workers; one source publisher.
- Preserve fresh authority gates, frozen graph, complete groups, semantic revisions and manual outputs.
- Keep 20 GiB local floor and reservations until all consumers finish.
- Continue the live rollout while implementing; preserve all caches and outputs on replacement.

## Review Focus

- Coalesced and late responses must never restore stale authority or strand reservations.
- Publisher failure/shutdown cannot leave an overlapping source writer or report success.
- Confirmed holds invalidate current search while publication is busy.
- Completion must wait for publication and final reconciliation, including empty/held groups.
- Read-only discovery cannot become a new coordinator I/O barrier.

### Task 1: Asynchronous publisher and discovery with coordinator integration

**Files:** Create src/markdown/continuous_publication.rs; modify src/markdown/{continuous,mod}.rs; tests/markdown_continuous.rs.
**Interfaces:** nonblocking publication submit/poll, sequenced outcomes (published, superseded, reconciled), single worker-owned Session; discovery result via channel. Coordinator owns durable updates and reservations.

- [ ] Write gated publication integration test: all six cached groups resolve and six extraction jobs finish while source publication remains blocked; coordinator stays running. Watch RED.
- [ ] Implement worker/request coalescing, parent ingestion and durable scheduling; move discovery off the loop; reconcile through the publisher.
- [ ] Add queued-hold and publisher-failure tests; retain short authority gates and source ownership.
- [ ] Run full locked Rust suite, fmt, strict Clippy and release build; commit.

### Task 2: Review, pilot and controlled live replacement

**Files:** Update operator/pilot documentation and private deployment records.
**Interfaces:** Existing cached library inventory/output and source manifests.

- [ ] One fresh Sol review of this change, one tested correction pass, no re-review.
- [ ] Pilot the gated publisher and verify unchanged source PDF hashes and earlier Markdown stability.
- [ ] Replace the live coordinator safely; confirm resolved groups advance independently while publication runs; record status and logs.
- [ ] Commit documentation and leave the running rollout and branch in place.
