# Standalone Rust PDF reader

## Intent and decisions

Replace PyMuPDF in the unified Python PDF/5etools converter's PDF-reading layer
with a standalone Rust worker. Searchable Markdown remains the primary goal;
5etools encoding consumes extracted text downstream. The user selected Rust,
then a standalone command, and accepts memory growth for large PDFs because
most documents are small. Favor a low baseline and reliable text over a new
lazy-loading parser project.

The pilot is private scratch at `source-selection-data/pdf-backend-pilot-01/`.
Seven PDFs, at most five pages each, established a starting point. Source
patches eliminated sampled Image-XObject panics and reduced one large encrypted
PDF's peak from about 700 to 462 MiB. The final worker preserved every valid
page-linked bookmark. These findings are not full-library validation.

## Approaches

- Standalone Rust worker: selected. Matches existing batch tooling; streams
  page records and releases document allocations on exit. Requires a small
  process protocol and consumer adapter.
- PyO3 reader inside Python: avoids process/protocol overhead but shares the
  converter's memory lifetime and crash boundary. Not selected.
- A new lazy PDF parser: could further reduce large-file peaks but expands
  scope substantially. Deferred under the user's clarified memory preference.

## Deliverables and boundaries

1. A buildable, tested Rust reader CLI with versioned streamed output.
2. A Python adapter used by the unified v2 converter for metadata, bookmarks,
   profiling, printed-ToC detection and page text; Markdown-only runs must not
   import PyMuPDF or start a PDF worker.
3. Reproducible offline quality/performance checks and build/run documentation.

Keep PDF selection, archive handling, adjacent Markdown/provenance conventions,
LLM providers, 5etools schema, and the current bulk Markdown rollout unchanged.
This is not a library-wide reconversion or a rewrite of legacy v1 entrypoints.
Do not replace the existing bulk pipeline's Poppler backend in this change.
OCR stays a separate existing stage. No new automatic inference calls.

## Rust implementation

Proposed builder call: a dedicated `pdf-reader/` crate and `rpg-pdf-reader`
binary under `pdf-translators`, reusing the repository's Rust toolchain.
Use lopdf 0.47 with the richer pdf-extract traversal, upgraded to the same
lopdf version. The simple lopdf extract_text API alone missed text inside
Form XObjects in the pilot.

Promote only reviewed source changes from the pilot, with regression tests:

- Skip bitmap Image XObjects; traverse text-bearing Form XObjects.
- Return structured content errors rather than unwrap/panic on decode failure.
- Release raw encrypted-object copies as they are consumed.
- Honor extraction filters after decryption; retain required font, Form, page,
  and object-stream data. Do not infer general encrypted-PDF correctness from
  the pilot's default-password samples.

Pin dependencies and retain source patches and license notices reproducibly.
Builder chooses a small vendored patch or a pinned maintained fork; no binary
patching, global crate replacement, or production dependency on private scratch.
Disable implicit library-wide parallelism: the batch scheduler owns concurrency.

Improve spacing using glyph position/font information, with specific
small-caps and table regressions. Do not blindly remove spaces or join words.
Content and searchable words need to be right; byte-for-byte matching of
PyMuPDF whitespace is not a requirement. Surface unsupported content explicitly.

## Command and protocol

Proposed interface:

    rpg-pdf-reader inspect INPUT.pdf
    rpg-pdf-reader extract INPUT.pdf [--pages 1,2,8-10]
    rpg-pdf-reader --version

`inspect` emits metadata/outlines without page extraction. `extract` defaults
to all pages; selection is explicit, 1-based, validated and de-duplicated in
ascending order. Reject invalid/out-of-range selections before emitting text.
The pilot and comparison commands always request at most five pages per PDF.

Stdout is UTF-8 JSON Lines, one complete record per line. Diagnostics go to
stderr. Do not retain a document-sized stdout buffer in either process.

- `document`: first record; protocol version 1, backend/build identity,
  page count, requested page numbers, and ordered outline entries.
- `page`: page number and Unicode text; an empty string is a successful
  empty-text extraction, not an OCR claim.
- `error`: stable code, message, optional page number. Distinguish unreadable
  input, password required, unsupported/malformed content, resource failure.
- `end`: final record, `complete`, requested/emitted/failed page counts.

Successful inspect/extract requires exit 0, exactly one document record and
one end record, complete=true, and every requested page exactly once. Errors,
missing records, unknown protocol versions, malformed JSON, duplicate or
unexpected pages, and truncated streams cannot produce a successful extract.
A page failure may be recorded and later pages examined, but the final extract
is incomplete and nonzero; downstream code must not publish it as complete.
Use exit 2 for invalid command arguments and exit 1 for extraction failure.

Represent outline entries as ordered depth/title/optional-page records.
All valid destinations remain 1-based. Missing destinations are null, never
invented page 1. Retain structural containers for grouping. The Python adapter
uses valid destinations for page ranges and can derive a container range from
valid descendants. A group without any resolvable descendant is retained in
outline diagnostics but cannot fabricate a content range.

Default/empty-password PDFs are supported. A PDF requiring an unavailable
password produces a clear error; do not introduce a password-storage workflow.

## Converter adapter and lifecycle

Add a focused Python adapter that discovers the built worker through an
explicit executable setting or documented checkout build location. Missing
worker errors should identify the build command. No silent PyMuPDF fallback
for the new v2 path. Keep existing explicitly selected OCR paths working.

The worker streams page data; the adapter may retain the existing `units`
representation required by chunking, once per page. This milestone does not
promise constant memory independent of document size. Do not reconstruct
an additional whole-document string merely to cross the process boundary.
On cancellation or consumer failure, terminate/reap the child and drain or
redirect stderr so a full pipe cannot deadlock extraction.

Keep ToC-tree construction, printed-ToC parsing, hyphenated-word repair,
shared-page splitting, and chunk assembly deterministic. Refactor their PDF
access to consume adapter facts/page text while preserving pure helper APIs.
Within a conversion, reuse metadata and already-read sampled pages; never
start a fresh document load for every page or section. Inspections for routing
can be separate from a single full extraction process, but duplicate sampled
page text must not create duplicate units. Builder may spool pages locally
rather than keep two copies if that simplifies this boundary.

Remove eager fitz imports from the unified converter and shared text/ToC/model
import chain. Legacy entrypoints may retain lazily loaded compatibility code.
A Markdown-only conversion must work without the worker and without PyMuPDF
installed. Existing OCR subprocess environments may keep their own dependency.

## Cached work and rollout

A different extractor can change whitespace, text order, chunk boundaries,
and prompt content even when the source PDF is unchanged. Current response
names based on ordinal plus title are insufficient evidence of equivalence.

- Tag new Rust extract metadata with backend/version identity.
- Preserve existing extract artifacts and their ability to load/split/encode.
- Keep Rust extraction/response artifacts separate from historical backend
  artifacts; do not overwrite or silently relabel them during migration.
- Reuse a response for a Rust chunk only when its saved exact prompt digest
  matches the new prompt (including system/model settings that affect reuse).
  No repeated full-PDF hashes are required for this check.
- Legacy responses without that binding remain usable with their original
  extraction; do not automatically attach them to newly extracted Rust chunks.
- A failed/incomplete worker run must not replace a valid extraction cache or
  publish a completed Markdown/5etools result. Stage and atomically commit
  successful extraction artifacts through existing publication conventions.

Enable the Rust path after offline acceptance, with a documented explicit
executable override. Do not restart existing services or reconvert the library
as part of installation/verification. Changes apply to subsequent invocations.

## Acceptance

Use non-private fixtures for deterministic regression tests and bounded local
samples for quality checks. Raw source text and private paths stay ignored.

- All pages/counts/valid bookmark titles, destinations, depth and order match
  checked source expectations. Include duplicate titles, optional destinations,
  Unicode, Forms containing text, bitmap images and empty-image-only pages.
- Small-caps headings remain searchable as whole words. Tables preserve checked
  labels, numbers and reading order; inspect rendered source where extraction
  baselines disagree. Unresolved issues are explicit failures/review cases,
  never silently accepted missing content.
- Encrypted loader tests exercise object references and compressed object
  streams; source patch correctness must be tested beyond memory improvements.
- Protocol tests exercise malformed/truncated/duplicate data, worker crash,
  blocked stderr, timeout/cancellation, and no partial cache publication.
- Cache tests prove changed prompts cannot reuse ordinal/title-only historical
  responses and unchanged bound prompts can resume.
- Run the converter's meaningful offline suites through the Rust adapter;
  verify OCR routing remains deliberate and Markdown-only runs import no fitz.
- Measure small and large documents in fresh processes, repeated runs; report
  worker RSS and controller-plus-worker memory separately. Accept size-related
  large-file growth. Preserve the pilot's low small-file baseline rather than
  treating 462 MiB as a universal budget or promising constant memory.

No source deletions or live inference are needed for acceptance. Report any
pre-existing unrelated test failures separately from regressions.

## Calls left to the builder

Choose internal Rust modules, process timeout defaults, stderr buffering,
build helper details, and fixture generation under the stated contracts.
New unresolved user-facing choices should be raised before changing scope.
