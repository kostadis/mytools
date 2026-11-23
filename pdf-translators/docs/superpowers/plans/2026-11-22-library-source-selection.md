# Library Source Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver issue #144: an evidence-backed, reviewed list of current, distinct DriveThru source PDFs, without converting them or modifying the library.

**Architecture:** Add an independent Rust crate exposing a library and the `rpg-source-select` binary. Persist inventory, content evidence, candidate groups, and decisions separately in a dedicated SQLite database; export a versioned JSON manifest and deterministic TSV/report views. Use read-only PDF inspection and external reader/judge packets rather than adding a new inference transport or coupling selection to 5etools encoding.

**Tech Stack:** Rust edition 2024, MSRV 1.95 (matching the neighboring `markdown-editor` crate; installed compiler is 1.98.1). Use `serde`/`serde_json` 1, `clap` 4, `rusqlite` 0.43 with bundled SQLite, `sha2` 0.10, `csv` 1, `regex` 1, `flate2` 1, `chrono` 0.4, `lopdf` 0.47, and `thiserror` 2; `tempfile` 3 for tests. Use installed Poppler `pdftotext` for text extraction. Commit `Cargo.lock`. No Python runtime, bindings, or automatic provider calls.

**Spec:** `docs/superpowers/specs/2026-11-22-library-source-selection-design.md`; authoritative filed copy: https://github.com/kostadis/mytools/issues/144. This plan covers milestone 1 only.

## Global Constraints

- All original files stay in place. Never delete, rename, move, or write beside sources.
- Do not modify `batch/batch_convert.py`, its state DB, existing encoder behavior, or rpg-lib's stored flags.
- Dungeon Masters Guild is the baseline, not a request to reconvert it. JSON existence never proves Markdown completion.
- Include text-bearing handouts, reference sheets, and map booklets. Sparse text is not proof that an asset is purely visual.
- Do not filter by game system. Preserve separate languages, RPG systems, volumes, and supplements.
- Filename versions, `.old`, timestamps, text similarity, and inherited flags are evidence, not proof of chronology or equivalence.
- Use deterministic code where possible, simpler models for factual reading, and Sol for reasoning/judgment; uncertain decisions reach the user.
- Inventory directly available PDFs and report archives as uninspected containers. No bulk OCR or inference during planning.
- Working data belongs in an explicitly supplied `--work-dir` outside the scanned root. Book excerpts and real review packets are private working data, never committed fixtures.
- All new selector code and tests are Rust. The existing `adventure_model_minimal` crate is a separate project and is not modified.
- Every task follows the failing-test / implementation / passing-test cycle below; commit only the task's files. Tests use synthetic PDFs and temporary work directories, never the real library.

## Review Focus

1. Same-size file replacement with preserved mtime: compare device/inode/ctime where reliable and content-verify a reviewed group before applying its decisions; test in Tasks 1 and 4.
2. One product ships distinct works or system/language editions: a candidate group may be split and must not imply equivalence; test in Tasks 2 and 4.
3. Equal or empty text hides scanned writing or differing images: never auto-exclude on text alone; test in Tasks 3 and 4.
4. New candidate joins a previously reviewed group: invalidate the affected group decision even if all original files are unchanged; test in Tasks 2 and 4.
5. Baseline equivalence across folders: compare it, but keep established output references out of the default new-work queue; test in Tasks 4 and 5.

## Files and interfaces

All paths below are relative to `pdf-translators/` in the `kostadis/mytools` repository.

Create a standalone crate at `source-selector/`: `Cargo.toml`, `Cargo.lock`, `src/lib.rs`, `src/main.rs`, and focused `src/{models,store,inventory,hints,grouping,evidence,compare,review,export,cli}.rs` modules. Add integration tests under `source-selector/tests/`, synthetic PDF builders in `tests/common/mod.rs`, and `docs/source-selection.md`. Each module owns its named responsibility; keep network/provider transports out. Register package/library name `rpg-source-select` / `rpg_source_select` and binary `rpg-source-select`. Do not make this a Python extension or move existing converter logic. Add `source-selector/target/` to this project's `.gitignore`.

Use typed Rust structs/enums with `serde::{Serialize, Deserialize}`, snake_case serialized enum variants, and explicit semantic `validate` methods. Export `Result<T>` and a typed `SelectionError` with `thiserror`. Use `Path`/`PathBuf` internally, retaining path identity without lossy string conversion; non-UTF-8 paths get a lossless byte representation in the source record and an explicit export limitation in TSV. Use `Option<T>` for unknown values. The types carry:

- `Source`: `source_id`, `relative_path`, `kind` (`pdf`/`archive`), `publisher`, `product_folder`, `fingerprint`, `read_error`, `baseline_established`, `artifacts`, `metadata`. `source_id` is SHA-256 of normalized root identity plus case-preserved relative path; it identifies a location, not a work. Fingerprint stores size, mtime_ns, ctime_ns, device, inode, and optional sha256. Metadata values keep their provenance.
- `Hint`: `origin`, `source_ids`, `payload`, `unmatched_references`; `origin` is `muse`, `rpglib`, `legacy_skip`, or `baseline`. Hints never change source status.
- `Group`: `group_id`, ordered `source_ids`, `membership_digest`, `reasons`; a connected candidate component can contain several distinct works. `membership_digest` binds current members and fingerprints; stable `group_id` is retained through membership changes by store reconciliation.
- `Evidence`: `source_id`, `sha256`, `version`, `pdf_metadata`, `pages` (1-based page, verbatim text, image/annotation counts), `bookmarks`, `errors`, `text_quality`, `claims`. `claims` carry kind, value, source/page, verbatim supporting quote, actor, and role. Unreadable or unknown metadata stays explicit.
- `Decision`: `group_id`, `membership_digest`, `evidence_digest`, `actor`, `actor_role` (`deterministic`/`reader`/`sol`/`user`), `outcomes`, `rationale`, `evidence_refs`. Each outcome carries `source_id`, `status`, optional `work_id`, optional `representative_id`/`successor_id`. Status values: `selected`, `exact_duplicate`, `equivalent_presentation`, `superseded`, `distinct_work`, `needs_review`, `excluded_asset`, `unreadable`.
- `SelectionSnapshot`: schema version `1`, root, scan timestamps, coverage/errors, sources, groups, evidence references, decisions, works, and queue. One queue item per selected work carries chosen source, source fingerprint, all related source IDs, book IDs and attributed metadata where available, plus unverified artifact references.

Keep schema version `1` in database metadata and exports. Assign persistent work IDs on accepted decisions; retain them across unchanged reruns. A split/merge records prior work IDs rather than silently reassigning history.

---

### Task 1: Read-only inventory and durable state

**Files:** Create `source-selector/Cargo.toml`, `src/{lib,models,store,inventory}.rs`, `tests/inventory.rs`, and `.gitignore` entry. File paths under `src/` and `tests/` in the following tasks belong to this crate.

**Interfaces:** `scan_root(root: &Path) -> Result<InventoryResult>`; `Store::open(path: &Path) -> Result<Store>` with `upsert_inventory(&mut self, result: &InventoryResult) -> Result<()>`, `sources(&self) -> Result<Vec<Source>>`, `get_cached(&self, source_id: &str, stage: &str, cache_key: &str) -> Result<Option<serde_json::Value>>`, and `put_cached(&mut self, source_id: &str, stage: &str, cache_key: &str, payload: &serde_json::Value) -> Result<()>`. `InventoryResult` contains root, start/end timestamps, sources, and path-specific errors. SQLite connection cleanup is RAII; mutating store methods use transactions.

- [ ] Write tests with these assertions: uppercase `.PDF` is inventoried; `.old` PDFs remain; archives are counted separately; `-responses` directories and converter input/response/parsed triplets are excluded; unreadable directories produce coverage errors; a symlink is recorded but not followed outside the root; bytes and timestamps of all source files remain unchanged; replacing a file with equal size/mtime changes its fingerprint when ctime/inode changes; reusing a store with a different root refuses.
- [ ] Run `cargo test --manifest-path source-selector/Cargo.toml --test inventory`; expect a missing integration target/type compile failure before implementation, then assertion failures as needed. A red-phase compile failure must disappear once the interface exists.
- [ ] Implement the interfaces using `std::fs::read_dir`, `symlink_metadata`, platform-specific metadata extensions behind `cfg`, and `rusqlite` transactions. Unknown device/inode/ctime fields remain `None` on unsupported platforms. Never follow directory symlinks. Record artifact siblings as references without reading or trusting them. Treat extracted PDFs in ordinary directories independently of archive records. Cache keys include stage algorithm version and the observed fingerprint. Store tables: `meta`, `sources`, `hints`, `groups`, `evidence`, `decisions`, and `works`; immutable history and current pointers must be distinguishable.
- [ ] Run `cargo test --manifest-path source-selector/Cargo.toml --test inventory`; expect all pass.
- [ ] Commit the inventory/state deliverable with `feat(pdf-translators): inventory source candidates without changing the library`.

### Task 2: Import hints and discover duplicate/candidate groups

**Files:** Create `src/{hints,grouping}.rs`, `tests/grouping.rs`; extend `src/store.rs` for hints/group reconciliation.

**Interfaces:** `read_muse(csv_path: &Path, sources: &[Source], twins_path: Option<&Path>) -> Result<Vec<Hint>>`; `read_rpglib(json_path: &Path, sources: &[Source]) -> Result<Vec<Hint>>`; `hash_source(path: &Path) -> Result<String>`; `build_groups(sources: &[Source], hints: &[Hint], store: &mut Store) -> Result<Vec<Group>>`; `Store::reconcile_groups(&mut self, groups: &[Group]) -> Result<Vec<Group>>` persists identities and marks affected decisions stale.

- [ ] Write tests asserting: identical bytes across product folders join one exact-copy set without models; equal-size different bytes do not; changing a source during hashing produces an error and discards the hash; Muse IDs/confidence and unmatched entries remain attributed hints; relative and absolute rpg-lib filepaths map only within root; twin folders differing in dash style compare; `RotDCE-v2` and `RotDCE-v3` become candidates without a chosen winner; same product ID with distinct chapter names is not auto-collapsed; missing game-system metadata is allowed; newly joined group members invalidate earlier decisions; high-confidence Muse choices do not suppress peers.
- [ ] Run `cargo test --manifest-path source-selector/Cargo.toml --test grouping`; expect failures for missing grouping/import behavior.
- [ ] Implement imports using the `csv` crate with serde records and JSON metadata snapshots from the existing rpg-lib API. Accept Drive metadata from optional snapshot rows (`drive_file_id`, `drive_modified_time`) and report unavailable fields; do not require live Drive access or query the library DB. Accept twin-folder hints as a JSON array of publisher plus folder pairs. Legacy `.extract_skip` rows are hints only. Use size buckets to hash possible exact copies lazily; detect changes with pre/post stat checks. Candidate keys normalize punctuation, whitespace, known product prefixes, `.old` suffixes, and version/presentation markers while retaining volume numbers, language/system labels, and distinct title words. Same-product and Muse relationships may create broader review components but never prove equivalence. Compare across the entire root, including DM's Guild.
- [ ] Run `cargo test --manifest-path source-selector/Cargo.toml --test inventory --test grouping`; expect all pass.
- [ ] Commit with `feat(pdf-translators): discover source duplicates from attributed hints and hashes`.

### Task 3: Extract and compare reusable document evidence

**Files:** Create `src/{evidence,compare}.rs`, `tests/evidence.rs`, `tests/common/mod.rs`, and `tests/poppler.rs`.

**Interfaces:** `inspect_pdf(path: &Path, source: &Source, pages: Option<&[u32]>, extractor: &dyn TextExtractor) -> Result<Evidence>`; `compare_evidence(left: &Evidence, right: &Evidence) -> Comparison`; `validate_claim(claim: &Claim, evidence: &Evidence) -> bool`; `TextExtractor::extract(&self, path: &Path, pages: &[u32]) -> Result<Vec<PageText>>`; `PopplerExtractor::new(binary: PathBuf, timeout: Duration) -> Self`. `Comparison` exposes exact-byte equality, normalized-text equality, text overlap, changed-page references, image/annotation differences, and limitations; it does not choose a newer version.

- [ ] Write synthetic-PDF tests asserting: raw embedded PDF date strings and malformed dates survive; page evidence and bookmarks are 1-based; quotes preserve original spelling/punctuation; claim verification normalizes whitespace only; metadata mtime disagreement is represented; files named `v1` and `v3` with conflicting internal revision dates remain unordered by comparison; empty/scanned text is `unknown` rather than equivalent; equal text with different images remains flagged; a text-bearing map booklet is eligible for review/selection despite the old skip marker; a cached evidence record is reused only for matching hash/algorithm; failed reads cannot produce empty successful evidence.
- [ ] Run `cargo test --manifest-path source-selector/Cargo.toml --test evidence`; expect missing-interface compile failures in the red phase; expect compiling assertions after implementation.
- [ ] Implement native PDF structure/metadata inspection with `lopdf`: resolve indirect Info values, retain undecoded date strings and XMP where available, use `get_pages()` and `get_toc()`, and inspect page resources/annotations with recursion/size bounds. Unresolved or unsupported resources are unknown, never zero. Extract text with `PopplerExtractor` using `std::process::Command` and separate arguments (`pdftotext -enc UTF-8 -eol unix`, page ranges, absolute PDF path, `-` for stdout); preserve form-feed page boundaries. Never use a shell. Terminate timed-out children and report tool/parser failures explicitly. Unit tests inject a deterministic extractor; a separately marked ignored Poppler integration test uses a synthetic PDF generated with `lopdf` and runs explicitly during verification. Missing Poppler leaves `scan`, `status`, and packet imports usable and `inspect` reports the specific missing dependency. For competing groups, extract all page text once and cache compressed evidence under the verified content hash. For singletons, inspect the first three pages plus up to ten evenly distributed pages as a cheap text-bearing screen; report the sampled coverage, and request additional pages rather than treating a blank sample as proof of no content. Match text and changed-page signatures with normalized whitespace plus token fingerprints; compare token/page fingerprints with bounded line-alignment code for changed excerpts, not whole-book quadratic character alignment. Preserve case/punctuation in evidence. Similarity scores are measurements only. No automatic OCR: sparse/unreliable text creates an inspect/OCR-required review item for this milestone.
- [ ] Run `cargo test --manifest-path source-selector/Cargo.toml --test evidence --test grouping`; expect all pass.
- [ ] Commit with `feat(pdf-translators): cache source metadata and page-level comparison evidence`.

### Task 4: Evidence packets, Sol judgments, and persistent user rulings

**Files:** Create `src/review.rs`, `tests/review.rs`; extend `src/store.rs` decision/work methods.

**Interfaces:** `prepare_packets(group: &Group, evidence: &[Evidence], role: ActorRole, max_chars: usize) -> Result<Vec<ReviewPacket>>` (CLI default 32,000 Unicode scalar values); `apply_reader_claims(packet: &ReviewPacket, claims: &[Claim], evidence: &[Evidence]) -> Result<Vec<Claim>>`; `propose_decision(group: &Group, evidence: &[Evidence], prior: Option<&Decision>) -> Decision`; `accept_decision(decision: Decision, group: &Group, evidence: &[Evidence]) -> Result<Decision>`; `Store::save_decision(&mut self, decision: &Decision) -> Result<()>`; `Store::current_decisions(&self) -> Result<Vec<Decision>>`.

- [ ] Write tests asserting: exact copies get stable representative selection, with an explicitly established baseline preferred; a lone `.old` source goes to review; dates/filename ordering/text overlap alone never supersede; a reader claim has a checked quote and cannot exclude a differing source; fabricated quotations and unknown page IDs are rejected; Sol/user can split a candidate group into distinct works; equivalent/superseded outcomes require valid representative/successor references within the current group and checked evidence; dangling references, cycles, omitted members, and a selected unreadable source are rejected; changed bytes or group membership reject stale rulings; an unchanged ruling is reused; an uncertain baseline-related candidate is held; textual handouts may be selected and no-text scans are not silently excluded.
- [ ] Run `cargo test --manifest-path source-selector/Cargo.toml --test review`; expect failures before implementing the policy.
- [ ] Implement deterministic proposals for exact copies and uncontested readable text-bearing sources only. Other equivalence, asset, and chronology judgments use imported `sol` or `user` decisions with evidence references; conflicting or incomplete evidence yields `needs_review`. Recompute/bind content hashes for every affected group before accepting and before exporting reviewed outcomes. Require nontrivial exclusion rationale plus supporting in-document evidence; filename/timestamp-only citations are insufficient. A reader never submits final decisions.
- [ ] Implement JSON packet export/import rather than a new API client. Reader packets contain bounded quoted pages and extraction questions; judgment packets contain validated claims, metadata conflicts, content differences, and an explicit decision schema. Every part declares coverage and omissions; splitting a packet cannot silently drop pages or imply full review. Support requesting extra page ranges through the evidence interface. Record actor/model label, role, packet digest, and evidence digest. The current agent workflow can dispatch cheaper readers and use Sol for judgment; the selector itself neither launches models nor incurs provider charges. Truncated/unparseable returns remain pending.
- [ ] Run `cargo test --manifest-path source-selector/Cargo.toml --test review --test evidence`; expect all pass.
- [ ] Commit with `feat(pdf-translators): review source identity and revisions with bound evidence`.

### Task 5: Export the reviewed manifest, queue, and coverage report

**Files:** Create `src/export.rs`, `tests/export.rs`.

**Interfaces:** `build_snapshot(store: &Store) -> Result<SelectionSnapshot>`; `write_exports(snapshot: &SelectionSnapshot, out_dir: &Path) -> Result<std::collections::BTreeMap<String, PathBuf>>`. Output files: `selection.json`, `queue.tsv`, `review.jsonl`, `report.md`, and `baseline-findings.json`.

- [ ] Write tests asserting: one queue item per selected work; selected text-bearing handouts remain eligible; distinct systems/volumes remain separate; unresolved, excluded, stale, superseded, and unreadable sources are absent from the executable queue; excluded sources retain representative/successor links and reasons; source fingerprints and evidence digests survive serialization; archives/errors/partial inspection remain visible in coverage; counts reconcile with inventory; an established DM's Guild selection is recorded as baseline reuse and omitted from the default new-work queue; a mere `.json` sibling does not establish baseline or Markdown completion; changed baseline candidates appear only in separate findings; export failure cannot replace a previously valid complete export set.
- [ ] Run `cargo test --manifest-path source-selector/Cargo.toml --test export`; expect missing-interface compile failures in the red phase; expect compiling assertions after implementation.
- [ ] Implement deterministic ordering and staged generation publication: write a complete generation under work-dir, validate it, then atomically replace a `current.json` generation pointer. Require `--baseline-manifest` input to explicitly establish baseline identities; when absent, identify DM's Guild artifact-bearing candidates as unverified baseline references and hold them for baseline confirmation rather than silently reconverting. The report states this limitation. All non-baseline uncontested works can still proceed. `queue.tsv` columns: work_id, source_id, relative_path, fingerprint_json, title, publisher, book_ids_json. The full JSON remains authoritative.
- [ ] Run `cargo test --manifest-path source-selector/Cargo.toml --test export --test review`; expect all pass.
- [ ] Commit with `feat(pdf-translators): export a reviewed source list with honest coverage`.

### Task 6: Batch CLI, operating guide, and representative pilot

**Files:** Create `src/{main,cli}.rs`, `tests/cli.rs`, `docs/source-selection.md`; add one short link under `BATCH.md` describing the independent Rust selector.

**Interfaces:** `cli::run(args: impl IntoIterator<Item = OsString>) -> Result<ExitCode>`; `main()` delegates to this entry point. Use clap-derived typed subcommands; take source paths as `PathBuf`. All subcommands require `--work-dir`. `scan --root PATH [--muse-csv PATH] [--twins-json PATH] [--rpglib-json PATH] [--baseline-manifest PATH]`; `inspect [--group ID] [--limit N] [--pages RANGE]`; `review export --role reader|sol|user [--limit N] --out PATH`; `review import --file PATH`; `export`; `status`. Commands load the stored root rather than silently defaulting to DM's Guild. Exit codes: 0 success, 1 operational failure, 2 usage/schema error; unresolved cases are reported counts, not a global failure.

- [ ] Write subprocess/CLI tests asserting: `--help` works without model credentials/5etools imports; the work directory inside or aliasing the root is rejected; missing mount refuses without overwriting the previous manifest; an interrupted scan keeps the last complete inventory and resumable caches; one failed inspection does not abort others; hostile/path-traversing imported source references are refused; nonexistent requested group/page is an explicit error; two unchanged runs reuse hashes/evidence/rulings and give the same queue; paths that cannot be represented in TSV remain losslessly recorded in JSON with an explicit coverage warning; `--limit` reports remaining groups; a miniature cross-folder library plus imported decisions produces the expected manifest without opening a network connection or changing any source.
- [ ] Run `cargo test --manifest-path source-selector/Cargo.toml --test cli`; expect entry-point failures before implementation. Add tests for non-UTF-8 filenames, missing/failed/timeout Poppler, and literal filenames containing shell metacharacters; verify these never execute a shell.
- [ ] Implement the CLI and guide, including a sample agent reader/judge packet loop, actor/role requirements, user selection/distinct/defer examples, archived-PDF limitation, baseline confirmation, coverage/error interpretation, source changes, and recovery. CLI `status` is read-only. Explicit `inspect`/packet requests bound expensive reading; no scan command launches a full-library model run.
- [ ] Run `cargo fmt --manifest-path source-selector/Cargo.toml --check`, `cargo clippy --manifest-path source-selector/Cargo.toml --all-targets -- -D warnings`, `cargo build --manifest-path source-selector/Cargo.toml --locked`, `cargo test --manifest-path source-selector/Cargo.toml --locked`, and `cargo test --manifest-path source-selector/Cargo.toml --locked --test poppler -- --ignored`; expect success, with the explicit Poppler round-trip passing. Run the existing batch regression tests with `pytest -q tests/test_batch_dedup.py tests/test_batch_dispatch.py tests/test_batch_main.py tests/test_state_db.py tests/test_chunk_cache.py`; these verify preservation of the existing Python batch only. Run `git diff --check`; expect no errors.
- [ ] Run a read-only representative pilot against a bounded sample from Muse's ambiguous cases, cross-folder twins, distinct bundle contents, and text-bearing aids, with private work data outside the library. Include the known RotDCE candidate pair as a test of grouping, not assumed chronology. Start with at most 10 groups. Record coverage, automatic decisions, unresolved cases, elapsed time, bytes inspected, evidence reuse, and model reading/judgment work separately. Ask the user to rule on unresolved cases; do not invent publication order to finish the pilot. Do not extend unattended exclusion decisions to the whole library until the sample has been reviewed.
- [ ] Commit the CLI/documentation deliverable with `feat(pdf-translators): expose the reviewed source-selection workflow`. Update issue #144 with verification and pilot outcomes; leave it open if the reviewed list or agreed pilot remains outstanding. No changes to milestones 2–4.

## Self-review and execution handoff

Spec coverage: inventory/archives/errors (Task 1), inherited hints and cross-folder candidates (Task 2), content and metadata evidence (Task 3), model-role split and reversible rulings (Task 4), manifest and baseline preservation (Task 5), resumability and reviewed pilot (Task 6). All five Review Focus cases have tests assigned above. Unresolved source chronology remains a user decision, not an implementation shortcut.

Designer calls for review: use external model packets instead of a new provider transport; require explicit baseline identity rather than trusting JSON existence; no automatic targeted OCR in milestone 1, with sparse-text cases kept pending; immutable export generations; ten-group initial pilot. These choices keep the first milestone bounded and let cached evidence support later stages.

Recommended execution: native implementation in this chat, task by task, followed by an independent Sol review of the complete change. The tasks share record schemas and state transitions, so per-task fresh implementers add coordination cost. Cheaper models can read bounded source evidence when the pilot begins. The language is Rust by explicit user instruction. Implementation starts after plan review; establish workspace isolation then, honoring any user preference and keeping unrelated local edits intact.

## Rust dependency references

- [lopdf Document API](https://docs.rs/lopdf/0.47.0/lopdf/struct.Document.html): PDF object access, page mapping, and bookmarks.
- [rusqlite Connection API](https://docs.rs/rusqlite/0.43.0/rusqlite/struct.Connection.html): transactional SQLite state.
- Poppler `pdftotext -h` verified locally; installed version 26.01.0. It is a text extractor invoked from Rust, not a Python dependency.
