# Presentation and citation fixes implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix pilot-01 discovery and packet-link errors, then validate on a disjoint real-source subset.

**Architecture:** Extend existing Rust grouping with presentation suffix candidates. Add source/page/quote binding for packet-free reader responses, preserving explicit legacy responses and existing decision gates. Keep the pilot in ignored private working data.

**Tech stack:** existing Rust, regex, serde, rusqlite and Poppler; no new dependencies.

**Spec:** `../specs/2026-11-23-presentation-citation-design.md` (user requested fixes and disjoint rerun).

## Global constraints

- Maximum five sampled pages per byte content, no automatic OCR or extra pages.
- Candidate relationships do not establish equivalence or chronology.
- Preserve original sources, Dungeon Masters Guild results, and the running hash scan.
- Factual reading uses simpler models; semantic assessment uses Sol.

## Review focus

- No Background/Digital/BW/Colour aliases must reach the same comparison group even when each has byte-identical old copies.
- Volume, language and ruleset suffixes must remain distinct.
- Auto-binding must reject stale membership/hash, unsupported quotes, unknown sources/pages and distinct ambiguous fragments.
- Reader imports must stay atomic and record source/hash/page/packet provenance without weakening Sol/user judgments.
- The new pilot must share neither paths nor content hashes with pilot 01.

### Task 1: Discover presentation candidates

- [x] Add failing tests for the missed presentation aliases and protected labels.
- [x] Add a presentation key and attributed candidate grouping; keep differing bytes unresolved.
- [x] Run grouping and CLI checks to prove presentations no longer escape default review.

### Task 2: Bind factual citations in Rust

- [x] Add failing tests for packet-free multi-page claims, stale/unknown/ambiguous bindings and transaction rollback.
- [x] Record source SHA-256 on excerpts and resolve claims to issued current reader fragments.
- [x] Import packet-free claims, persist binding audit, and preserve legacy explicit responses and decision validation.
- [x] Update reader templates/instructions and operator notes.
- [x] Run full Rust suite, explicit Poppler test, formatting, build and Clippy. Request one final narrow Sol code review and address important findings.

### Task 3: Disjoint pilot

- [x] Select/stage completed hashes from new products, assert zero path/hash overlap with pilot 01, and preserve original-source provenance.
- [x] Run scan and bounded extraction in separate pilot state; verify new presentation groups are exposed to review.
- [x] Run factual readers without packet IDs, audit semantics with Sol, import supported facts via Rust auto-binding, and report outcomes without automatic exclusions/conversions.

## Verification and rulings

One fresh Sol code review found four important workflow defects plus an audit replay defect. Each was reproduced with a failing test and fixed in one correction pass: failed exports no longer issue packets; presentation keys preserve dotted/explicit numeric ruleset qualifiers; reader fragmentation remains stable across fact imports; empty replies are no-ops; original binding mode/time survives replay. No second review round was requested.

Fresh verification passed 68 normal Rust tests, one explicit installed-Poppler roundtrip, formatting, build, Clippy with warnings denied, and whitespace checks.

Pilot 02 used four different product families, 18 original paths, nine distinct byte contents and 45 unique sampled pages, with zero path/hash overlap with pilot 01. All four families reached default reader review as presentation candidates. All 27 cheap-reader claims auto-bound without packet IDs, serialization repairs or citation repairs, and all 27 passed Sol's semantic audit. No selection decisions or conversions were imported/run. Detailed private evidence is in `source-selection-data/content-pilot-02`.

Ruling: preserve numeric qualifiers in the new presentation path even if it misses a comparison between differently numbered presentation filenames; avoiding new cross-ruleset links is preferable to guessing edition semantics. Older title/version candidate logic remains a separate source of relationships.

Ruling: only the model-reading jobs run concurrently. Scan, inspection, packet export and claim import run in sequence for a given pilot state; concurrent inspection/import writers were outside review and pilot coverage.

Ruling: the full-library hash process uses its already-running executable and was not restarted. Once it finishes, refresh its scan using the updated binary to apply the new grouping while reusing completed hash caches.
