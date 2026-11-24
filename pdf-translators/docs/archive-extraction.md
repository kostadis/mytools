# Extract the current library archives

The Rust selector delegates ZIP/RAR/7z decoding to native `bsdtar` (libarchive), retaining the archives. For each archive it writes a separate `<archive filename>.extracted` folder beside that file. Existing destinations are preserved as conflicts. Very long archive names use a source-ID-based destination, recorded in the receipt. No Markdown conversion is started by this command.

```bash
rpg-source-select --work-dir /path/to/completed-scan-state archive-extract \
  --output /path/to/private/archive-state --extractor /path/to/bsdtar --workers 4
```

The original scan root and identity are verified. A private `jobs.json` freezes the initial archive list and records discovered nested ZIP/RAR/7z files; nesting beyond eight levels is recorded for later review. Each archive is decoded in `.rpg-archive-staging` at the library root. Only successful extraction with an unchanged source observation is published by an atomic no-overwrite directory rename. Native path-traversal protections remain enabled. Links and special entries are not published. The PDF inventory excludes incomplete archive staging.

Per-archive `records/` receipts are committed before extraction and directory publication. Successful receipts are reused; extracted-but-not-yet-published intents recover by directory identity. Interrupted/capacity-blocked stages are reclaimed only when their ownership and real directory identity match. Failed stages remain available for inspection; retrying failed work preserves the prior receipt in `history/`. Unknown or replaced directories are never removed. The extractor is killed/reaped on every early exit; both the destination and private output retain a 20 GiB free-space floor. A capacity pause exits75 with unfinished work queued.

`status.json` records completed/reused/active/queued archives, failures/conflicts, extracted file/PDF counts and bytes. Totals grow as nested archives are discovered. File counts include nested archive files; PDF counts are entries exposed by extraction, not deduplicated works or newly converted Markdown. `extraction.log` records every archive and 30-second heartbeats; `logs/<source-id>.log` records every extracted entry and native diagnostics. Completion is durable after each archive. `--retry-failed` retries recorded failures; it never overwrites existing destinations. `--limit N` freezes a bounded scope and requires a separate output from an unlimited run.

## CIFS rollout

The current source is `/mnt/winshare` with scan state `source-selection-data/winshare-current-state`. Archive state is `source-selection-data/winshare-archive-extraction`; its existing `preflight.json` has central-directory observations. Initial scope is1,442 archives (1,422 ZIP/20 RAR), totaling149,851,892,528 packed bytes. ZIP headers declare about142.57 GiB of expanded content,2,020 PDF entries and143 nested archives, with seven header/index failures and no encrypted ZIP flags. One173-byte `.ZIP` is an HTML502 error response. Native decoding may recover some index-damaged archives; failures remain individually logged.

The native tool is libarchive-tools3.8.5, matching installed libarchive3.8.5. It was downloaded/unpacked privately; no system package installation was required. A real2.76 MB RAR decoded successfully into3 files with its original size/timestamps unchanged. Tests cover native nested ZIP extraction, preserved manual outputs, traversal rejection, receipt/staging substitution, resumed owned-stage reclamation, child cleanup after I/O failure, source-parent redirection and retryable low-space exit.

A bounded real-root pilot uses separate private pilot state. Its exact per-source receipts/logs are migrated into the full output before launch; its limited `jobs.json` is not copied. This lets the unlimited scope reuse the pilot's published directories without confusing them with unowned manual outputs. Production and pilot coordinators do not run concurrently on this library.

Deferred minors from the single final review: the full job manifest is rewritten after each successful archive even when no children were added; and the inventory's reserved staging-name exclusion currently applies at every directory depth rather than only at the library root. Neither blocks this rollout. No additional legacy PDF/Markdown selection authority is imported or modified.
