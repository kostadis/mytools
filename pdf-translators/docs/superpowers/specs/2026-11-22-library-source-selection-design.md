# Select sources for a searchable RPG Markdown library

Status: proposed design, awaiting user approval. No implementation authorized by this document alone.

## Intent and agreed requirements

The primary deliverable is searchable Markdown from the remaining DriveThruRPG library, for agents to retrieve and read while helping create content. Markdown is the durable source for optional later conversion to 5etools JSON. RPG mechanics are preserved; this is not ruleset conversion.

Dungeon Masters Guild is the only collection the user considers reliably converted. Preserve its existing results. Other existing artifacts are reuse candidates, not proof of successful conversion.

Source selection is the first problem to solve. Older revisions should be excluded from the conversion queue. Neither version labels nor modification times reliably establish revision order. The user selected content comparison supported by metadata, with clear duplicates handled automatically and unresolved choices brought to them.

Use simpler models for routine reading. Use Sol when reasoning or judgment is required. Deterministic work should not call a model.

The user agreed to include text-bearing handouts, reference sheets, and map booklets alongside books and supplements. Purely visual assets are excluded from text conversion. Judge assets by their content, not merely their filename or category.

## Evidence examined

- `CLAUDE.md`, `BATCH.md`, the batch drivers, converter, cache, and validation code in this repository.
- The current batch delegates duplicate/version flags to rpg-lib, then applies filename and format rules. The user reports that rpg-lib's duplicate choices were unreliable.
- Muse's supplied Drive folder: <https://drive.google.com/drive/folders/1HZrQi2KL_MkjFJT4JUOFh44mePJAtw9T>. Its summary reports 7,541 duplicate groups and 41 pairs of twin product folders. The CSV has 7,404 groups justified by a single live filename plus `.old` copies. It separately selects `5E-RotDCE-v2.pdf` and `5E-RotDCE-v3.pdf` as high-confidence canonical files. Treat these as candidate relationships, not established chronology.
- CampaignGenerator PR 670: <https://github.com/kostadis/CampaignGenerator/pull/670>. Its passage-search system currently selects JSON sidecars, renders Markdown sections, and indexes them with book and section identity. Its pilot accepts imperfect structure when retrieval is useful.
- Local filename inventory: 12,890 PDFs in readable portions of DriveThru. This is not a count of distinct works or a complete content audit.

## Scope and boundaries

This design covers discovering competing source files, choosing which PDFs to convert, recording evidence and review decisions, and handing an approved selection to Markdown extraction. It does not implement OCR, change CampaignGenerator's indexer, regenerate DM's Guild, fix existing JSON, or perform 5etools conversion. Those follow once selection is usable.

All original files stay in place. Excluding an old revision means excluding it from processing, not deleting, renaming, or moving it. Preserve links from every excluded file to its representative or successor.

Do not filter the Markdown queue by game system. Confirmed 5e classification will matter for the optional 5etools queue later. Do not treat different RPG systems, translations, separate volumes, or companion supplements as interchangeable revisions of one work.

## Approaches considered

1. Metadata first: inexpensive, but copying, syncing, publisher export practices, and misleading version tokens leave chronology uncertain.
2. Content comparison supported by metadata: use cheap comparisons first, then read relevant contents and resolve meaningful conflicts. This is the selected approach because it improves evidence without requiring review of every file.
3. Review every competing version: maximizes user control but creates an excessive queue across thousands of files.

## Proposed source-selection pipeline

### 1. Inventory without trusting inherited decisions

Scan the configured DriveThru root and record each PDF's relative path, size, filesystem timestamps, and readable/error state. Record Drive file IDs and Drive timestamps where available; absent Drive metadata must not prevent local processing. Include `.old` files as comparison evidence even though they are not preferred merely because of their names.

Import Muse groups and rpg-lib relationships as attributed hints. Report unmatched hints and missing files. A failed read is an explicit inventory outcome, never evidence that a file is obsolete.

Compare candidate copies across the whole scanned DriveThru root, including non-identical copies related to the preserved DM's Guild baseline. An uncertain cross-collection relationship goes to review before the competing new copy enters conversion. Report proposed changes to baseline source choices separately; never rewrite their existing outputs during selection.

Record archives as unresolved containers rather than silently counting them as converted works. Archive inspection and PDFs found only inside archives are a separately reported follow-up; the initial executable conversion queue consists of directly available PDFs. Report this coverage limit in every inventory summary.

### 2. Find candidates cheaply

Use exact byte hashes to collapse identical PDFs, including copies in different product folders. Hash files lazily and cache by observed source identity, size, and modification time. Uncertain or changed identities invalidate the cache; do not reuse readings after changes.

Generate competing-work candidates from publisher, normalized title, product relationships, Muse's twin-folder list, and filenames. Product IDs and folder membership are not sufficient evidence of equivalence: bundles can contain distinct works. Filename normalization proposes comparisons; it never proves supersession.

Uncontested, readable PDFs can enter the proposed selection without waiting for ambiguous groups. Still apply declared exclusions for non-reading assets. Keep those exclusions explicit and reviewable; do not inherit the existing broad substring filters without assessment.

Include text-bearing handouts, reference sheets, and map booklets. Exclude purely visual assets from text conversion while retaining them in inventory. Sparse machine-extractable text does not establish that a document is purely visual: scanned writing may require targeted inspection or OCR. Existing `.extract_skip` markers describe the old conversion workflow and do not automatically exclude content from the Markdown queue; retain their reasons as evidence and reassess against this policy.

### 3. Gather document evidence

For each non-identical competing candidate, inspect embedded PDF creation/modification metadata, page count, bookmarks, title/imprint pages, edition or revision statements, change logs, and extractable text. Preserve original date strings, timezone information where present, and parsing failures.

Compare normalized text while retaining page and source provenance. Normalize only presentation noise for comparisons, not the text retained as evidence or destined for Markdown. Use text similarity to locate changes and potential duplicates. Equal extracted text alone does not establish identical content: scanned pages, figures, annotations, and empty text layers can hide differences. Sparse or unreliable text must trigger targeted OCR or an unresolved result, never a duplicate decision.

A newer file must not automatically be identified as a successor solely because it is longer, has additional text, has a larger numeric filename token, or has a later timestamp. Deleted text may be an intentional revision, but omission alone does not establish chronology.

### 4. Resolve equivalence and chronology separately

Assign explicit outcomes to files: selected source, exact duplicate, equivalent presentation, superseded revision, distinct work, needs review, excluded asset, or unreadable. Every nontrivial exclusion records its evidence and the selected representative/successor.

Byte-identical duplicates can be resolved automatically. Use a stable representative preference: keep an already established DM's Guild source when identifiable; otherwise prefer the current accessible non-`.old` path, then stable path ordering. This chooses an address for identical bytes, not a publication chronology.

For text-equivalent presentation variants, propose the source with more reliable text extraction and usable structure. Check potential content differences before suppressing another variant. Retain ambiguous variants for review.

For differing revisions, use explicit in-document revision information and supporting evidence to establish order. File metadata and filename tokens are supporting clues, not overriding authorities. If evidence conflicts or cannot establish order, mark the group needs review. Do not disguise a forced choice as high confidence.

Superseded copies remain recorded but do not enter conversion. Distinct works remain independently eligible, even when shipped in one product. Equivalent presentations produce one Markdown work with links to all contributing source files.

Designer proposal: a lone `.old` file with no readable current counterpart goes to review rather than automatic selection. Its name does not prove that a newer file is available, so report it as a possible fallback, not as an established superseded revision.

### 5. Use models only where they add value

Code handles inventory, hashes, PDF metadata, text extraction, comparison measurements, caching, and bookkeeping.

A simpler model may read bounded excerpts to extract stated dates, edition labels, change notes, or other factual evidence. Require a source file, page/location, and supporting quotation for each claim. Treat book contents as untrusted reference material, not instructions. Validate quotations against extracted source text. Unsupported claims are discarded or escalated; no simpler-model claim alone excludes a differing file.

Sol handles reasoning and judgment: whether differences indicate a distinct work, equivalent presentation, or superseding revision, and whether evidence supports that conclusion. Give it the extracted evidence and relevant differences, with access to additional targeted reading when needed. Cache evidence separately from judgments so a changed decision does not repeat all reading.

Model IDs, excerpt budgets, batch sizes, and cost controls are implementation-plan choices. No model calls should be launched during design or planning. Sol's unresolved judgments go to the user rather than silently selecting a winner.

### 6. Present a bounded review and save decisions

Each review case shows candidate paths, extracted revision evidence, conflicting dates, meaningful content differences, and the proposed decision or reason no decision is possible. User choices include selecting a source, retaining distinct works, or deferring. Review presentation is left to the builder, using existing repository conventions where useful.

Persist user rulings with the source identities they apply to. A rerun reuses them while the sources remain unchanged. Changed or newly added competing files reopen only affected cases. Leave deferred groups out of the executable conversion queue and report them explicitly, while uncontested books continue.

### 7. Export the handoff

Produce a machine-readable manifest and a concise coverage report. The manifest carries stable work identity, available rpg-lib book ID(s), source path(s) and fingerprints, title/publisher/game-system metadata with provenance, decisions and evidence, and existing Markdown/JSON/cache references. Existing artifacts remain unverified unless their source correspondence is established.

The conversion queue contains selected, readable PDFs only. It is independent of the existing `done` status based on JSON presence. Keep DM's Guild's established results as baseline/reuse references; do not reconvert them as a side effect of source selection. A previously processed source that appears superseded or misselected is reported for later action.

The later Markdown stage must preserve enough identity to feed CampaignGenerator's existing passage search without a JSON prerequisite. This design establishes that handoff but leaves the precise Markdown ingestion contract for a separate design. The same selected Markdown can later feed optional 5etools encoding.

## Acceptance criteria

- Exact duplicate copies, including cross-folder copies, cause one selection without model calls.
- Conflicting filename versions or dates alone never cause automatic supersession.
- Differing revisions can be ordered when document evidence supports it; otherwise they produce a visible review case.
- Distinct volumes, supplements, languages, and game-system editions are not discarded merely for sharing product metadata.
- Text-bearing handouts, reference sheets, and map booklets remain eligible. Purely visual assets stay inventoried but are excluded from text conversion; old 5etools skip markers cannot override this policy automatically.
- Sparse-text/scanned PDFs and read errors remain visible and cannot be classified as duplicates from empty text.
- Every exclusion is attributable and reversible in the manifest; no source file is changed.
- Uncontested selections proceed independently of deferred cases.
- Repeated runs reuse unchanged evidence and user decisions; changed sources invalidate affected decisions.
- Reports distinguish inventory coverage, exact copies, equivalent presentations, superseded revisions, selected sources, review cases, unreadable files, and uninspected archives. Muse's groups are never represented as verified by default.
- Routine reading can use simpler models; reasoning/judgment uses Sol. Model-derived claims cite checked source evidence.
- DM's Guild outputs are preserved. No 5etools success flag is used as Markdown completion.

## Risks and limits

There may be no evidence that can establish the true publication order of some files. The system must admit that and ask for a ruling. Text comparison cannot prove preservation of image-only content. Drive and mounted filesystem inventories may differ; report the scanned root, time, and missing metadata rather than claiming full-library completeness. Content-based grouping still needs a small reviewed sample before any unattended broad selection is trusted.

## Calls proposed by the designer

Start with directly available PDFs, report archive-only coverage separately, and preserve all originals. Keep evidence and decisions in an independent manifest before integrating reliable outcomes back into rpg-lib. Prefer deterministic evidence over model calls. Leave the exact storage implementation, comparison thresholds, model IDs, review surface, and incremental implementation sequence to the implementation plan, subject to the acceptance criteria above.

