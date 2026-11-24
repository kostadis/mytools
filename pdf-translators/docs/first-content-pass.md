# Inspect a bounded PDF sample

The Rust selector's `inspect` command now samples at most five pages per PDF: the first four and the last, or every page of shorter documents. It no longer fully extracts competing candidates. It uses the installed Poppler `pdftotext`, preserves page boundaries and UTF-8 text, and records the extractor's executable, version output, and warnings alongside the page evidence.

From this project's directory, after completing a scan:

```bash
source-selector/target/debug/rpg-source-select --work-dir source-selection-data inspect --limit 10
```

`--limit` counts candidate groups, not pages or files. This command does not run models, OCR, Markdown conversion, or 5etools conversion. Do not run it against the large scan's state while that scan is still publishing inventory. The broad extraction pass has not started.

Unchanged cached samples are reused. Byte-identical copies share a single five-page budget by content hash, including earlier nondefault samples. They can reuse cached pages from other sources with explicit attribution; source-bound reader claims are not copied. Previously sampled pages count toward the five-page budget. The default can fill the remaining budget but never grows it beyond five. Legacy evidence with more pages is retained and reused without automatic extra extraction.

An operator can choose pages explicitly, for example `inspect --pages 1-3,12,90`, but cannot request more than five distinct pages, or exceed five when combined with existing sampled pages. Such a request exits with a usage error and preserves existing evidence; it does not mark the PDF unreadable. Additional reading requires a later policy decision.

Empty, sparse, scanned, damaged, encrypted, and unreadable cases remain explicit. No OCR or full-document extraction is triggered as a fallback. Samples that match do not establish whole-document equivalence or revision chronology. Unresolved competing sources stay in the review export. The five-page limit bounds text extraction and downstream model input; opening or hashing the PDF can still require reading the entire file.

The metadata fields `_text_extractor`, `_extraction_batches`, and `_sample_reused_from_sources` are selector provenance rather than publisher claims. Each batch records its pages, extractor, and warnings; earlier warnings survive later fills. Legacy provenance is explicitly marked unknown when unavailable. The extractor version is queried once per inspector process with the same timeout and output bounds as text extraction; a version-query failure is recorded explicitly rather than failing otherwise successful page extraction. Pipe draining also respects the timeout. On Unix, a timed-out extractor's private process group is killed to cover wrapper children.

Verification: 56 normal Rust tests and the explicit installed-Poppler roundtrip pass, as do formatting, build, and Clippy with warnings denied. A fresh run on the three-page Feats pilot extracted one sample, reused it for its identical copy, recorded the Poppler version, and reported zero failures. This does not establish full-library content-reading quality.
