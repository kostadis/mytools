# Rust heading parser with a memory acceptance gate

The Python PDF/5etools converter should use less peak memory. The user selected
trying fast-anything's Rust heading-parser port first, before broader changes
to retained document text. After reviewing measurements, the user accepted
the small memory cost for the CPU benefit and requested automatic Rust use
when available, with Python fallback. Memory optimization follows separately.

## Approaches

- Reduce retained Python text copies first: directly targets allocations but
  changes the chunking pipeline. Deferred.
- Port `parse_markdown_headings` and its `clean_heading` dependency through
  fast-anything: selected. Keeps the experiment narrow and supports recorded
  call verification. Python/Rust boundary copies may negate memory savings.

## Proposed change

Use fast-anything to record representative offline parsing calls and generate
the port contract. Implement the parser in Rust while preserving the Python
function's signature, heading objects, line list, cleaning rules, Unicode and
newline behavior, exceptions, and ordering. Do not change chunking, caching,
OCR, providers, or document selection. Keep Python fallback available.

Profile cached Markdown only; do not call an inference provider or write into
the source library. Keep document text and recorded calls out of Git. Commit
only reproducible source/build instructions and non-private tests or fixtures.

## Acceptance

Verify recorded calls through fast-anything and run the existing converter
tests plus meaningful parsing edge cases. Compare baseline and port in fresh
processes with the same inputs: the existing 166-page cached document and a
larger, explicitly synthetic stress input. Measure peak RSS and Python traced
allocations separately, with repeated runs to distinguish allocator noise.
Include Rust import/build integration in the end-to-end RSS measurement.

The port must preserve parsed output. The original activation gate required
lower peak RSS; measurements failed that gate. The user's subsequent decision
permits the measured roughly 0.3–0.5 MiB RSS increase for the parser speedup.
Use Rust automatically when the optional durable extension can load. Retain
Python when the extension is missing, cannot load, or FAST_ANYTHING_DISABLE
is set. Runtime parsing errors must propagate normally. Bind the caller's
MdHeading class explicitly. Do not claim offline measurements cover Marker
model memory or live inference.

## Initial measurements

The offline 166-page Markdown conversion used 70,428 KiB peak RSS in one run.
A separate run tracing allocations after imports peaked at 4,393,711 bytes.
These measure different things and are preliminary, not repeated baselines.
Fast-anything attributed 5.2% of runtime to heading parsing and recommended it
as a port candidate. These were design-time measurements before implementation.
