# Presentation and citation pilot 02

The second content-reading pilot used **four different products, 18 PDFs and nine distinct byte contents**, with **zero original-path or SHA-256 overlap** with pilot 01. It extracted 45 distinct pages in total, at most five per byte content. Nine identical copies reused samples; there were no extraction failures.

All four product families now reached default reader review as `presentation_candidate` groups. Differing contents remained unresolved and out of the experimental conversion queue.

| Product | Observed result | Deferred question |
| --- | --- | --- |
| Bad Decisions | Digital, colour-print and BW-print versions were compared together. Text matches on the five sampled pages; some image/annotation counts differ. | The remaining pages and visual equivalence are unverified. |
| Expanded Discoveries | Coloured and No Background versions were grouped. Sampled text matches. | Ten-page books were sampled on five pages; whole-document equivalence remains unproven. |
| Improved Travel Planning Sheet | Interactive and static versions were grouped. All five pages have equal extracted text, with different annotation counts. | Form behavior and visual equivalence remain open. |
| Chivalry & Sorcery character sheet | BW and standard versions were grouped despite a trailing date after the BW label. Both print VER 2.3; sampled text differs in places. | Extraction differences do not establish a revision, and each six-page document was sampled on five pages. The game is not inferred to be D&D 5e from a fifth-edition product label. |

Two parallel gpt-6-luna factual readers returned **27 claims without packet IDs**. Rust automatically bound all 27 to source/page/quote/hash-checked issued excerpts. Sol supported all 27 values in their cited-page context. The authoritative pilot state contains 27 facts and 27 automatic binding audit records, with **zero manual citation or serialization repairs**. No model selection decisions were imported. No OCR, extra pages, Markdown conversion or 5etools conversion ran.

The fixes also cover failed export publication, empty responses, stale/ambiguous citations, stable split-page re-exports, atomic imports and preservation of original binding provenance on replay. Verification passed 68 normal Rust tests plus the explicit Poppler roundtrip, formatting, build and Clippy with warnings denied.

Detailed manifests, original fingerprints, staged source hashes, private excerpts, reader output, audits, comparison results and reports are stored in the ignored `source-selection-data/content-pilot-02` directory. Original library files and established conversion outputs were preserved. This is a bounded pilot, not evidence that every presentation naming convention or library-wide grouping case is covered.

The full-library hash process continued on its existing executable. Refresh its scan after completion using the updated binary to apply the new grouping and reuse cached hashes. For a given state directory, keep write stages sequential; parallelize reading of the saved samples.
