# Standalone Rust PDF reader acceptance

The v2 converter and its batch classifier now use a standalone Rust PDF worker.
Markdown-only v2 runs import no PyMuPDF and do not require a worker. The existing
Rust bulk Markdown/Poppler rollout, source PDFs, services and historical
conversion artifacts were not changed by verification.

## Offline checks

- Rust worker: 16 passing regressions covering structural/duplicate/Unicode
  outlines, Forms/Images, Form graphics state and resource-local fonts,
  overprinted glyphs versus real repeated letters/numbers, embedded cmap
  recovery, explicit unmapped-glyph failure, encrypted references/image
  filtering, compressed objects, selection, malformed content and resource codes.
- Focused Python suite: 290 passed, 3 skipped; includes actual Rust+v2 dry-run
  with PyMuPDF imports blocked, process failure/timeout/stderr/protocol checks,
  prompt-bound cache/replay/batch resume and legacy artifact preservation.
- Full Python suite: 455 passed, 25 skipped, 3 pre-existing failures in unchanged
  claudelib API expectations (make_client/_norm_stop_reason unavailable in the
  checkout's claudelib namespace). These failures were independently reproduced
  before this migration. Skips include optional native-heading checks without
  their test override and existing optional integrations.

No inference provider, OCR model or library-wide reconversion ran. The actual
end-to-end converter test uses a generated non-private two-page PDF. Private
comparison runs request at most five pages per PDF (30 distinct pages total).
Raw text, source paths and order identifiers remain in ignored pilot scratch.

## Private corpus measurements

Three fresh release-worker processes per input, median peak RSS measured with
/usr/bin/time and wall time including process startup/JSON serialization.
PDF sizes and selected pages vary, so these are examples, not a throughput SLA.

| Case | PDF MiB | Worker RSS MiB | Wall ms | Complete runs |
|---|---:|---:|---:|---:|
| small-bookmarked-5e | 3.2 | 10.7 | 28 | 3/3 |
| large-bookmarked-226 | 46.3 | 101.4 | 161 | 3/3 |
| nulb-bookmarked-339 | 36.3 | 74.6 | 119 | 3/3 |
| character-sheet | 6.9 | 52.6 | 97 | 0/3 |
| unbookmarked-40 | 2.6 | 9.7 | 70 | 3/3 |
| image-heavy-106 | 221.6 | 462.3 | 621 | 3/3 |
| image-only-map | 1.8 | 7.6 | 5 | 3/3 |

All page counts and all valid page-linked outlines match the earlier PyMuPDF
baseline exactly. The worker also retains Nulb's 705 structural/linked entries;
350 have page destinations and 355 are containers/unresolved destinations.
The original simple Rust API omitted those 355 entries; this worker preserves
them as optional destinations rather than fabricating page 1.

The character sheet's pages 2 and 3 deliberately fail for unmappable CID glyphs:
its subset fonts omit both ToUnicode and an embedded Unicode cmap. A rendered
source check showed that the earlier engines could silently lose table digits.
The worker recovers characters when a real embedded cmap is available (the
non-private regression recovers exactly `1000`), and rejects unknown glyphs
otherwise. Those requests are incomplete, leave sources untouched and cannot
replace a complete extraction cache. Use explicit OCR or reviewed Markdown
for such documents; they are not silently accepted as successfully converted.
The image-only control is complete with empty text, and still requires OCR
if searchable text is desired.

Small-caps headings in the source sample now retain whole searchable words.
Form and table fixtures retain their checked labels and numeric values.
The text layer retains PDF drawing order; it does not promise arbitrary
multi-column/table reconstruction, or all-library font compatibility.

## Controller plus worker

The separate controller benchmark imports the real v2 converter and uses its
RustDocument adapter. It samples summed RSS every 2 ms across the controller
and its sequential worker calls. Medians of three fresh controller processes:

| Case | Controller before MiB | Sampled combined peak MiB |
|---|---:|---:|
| small-bookmarked-5e | 28.3 | 39.2 |
| nulb-bookmarked-339 | 28.4 | 101.3 |
| image-heavy-106 | 28.4 | 487.1 |

These sampled aggregates can miss short peaks and double-count shared pages;
they are not strict upper bounds. Child kernel high-water marks can inherit a
pre-exec controller RSS floor, so the standalone table is used for the worker's
own execution peak. Earlier measurements of the PyMuPDF converter import chain
were roughly 62 MiB; the new controller is about 28 MiB before extraction.
The initial small-file PyMuPDF comparison worker used about 58 MiB.

Large-file growth is accepted under the user's stated priorities. The patched
reader reduces the image-heavy encrypted sample from roughly 700 to 462 MiB;
its input buffer and raw-object copies still produce a transient loading peak.
No new lazy PDF parser was built. The performance checks cover selected pages,
not complete-book inference, rendering, OCR or whole-library throughput.

## Reproduce and recover

See [build, protocol and cache instructions](../pdf-reader/README.md),
[vendor source changes](../pdf-reader/vendor/PATCHES.md) and
[aggregate benchmark](../benchmarks/pdf_reader_memory.py).
New Rust extracts have separate filenames; response namespaces bind the exact
prompt set and settings. Existing extracts and legacy replay remain readable.
No PDF hashes were added to per-page or per-chunk loops. No binaries were
patched in place, globally installed, or committed.
