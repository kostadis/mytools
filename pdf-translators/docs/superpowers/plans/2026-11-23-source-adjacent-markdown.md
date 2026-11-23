# Source-adjacent Markdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Native execution continues as already chosen, with one fresh final Sol review.

**Goal:** Publish selected, nonempty Markdown beside its PDF with a recoverable per-directory current-document record.

**Architecture:** Extend coordinator publication with an explicit adjacent destination. Reuse native extraction/completion caches. Keep private ownership receipts and interrupted-publication intents outside the library; directory manifests commit current membership, and the local current corpus mirrors confirmed publications.

**Tech Stack:** existing Rust 1.95+, serde/json, SQLite, SHA-256 and Poppler; no new external service or model calls for conversion.

**Spec:** `../specs/2026-11-23-source-adjacent-markdown-design.md`, approved by “go”.

## Global Constraints

- `PDF-stem.md` beside the selected PDF; `current-documents.json` in each affected directory, supporting multiple works.
- Include source link/hash, work/source and selection identity, stable extraction time when known, converter/quality provenance and all physical pages.
- All nonempty complete extraction publishes; no OCR, history database, archives, or 5etools work.
- Private caches remain outside the source tree; PDFs and unowned/edited outputs are preserved.
- Assume Drive available. Single integrated command, two workers and 20-page ranges by default; no interactive per-file approval.
- Reconcile full latest snapshot despite bounded extraction batches. Never upgrade uncertain missing works to obsolete under incomplete coverage.
- Per-directory commits are atomic; multi-directory updates and Drive synchronization are not global transactions.

## Review Focus

1. A replaced/edited Markdown or redirected destination must never be overwritten merely because its filename matches.
2. A crash after Markdown rename but before manifest replacement must recover without fresh extraction, including A-to-B-to-A selection.
3. Empty directories and incomplete discovery must not leave an obsolete record falsely current or erase uncertain works.
4. Late jobs, changed PDFs and destination collisions must not enter the current view, while good independent directories publish.
5. Identical reruns must preserve bytes/timestamps; policy-only updates must refresh provenance from cached pages, including unusual Unix filenames.

### Task 1: Directory publication and recovery contract

**Files:** create `source-selector/src/markdown/adjacent/{mod,files,state}.rs`, `source-selector/tests/markdown_adjacent.rs`; extend `markdown/mod.rs`.

**Interfaces:** `adjacent::Session::new(output: &Path, snapshot: &Snapshot) -> Result<Session>` discovers manifests; `Session::sync(snapshot: &Snapshot, engine: &Engine, books: &[Book]) -> AdjacentReport`; `Book { ready: Ready, markdown: String, metadata: Value }`. `AdjacentReport` contains published work IDs, statuses/errors and reconciliation completeness. Private receipts/intents bind root identity, byte-safe path and checksum. Test helpers construct frozen selections from real fixture scans and completion caches.

- [ ] Write/run failing CLI tests for sibling Markdown and source links, several works per manifest, current-only publication and default local-only compatibility. Expected failure: new CLI option unrecognized.
- [ ] Write/run failing behavior tests for manual/edited files, invalid/foreign manifests and symlink destinations; expect preserved bytes, output conflicts and successful independent works.
- [ ] Implement byte-safe directory discovery/path validation, per-directory locks, owned record validation, durable receipts/intents and checksum-guarded atomic commits.
- [ ] Write/run recovery tests for pending intent after Markdown rename, A→B→A, lost private state and emptied-directory discovery; implement safe resume/reconciliation.
- [ ] Write/run coverage tests: unknown disappearance stays partial and previous entry keeps old selection authority; complete coverage retires managed entries without deleting files.
- [ ] Verify with `cargo test --test markdown_adjacent`; expected all relevant tests pass after CLI integration in Task 2. Commit the buildable integrated unit with Task 2 if declarations require both.

### Task 2: Rendering, coordinator integration and current mirror

**Files:** create `source-selector/src/markdown/render.rs`; modify `markdown/{publication,conversion,worker,selection}.rs`; extend new integration tests.

**Interfaces:** shared renderer returns target-specific Markdown with source links. Completion metadata carries optional stable `extracted_at` while preserving old checksum compatibility. `publication::publish_with_destination(output, engine, Option<&mut adjacent::Session>) -> Result<Publication>` wraps existing local-only publication. `Options.publish_next_to_source: bool` defaults false. Publication reports expose adjacent outcomes and only confirmed adjacent work enters that mode’s local current corpus.

- [ ] Add `--publish-next-to-source` and coordinator-owned session; reconcile before conversion and after completions, under latest selection lock. Expected new basic CLI tests GREEN, old tests unchanged.
- [ ] Add tests for zero-text/failed/sparse output, full-snapshot bounded batching, changed source, late worker, same-target collisions and byte-safe filenames. Expected only verified nonempty latest selections publish.
- [ ] Add tests for unchanged repeat and policy-only refresh: file mtimes remain unchanged on identical render; new snapshot changes metadata without new PDF extraction.
- [ ] Keep conversion/private-output guards intact. Add 100-item progress summaries and 30-second heartbeat for metadata/discovery/reconciliation work.
- [ ] Run full `cargo test`, explicit installed Poppler test, fmt and strict Clippy. Expected no regressions. Commit implementation.

### Task 3: Review, operator workflow and four-document verification

**Files:** update `docs/searchable-markdown.md`; create `docs/source-adjacent-markdown-pilot.md` and ignored private pilot evidence.

- [ ] Request one fresh read-only Sol review of this implementation against the spec and focus list; fix Critical/Important findings once using RED→GREEN regressions and the full suite.
- [ ] Build locked release. Publish beside the four staged pilot PDFs using the existing completed pilot state/cache, retaining original-library provenance. Verify four directory records, four sibling documents, 61 physical headings, links and source/output checksums.
- [ ] Repeat command and prove zero new extraction and unchanged destination bytes/mtimes. Rehash all staged PDF inputs to prove preservation. No full-library conversion is started.
- [ ] Document command, manifest/ownership/conflict/recovery behavior and measured pilot results. Commit verified changes on the current branch; preserve the active worktree.

## Execution ledger

Native execution is preserved from the existing session. The approved design and “go” authorize this implementation and staged pilot; no additional plan-approval stop is introduced.
