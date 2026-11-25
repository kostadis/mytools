# Standalone Rust PDF reader

`rpg-pdf-reader` supplies page text and outlines to the unified v2 converter.
The reader is Rust, including PDF/font parsing. It does not load PyMuPDF or
call OCR/LLM services. The existing bulk Markdown pipeline keeps its Poppler
backend; this change replaces PDF access in the Python v2 path and batch scan.

## Build and run

From the repository root (Cargo/Rust 1.95+):

```sh
cargo build --release --locked --manifest-path pdf-translators/pdf-reader/Cargo.toml
pdf-translators/pdf-reader/target/release/rpg-pdf-reader inspect '/path/book.pdf'
pdf-translators/pdf-reader/target/release/rpg-pdf-reader extract '/path/book.pdf' --pages 1,2,8-10
```

`extract` without `--pages` reads all pages. Selections are 1-based, sorted,
de-duplicated and checked against the page count before text is emitted.
Stdout contains UTF-8 JSON Lines; diagnostics use stderr. The source is read-only.
No output PDF or adjacent Markdown is written by this low-level worker.

The Python converter discovers `target/release/rpg-pdf-reader` in this checkout.
To use another build:

```sh
export RPG_PDF_READER='/absolute/path/rpg-pdf-reader'
export RPG_PDF_TIMEOUT=300  # seconds per inspect/extract request; default 300
python3 pdf-translators/converters/pdf_to_5etools_v2.py '/path/book.pdf' --provider claude-code --dry-run
```

The dry run above uses no inference. Normal conversion uses the existing selected
provider. Missing Rust builds produce build instructions; v2 does not silently
switch PDF engines. Markdown-only `--from-markdown` needs neither the PDF worker
nor PyMuPDF. Legacy converters/editors and Marker's separate environment may
still need PyMuPDF; this is not a package-uninstallation migration.

## Protocol version 1

Successful requests produce one `document`, selected `page` records, then one
`end` record and exit 0. `inspect` has no selected pages. Examples:

```json
{"type":"document","protocol":1,"backend":"rust-pdf-reader/1","build":"0.1.0","page_count":2,"requested":[1],"outline":[{"level":1,"title":"Chapter","page":1}]}
{"type":"page","page":1,"text":"Searchable text"}
{"type":"end","complete":true,"requested":1,"emitted":1,"failed":0}
```

Outline entries retain source order and depth, including duplicate titles and
containers with `page: null`. The Python adapter derives grouping ranges only
from real descendant destinations; it never turns an unresolved target into
page 1. Empty page text is a valid extraction result, not an OCR result.

Failure emits `error` with `code`, `message` and optional `page`, plus an
incomplete `end` when possible, and exit 1. Invalid CLI/page arguments exit 2.
A panic/crash, malformed/truncated stream, duplicate/unexpected/missing pages,
or unsuccessful exit is a failure even if earlier page records were emitted.
The adapter stages pages until the complete request validates, drains bounded
stderr, times out stalled workers and kills their process group on failure.

Default/empty-password encrypted PDFs are supported. Password-protected PDFs
without an available password return `password_required`. No password store or
credential command-line option is introduced. Page and object-stream decoding
has a 64 MiB decompression limit; unsupported/resource-limited content fails
explicitly instead of being published as a complete extraction.

## Text and font fidelity

Text-containing Form XObjects are traversed with inherited graphics state and
Form matrices; bitmap Image XObjects are not parsed as text instructions.
Font caches use the actual font dictionary, not resource names reused by Forms.
Positioned glyph output preserves small caps and reduces shadow overprints
without collapsing genuine repeated letters/numbers. PDF drawing order is
retained; this is plain text extraction, not a general table-layout engine.

When a CID font omits ToUnicode, an unambiguous embedded TrueType Unicode cmap
can recover its characters. If both maps are stripped, unknown glyphs cause a
reviewable page error. The worker does not guess missing digits or declare
incomplete text successful. Use the existing explicit `--force-ocr` workflow
(or reviewed `--from-markdown` input) for such files. Image-only pages similarly
still need OCR when readable text is desired. No OCR call happens automatically
because of a worker parsing error.

The seven-document acceptance sample includes a character sheet with stripped
font maps. Two sampled pages are deliberately rejected; the source PDF remains
untouched, and no complete extraction cache is published for that request.

## Existing caches and recovery

New batch PDF extracts use `<stem>-extract-rust-v1.json`; historical
`<stem>-extract.json` files remain readable and are not overwritten by a Rust
extraction. Encoding prefers an existing Rust artifact, otherwise legacy.
Existing completed work is not automatically reconverted. Extract writes stage
and atomically replace only their own destination after successful extraction.

Rust responses live under `<responses>/rust-pdf-v1/<request-set-digest>/`.
`rust-requests.json` binds each exact prompt plus system/model/provider/output
settings and backend identity. Identical partial runs can reuse cached entries.
Changing prompts/settings selects a separate directory. This deliberately
avoids cross-set reuse, even if only one prompt changed. No repeated full-PDF
hashes are added. Legacy response directories retain their original behavior
with historical extracts; unbound files cannot be adopted by Rust replay.

For `--replay-responses`, supply the original response parent or its matching
bound directory with the same extraction/model settings. Rust replay requires
per-chunk IDs, not positional guesses. Batch IDs are saved with the actual
submitted chunk IDs; Rust `--resume-batch` validates this association before
fetching or merging results. A batch ID from unrelated/unbound requests is
rejected before provider access.

## Tests and measurements

```sh
cargo test --locked --manifest-path pdf-translators/pdf-reader/Cargo.toml
python3 -m pytest pdf-translators/tests/test_pdf_backend.py pdf-translators/tests/test_response_binding.py pdf-translators/tests/test_pdf_to_5etools_v2.py -q
python3 pdf-translators/benchmarks/pdf_reader_memory.py --pdf '/path/book.pdf' --pages 1,2,3 --runs 3
```

The last command caps comparisons at five selected pages and prints metrics,
not source text. Aggregate controller-plus-worker RSS is sampled every 2 ms;
short launch peaks can be missed and shared pages can be counted twice.
Child kernel high-water marks can include a pre-exec inherited controller RSS
floor, so standalone `/usr/bin/time -v` measurements are used for the reader's
own execution peak. Do not treat a sampled aggregate as a strict memory bound.

See [acceptance results](../docs/rust-pdf-worker-acceptance.md) and
[vendor patch notes](vendor/PATCHES.md). Dependencies and local source patches
are pinned in Cargo.lock; no build edits the global Cargo registry. Large PDFs
can use more memory; the goal is a low common-case baseline, not constant RAM.
