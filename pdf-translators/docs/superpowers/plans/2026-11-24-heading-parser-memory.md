# Rust Heading Parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Try fast-anything's Rust heading parser and retain it only if peak memory improves.

**Architecture:** Preserve the Python parser as the reference and fallback. Use a PyO3 port with direct Python result construction to avoid an intermediate Rust copy of the entire document.

**Tech Stack:** Python, Rust, PyO3, fast-anything, pytest, RSS and tracemalloc measurements.

**Spec:** `docs/superpowers/specs/2026-11-24-heading-parser-memory-design.md`

## Global Constraints

- Memory matters more than CPU time; identical parsed output is required.
- No live inference or source-library writes; private recorded text stays out of Git.
- User amendment: accept the measured ~0.3–0.5 MiB RSS cost for parser CPU performance; use Rust when available with Python fallback. Then address memory separately.

## Review Focus

- Python splitlines recognizes Unicode separators and CRLF; preserve exact lines.
- Heading regex whitespace, empty titles, bold removal, and hash limits must match.
- Unicode titles and astral characters must survive the FFI boundary.
- Result objects must remain mutable MdHeading instances from the converter.
- Native import and boundary allocations count toward peak RSS; Python allocations alone cannot decide acceptance.

### Task 1: Record and implement the parser

**Files:** private `.fast/ports/*` tool contract; durable Rust source under `native-heading-parser/`; differential tests under `tests/test_native_heading_parser.py`; `.gitignore` for private tool state.

**Interfaces:** `parse_markdown_headings(md_text: str) -> tuple[list[MdHeading], list[str]]` stays unchanged. The native extension returns the same lines and heading values; the adapter must instantiate the original dataclass.

- [x] Record calls with fast-anything and read its complete TASK.md and generated contract.
- [x] Write differential tests for the five review focus conditions; run against the unimplemented native parser and observe failure.
- [x] Implement the Rust parser, durable build helper, and startup loader; retain reproducible source outside ignored recordings. Explicitly bind the converter's heading class and propagate parser errors.
- [x] Build and run recorded-call verification plus differential tests and the existing converter suite.

### Task 2: Measure and decide

**Files:** reproducible offline benchmark script and experiment report under `benchmarks/` and `docs/`.

**Interfaces:** benchmark accepts a caller-supplied Markdown file, creates synthetic stress data itself, runs fresh Python/native child processes, and records RSS, traced allocations, timing, and output equivalence without publishing source text.

- [x] Run repeated baseline/native measurements on the cached 166-page document and a large synthetic document.
- [x] Run fast-anything enable/bench/report only after verification; remove its temporary activation block, and use the durable loader under the user's revised activation choice.
- [x] Record the evidence, build and undo instructions, and limitations.
- [ ] Run final verification and request independent review.

### Task 3: Release discarded ancestor bodies (user follow-up)

**Files:** `_split_into_chunks` in `converters/pdf_to_5etools_v2.py`; regression in `tests/test_pdf_to_5etools_v2.py`; `benchmarks/chunk_split_memory.py` and measurement summary.

**Interfaces:** Same chunk list, bodies, root/target objects, and prose-stub flags. Drop the oversized parent body before recursively constructing descendants.

- [x] Measure retained ancestor bodies on synthetic nested source text.
- [x] Add a weak-reference lifetime regression; observe failure while a discarded parent remains alive.
- [x] Release the parent body, verify regression and converter suite pass.
- [x] Compare RSS and traced allocations in separate fresh processes against the two baseline splitting functions from Git; verify exact chunk equivalence.
