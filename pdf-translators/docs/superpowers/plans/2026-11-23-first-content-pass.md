# Five-page content samples implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound the first extraction pass to five pages per PDF and reuse identical samples without automatic escalation.

**Architecture:** Keep the Rust/Poppler extractor and existing SQLite evidence store. Replace full competing-document extraction with bounded page selection; reuse identical byte samples with explicit provenance. Leave uncertain outcomes in the existing review export.

**Tech Stack:** Rust, lopdf, Poppler, rusqlite, existing synthetic-PDF fixtures.

**Spec:** `../specs/2026-11-23-first-content-pass-design.md` (user approved).

## Global constraints

- At most five extracted pages per PDF in the first pass; no automatic additional pages or OCR.
- Preserve originals and Dungeon Masters Guild outputs.
- Matching samples cannot establish whole-document equivalence or chronology.
- Do not start parallel model execution or the broad content-reading pass as part of this change.

## Review focus

- Large singleton and competing PDFs must both obey the five-page budget.
- Unknown page counts must fail closed rather than request the whole PDF.
- Repeated runs and explicit page requests must not quietly grow the sample beyond five pages.
- Identical copies may share page evidence, but source-bound claims must not be transferred.
- Sparse extraction and partial coverage must stay visible and unresolved.

### Task 1: Enforce bounded, reusable extraction

**Files:** modify `source-selector/src/cli/inspect.rs`, `source-selector/src/evidence.rs`, `source-selector/src/cli.rs`; tests in `source-selector/tests/cli.rs` and `source-selector/tests/poppler.rs`; update operator notes.

**Interfaces:** preserve `inspect_pdf` for low-level tests and explicit internal use; enforce first-pass policy at the operator CLI. Keep the existing Evidence schema, adding attributed extractor information to its metadata.

- [x] Write real CLI tests for 100-page singleton and competing candidates: pages are exactly 1,2,3,4,100, and reruns extract no new pages.
- [x] Add cases for over-budget ranges, accumulated samples, identical-byte reuse, and empty/scanned sample deferral.
- [x] Run tests and observe failures before implementation.
- [x] Implement bounded selection, fail-closed page-count handling, missing-page-only extraction, and byte-identical sample reuse with cleared reader claims.
- [x] Record extractor provenance and update the CLI help and operator notes. Verify existing evidence and human authority tests remain green.
- [x] Run the Rust suite, explicit Poppler test, formatting, and Clippy. Request one narrow final review and fix important findings.

Ruling: default page selection is first four plus final, rather than guessing bookmarks, because the user approved that concrete baseline and uncertain cases are intentionally deferred.

## Final review and verification

A fresh Sol reviewer reproduced three important defects: a late identical copy could create a second nondefault sample, partial fills lost prior warnings/tool attribution, and inherited subprocess pipes could outlive the timeout. Each finding was reproduced with a failing test, then fixed in one correction pass. Final checks: 56 normal Rust tests, one explicit Poppler roundtrip, formatting, build, and Clippy with warnings denied all pass. No second reviewer round was requested.

Ruling: the budget applies to shared byte identity, not just a source path, to avoid resampling exact copies. Existing five-page samples are preferred even when their page numbers differ from the default.

Ruling: mixed samples retain per-batch provenance and all prior warnings; legacy provenance is unknown rather than relabeled with the newest extractor. Their source-bound reader claims stay with the original source.

Ruling: subprocess deadlines include pipe draining. Unix extractor process groups cover wrapper descendants; reader/reaper threads do not block a timeout return.

The small real Feats pilot passed with one three-page sample reused for its identical copy and zero failures. The full byte scan remains a separate running job; the broad content-reading pass and all model calls remain unstarted. The reviewer did not exercise concurrent writers or broader real-library extraction quality.
