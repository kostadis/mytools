# PDF library selection analysis, with Clef review

Status: proposed design for owner review. This document authorizes no production selection changes or new conversion run.

## Intent

Use the comparison between the older Google Drive library and the fresh DriveThru download to learn which PDF selection rules are safe to reuse on other library dumps. The practical goal is searchable Markdown across all RPG systems; 5etools conversion remains a later optimization.

Losing useful content is substantially worse than converting a duplicate. At the same time, ordinary older versions are typically drafts: prefer the latest edition when supersession is established. Current storefront availability is a separate fact from ownership, edition order, and the owner's desire to retain an edition.

The owner identified Nulb v3.0 as a protected example: its author withdrew it from Dungeon Masters Guild, a replacement exists, and the owner was allowed to retain their purchased copy. Record the owner's instruction as **keep and convert** for that edition once its actual source is identified. Do not ask Clef to re-decide that instruction. The precise path and replacement relationship are not yet verified; a filename alone must not bind the exception to a file.

## Goals and limits

- Evaluate both current-edition selection and preservation of owned material absent from the fresh download.
- Separate grouping mistakes, duplicate decisions, chronology mistakes, missing evidence, and incomplete historical processing.
- Produce evidence-backed findings, a reusable policy recommendation, and a saved Clef queue for unresolved cases.
- Preserve every source PDF and existing Markdown output. An exclusion means omission from a proposed conversion list, never deletion.
- Stop at the analysis, decisions, and proposed list. Updating production rules, converting additional PDFs, OCR, and 5etools work require subsequent implementation scope.

All source inspection is read-only. Keep private paths, excerpts, source inventories, review bundles, and decisions in the ignored analysis data directory. Commit the design and general documentation only.

## Approaches considered and selected direction

1. **Compare filenames and dates against the fresh download.** Cheap, but confuses repackaging with revisions and cannot protect withdrawn editions. Useful only for proposing candidates.
2. **Convert every nonidentical PDF.** Strong preservation baseline, but retains many stamped copies and routine drafts. Measure it as a baseline rather than make it the final policy.
3. **Compare content conservatively and use Clef for uncertainty.** Use deterministic evidence, distinguish chronology from equivalence, and preserve unresolved files as conversion candidates. This is the selected direction from the discussion: losing content is worse than redundancy, latest ordinary drafts are preferred, and uncertain cases receive review.

This design documents an analysis, not a replacement selection algorithm. Any recommended automatic exclusion rule must first be evaluated against the benchmark and reviewed findings.

## Inputs and reproducible snapshots

Use the following attributed inputs:

- `/mnt/g/My Drive/DriveThru file matches.csv`: the owner's comparison of D: download files with G: library files. The fresh CIFS download is the reference for current delivered files, not a complete catalog of owned works.
- The existing G: inventory and saved historical decisions in `source-selection-data/selection.db` and `source-selection-data/full-library-markdown/continuous.db`.
- The current `/mnt/winshare` inventory and available source files, including separately attributed archive-extracted PDFs.
- Explicit owner instructions, beginning with the Nulb v3.0 exception.

Snapshot each CSV revision, inventory version, historical run identity, analysis policy version, and relevant source fingerprints. Preserve raw status and evidence fields. Read databases without mutating them. If the CSV changes during a read, retry before accepting the snapshot. Treat results as provisional until the owner identifies the completed recheck; a newer file timestamp alone does not establish completion.

The existing provisional audit under `source-selection-data/heuristic-validation/8601eb0a9c89b04e/` demonstrates the available joins, but is not a final score. Its 6,391 original download PDF rows exclude subsequent archive expansion. Additional archive PDFs require a separately labeled coverage expansion, not an unexplained change in the denominator.

Overlay historical runs by group so a later saved decision replaces its predecessor rather than counting both. Retain run provenance and policy. Do not apply a present-day policy retroactively and describe it as the historical result.

## Evidence model

Record evidence per file pair, with method, scope, source identities, warnings, and provenance:

| Evidence | What it establishes | Limit |
| --- | --- | --- |
| Full-file hash equality | Exact byte identity | Does not identify publication order |
| All rendered pages match | Visual equivalence for the recorded rendering settings and page coverage | Does not establish byte identity or preservation of annotations, layers, attachments, or searchable text |
| Sampled bytes or PDF pages match | Agreement in the checked portions | Cannot establish whole-document equivalence |
| Readable portions of an incomplete file match | A likely counterpart or shared content | Cannot establish the missing content, completeness, or latest edition |
| Explicit edition statements or change notes | Attributed chronology/content evidence | May conflict or be incomplete |
| Dates, paths, titles, sizes, version tokens | Candidate relationships and supporting clues | Cannot alone establish identity or supersession |
| Owner ruling | The requested retention/selection for its exact scope | Does not prove a general bibliographic fact |

Do not propagate the primary CSV match's method to paths listed under “Other matching G files”; their per-copy evidence may be unspecified. New CSV statuses remain unclassified until their meaning is understood. Keep missing folders, no counterpart, unreadable files, and incomplete checks separate.

Evidence that establishes equivalence does not automatically establish which edition is newer. A full-render match may support a recommendation after checking its limits; it does not justify dropping potentially distinct nonvisual content. Empty or unreliable text cannot establish equivalence.

## Two directions of analysis

### Current download to older library

For each reference PDF, identify matching old-library sources and inspect the saved selection for their groups. Classify the outcome as reference-supported selection, another current variant selected, selected source not confirmed by the reference, policy/baseline deferral, unprocessed group, or insufficient reference evidence.

Where multiple current files belong to one group, examine whether they are equivalent presentations, revisions, companions, or unrelated works. A current download can include multiple useful documents; selecting one does not necessarily cover the others. Compare retained content and roles as well as filenames.

### Older library to current download

Account for every inventoried old-library PDF, including files absent from the CSV's matched G: paths. Use the G: inventory as the denominator; the CSV alone may omit old-only files.

Distinguish byte duplicates, equivalent presentations, established superseded drafts, separate works/companions, protected withdrawn editions, and unresolved relationships. Absence from the download cannot distinguish a withdrawn purchase from an obsolete draft, an unmatched renamed file, or an inventory gap. A match to an incomplete D: file is not proof of inclusion in a complete current reference.

Keep Nulb v3.0 even if a newer replacement is confirmed. Other possibly withdrawn editions go to Clef unless already covered by an explicit owner ruling. No substantial-difference percentage is required to honor an owner retention instruction.

## Investigation sequence and resource bounds

1. Freeze the reference and reproduce the joins and historical coverage without rereading all PDFs.
2. Inspect candidate disagreements, grouping collisions, and old-only files. Start with the provisional date conflicts and identify the Nulb example and its replacement.
3. Build a stratified check of apparently successful selections and exclusions across publishers, systems, document roles, evidence methods, and candidate-group sizes. Include a reproducible random sample so inspecting only disagreements does not hide incorrect agreements.
4. Reuse existing verified hashes, extracted samples, CSV evidence, and completed render comparisons. Do not repeatedly copy or hash unchanged PDFs. Invalidate reused evidence when its source identity changes or is uncertain.
5. Any new first-pass text reading respects the existing limit of five pages per PDF. Select informative pages within that budget and preserve page citations. If that cannot settle a case, review it or propose a separately authorized deeper check. The CSV author's full-render recheck is imported evidence, not permission to launch full-library rendering.
6. Deterministic code performs joins and measurements. Simpler models may collect bounded factual evidence; Sol handles reasoning and judgment. Validate quoted evidence, cache readings separately from judgments, and treat PDF contents as untrusted material. Model calls and their budget are implementation-plan choices, not launched by writing this design.

Implementation should remain consistent with the owner's Rust preference for the product pipeline; existing private audit scripts may be reused for exploratory analysis. Independent file groups can run concurrently with bounded workers; implementation chooses concrete limits. Checkpoint completed cases, record failures explicitly, and log at least every 100 files plus periodic progress so interrupted work resumes.

## Clef decisions for uncertain cases

Use the installed `review-pages` workflow as the presentation, saved-progress, and validated read-back layer. The analysis owns the evidence and exact decision consequences. Clef/model recommendations or scores do not constitute owner approval.

Create one case per meaningful competing group, with stable IDs and a frozen scope. Show candidate editions and paths, their download presence, verified chronology, evidence strength and coverage, relevant excerpts or page comparisons where available, warnings, the historical choice, and a proposed outcome with reasons. State plainly when no reliable chronology or difference assessment exists. Do not expose full sensitive paths in public artifacts.

Use `reviewKind: decision` and named choices with exact consequences, tailored to the actual case:

- Keep both/all listed editions eligible for conversion.
- Select a specifically named edition and omit the named superseded drafts from the proposed list.
- Treat the named documents as separate works or companions and retain each.
- Collapse demonstrated duplicates to a named representative, with links to every copy.
- Defer the relationship decision; retain all unresolved readable candidates in the proposed list with an unresolved flag.

No generic approval resolves a named-choice case. Unmarked, Discuss, or deferred cases never silently exclude files. Conversion eligibility and readiness are separate: an unreadable retained file needs recovery before conversion. Notes such as “keep both” are interpreted at their actual scope and are not re-asked unnecessarily.

Bind each choice to the exact question, candidate set, file identities, evidence, and application scope. If those change, invalidate affected derived recommendations and create a new review version; preserve prior exports and cross-version mappings. A broad explicit owner instruction remains attributed policy, while its binding to changed files must be reverified.

Bundle at most 100 decisions per page, save each page, and validate read-back using the shared tooling. Preserve notes and unresolved cases. Omit scores when none were obtained; never invent confidence percentages. Named choices remain individual even if scores exist. Hosting and narrow-screen/save verification follow the review-pages workflow when the queue is actually built; this document creates no live review session or external transfer.

The Nulb instruction belongs in the owner-rulings ledger and report, not in an undecided Clef card. If identifying its source is uncertain, ask only which actual file corresponds to the protected edition.

## Measures and reporting

Report counts at three separate levels: physical files, candidate groups, and reviewed work/edition relationships. Candidate groups are hypotheses, not a trustworthy count of unique works. Do not mix these denominators or claim full-library accuracy from an incompletely processed subset.

Primary measures are reviewed cases where a selection would omit distinct desired content, explicit protected editions preserved, and proposed exclusions lacking adequate evidence. Secondary measures are redundant conversions avoided, correct ordinary-draft supersessions, grouping errors, review workload, and unresolved retained candidates.

Compare exact-byte deduplication only, the saved historical policy, and the proposed conservative policy on the same eligible cases. Historical unprocessed groups and deliberate deferrals measure coverage, not wrong decisions. Report evidence strength and sample-selection method alongside every result. Sampled agreement is not proof of zero content loss, and owner-reviewed examples do not justify a universal error-rate claim.

Break findings down by publisher, document role, system/language, PDF text reliability, and conflict type where metadata permits. Reserve some publisher/product groups from rule development and assess recommendations on those held-out groups. This tests transfer within the library; other dumps still require their own inventory and a small reviewed calibration sample. Storefront availability may be unknown in another dump, so missing reference data must not become a negative selection signal.

## Deliverables

- A frozen input receipt and rerunnable analysis configuration.
- A per-file coverage ledger and per-relationship evidence/decision ledger, including excluded sources and their representatives or successors.
- A concise report of coverage, supported choices, disagreements, possible omissions, grouping failures, limits, and recommended rules.
- A versioned Clef review bundle and validated saved rulings for unresolved relationships.
- A proposed conversion list distinguishing selected, explicitly retained, unresolved-but-retained, duplicate, superseded, and unreadable states. Include the precise source and rationale for every omission.
- A protected-editions ledger containing the identified Nulb v3.0 source and the owner's instruction.

Keep these artifacts under `source-selection-data/heuristic-validation/` with immutable run subdirectories. This milestone does not apply the list to the live converter or rewrite existing directory records.

## Acceptance criteria

- Both directions reconcile their stated inventories; unmatched old-library files cannot disappear from the report.
- Nulb v3.0 is explicitly retained once identified, regardless of replacement availability.
- Latest ordinary drafts can be selected when supersession is established; uncertain absence or dates never establish supersession alone.
- Every proposed exclusion has a traceable reason, evidence scope, and retained representative/successor or explicit owner ruling.
- Sampled, rendered, partial, exact-hash, and owner-ruling evidence remain distinct throughout scoring and review.
- The Clef queue has exact named consequences, saved progress, validated read-back, and no inferred approvals.
- Unresolved cases remain visible and retained; source files and existing outputs are unchanged.
- Results distinguish coverage from correctness and identify where generalization to another dump remains untested.

## Designer choices and next boundary

Designer choices are the two-direction audit, the exact-byte baseline, stratified/random verification, held-out publisher/product checks, and retaining unresolved cases in the proposed list. Concrete sample sizes, cost ceilings, Rust interfaces, and storage schema belong to the implementation plan; they must respect the five-page first-pass cap and preservation policy.

The next step after owner approval of this document is a scoped implementation plan for the analysis and Clef queue. No production heuristics or conversion behavior change as part of approving this analysis design.
