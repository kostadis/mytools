# Library Selection Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible, read-only audit of current-edition choices and preservation of owned editions, with a Clef queue and a proposed conversion list.

**Architecture:** Add an isolated `analysis` module and CLI command family to the existing Rust selector. Freeze reference inputs, reconstruct historical decisions without changing them, analyze relationships in both directions, then export review cases and consume validated owner rulings. All derived state lives in a new private run directory; no command applies decisions to production.

**Tech Stack:** Rust 1.95, existing serde/csv/rusqlite/sha2/clap dependencies, Unicode normalization and case-folding helpers, SQLite backup support, and the installed Python review-pages builder/read-back tools. Native Poppler sampling remains an explicit bounded follow-up, not part of an automatic whole-library pass.

**Spec:** `pdf-translators/docs/superpowers/specs/2026-11-24-library-selection-analysis-design.md` (approved by owner).

## Global Constraints

- “Losing useful content is substantially worse than converting a duplicate.”
- “At the same time, ordinary older versions are typically drafts: prefer the latest edition when supersession is established.”
- “All source inspection is read-only.”
- “Any new first-pass text reading respects the existing limit of five pages per PDF.”
- “Deterministic code performs joins and measurements. Simpler models may collect bounded factual evidence; Sol handles reasoning and judgment.”
- “No generic approval resolves a named-choice case. Unmarked, Discuss, or deferred cases never silently exclude files.”
- “The Nulb instruction belongs in the owner-rulings ledger and report, not in an undecided Clef card.”
- “This milestone does not apply the list to the live converter or rewrite existing directory records.”
- Keep private library data under ignored `pdf-translators/source-selection-data/heuristic-validation/`; only synthetic fixtures enter Git.
- No automatic OCR, whole-document extraction/rendering, model calls, source copying, repeated PDF hashing, conversion service changes, or external evidence transfer.

## Review Focus

1. Windows CSV paths containing commas, embedded newlines, Unicode variants, or case collisions must resolve without merging distinct files silently (Task 1).
2. Older runs, interrupted runs, or a group spanning multiple current PDFs must not inflate success or classify an unprocessed choice as incorrect (Tasks 2–3).
3. Old-only withdrawn editions, incomplete references, and unknown evidence labels must remain visible and eligible rather than become automatic exclusions (Tasks 1, 3).
4. A new candidate or changed evidence must invalidate only affected file-bound rulings, while preserving saved notes and the owner's explicit retention instruction (Tasks 3–5).
5. Interrupted writes and stale/foreign Clef exports must not replace completed evidence or create approvals (Tasks 1, 4–5).

## Files and interfaces

Create `source-selector/src/analysis/{mod,models,inputs,history,audit,sampling,review,report}.rs` beneath `pdf-translators/`. `models` owns typed records; the other files own their named stage. Add `src/cli/analysis.rs`, register it in `src/cli.rs`, and expose `pub mod analysis` in `src/lib.rs`. Reuse `Store::open_readonly`, source models, digest helpers, and evidence readers where they fit; do not reuse methods that create authority locks or mutate production state.

Create integration tests `tests/analysis_{inputs,history,audit,review,cli}.rs` and shared synthetic fixture helpers under `tests/common/`. Add `pdf-translators/docs/library-selection-analysis.md` with the operational commands and reference-completion procedure.

All Rust paths below are relative to `pdf-translators/source-selector/`. Commands run from that directory unless stated otherwise.

Shared JSON types are versioned with `schema_version: 1`:

- `AnalysisConfig`: CSV path; D/G Windows root mappings; G inventory DB; current inventory DB; historical continuous DB/status; explicitly ordered historical run IDs (oldest first); owner-rulings JSON path; evidence-import paths; `reference_complete: bool`; `sample_seed: String`; `sample_per_stratum: usize` (default 5); `holdout_percent: u8` (default 20). Omit model configuration: this milestone launches none.
- `FrozenInputs`: input receipts, local snapshot paths, inventory snapshots, normalized reference rows, and run-order provenance. Receipt fields include original path, SHA-256 of snapshot, size, snapshot time, and source observation. No source PDF hashes are computed by this stage.
- `PairEvidence`: pair of source identities, method enum (`ExactBytes`, `AllRenderedPages`, `SampledBytes`, `SampledPages`, `PartialReference`, `UnspecifiedOtherCopy`, `Unconfirmed`), page/byte scope, original status, raw evidence, warnings, provenance. Evidence can support identity without establishing chronology.
- `RetentionRule`: owner wording and provenance; `unbound` or a verified source/edition binding; action (`KeepAndConvert`); explicit relationship scope. Nulb starts unbound until the actual source is established.
- `HistoricalView`: one attributed effective historical observation per group, its selected sources, policy/baseline deferrals, run ID, and unprocessed coverage. Never make the Python prototype's permissive fallback run ordering authoritative.
- `AuditResult`: per-reference outcomes, every old PDF's coverage, relationships, proposal states, evidence links, protected editions, unresolved cases, and denominator receipts. Proposal states: `Selected`, `ExplicitlyRetained`, `UnresolvedRetained`, `Duplicate`, `Superseded`, `UnreadableRetained`.
- `ReviewCase`: stable case ID, question, candidate identities/fingerprints, evidence digest, exact named outcomes, recommendation and warnings; `ReviewResults` preserves validated named picks, Discuss/unmarked states, notes, and export provenance.

Designer implementation choices: first audit imports existing evidence only; initial sampling selects up to 5 relationships per stratum, and 20% of publisher groups are held out deterministically. Both are reported and configurable; neither implies statistical confidence. If publisher is unknown, hold out whole product-folder groups and report that fallback. No rule learning or unattended model work is hidden in these settings.

---

### Task 1: Freeze and validate reference inputs

**Files:** create `src/analysis/{mod,models,inputs}.rs`, `tests/analysis_inputs.rs`; modify `src/lib.rs`, `Cargo.toml`, `Cargo.lock`.

**Interfaces:** `inputs::freeze(config: &AnalysisConfig, output: &Path) -> Result<FrozenInputs>`; `inputs::normalize_windows_relative(path: &str, root: &str) -> Result<String>`. `freeze` produces an immutable receipt and copies of non-PDF inputs, and SQLite snapshots via a read-only source connection and backup destination in the run directory. An existing run with different inputs is rejected, not overwritten.

- [ ] Write tests `csv_paths_preserve_commas_and_newlines`, `unicode_path_collisions_are_reported`, `unknown_and_partial_methods_do_not_confirm_full_match`, and `changed_or_interrupted_snapshot_is_not_committed`. Assert NFC plus full case folding for comparison, retain original spelling, split other-copy paths on newlines, reject paths outside declared roots and traversal, and preserve the primary/other-copy evidence distinction. Unknown status remains unconfirmed. Duplicate reference paths or normalization collisions yield a diagnostic, never a silent overwrite. Use injected read hooks to simulate a CSV changing mid-read.
- [ ] Run `cargo test --test analysis_inputs`; confirm failures because the analysis interfaces do not yet exist.
- [ ] Implement the models and snapshot stage. Validate CSV headers even for an empty CSV; accept UTF-8 BOM and RFC CSV quoting. Preserve all raw evidence. Add Unicode helper dependencies and rusqlite `backup` feature only as needed; use the existing Rust version. Write temporary artifacts followed by atomic rename and receipt-last publication. Hash non-PDF snapshots once; do not open any PDF.
- [ ] Run `cargo test --test analysis_inputs`; require all cases pass, including read-only SQLite source checks and repeated identical snapshot reuse.
- [ ] Commit only the module, dependency updates, and synthetic tests with message `feat: freeze library analysis inputs without modifying sources`.

### Task 2: Reconstruct historical decisions with explicit provenance

**Files:** create `src/analysis/history.rs`, `tests/analysis_history.rs`; extend `models.rs` and `mod.rs`.

**Interfaces:** `history::load(inputs: &FrozenInputs) -> Result<HistoricalView>`. Read only snapshot DBs. Consume existing `sources`, `groups`, `continuous_groups`, and final status shapes; isolate their deserialization adapters from the audit logic.

- [ ] Write `latest_saved_group_overlays_older_without_double_vote`, `unprocessed_and_deferred_are_not_bad_choices`, and `unknown_run_order_is_rejected`. Synthetic runs must include an older-only group, an updated group, multiple current files in one group, a baseline hold, an unprocessed group, and an unsupported historical policy. Assert a missing observation is coverage only; unsupported policy remains attributed and unscored with a warning.
- [ ] Run `cargo test --test analysis_history`; confirm failure for the missing loader.
- [ ] Implement `load`, requiring explicit ordering for all included runs and checking the supplied latest-run status. Carry old-only observations forward with their original run identity, without treating them as observations from the latest run. Reuse saved exact hashes as source-bound evidence, never as chronology. Report stale inventory membership and source fingerprint mismatches.
- [ ] Run `cargo test --test analysis_history`; require all cases pass, source DB receipts unchanged, and one effective observation per group.
- [ ] Commit with message `feat: reconstruct historical selection coverage for analysis`.

### Task 3: Audit both directions and select an investigation sample

**Files:** create `src/analysis/{audit,sampling}.rs`, `tests/analysis_audit.rs`; extend shared models.

**Interfaces:** `audit::compare(inputs: &FrozenInputs, history: &HistoricalView, rules: &[RetentionRule]) -> Result<AuditResult>`; `sampling::select(audit: &AuditResult, config: &AnalysisConfig) -> Result<SampleManifest>`. The sample is a worklist, not an automatic evidence-reading job.

- [ ] Write `old_only_sources_reconcile_to_inventory`, `nulb_keep_overrides_replacement_without_reasking`, `unbound_nulb_rule_does_not_guess_by_name`, `uncertainty_and_partial_matches_remain_retained`, and `multiple_current_variants_are_not_one_work`. Assert every old PDF has a coverage row; every proposed omission links to a representative/successor or explicit ruling; a CreationDate later than another file's ModDate cannot establish supersession. Distinct systems/languages/companions remain separate or unresolved.
- [ ] Write `sample_is_reproducible_and_publisher_holdouts_do_not_leak`. Assert fixed configuration yields identical selection, at most 5 ordinary sample relationships per stratum, 20% deterministic publisher assignment, folder fallback when publisher is unknown, no product split across development/holdout, and inclusion of all flagged disagreements independently of the random sample. Changed seeds alter sampled membership without changing the underlying audit counts.
- [ ] Run `cargo test --test analysis_audit`; confirm failure for missing interfaces.
- [ ] Implement the audit and sample selection. Preserve the reference-direction categories in the spec; use all inventoried G: sources for reverse coverage, including PDFs absent from any CSV path. Keep archive-expanded reference coverage separate. A sampled match may support correspondence but cannot alone justify exclusion. Apply no new automatic content-equivalence rule. Use explicit owner/evidence imports for established chronology, full comparisons, and retention; otherwise retain unresolved candidates. Protect an exact verified Nulb binding; leave an unbound retention rule visible as an unfinished identification task.
- [ ] Run `cargo test --test analysis_audit`; require reconciliation and exclusion invariants across all synthetic cases. Include a changed/new candidate test that invalidates file-bound decisions while retaining broad owner instructions as policy.
- [ ] Commit with message `feat: audit selection and preservation in both directions`.

### Task 4: Export Clef cases with exact decision scopes

**Files:** create `src/analysis/review.rs`, `tests/analysis_review.rs`; extend shared models.

**Interfaces:** `review::export_cases(audit: &AuditResult, out: &Path) -> Result<ReviewManifest>`. Produces versioned `review_items.json`, `review_map.json`, and case membership receipts compatible with `/home/kostadis/.codex/skills/review-pages/references/inputs.md`. It does not host pages, score cases, or invent approvals.

- [ ] Write `named_choices_have_exact_non_destructive_outcomes`, `known_owner_ruling_is_not_an_undecided_card`, and `changed_case_cannot_overwrite_frozen_bundle`. Assert `reviewKind: decision`, `choiceOnly: true`, every pick has complete `pickTexts` plus an exact map action, and defer retains every unresolved readable candidate. Verify HTML-sensitive titles/excerpts are escaped and case identity includes candidates, fingerprints, evidence, and scope. Unreadable retained files are never advertised as ready to convert.
- [ ] Run `cargo test --test analysis_review`; confirm failure for missing exporter.
- [ ] Implement the exporter using named edition labels and descriptive consequences. Include historical choice, chronology limitations, content evidence coverage, download presence, and reasons. Keep complete private paths in evidence details only; use relative labels on cards. Map actions only to analysis proposal states. Export without scores and keep named choices individual.
- [ ] Run `cargo test --test analysis_review`. On a synthetic export also run the installed `review-pages/scripts/build_pages.py --items ... --map ... --out ... --page-size 100`; require valid membership receipts and no more than 100 items on a page. This fixture validation need not launch a server.
- [ ] Commit with message `feat: export evidence-bound Clef selection cases`.

### Task 5: Read back rulings and produce qualified reports

**Files:** extend `src/analysis/review.rs`; create `src/analysis/report.rs`; extend `tests/analysis_review.rs` and create report assertions within `tests/analysis_audit.rs`.

**Interfaces:** `review::load_results(manifest: &ReviewManifest, normalized: &Path) -> Result<ReviewResults>`; `audit::with_rulings(audit: &AuditResult, results: &ReviewResults) -> Result<AuditResult>`; `report::write(audit: &AuditResult, sample: &SampleManifest, out: &Path) -> Result<()>`. Inputs come from the installed `read_results.py`, which owns raw export validation; Rust additionally checks case membership and exact scope bindings before applying only to analysis state.

- [ ] Write `foreign_or_stale_picks_are_rejected`, `discuss_unmarked_and_notes_preserve_uncertainty`, and `report_separates_files_groups_relationships_and_coverage`. Assert notes survive byte-for-byte, generic approve cannot resolve choice-only cases, and source-bound changed evidence reopens a case. A saved note requiring interpretation stays pending; clear “keep both” instructions can be recorded with scope and provenance. Compare exact-byte baseline, historical policy, and conservative proposal only on like-for-like eligible cases; report unprocessed coverage separately.
- [ ] Run `cargo test --test analysis_review` and `cargo test --test analysis_audit`; confirm new cases fail.
- [ ] Implement read-back and output: `summary.json`, `report.md`, `reference-rows.csv`, `old-library-files.csv`, `relationships.jsonl`, `proposed-conversion-list.json`, `protected-editions.json`, and `sample-manifest.json`. Report evidence methods, missing/partial references, protected/unbound retention rules, denominator receipts, split/sample settings, and unresolved retained cases. Mark reports provisional unless the frozen configuration contains the owner's reference-completion attestation. No unsupported overall accuracy percentage or count of “unique works” from candidate groups.
- [ ] Run both test targets; require all pass, no changes to frozen inputs, and conservation of every old source and its disposition. Report candidate errors separately from confirmed reviewed omissions.
- [ ] Commit with message `feat: validate review rulings and report preservation outcomes`.

### Task 6: Add resumable CLI and run a bounded real-data audit

**Files:** create `src/cli/analysis.rs`, `tests/analysis_cli.rs`, `../docs/library-selection-analysis.md`; modify `src/cli.rs` and `src/analysis/mod.rs`.

**Interfaces:** add `analysis run --config PATH --output DIR`, `analysis review-export --run DIR --output DIR`, and `analysis review-import --run DIR --results PATH --output DIR`. Register an `Analysis` nested subcommand and keep dispatch isolated from scan/Markdown commands. Stage receipts provide resume boundaries; imported rulings produce a new derived run, never overwrite the original.

- [ ] Write CLI tests `analysis_does_not_touch_production_or_pdfs`, `resume_preserves_completed_stages`, `changed_inputs_require_new_run`, and `review_import_only_changes_derived_outputs`. Put synthetic PDFs and DBs behind write-denied permissions, compare input content/metadata before and after, simulate interrupted stage output, and reject an output directory overlapping any source/input path. Assert progress JSON/logging at every 100 records and at least every 30 seconds, including explicit stage, totals, remaining, and errors. Logging tests use an injected clock, not real sleeps.
- [ ] Run `cargo test --test analysis_cli`; confirm failure for missing commands.
- [ ] Implement CLI orchestration with atomic stage publication, configuration/receipt validation on resume, and explicit diagnostics. The evidence-import validator accepts only source-bound method/scope/provenance records; model evidence additionally requires model ID, Sol for judgment, and checked page citations for factual quotations. Unknown/unbound evidence stays unconfirmed. This task adds no model endpoint or new extraction subprocess. Document how to import a later completed CSV, bind Nulb after verified identification, obtain bounded evidence using the existing five-page tools, and import finished all-render/partial checks without exaggerating them.
- [ ] Run `cargo fmt --check` and `cargo test`; require the normal suite passes, with optional system tests reported accurately. Run `cargo test --test analysis_cli` against a temporary output directory and confirm no source/production mutations.
- [ ] Run a private provisional audit against the current frozen CSV and input DB snapshots. First identify the available inventory paths and explicit historical run order from their receipts; do not guess. Use the recorded defaults of 5 per stratum and a 20% holdout. Reconcile the original 6,391 reference PDF rows for that snapshot; report expanded archive scope separately. Investigate the Nulb binding using existing inventory/evidence; if it cannot be verified, report the unbound protection rather than silently selecting a filename. Produce the first evidence-only Clef queue without launching paid calls or additional PDF reads.
- [ ] Build and serve the frozen queue through `review-pages` if there are unresolved cases. Follow its durable hosting and read-back instructions; for more than three total decisions use its default private Tailscale route. Verify navigation, narrow-screen layout, Save to VM, reload, and stale-save rejection on synthetic fixtures; never create synthetic votes in the live queue. Preserve all existing services. Hand over the actual queue URL and counts, with the instruction to save each page. Leave substantive review decisions to the owner.
- [ ] Commit code, synthetic tests, and general run instructions with message `feat: expose resumable library analysis workflow`. Do not commit private runs or capability URLs. Report provisional findings, outstanding evidence and Nulb binding status, and the path to the proposed list. Stop before applying any production change.

## Self-review and handoff

Spec coverage: Tasks 1–2 cover snapshots and historical attribution; Task 3 covers both directions, retention, sampling and transfer checks; Tasks 4–5 cover Clef, rulings and all report/list deliverables; Task 6 covers resume, logging, bounded evidence operations and an initial real-data run. All five Review Focus conditions have explicit test owners. Shared names/signatures are defined above and reused consistently.

The initial run is deliberately provisional while the owner's CSV recheck remains unfinished. Completion of this implementation does not mean all relationships have been adjudicated. Its useful output is a reproducible audit plus a saved, actionable review queue that cannot silently lose candidates.

Recommended execution: native implementation in this session, task by task, followed by one independent branch review. The tasks share a typed audit model and read-only boundary; keeping implementation in one context reduces interface churn. Review-page owner decisions occur after the queue is available and do not prevent completing or testing the analysis software.
