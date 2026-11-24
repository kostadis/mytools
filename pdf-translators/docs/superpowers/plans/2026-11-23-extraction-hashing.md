# Reduce extraction hashing

> Execute natively using superpowers:executing-plans; one fresh final review.

**Goal:** Remove unnecessary full-file reads from PDF staging and extraction.

**Design:** The user rejected hashing the entire private cached PDF after each range as overkill. Hash once while copying a new source, or once when accepting an existing cached source, and once at completion. Compare existing inventory fingerprints between ranges (size, inode/device, modification/change times) to reject ordinary mutation before checkpointing. Preserve publication's independent source validation and all durable chunk checksums. For an existing cache, retain the live-original comparison so an accessible changed source remains an error. No Drive API changes or concurrency changes.

**Approaches:** Only remove the staging pre-read, or also remove per-range local hashes. Implement the broader reduction requested in the conversation, retaining cheap mutation detection and boundary verification.

**Tech stack:** Existing Rust project; no dependencies.

## Review focus

- Source changed before staging must fail the copy hash.
- Existing cache must not mask an accessible changed original.
- Cache changed during extraction must fail before the affected range is committed.
- Same-size cache edits and replacement must be detected by fingerprint identity/times.
- Resume must keep chunk checksums and completion validation.

## Task 1: Simplify verification and deploy

- [x] Add a Linux regression using a large PDF and extractor wrapper reporting worker read counts; assert no full-file read between page ranges. Watch it fail.
- [x] Update worker staging to avoid the original pre-read when copying; replace range hashes with fingerprint comparisons, retaining final hash.
- [x] Run conversion tests and whole cargo suite, fmt, clippy, release build. Existing mutation/resume/source-change tests must pass.
- [ ] Commit, obtain one fresh Sol review, address important findings once, verify, then restart continuous rollout on an immutable binary preserving caches and publication records. Record deployment evidence.

## Verification and final review

- Read-volume regression RED: 8,736,922 bytes read between ranges for an 8,389,600-byte PDF. GREEN: range-start counts 8,400,919 / 8,748,239 / 9,112,406 bytes; first staging read is also below twice PDF size.
- One fresh Sol review found that the existing-cache fingerprint must be captured before cached SHA verification and carried through the live-original check into extraction. Fixed in one pass. A Linux file-lease regression deterministically pauses the original read, edits the cached PDF without changing its size, and asserts that no unverified range is checkpointed. RED (unverified content checkpointed) → GREEN.
- Final whole suite: 157 passed, 2 optional tests ignored. All 16 conversion tests passed. fmt, diff-check, clippy with warnings denied and release build passed.
- Runtime audit found previous controller absent, without a terminal log entry; no cause established. All rollout locks free. Existing state retained: 820 staged PDFs, 3,407 page ranges, 370 ownership receipts. Resume through a user service so the process is independent of the chat terminal; no automatic retry policy added.
