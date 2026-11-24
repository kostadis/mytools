# Google Drive CLI transport implementation plan

> **Status: shelved at the user’s request.** Retained for reference; resume only on explicit request. No CLI transport implementation was deployed. The unfinished test draft is archived privately under `source-selection-data/shelved-gdrive-cli-transport/`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Execute natively; one fresh Sol final review and one correction pass. Steps use checkboxes for durable progress.

**Goal:** Run discovery, PDF reads, extraction and sibling Markdown publication through the Rust CLI with no mounted-Drive dependency.

**Architecture:** Add versioned JSON `google api` commands to `gdrive-cli`. A separate Drive coordinator in the selector uses those commands and the existing group-selection, native extraction, rendering and content-addressed caches; filesystem operation remains intact. Drive IDs/observations are explicit source metadata and backend identity, never fake filesystem inputs.

**Tech stack:** Rust 1.95+, existing reqwest/Tokio/serde, SQLite and Poppler. Add SHA-256/MD5 to the CLI for streaming verification.

**Spec:** `pdf-translators/docs/superpowers/specs/2026-11-23-gdrive-cli-transport-design.md` (approved).

## Global constraints

- Preserve existing policy, embedded-date recency, whole groups, manual holds, baselines and edited outputs.
- Preserve the two-worker resource limit, 20 GiB floor, durable checkpoints and source SHA cache identity.
- Keep production filesystem service running until both stages and pilots pass. No interim hybrid production rollout.
- All remote access is through the configured CLI; no mount fallback or selector OAuth token storage.
- Follow physical descendants only; shortcuts and unproven absences remain deferred.
- Remote writes require a separate write login and proven server-side stale-write rejection.

## Review focus

- Partial or resumed scans must not drop historical group members: task 2/4 tests changing pages, scope mismatch and missing mappings.
- A source edited between metadata/download/extraction/publication must lose eligibility: task 1/5/6 version-change tests.
- Interrupted creates must not make duplicate outputs: task 3/6 preallocated-ID and unknown-response tests.
- Concurrent manual edits must survive: task 3/6 stale ETag and adoption/conflict tests.
- A transport switch must reuse only matching SHA/engine ranges: task 4/5 migration and checksum tests.

## Task 1: Versioned CLI metadata and streaming downloads

**Files:** new `gdrive-cli/src/google/api.rs`, `gdrive-cli/tests/google_api_test.rs`; modify `gdrive-cli/{Cargo.toml,Cargo.lock,src/lib.rs,src/google/mod.rs,src/auth/google.rs}`.
**Interfaces:** `google api stat ID`, `list --parent ID [--page-token TOKEN]`, `download ID --out PATH [--expected-sha256 SHA]`; all return schema-version-1 JSON. `DriveClient` has production and injected-test HTTP endpoint constructors. Noninteractive API auth fails clearly; `authorize --write` is the explicit interactive path.

- [ ] Write HTTP-server tests for metadata/ETag fields, scope query escaping, transient retry, changed remote version, wrong length/SHA/MD5, interrupted transfer, existing output preservation and complete streaming acceptance. Run RED.
- [ ] Implement bounded retries/timeouts, streamed file hashing, temporary-file cleanup and atomic no-clobber acceptance. Keep legacy commands compatible. Serialize token refresh across processes and atomically save mode-0600 tokens.
- [ ] Run new tests and entire CLI suite, format/lint, then commit. Confirm existing CLI commands still parse.

## Task 2: Scoped, resumable inventory and coverage

**Files:** extend CLI API commands; new selector `src/markdown/drive/{mod.rs,client.rs,inventory.rs}` and `tests/markdown_drive_inventory.rs`; expose module and `markdown-drive` CLI entry.
**Interfaces:** typed `Client::stat/list/download/start_changes/changes` subprocess calls; typed `Observation`, `Inventory` and `ScanState`. Inventory persists folder frontier, page token, entries, root and change cursor in private output. `markdown-drive --gdrive-cli PATH --root-id ID --output PATH --inventory-only` produces checkpointed inventory.

- [ ] Write tests with a controlled CLI fixture for empty pages with tokens, interrupted/resumed folder traversal, root/scope mismatch, shortcuts, duplicate names, moved/deleted entries and changing scan observations. Run RED.
- [ ] Implement bounded subprocess cancellation, versioned response validation and persisted traversal. Reconcile Drive changes or conservatively refuse absence authority when stability is unproven. Log every100 files and30seconds.
- [ ] Run selector suite and commit. Live read-only root discovery and inventory evidence may be gathered without touching production state.

## Task 3: Conditional CLI publication primitives

**Files:** extend `gdrive-cli/src/google/api.rs`; new `google/write.rs` if needed; expand HTTP tests.
**Interfaces:** `generate-ids`, `upload --id ID [--parent ID --name NAME] --file PATH --mime MIME [--if-match ETAG] [--create]`, `create-folder`, and explicit `authorize --write`. Machine responses include resulting observation/ETag. Update requires a prior ETag; creates require preallocated ID.

- [ ] Write tests for conditional multipart media updates, stale412, preallocated-ID duplicate409 verification, parent preservation, metadata preservation, missing ETag refusal and response-loss recovery. Run RED.
- [ ] Implement read/write credential separation and conservative conditional-write behavior. Prove stale conditional updates against a disposable real Drive file before production API writes.
- [ ] Run CLI suite and commit; if authorization/capability blocks real writes, complete remaining private/read-only work and report the concrete prerequisite.

## Task 4: Source bridge and unchanged selection policy

**Files:** new `drive/bridge.rs`, `drive/metadata.rs`, `tests/markdown_drive_bridge.rs`; small changes to `selection.rs` for explicit remote root identity.
**Interfaces:** `bridge(legacy:&Store, inventory:&Inventory) -> Bridge` preserving source IDs, group membership, review records and baseline flags. Candidate metadata comes from verified local staged bytes. Selection uses existing `resolve_group` policy with Drive root identity.

- [ ] Write tests for unique path binding, transformed/duplicate names, changed known SHA, no-hash fresh baselines under owner confirmation, missing group competitors, holds/baselines and stable work IDs. Run RED.
- [ ] Implement durable bridge report and isolated Drive selection store. Preserve missing/ambiguous competitors as unavailable candidates. Reuse old SHA metadata/engine/page caches only after a valid content binding; no hash-specific evidence is silently upgraded.
- [ ] Run selector suite and commit. Keep all migration state outside the library and back up original state before final cutover.

## Task 5: API-only extraction and private Markdown pilot

**Files:** new `drive/runner.rs`, `drive/source.rs`, `tests/markdown_drive_conversion.rs`; small changes to `worker.rs`, `publication.rs`, `render.rs` and capacity integration.
**Interfaces:** Drive source provenance provides executable/root/file/observation bindings. `worker::stage` and `frozen_source_matches` route explicit Drive sources through the backend, retaining existing filesystem branches. Source links become Drive URLs. Driver assembles the same selection/quality artifacts and confirmed local corpus.

- [ ] Write mount-unavailable tests proving full native extraction, exact page coverage, crash resume, cached-range reuse, changed source rejection and capacity denial. Run RED.
- [ ] Implement bounded metadata/download/extraction scheduling and source authority checks; no per-range full-PDF hash and no mounted verification. Capacity IPC continues to protect actual allocation growth; two isolated workers at most.
- [ ] Run full selector suite, native-Poppler checks and a representative private live pilot using the benchmark PDFs plus copied existing checkpoints. Commit evidence/docs and code.

## Task 6: API sibling publication and recoverable journals

**Files:** new `drive/publication.rs`, `drive/state.rs`, `tests/markdown_drive_publication.rs`; coordinator integration.
**Interfaces:** publish by parent/file IDs, owned prior checksum/ETag and preallocated new IDs. Journal records intended Markdown/manifest bytes, expected observations and current selection revision before each write. Manifest is commit record; local current corpus includes confirmed entries only.

- [ ] Write tests for edited/unowned files, duplicate sibling names, receipt-based legacy adoption, crash after Markdown/before manifest, lost create response, stale source/selection, review holds and partial/unknown directory entries. Run RED.
- [ ] Implement conditional writes, idempotent recovery and preserved historical outputs with a single publisher. Do not overwrite any output without exact ownership plus enforced server precondition. Keep discovery/extraction independent of slow publication.
- [ ] Run both full suites and a disposable-folder live publication/restart/stale-edit pilot. Commit.

## Task 7: Verify, review and cut over

**Files:** operator docs; private immutable executable pair, bridge/ownership backup, pilot/deployment evidence.

- [ ] Verify complete bridge report and preserve unresolved membership. Resolve only unambiguous generated-file ownership from current receipts/bytes. Recover existing filesystem journal before stopping its sole writer.
- [ ] Run both complete suites, fmt/clippy/release builds and live pilots; collect fresh timing/cache-hit/zero-mount evidence. Commit.
- [ ] Request one fresh Sol final review of this change range and plan. Fix important findings once using RED→GREEN tests; rerun both suites. Record any rulings/minors.
- [ ] Deploy immutable CLI/selector pair under user service only after all prerequisites pass. Preserve databases/checkpoints/receipts and confirm sustained extraction/publication past prior failure point. No push/merge requested.

## Execution record

The user approved the design and said “let's do it”; native execution continues under the established session preference without another method-selection prompt. Implementation ledger belongs to this plan's ignored `.superpowers` workspace; copy final evidence into private runtime records before cleanup.
