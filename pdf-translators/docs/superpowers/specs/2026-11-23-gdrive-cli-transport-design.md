# Google Drive CLI transport for searchable Markdown

> **Status: shelved at the user’s request.** Retained for reference; resume only on explicit request. No CLI transport implementation was deployed. The unfinished test draft is archived privately under `source-selection-data/shelved-gdrive-cli-transport/`.

## Intent and agreed direction

Use the existing, compiled and authorized Rust `gdrive-cli` as the Drive adapter for the Rust source selector. The user wants to remove as much mounted-drive dependence as possible. The destination remains searchable Markdown beside each selected PDF, plus a per-directory `current-documents.json`; 5etools remains deferred. Implement in two stages: PDF discovery/reads first, API publication second. This document covers both stages; each has an independent delivery and pilot.

The current continuous converter stays running during development and stage-one private pilots. Make the production cutover only after stage-two API publication passes verification, retaining private databases, cached PDF bytes, extracted ranges, source-selection decisions and ownership history. Do not add an interim hybrid production publisher or replace sibling publication with a local-only production sink. This rollout order is the designer's call, preserving continuous sibling Markdown while avoiding a temporary integration. The data lives in the same Google library, as confirmed by the user after the mount changed inode identities.

## Evidence

The authorized release CLI passed a read-only root request. Its `google cat FILE_ID --out PATH` downloads PDFs through Drive's media endpoint. A three-file benchmark verified SHA-256 equality with mounted copies and matched Drive MD5 checksums:

| Size | Mounted copy | CLI download |
| --- | --- | --- |
| 2.0 MiB | 0.072 s | 1.429 s |
| 49.0 MiB | 1.676 s | 4.704 s |
| 159.7 MiB | 5.382 s | 2.912 s |

The mounted path may benefit from host/OS caches; the production converter was running. These numbers establish feasibility, not a general speedup. Private evidence is under `source-selection-data/gdrive-download-benchmark/`. The metadata scan was intentionally stopped after collecting sufficient benchmark candidates and is not a complete inventory.

Today the CLI downloads whole responses into memory, its scan is not folder-scoped/checkpointed, `get` exposes only minimal metadata, and it cannot upload Markdown. Its existing read-only token does not authorize publication; use its separate write-token flow when stage two is ready.

## Approaches

1. **Extend the CLI and call it as a subprocess. Chosen by the user.** Reuse working authentication, independently test Drive commands, and keep credentials out of selector state. Requires stable JSON contracts and bounded child execution.
2. Extract a shared Rust Drive client and link both programs. Avoids subprocess boundaries but introduces a larger refactor and couples the two projects. Deferred.

A complete local mirror is unnecessary: the library is roughly 312 GiB and the selector already has a bounded, content-addressed extraction cache.

## Requirements

- All product code remains Rust. Poppler remains the text extraction engine; no OCR or LLM calls.
- Stable Drive root/file/parent IDs replace mount device/inode observations for remote operations. Human paths remain display/search provenance.
- Preserve whole-group duplicate/version decisions, exact aliases, baseline protections and User/Sol decisions. Recency uses embedded PDF metadata, never Drive timestamps or revision numbers.
- Reuse existing verified PDF/page/engine caches by SHA-256. Do not re-extract a PDF merely because its transport changed.
- Native extracted text and physical-page provenance retain existing publication policy. Keep manual/foreign/edited outputs and historical Markdown.
- Keep bounded concurrency, a 20 GiB local free-space floor, atomic checkpoints, durable receipts/journals, logging every 100 files and 30-second heartbeats.
- No PDF modifications, deletions, moves, public sharing, or new search database.
- Filesystem mode remains supported explicitly. Drive mode must never silently fall back to the mount, even for verification or discovery.

## Stage one: Drive discovery and PDF reads

### CLI boundary

Add scoped, restartable Drive listing and richer file metadata to `gdrive-cli`. Preserve existing command behavior; add flags/subcommands rather than silently replacing output formats. Machine output includes a schema version; operational progress/errors use stderr. The selector calls an explicitly configured executable path with argument arrays, timeouts and cancellation. Never expose OAuth tokens in arguments, logs or state.

Inventory a configured Drive folder ID and its physical descendants. Persist pagination/frontier progress; mark traversal complete only after every page/subfolder succeeds. Empty pages with a continuation token do not end a scan. Exclude trashed entries. Include shared-drive support and required resource keys. For this initial release, record shortcuts and their supplied target metadata as deferred coverage; do not follow them inside or outside the configured root. Reject a shortcut as the configured root until it is explicitly resolved. This is the designer's call, keeping scope consistent with the prior filesystem inventory and avoiding external targets/ambiguous publication parents. Treat ambiguous paths and incomplete scopes as unresolved coverage, not absent files or automatic winners; a deferred shortcut does not authorize decisions about its target.

Required file observations include ID, parent ID, raw name, MIME type, size, checksums when available, Drive version/change observations, and download capability. Version/time fields detect changes; they do not rank editions. Store identity and observations separately from display paths. Rename/move with unchanged PDF bytes should preserve extraction caches and work identity where already established; changed parent/name triggers grouping reconciliation when necessary.

Stream downloads into a unique local temporary file while calculating SHA-256 and checking expected size. Atomically accept only a complete matching download. Check observed remote identity/version/checksum before and after transfer; retry a concurrent remote change as a changed observation, never label mixed/unbound bytes successful. If the frozen queue has an expected SHA-256, it must match. No extra mounted-file reads or per-range PDF hashes. Interrupted downloads can restart; HTTP-range resumption is optional and must bind to the same remote version if implemented.

Retry transient network errors and rate limits with bounded backoff; preserve terminal authentication/access/not-found outcomes distinctly. Refresh tokens safely when parallel CLI children start together; avoid concurrent token-file truncation. A timed-out child cannot leave a complete-looking cache file.

### Existing library bridge

Resolve the actual DriveThru root folder, save its ID, and produce an explicit mapping between existing source IDs and Drive IDs. Parent hierarchy and raw names narrow candidates; handle names transformed by Windows/mounted filesystem rules explicitly, never guess when several IDs fit. Size/MD5 can narrow matches; accepted content bindings must be grounded in the existing SHA-256 or owner-confirmed migration evidence. Download uncertain candidates into the same bounded cache and compare SHA-256. Do not drop unmatched historical candidates to make a group resolvable.

Keep a durable mapping table and migration report (matched, ambiguous, missing, inaccessible, content-changed). Preserve current source/work IDs for confidently matched records so existing decisions and ownership still apply. For a historical source with no prior SHA-256, a unique full-hierarchy/raw-name match plus matching size and the owner's unchanged-library confirmation may establish identity continuity; label its first verified remote SHA as a fresh baseline, not proof of equality with unknown historical bytes. This is the designer's migration policy and introduces no additional legacy mounted-file read. If the hierarchy/name translation is ambiguous or size differs, defer the bridge. Preserve holds/baseline flags and revalidate byte-bound evidence before granting authority; never reuse extracted text without a matching actual SHA. New remote files receive stable IDs rooted in the Drive root/file IDs.

Complete remote coverage is required before treating any missing member as absent. A successful traversal alone is insufficient if the namespace changed during it. The builder must verify a scoped change-cursor reconciliation strategy, or conservatively retain affected prior membership as pending when coverage cannot be established. Persist scan/cursor progress with the relevant Drive root and observations; a resumed scan must not erase old candidates on an unproven absence. A Drive-only run can continue resolution/extraction without `/mnt/g`; source access is routed through an explicit backend boundary rather than paths disguised as remote URLs.

Embedded metadata is parsed from the verified local PDF and cached by SHA-256. Resolve groups with the same policy as filesystem mode. Source change/review checks and publication eligibility use remote observations in Drive mode. Existing worker leases and resource reservations still cover staging plus extraction.

### Delivery and pilot

First produce private searchable Markdown with API-only discovery, validation and reads. Use an isolated local publication sink and private state for the pilot; it must not start a second writer in the live output namespace or beside source PDFs. Validate representative large/multicolumn PDFs, duplicate names/aliases, interrupted downloads, remote source changes, ambiguous mappings and recovery with the mount unavailable. Demonstrate reuse of copied/read-only existing extraction ranges and report fresh extraction separately from cache validation. Freeze a complete bridge report before the final full-library cutover, which follows stage-two verification. The live filesystem service continues during this stage.

## Stage two: publish through the CLI

Add commands to create binary Markdown/JSON files in an explicit parent ID and update owned files by ID. Upload ordinary `.md` and `.json` blobs, not native Google Docs. Markdown contains a Drive PDF link and source ID/SHA provenance. Keep PDF-stem naming and the directory record's existing multiple-work/pending/conflict semantics; add versioned remote identity fields without invalidating existing records.

Discover sibling files by parent ID. Duplicate same-name outputs are a conflict until exact ownership is established. Adopt existing generated Markdown/records only through matching receipts/checksums and unambiguous IDs. A filename or app property alone does not prove that current bytes are owned. Keep generated output IDs, checksums, remote observations and operation nonces in durable local receipts; app-private properties may provide recovery hints.

Publication revalidates selection and the remote source observation. An unchanged, already verified remote version can reuse its SHA binding. If source bytes changed, withdraw eligibility through the existing policy rather than publishing stale content. Changes/holds must supersede queued publication work just as they do today.

Write Markdown first and the directory record last as the commit record. A journal records intended IDs, expected prior bytes/versions and new checksums before remote writes. Use pre-generated file IDs for creates so a lost response/retry cannot create duplicates. Verify a conflict response against the journaled ID and desired content; never assume it means success. The API does not provide an atomic transaction spanning Markdown plus directory record: recovery completes or reports partial publication, and the local current-search view includes only confirmed committed entries.

Owned-file updates must use an enforced server-side conditional write that refuses stale observations. Verify the exact supported ETag/conditional-update behavior with a disposable-file pilot before enabling production updates; do not substitute an unprotected read-then-write check. If the transport cannot enforce this, keep affected existing outputs as conflicts and return to the design before offering automatic replacement. This technical capability check is a stage-two prerequisite, not an assumption about the API. Manual edits between reading and writing must survive.

Keep the current single publication owner and durable operation leases. Cut over only after the filesystem publisher has stopped and no active source-directory operation remains unrecovered. Recover the existing ownership journal before migration; retain its full backup and history. The new publisher never runs alongside an old source-tree writer for the same library.

Use the CLI's separate write authorization when stage-two code and disposable-folder pilot are ready. Request only needed access through the established CLI login; do not print/store tokens in the selector. Pilot writes are limited to a clearly isolated test folder before production publication. Existing Markdown editing and sharing settings are preserved.

## Verification and rollout

Use controlled HTTP-server tests for listing pagination, version changes, throttling, failed transfers, authentication refresh and unknown upload results. Real CLI integration tests exercise streaming and machine-output contracts. Selector tests prove cache reuse, ambiguity preservation, source-change fences, stale-worker handling, edited-output preservation, crashes between remote writes and local checkpoints, and duplicate-free retries. Retain the existing filesystem suite.

For each stage, record source IDs, checksums, transfer/extraction/publication timings, cache hits, errors and restart behavior in private evidence. Test Drive mode with the mounted path deliberately unavailable to the test process; do not unmount the live library. Keep the running production job until a tested replacement can take its existing leases. Deploy an immutable selector/CLI version pair under the user service; show durable progress and preserve rollback state.

Success: the final pipeline discovers, selects, reads, extracts and publishes the library through `gdrive-cli` plus local cache/Poppler, with no dependency on a mounted Drive folder. Existing verified conversions and manual edits remain preserved. No fixed speedup is promised.

## Builder choices

The implementer chooses exact Rust module names, versioned JSON schemas, SQLite migration numbering and CLI command spelling, consistent with the two existing projects. Use a transport/backend boundary without rewriting selection policy or introducing a shared OAuth library. Start with two concurrent downloads/extractions within existing capacity reservations; tune only from measured results. Group the implementation plan by stage; do not make stage one depend on upload permissions or stage-two API capabilities.

## API references

- [Drive upload and idempotent pre-generated IDs](https://developers.google.com/workspace/drive/api/guides/manage-uploads)
- [Drive file observations](https://developers.google.com/workspace/drive/api/reference/rest/v3/files)
- [Drive file updates](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/update)
