# Continuous Markdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Publish selected library Markdown while metadata checking continues, retaining durable progress and conservative selection authority.

**Architecture:** A native coordinator resolves complete groups from cached or isolated metadata requests, schedules two existing extraction workers, and publishes scoped group revisions. SQLite records group decisions and queue state atomically; scoped source records preserve unresolved neighbors.

**Tech Stack:** Rust, existing SQLite/serde/Poppler/filesystem contracts; no new runtime service.

**Spec:** ../specs/2026-11-23-continuous-markdown-design.md

## Global Constraints

- One metadata process, two extraction workers, 300-second metadata deadline, 20-page chunks.
- Local free floor 20 GiB, per-job reservations, destination capacity checked separately.
- Entire frozen groups, internal dates, existing review and baseline policy; no OCR or 5etools.
- Preserve existing caches, PDFs, edited/unowned outputs and uncertain historical lineage.
- Per-group semantic revisions exclude incidental observations and unrelated inventory changes.
- Review writers and final source/current-pointer commits share the main-store authority gate.
- Continuous manifests use schema 2 and explicit local coverage; legacy batch semantics remain unchanged.

## Review Focus

- Unknown prior manifest lineage remains unverified until its exact source coverage proves retirement (task 2).
- Review changes during extraction cannot restore revoked current search (task 3).
- Late metadata results and known-byte changes cannot select against the old graph (task 3).
- Concurrent reservations cannot spend the same free space; no-fit exits are retryable (task 3).
- Cache bootstrap and manifest discovery must not delay the first cached group's publication (tasks 2–4).

### Task 1: Shared complete-group resolver and metadata cache interface

**Files:** Modify src/markdown/selection.rs, metadata.rs and store.rs; test tests/markdown_continuous.rs.
**Interfaces:** `selection::resolve_group(store, output, root, group, candidates, provenance) -> Result<Snapshot>` returns one complete-group resolution; `metadata::cached(...) -> Result<Option<Candidate>>` performs no PDF-content reads. Shared authority gate on Store.

- [ ] Write tests comparing batch/group resolution, incomplete-group refusal, same-byte observation stability and cached lookup without content reads.
- [ ] Run `cargo test --test markdown_continuous`; observe missing-interface failures.
- [ ] Extract existing policy, implement cache lookup and semantic revision, gate supported authority mutations.
- [ ] Run `cargo test --locked`; expect all tests passing; commit task.

### Task 2: Scoped incremental publication

**Files:** Modify src/markdown/{publication,render}.rs and adjacent/mod.rs; test tests/markdown_continuous.rs.
**Interfaces:** `Session::new_scoped` avoids tree discovery; scoped snapshots distinguish complete groups from pending groups. Publication accepts explicit authority snapshot and own-work revisions.

- [ ] Add tests for mixed-directory groups, holds, unsupported manifests, unchanged bytes across unrelated groups/runs, and empty revoked current view.
- [ ] Run focused tests and observe expected assertions fail.
- [ ] Implement schema-2 scoped merge, safe retirement and lazy discovery; preserve legacy full snapshots.
- [ ] Run `cargo test --locked`; expect all tests passing; commit task.

### Task 3: Durable continuous coordinator and bounded workers

**Files:** Create src/markdown/continuous.rs and capacity.rs; modify cli.rs, conversion.rs, worker.rs and markdown/mod.rs; test tests/markdown_continuous.rs.
**Interfaces:** `continuous::run(work, Options) -> Result<Status>` owns rollout/conversion locks, metadata requests and durable group/job ledger; hidden metadata worker writes only byte caches. CLI `markdown-continuous` supports explicit retry and timeout options.

- [ ] Add subprocess tests: gated uncached metadata while cached group actually publishes; partial groups; crash/resume; review revocation; metadata timeout; source-byte change versus unchanged-hash fingerprint change; fit/no-fit reservations.
- [ ] Run focused tests; expect unknown command/failing behavioral assertions.
- [ ] Implement cache-first dynamic scheduler, group transactions, source/authority reconciliation, reservations and durable distinct statuses with 100-item/30-second logging.
- [ ] Run `cargo test --locked`; expect all tests passing; commit task.

### Task 4: Pilot, final review and live transition

**Files:** Update docs/searchable-markdown.md and deployment/pilot documentation; retain private deployment records.
**Interfaces:** Existing four-document pilot and production metadata.db/extraction caches; immutable deployed binary.

- [ ] Run four-book plus delayed-metadata pilot, confirm first sibling publication precedes metadata completion and all original PDF hashes remain unchanged.
- [ ] Run fmt, strict Clippy, full locked suite, Poppler and mounted-filesystem checks, locked release build.
- [ ] Request one fresh Sol final review; address important findings in one tested correction pass.
- [ ] Stop old controller first, then metadata producer; verify released locks and preserve SQLite/WAL; start new coordinator using existing inventory/cache output.
- [ ] Confirm real library sibling Markdown publication alongside pending metadata; document command/log/status paths and commit code/docs.
