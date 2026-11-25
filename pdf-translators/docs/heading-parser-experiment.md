# Python converter performance work

The converter automatically uses the optional Rust heading parser when built.
It also releases discarded parent text before recursively splitting oversized
sections. Both changes preserve conversion contents and ordering.

## Rust parser

Fast-anything 0.8.6 identified `parse_markdown_headings`, which accounted for
5.2% of the initial offline run. Its Rust port reads existing Python Unicode
storage without making a full Rust string copy and constructs the original
`MdHeading` objects. Python handles `splitlines`, string replacement, and
stripping so Unicode and lone surrogates preserve their existing behavior.

Fast-anything verified **35/35 calls**: one real recorded call, eight generated
edge cases, and 26 derived cases. Its focused benchmark measured about **2.9×**
faster parsing (5.7 ms versus 2.0 ms). The initial full-command benchmark was
**298 ms versus 296 ms**, median of five interleaved runs, with ±11 ms reported
variation. That end-to-end difference is within noise.

The durable extension was then measured in five fresh processes per mode,
workload, phase, and instrumentation setting. RSS includes imports and native
library loading. Tracemalloc uses separate processes. Worker timings exclude
imports. The real input was cached Markdown for a 166-page document; the
32 MiB synthetic input includes Unicode. All compared outputs matched.

| Workload | Phase | Python median RSS | Rust median RSS |
|---|---|---:|---:|
| Real document | Parsing | 64.81 MiB | 65.24 MiB |
| Real document | Offline conversion | 65.61 MiB | 66.00 MiB |
| Synthetic 32 MiB | Parsing | 225.47 MiB | 225.81 MiB |
| Synthetic 32 MiB | Offline conversion | 353.14 MiB | 353.48 MiB |

This parser is a CPU optimization, with roughly 0.3–0.5 MiB extra peak RSS.
The user accepted that cost and requested automatic use when available,
followed by separate memory optimization. Missing or unloadable binaries use
Python at startup; parsing errors propagate normally. Set
`FAST_ANYTHING_DISABLE=1` to select Python explicitly.

Build and undo instructions are in
[native-heading-parser/README.md](../native-heading-parser/README.md).
The temporary fast-anything activation block was removed; runtime loading
uses the durable crate's build output, not private `.fast/` artifacts.

## Nested chunk splitting

Previously `_split_into_chunks` retained an oversized parent's reconstructed
body in its stack frame while recursively reconstructing child bodies. Deep
sections could retain multiple full-document strings simultaneously. The fix
releases the discarded parent body immediately after deciding to split it.
Prose stubs, leaf bodies, root identities, and ordering stay unchanged.

The regression test checks that discarded ancestors are no longer alive when
child text is constructed. The reproducible synthetic benchmark compares the
two splitting functions from Git revision `76c6229` with the current ones,
using the same imports, 65,536 unique text units, three oversized ancestors,
and two leaves. It compares emitted chunk metadata and contents and measures
RSS and traced allocations in separate fresh processes. Results are in
[the measurement summary](../benchmarks/results/2026-11-24-chunk-split.json).
This targets deep oversized sections; flat or already-small sections gain
little from this particular change.

| Nested splitting measurement | Before | After |
|---|---:|---:|
| Median peak RSS | 232.6 MiB | 132.9 MiB |
| Median peak Python allocations during splitting | 133.2 MiB | 33.8 MiB |
| Median split time | 81.3 ms | 79.7 ms |

RSS fell about **43%** and traced allocations about **75%**, with identical
chunks across five interleaved runs per mode and instrumentation setting.

```sh
python3 benchmarks/chunk_split_memory.py --runs 5
```

## Verification and limits

Differential tests cover Unicode whitespace and line separators, CRLF,
unbounded hash counts, bold markers, empty/whitespace titles, lone surrogates,
invalid input errors, and the exact mutable heading class. Startup tests
exercise automatic native selection, forced Python, missing/unloadable
binaries, class binding, and runtime error propagation.

The broader existing suite has three independently reproduced failures in
`test_llm_backend.py`: the checkout resolves a `claudelib` namespace without
`make_client` or `_norm_stop_reason`. Those files were not changed here.
The existing PyMuPDF `fitz` deprecation warning also remains.

These measurements exclude live inference, OCR models, and PDF rendering.
They do not establish whole-library throughput or a fixed memory bound.
Private source documents and fast-anything call recordings are not committed.

Parser measurement summary:
[2026-11-24-heading-parser.json](../benchmarks/results/2026-11-24-heading-parser.json).
