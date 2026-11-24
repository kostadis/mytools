# Convert the refreshed current-download library

> Execute natively using superpowers:executing-plans; one fresh Sol review, one correction pass.

**Goal:** Convert every PDF under `/mnt/winshare` to searchable sibling Markdown, preserving source files and manual outputs.

**Design / user requirement:** The owner re-downloaded the library and says these are the most recent delivered files. Treat each PDF as a current input, including multiple publisher-supplied variants. Do not apply historical date/duplicate exclusion. Reuse the existing Rust continuous converter, publication journals, range checksums, configurable workers (four requested for this run), 20 GiB floor and no-text/OCR exception policy. Existing `current-documents.json` semantics and source links remain. Archives and non-PDF files are outside this run. The gdrive CLI design stays shelved.

**Approach:** Add explicit `scan --current-library` policy, producing one group per PDF. Resolve those groups from the owner's current-download assertion instead of embedded recency, while preserving any explicit review/hold and normal output ownership checks. Normal scans retain their existing behavior. Use new private state/output namespaces for this different root; copy prior metadata and content-addressed extraction caches without importing old selection/ownership authority.

## Task 1: Current-library policy

- [x] Write integration tests proving all current PDFs (including conflicting/missing dates and same-product variants) publish, native-empty files remain OCR exceptions, manual Markdown survives, and resumes reuse ranges. Run RED.
- [x] Implement `Scan.current_library`, singleton PDF grouping and persistent policy metadata, with current policy selection basis. Skip historical candidate warm-hashing in this mode; continuous metadata/extraction performs byte verification. Preserve existing policy for default scans and review/hold priority.
- [x] Run full selector suite, fmt, clippy and release build. Review once with fresh Sol; fix Important/Critical once with failing regression tests, then rerun suite. Commit.

## Task 2: CIFS rollout

- [x] Run the existing mounted-filesystem publication/replacement/resume probe under `/mnt/winshare` in an isolated temporary directory, then remove it.
- [x] Create separate `winshare-current-state` and `winshare-current-markdown` private namespaces. Seed verified SHA metadata and extraction caches without copying old root identities, selection records or ownership journals. Record source manifest and cache counts.
- [x] Run current-library inventory, log every 100 files, confirm all 6,391 PDFs grouped individually and preserve non-PDF/archive accounting. Perform a representative real-PDF pilot and verify source hashes, relative links, sibling Markdown and directory record behavior.
- [x] Deploy immutable tested binary as a dedicated user service; keep checkpoints and append-only logs. Verify fresh extraction/publication beyond one minute and report progress paths. Document the new root/policy and deployment evidence; commit docs. No push requested.

## Review focus

- A corrupt PDF must fail individually without blocking the rest.
- Identical bytes at distinct paths must each get a sibling output, sharing extraction safely.
- Manual or differently cased conflicting outputs on CIFS must never be overwritten.
- Explicit holds and baselines from default-policy libraries must not be weakened by the opt-in policy.
- A rescan must not silently switch a library policy or carry unrelated source-root authority into the new run.

## Final review evidence

One fresh Sol review found three important issues, fixed in one pass with RED→GREEN regressions: colliding sibling filenames, explicitly confirmed baselines, and concurrent scan policy/progress races. The full suite passed 163 tests (2 optional ignored); the optional mounted CIFS probe passed separately. fmt, clippy with warnings denied and release build passed.

Deferred minor: historical MuSe hints spanning groups can trigger `needs_regroup` in current-library mode. The fresh CIFS inventory has no hints and does not use those import flags.

## Worker-count steering

The owner requested four converters after initial deployment. Added positive `markdown-continuous --workers` (default two), a gated integration test proving four distinct extractors are active concurrently, and retained aggregate capacity reservations. Four-worker test RED→GREEN; final whole suite 164 passed / 2 optional ignored; fmt/clippy/release passed. Production output is on a disk with roughly 304 GiB available and the host has roughly 41 GiB available RAM.

The initial CIFS service passed sustained extraction/publication with 386 confirmed publications before the requested worker-count restart. The replacement uses code `a46aae7`, immutable `selector-a46aae7`, SHA-256 `668b55362e302ccdd95fbbe85046c7ea6d355de1d8428ac8d69c203f54ca4fec`. Four live isolated PDF worker PIDs were verified, with no failures/output conflicts at restart. Two existing Markdown samples retained their SHA-256 and modification times; all private databases/ranges/receipts were retained. Evidence: `winshare-current-markdown/{deployment.json,four-worker-transition.json}` and `winshare-current-pilot/verification.json` under private source-selection data.
