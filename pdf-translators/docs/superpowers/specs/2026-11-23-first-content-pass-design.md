# First content-reading pass

## Agreed scope

The user approved an initial limit of at most five extracted pages per PDF and the Poppler-first extraction approach. Anything still unresolved after that pass is deferred for a later decision. Do not automatically expand the page sample, request additional ranges, or fall back to extracting the full document. This refines the existing source-selection design; it does not authorize Markdown conversion or change its preservation rules.

Independent candidate groups can be processed concurrently. Four concurrent groups and a first batch of twenty groups were proposed, but concurrency, model budget, and unattended model execution have not yet been agreed. No model calls are authorized merely by recording this design.

## Reading and evidence

Default to the first four pages and the final page (all pages for documents shorter than five pages). Allow an operator to target other pages within the same budget using the existing explicit page-range option. Reading bookmark targets automatically is deferred, rather than adding a heuristic that could spend the page budget on irrelevant pages. Page choice is not permission to sample more than five pages.

Reuse a sample for byte-identical copies with fresh source attribution; do not copy source-bound reader claims to another source. Preserve UTF-8 text, page boundaries, source hashes, extraction warnings, and extractor provenance. Empty, unreliable, scanned, or encrypted results remain deferred; no automatic OCR. The cap limits text extraction and model input, not the bytes needed to open or hash a PDF.

Code performs PDF inspection and bookkeeping. Simpler models collect factual evidence with verified page citations. Sol handles reasoning and judgment. Save extracted pages and model readings separately so completed work can be reused. A matching page sample cannot establish that entire PDFs have equivalent content or that no meaningful differences exist.

Keep byte-identity decisions separate from sampled content judgments. Reading file bytes to compute a SHA-256 hash is not page-text extraction and is not limited by the page budget. Filenames, page counts, and dates alone do not establish chronology. Preserve all originals and existing Dungeon Masters Guild outputs.

## Approaches considered

Full-document extraction is too expensive for large PDFs and is outside this first pass. Automatic progressive extraction could improve coverage but would exceed the user's decision to defer unresolved cases. The selected approach is one bounded sample per PDF, followed by evidence-backed decisions where possible and an explicit deferred list for the rest.

## Implementation status

The Rust CLI now enforces the user-approved five-page reading policy, preserves extractor provenance and warnings, and reuses byte-identical page samples without transferring source-bound claims. The ongoing inventory/hash scan does not run that extraction stage. Parallel model execution and the broader reading pass have not started. See `docs/first-content-pass.md` for operation and cache behavior.
