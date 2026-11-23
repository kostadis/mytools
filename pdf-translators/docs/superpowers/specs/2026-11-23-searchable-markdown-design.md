# Select recent PDF sources and create searchable Markdown

Status: proposed design for user review. This document authorizes no implementation or conversion run by itself.

Review in brief: select an unambiguous newest source from embedded modification/creation metadata; keep alternatives and ambiguous cases recorded; convert the complete winning PDF through native text extraction into page-based Markdown; checkpoint completed ranges; publish one current search copy per work. Keep the existing selection exports compatible by adding a separate Markdown queue. Start with four cached pilot sources and 61 pages. OCR, layout reconstruction, automatic index promotion and 5etools encoding remain separate work.

## Purpose and approved requirements

The primary deliverable is a searchable Markdown library for finding material while creating content. Markdown is the durable base; optional 5etools encoding and CampaignGenerator search integration remain later work. Include all RPG systems and text-bearing play aids, not just D&D 5e. Preserve mechanics and source wording.

The user selected this operational source preference: use the PDF's internal modification date, falling back to its internal creation date, to choose the most recent file to scan. Missing, invalid, tied, or conflicting dates are flagged. Filename version numbers and filesystem timestamps do not override that preference.

The user also accepted page-by-page searchable Markdown as the initial output. The five-page limit applies to first-pass source inspection. Converting an approved source reads its **entire PDF**, not just its five-page sample. Unresolved source choices, OCR cases and layout cleanup can be decided later.

Original PDFs and established Dungeon Masters Guild conversion outputs must remain unchanged. Existing JSON alone is not proof of Markdown completion. Use deterministic Rust code for metadata selection, extraction, caching and bookkeeping; ordinary date selection and native conversion require no model calls. Simpler models remain available for factual reading, and Sol for judgment when a separate review needs it.

## Evidence and starting point

The Rust selector already inventories files, hashes possible copies, caches evidence, creates candidate groups, extracts bounded page samples and records review decisions. It supports presentation candidates and automatic source/page/quote citation binding. Pilot 02 compared four new product families, 18 paths and nine byte contents using 45 sampled pages. All 27 factual claims bound automatically and passed Sol's audit. Different presentation contents stayed deferred under the earlier proof-oriented selection policy.

This design adds a user-approved **selection preference**, so those groups can progress without claiming that their PDFs are visually identical or that publication chronology was proved. The current OCR-only `converters/extract_markdown.py` uses Marker or Mistral; the proposed native-text route is a new Rust capability using installed Poppler.

The full-library hash scan continues independently. It started before the latest grouping changes. Refresh its completed scan with the updated executable, reusing cached hashes, before applying this policy to its authoritative groups. An incomplete scan must not publish a falsely complete library selection.

## Approaches considered

1. **Prove every differing file equivalent or superseded before conversion.** Conservative, but both pilots show this can leave useful sources deferred despite good identification evidence.
2. **Select by embedded dates, then create a native-text search copy.** Selected direction: follows the user's recency preference and searchable-Markdown goal, costs no model calls for routine work, and keeps alternatives available.
3. **OCR or semantically reconstruct every book first.** Can improve image-only text and layout, but adds runtime, dependencies and possibly API cost. Defer it until native extraction exposes which sources need it.

## 1. Selection units and authority

A candidate group is a proposal to compare files, not proof of one work. Apply recency automatically only within an eligible work family:

- An existing reviewed work boundary; or an existing filename/presentation candidate group whose non-identical members share a publisher and product folder, with no explicit conflicting language, volume, document-role or ruleset/edition qualifier.
- Product-folder membership alone is insufficient. Bundles retain separate source groups. Do not rank all files in a product against each other.
- Coarse rpg-lib/Muse relationships, generic cross-product titles, cross-publisher relationships, or explicit protected-qualifier conflicts remain identity-review cases. Expanding their eligibility is separate work.
- Exact byte aliases may be recognized across folders; they are one content candidate and do not create a date tie. An alias that joins a wider ambiguous family cannot make that entire family eligible automatically.

For the initial implementation, evaluate the **entire existing connected component**. Do not split out and process a seemingly safe local subset when a broader relationship or alias has connected it to an ambiguous family. Every non-identical member must satisfy the family gate; pooled group reasons alone are insufficient. This avoids requiring a new edge-level relationship store in this milestone.

Protected-qualifier conflicts come from explicit raw filename/folder labels or attributed reviewed/catalog metadata identifying different volumes, languages, roles or rulesets. Missing labels alone are not a conflict, but generic cross-product title agreement is not an eligible work boundary. Inspect raw qualifiers before permissive title/version normalization, including dotted ruleset editions such as D&D 3.0 versus 3.5. Treat uncertain conflicts as deferred rather than guessing a split.

Existing current per-work user rulings take precedence over the bulk policy. Preserve reviewed work boundaries and report any proposed change to an established reviewed selection. Baseline-linked Dungeon Masters Guild work remains a reuse/baseline-review result, not a new PDF-conversion job. Do not overwrite its outputs or count a JSON sidecar as searchable Markdown.

An explicitly adopted Sol selection also remains a reviewed choice: report a different recency winner for review rather than replacing it under the bulk preference. Automatically generated proposals and advisory pilot reports are not adopted rulings. Explicit human holds remain attached to the work/known source lineage when group membership grows; added or changed sources cause renewed review, not an automatic release of the hold. Reuse a positive ruling only while its bound source identities remain valid. Where regrouping makes the reviewed boundary uncertain, defer affected components conservatively. The implementation plan must preserve this authority/history rather than migrate it into a policy-looking human decision.

An uncontested source may retain its existing selection without a recency comparison. Missing dates are still reported. The existing undated lone-`.old` fallback remains deferred; a valid uniquely dated source is not rejected merely for having `.old` in its name. Names never establish publication age.

## 2. Embedded-date policy

Read metadata without extracting page text. Preserve source SHA-256, raw values, field names, timezone/precision and parse errors. Cache metadata independently of page samples and decisions.

For each distinct byte content:

1. Read PDF Info `/ModDate` and `/CreationDate`, plus recognized XMP modification/creation equivalents where present. Never rank by filesystem times, cache-copy times, filename tokens, copyright text or XMP `MetadataDate`.
2. Resolve the modification field first. If no internal modification value is present, resolve creation as the fallback. This priority is **per file**: a newer creation-fallback date may outrank another file's older modification date.
3. Normalize explicit offsets to UTC before comparing. Preserve original strings and provenance. Do not compare raw date strings lexicographically.
4. Agreeing PDF Info/XMP representations describe one value. Conflicting representations, malformed present ranking values, or modification dates definitely preceding creation are flagged for review. A malformed modification date is not silently replaced by creation.
5. Represent supported partial dates with their precision/possible interval. Compatible less-precise fields may be resolved by a more precise **explicitly zoned** Info/XMP representation of the same date concept. Zoned intervals must intersect; an offset-free field must agree on its stated calendar/time components with the zoned representation in that representation's own timezone. Use the actual more precise field as the ranking witness, retaining the weaker raw value and a resolution note. Do not fabricate a timezone for the weaker field. If no zoned witness exists, or representations contradict each other, defer competing families. Overlapping candidate intervals that prevent unique ordering are also deferred. Detailed parser support belongs in the implementation plan; unsupported forms are explicit outcomes.

Choose a winner only when every competing content candidate is accounted for and its date is unambiguously later than the others. Do not ignore an undated or unreadable competitor to manufacture a winner. Equal dates for different bytes are deferred; equal dates for identical bytes are just aliases.

Select an accessible representative address for the winning bytes, preferring an established address, then a non-`.old` alias and stable path order. That address preference is unrelated to publication chronology.

Record `selection_basis = newest_internal_date_v1`, effective field/date, all compared candidates, source hashes, policy version and flags. The result means **chosen under the user's preference**, not **proved to supersede every alternative**. No Sol call is required merely to apply that preference.

## 3. Ready bucket and handoff

Add an explicit policy selection record rather than disguising policy alternatives as proved `superseded` or `equivalent_presentation` outcomes. Preserve a stable work ID and link every retained alternative to its policy-selected primary. Existing explicit review decisions and their evidence remain distinguishable.

The handoff has three principal outputs:

| Bucket | Meaning |
| --- | --- |
| Ready for native Markdown | Eligible work family, selected readable source, frozen source hash, no unresolved date/identity conflict or baseline block. |
| Deferred source choice | Missing/conflicting/unorderable dates, unknown competitor, identity conflict, or a protected reviewed/baseline choice needing a ruling. |
| Existing/reuse | An established baseline or a verified matching Markdown artifact; report actual format and source correspondence. |

Each ready entry carries work/source IDs, original root and relative path, SHA-256, publisher/title with provenance, selected internal dates, retained alternative IDs and policy version. A frozen queue snapshot is an executable contract; later source selection changes do not silently change an active conversion job. Changed inputs invalidate affected selection/artifacts. Reuse unchanged metadata, prior rulings and extraction checkpoints.

Ready means **ready to attempt native conversion**, not already proved text-bearing. Verified bytes and parsable metadata plus the selection/authority rules are sufficient; a five-page sample is not mandatory for an otherwise eligible singleton, exact-copy family or dated winner. A sparse existing sample does not block the attempt. Full conversion determines whether useful text is available. Explicit reviewed asset exclusions/holds still apply. Unknown or failed metadata on a competing candidate still blocks that family.

Keep existing `selection.json`, `queue.tsv` and review outcome semantics intact for legacy consumers. Add a separate, versioned `markdown-selection.json`, `markdown-queue.tsv` and `markdown-review.jsonl` generation with its own current pointer. The converter consumes an explicit frozen generation of this new queue. Policy records distinguish `ready_by_policy`, `retained_alternative`, `deferred_choice` and `existing_or_baseline`; they do not impersonate per-file user rulings or rewrite legacy `needs_review` outcomes into proof of supersession. Reports label which selection basis they describe. Existing legacy queue entries may be translated only when their source identity and authority satisfy the new contract; a bare TSV row is insufficient authorization to convert a different file.

## 4. Full native-text conversion

For ready entries, stage only the selected PDFs needed by the current bounded batch into a private local cache. Stream the copy and verify SHA-256 against the frozen selection before extracting. Preserve original-file provenance separately from cache timestamps. Never duplicate the whole Drive library just to start conversion.

Use the existing Rust-to-Poppler subprocess boundary for native text extraction, with UTF-8, explicit PDF page ranges, page boundaries, timeouts and bounded output. Extract every page of the selected document in bounded ranges. Unknown page count, encryption, corrupt input or failed ranges are explicit failures; do not silently switch to OCR or drop pages.

Designer-proposed defaults: two independent conversion workers and 20-page ranges. A coordinator owns SQLite writes, leases and publication. Workers use immutable job descriptions/local sources and return completed range artifacts. They do not race inspection/import writes against the same evidence snapshot. A worker crash must not discard other workers' work or terminate the coordinator. Final worker/process/resource choices may be refined in the implementation plan while preserving these guarantees.

This route uses no LLM, OCR API or GPU model. Retain the original native page text before Markdown assembly. Preserve numbers, names, rules text, line breaks and Unicode; do not summarize, rewrite, infer heading hierarchies, remove repeated material or silently dehyphenate words. Text is untrusted reference content, never executable instructions.

## 5. Markdown and quality contract

Publish one current Markdown search document per work, retaining an immutable source/converter-specific artifact behind it. Use a display title with attributed provenance and a page heading/anchor for every physical PDF page. PDF page numbers, rather than printed page labels, are authoritative for citations; retain printed labels separately if available.

```text
---
format_version: 1
work_id: ...
source_id: ...
source_sha256: ...
selection_basis: newest_internal_date_v1
pdf_page_count: ...
pages_attempted: ...
extraction_status: complete_native_pass
quality_flags: [...]
---
# Display title

## PDF page 1
Extracted text...

## PDF page 2
Extracted text, or an explicit no-native-text marker...
```

The companion page artifact records text, physical page number, extraction warnings and provenance. The document manifest records source locations, alternatives, raw/normalized date evidence, parser/extractor/options/format versions, page coverage and artifact checksums. YAML/Markdown escaping must preserve literal source text rather than interpreting source HTML as active markup. Include source information sufficient to reopen the original PDF.

Use native reading order for this search copy. Preserve table-like spacing where available; do not fabricate Markdown table rows or claim that layout-sensitive material has been reconstructed. Every native output carries the limitation that image-only content and layout may be incomplete. Specific table/column/glyph warnings are best-effort supplements, not proof that all problems were detected.

`partial_or_sparse_text` is a diagnostic, not a reliable scanned-page detector. The implementation must record empty pages and basic suspicious-text warnings, but it need not prove that a caption-bearing page contains no further image-only writing. Image/resource evidence may improve warnings where readily available; semantic completeness remains unverified even when every page returns some text. Specific warning thresholds can be calibrated in the pilot and recorded with the extractor contract.

Separate operational coverage from semantic completeness:

- `complete_native_pass` means all physical pages were attempted successfully, not that every visible word or image was captured.
- Nonempty but sparse/mixed text remains available for search with `partial_or_sparse_text`/layout warnings and explicit empty-page records. Do not discard a short useful play aid just because it has few words.
- Zero-text sources enter `needs_ocr_or_visual_review`; do not publish an empty document as successful searchable Markdown. Empty extraction alone never proves a disposable visual asset.
- A failed range leaves a resumable incomplete job, not a complete current Markdown document. Completed ranges remain cached. Report the missing page ranges.

No semantic/visual fidelity certification is implied. The PDF stays available to verify tables and mechanics. OCR, layout repair, image extraction, full-text semantic editing and 5etools encoding are outside this first conversion pass.

## 6. Resume, publication and operation

Persist job/checkpoint state independently of selection decisions. Page-extraction cache keys include source hash and extractor identity/version/options. Markdown assembly additionally binds work/source identity, selection provenance and artifact-format version. A policy-only rerun may reassemble front matter from cached pages; it must not repeat successful PDF text extraction for the same bytes and extractor contract.

Checkpoint every completed page range and completed book. Retry only unfinished/invalidated ranges for a matching source/extractor contract. Validate cached range coverage/checksums before assembly; a corrupted checkpoint is retried, not trusted. Stale worker leases are recoverable after a crash. Bound retries and leave persistent errors visible while other sources continue.

Publish complete corpus generations with a catalog and a `books/` directory of ordinary Markdown files, using hardlinks or copies of completed immutable artifacts. On the initial Linux host, atomically replace an application-managed `corpus/current` directory symlink to the committed generation. The declared default search root is `corpus/current/books`; original sources are not linked or modified. Internal caches and older generations are outside that root. This gives **one current document per published work** and a consistent plain-file search view. A future platform without this publication mechanism needs an equivalent explicit contract.

Publication rules are explicit:

- A generation can contain successful books plus catalog entries for deferred, failed, zero-text and unfinished jobs. It is complete when all files it claims to publish exist, pass checksum/coverage checks and are enumerated consistently; not when every job in the batch succeeds.
- Publish successful books without waiting for failing or unfinished independent jobs. Carry forward an older published artifact only if it still matches the current selected source hash and compatible converter contract.
- If selection snapshot A changes to B, an A job may finish into the content cache. It cannot repoint the default to A or publish a source B no longer selects. Reuse its pages for B only when the source hash/extractor contract match, reassembling B's selection metadata as needed.
- A work whose old source is no longer selected has no matching current Markdown until its replacement succeeds. A new B generation reports that work as pending/deferred/failed and excludes the mismatched old document from its default books view. The older generation remains recoverable; no automatic fallback to an older PDF is performed.
- If there is no publishable B content, keep the last good published generation A and report `published_snapshot=A`, `latest_selection=B`, `publication_pending=true`. Do not claim that A satisfies B. Failed writes or an unavailable mount never replace good output with an accidental empty publication.
- Before advancing the pointer, the coordinator checks the latest approved selection generation. Source changes or newer selections invalidate promotion, not already completed cached work. Zero-text jobs are terminal native-extraction outcomes needing a later OCR/visual decision, rather than automatic endless retries.

Keep outputs outside the original library, private by default and ignored by Git in the current workspace. Log metadata/selection/conversion progress, job starts/completions, page-range checkpoints, warnings and errors. Preserve the existing every-100-file summaries and add a heartbeat during long jobs so a quiet large file does not look abandoned. Reports reconcile ready/deferred/baseline/converted/sparse/zero-text/failed/remaining counts and distinguish files, byte contents and works.

An unavailable Drive mount cannot replace a completed inventory or corpus with an empty one. A verified local source cache may finish an already frozen job, labelled with its selection snapshot, without pretending to observe new Drive changes. New discovery/selection waits for valid source access. Archive-only coverage remains tracked by issue #147.

## 7. First conversion pilot

The proposed first batch uses the already staged pilot-02 families. Their PDF Info and XMP dates agree, and each has a unique newest content candidate after collapsing byte aliases:

| Work | Policy-selected source | Effective modification time (UTC) | Full pages |
| --- | --- | --- | ---: |
| Bad Decisions | Colour-print PDF | 2021-08-21 00:57:14 | 40 |
| Expanded Discoveries | No Background PDF | 2020-07-07 14:58:30 | 10 |
| Improved Travel Planning Sheet | Static PDF | 2019-04-22 14:40:48 | 5 |
| Chivalry & Sorcery character sheet | BW PDF | 2020-03-25 16:46:26 | 6 |

This is four selected works and **61 full PDF pages**. Selection uses original embedded dates, never staging timestamps. Keep all alternatives and PDF hashes in the pilot manifest. Use a separate output namespace; do not promote it to the full library/search index automatically.

Check that known phrases from sampled pages can be found in each resulting Markdown document, every page has a corresponding artifact/heading, interrupted work resumes, and no originals or existing outputs change. Review representative tables/forms and inspect any warnings. Record limitations rather than silently escalating OCR or extracting alternate PDFs.

## Acceptance criteria and boundaries

- Date tests cover timezone normalization, creation fallback, agreeing/conflicting Info/XMP values, invalid/partial/missing dates, ties, undated competitors, and modification-before-creation conflicts.
- Selection tests protect different volumes/languages/rulesets, aliases, user rulings and baseline-linked work; policy alternatives remain recoverable and are not labelled proven obsolete.
- Four expected pilot winners are selected reproducibly, including the static sheet despite its interactive alternative and filenames that are unhelpful for chronology.
- Conversion attempts every page of selected PDFs, obeys resource bounds, preserves page provenance and useful text, and makes no routine model/OCR calls.
- Crash, failed-range, corrupt-cache and changed-source tests demonstrate resume/invalidation and preserve the prior good publication. A worker failure does not stop independent jobs.
- Sparse/mixed/zero-text cases are reported honestly; layout completeness is never inferred from successful text extraction.
- Default search sees one current Markdown document per work with no stale-generation duplicates. The pilot demonstrates literal phrase search and page/source recovery.
- Source-selection changes during jobs, partial batch success, zero-text results and failed publication follow the explicit snapshot/promotion rules; no stale job can repoint the default corpus.
- New Markdown selection artifacts are additive; existing legacy export/TSV schemas and reviewed decision semantics retain their meanings.
- Existing Python converters, rpg-lib flags, Dungeon Masters Guild artifacts, archives and source files are not rewritten as side effects.

This design expands the earlier list-only milestone at the user's request: it adds a ready bucket and a bounded full-Markdown pilot. Broad library conversion, CampaignGenerator index promotion, OCR spending, and optional 5etools conversion remain separate actions.

## Designer proposals for review

The user chose internal-date preference and searchable Markdown. The proposed family eligibility guards, Info/XMP consistency handling, conservative incomplete-date handling, two-worker/20-page defaults, publication/search-view contract and initial four-work/61-page batch are design calls for review. Parser/library choices, exact CLI flags and module boundaries belong in the implementation plan; they must preserve the contracts above.

A fresh Sol builder check identified seven planning questions about family boundaries, review authority, publication cuts, Ready eligibility, export compatibility, date agreement and sparse-text meaning. These are resolved above as explicit designer proposals. No new user preference has been assumed about OCR spending, supersession proof, visual fidelity or automatic index promotion.
