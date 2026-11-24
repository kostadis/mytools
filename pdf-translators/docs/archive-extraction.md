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

## Deployed batch

Code `53fbbe3` is deployed as immutable `archive-selector-53fbbe3` (SHA-256 `b8e72e8c2e601914893397a93a1db52e0458de4089aa207f7c101cd2ff5429a6`), paired with private `bsdtar-3.8.5` (SHA-256 `a160f970a1ba6e6fe4ee3300f1bb8536fb5e8af04daf862cea97f79918964826`). The full Rust suite passed167 tests (9 optional ignored); all8 archive integration cases, including native and low-space cases, passed separately. Format, clippy and release build passed. Important review findings were fixed in one pass with failing regressions; minor followups remain above.

The real CIFS pilot completed4 archives,96 files and6 PDF entries without errors/conflicts; a second run reused all4. Its completion records/logs were copied into the unlimited output, excluding the bounded manifest. User service `rpg-archive-extraction.service` runs four native decoders independently of the chat terminal and restarts on abnormal termination. Sustained progress past one minute was verified with66 completed archives,4 active workers,223 PDF entries and zero failures/conflicts. Total job count grows as nested archives are queued. This is an active batch, not a claim that all archives have finished.

```bash
systemctl --user status rpg-archive-extraction.service
watch -n 5 cat /home/kostadis/.codex/worktrees/rpg-source-selection/mytools/pdf-translators/source-selection-data/winshare-archive-extraction/status.json
tail -f /home/kostadis/.codex/worktrees/rpg-source-selection/mytools/pdf-translators/source-selection-data/winshare-archive-extraction/extraction.log
```

Private `deployment.json`, `pilot-verification.json`, `preflight.json`, per-source `records/` and per-entry `logs/` retain the verification and recovery evidence.

## Automatic PDF conversion after extraction

At the owner's request, `scripts/run_markdown_after_archives.sh` sequences the existing Rust scan and conversion commands after the archive batch. User service `rpg-library-after-archives.service` waits until extraction reports `completed` or `completed_with_exceptions`, with zero active and queued jobs, and the archive service has stopped. It acquires the archive lease before rescanning, so an archive retry cannot add PDFs mid-conversion. Capacity pauses and unfinished extraction do not trigger conversion. Invalid archives are recorded exceptions; successfully extracted folders remain eligible.

The follow-up refreshes the same current-library inventory at `/mnt/winshare`, then starts `rpg-markdown-winshare.service` with four workers and the existing `winshare-current-markdown` cache/output. It uses the immutable selector from archive code `53fbbe3` so incomplete staging is excluded. Matching page checkpoints are reused; current outputs retain normal ownership protections. The existing library is revalidated alongside the newly extracted PDFs. It waits for any existing converter before scanning and avoids starting a duplicate service.

The sequence is one-shot and persists its phase in `winshare-archive-extraction/markdown-followup.json`, with events in `markdown-followup.log`. Conversion progress remains in `winshare-current-markdown/continuous-status.json` and `continuous.log`. The follow-up service monitors conversion through its terminal status; an abnormal restart during conversion resumes monitoring. It does not classify native-empty PDFs as successful Markdown or automatically perform OCR.
