# Metadata-selected searchable Markdown implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Implement natively in this session, with one final Sol review.

**Goal:** Select the newest eligible PDF by embedded dates, preserve authority/alternatives, and run a resumable four-document full-Markdown pilot.

**Architecture:** Add an independent `markdown` subsystem to the existing Rust binary. Metadata and ready snapshots are additive to legacy selection. A single coordinator persists jobs; isolated child workers checkpoint native page ranges. Immutable corpus generations expose one current Markdown file per work.

**Tech stack:** existing Rust/chrono/serde/rusqlite/Poppler; add a bounded XML parser for recognized XMP date fields. No OCR/model API calls for conversion.

**Spec:** `../specs/2026-11-23-searchable-markdown-design.md`, approved by the user.

## Global constraints

- Embedded modification date then creation fallback per file, UTC-aware and conservative on conflicts/ties/unknown competitors.
- Preserve all original files, current user/Sol authority, human holds and Dungeon Masters Guild baseline protection.
- Separate policy queue; legacy JSON/TSV and proof outcomes retain semantics.
- Selection inspection remains capped at five pages; conversion attempts the full selected document.
- Two workers, 20-page ranges by default; page checkpoints verified before reuse; worker failures isolated.
- No routine model/OCR calls, no index promotion, no 5etools encoding.

## Review focus

1. Conflicting, offset-free, partial and mixed date representations must not silently produce a false winner.
2. Broad/coarse groups and changed reviewed groups must not discard independent works or override a hold.
3. Empty/scanned/sparse pages and literal Markdown/HTML must preserve searchable evidence without claiming semantic completeness.
4. Crashes, corrupt checkpoints and changed source/extractor contracts must resume or invalidate safely.
5. A stale frozen job must not publish over a newer selection, and failed books must not block good independent books.

### Task 1: Date evidence and additive ready snapshots

**Files:** create `source-selector/src/markdown/{mod,dates,selection,metadata}.rs`; expose existing metadata decoding internally; add `tests/markdown_selection.rs`.

**Interfaces:** `dates::resolve(&BTreeMap<String,Value>) -> DateEvidence`; `selection::select(&Store, &Path, Option<&Path>) -> Result<Snapshot>`; `selection::load_current(&Path) -> Result<Snapshot>`. Versioned Snapshot contains frozen Ready entries and all ready/deferred/baseline decisions, raw date witnesses, alternatives and source hashes. Optional provenance map preserves original IDs/paths for locally staged pilot inputs.

- [ ] Add failing date tests for timezone equality, creation fallback, invalid/missing values, Info/XMP conflict, compatible precision, ties and backwards modification dates.
- [ ] Add failing selection tests for alias collapse, four metadata winners, undated competitor, protected qualifiers, reviewed holds/choices, baseline reuse, sample-free Ready and legacy export preservation.
- [ ] Implement date parsing/evidence resolution and cache metadata by verified source SHA-256 independently of samples.
- [ ] Implement conservative whole-component eligibility and separate immutable `markdown-selection.json`, TSV and review JSONL generations.
- [ ] Verify tests; record interface/ruling changes and commit the completed unit.

### Task 2: Isolated workers, resumable ranges and publication

**Files:** create `source-selector/src/markdown/{conversion,worker,publication}.rs`; add `tests/markdown_conversion.rs`.

**Interfaces:** `conversion::run(output, options) -> Result<Report>`; `worker::run(job_path) -> Result<()>`; `publication::publish(output, snapshot, engine) -> Result<Publication>`. Workers stream/verify selected source caches and write atomic checksummed range artifacts; only the coordinator writes SQLite job/attempt state and current corpus pointers.

- [ ] Add failing tests for full page coverage, source/page front matter and escaping, zero-text deferral, sparse warnings, and simple phrase search.
- [ ] Add failing tests for interrupted range resume with unchanged checkpoint, corrupt-cache retry, worker failure isolation, changed source/extractor invalidation and cache reuse on policy-only updates.
- [ ] Add failing tests for partial batch publication, preserved previous generation, source-change invalidation and A-to-B selection promotion guards.
- [ ] Implement source staging, per-job leases, bounded worker processes/timeouts/heartbeats and atomic checkpoint validation.
- [ ] Assemble page-based Markdown/sidecars from completed ranges, preserve raw text, and publish checksummed generations with `corpus/current/books` search view.
- [ ] Verify tests and commit the completed unit.

### Task 3: CLI, operations and real pilot

**Files:** modify CLI dispatch; create `source-selector/src/cli/markdown.rs`, operator notes and pilot report.

**Interfaces:** `markdown-select --output PATH [--provenance PATH]` uses `--work-dir` for existing source state; `markdown-convert --output PATH [--workers 2 --chunk-pages 20 --timeout-secs 120 --limit N --retry-failed]` operates from the frozen output snapshot, including offline cached inputs. Hidden `markdown-worker --job PATH` enables isolated children without requiring a legacy database.

- [ ] Add real CLI tests for queue/corpus output guards, empty/latest pointers, job resume, legacy compatibility and immutable-input provenance.
- [ ] Wire CLI and operational reports; document write-stage sequencing and source/cache/output directories.
- [ ] Run the Rust suite, explicit Poppler test, format, build and Clippy; request one fresh Sol review and address important findings with RED-to-GREEN regressions.
- [ ] Select from `content-pilot-02/state` into a separate `markdown-pilot-01` namespace, with original provenance mapping. Confirm four expected winners and 61 full pages.
- [ ] Run conversion, verify page headings/artifacts and known phrases, rerun to prove cache reuse, record warnings and preserve all original hashes/outputs.
- [ ] Commit verified code and pilot summary. Keep broad library conversion and index publication unstarted.

## Ledger

Execution method: native, as already chosen and now explicitly authorized to implement/run the pilot. No extra approval gate is introduced by this plan.
