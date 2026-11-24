<!--
Sync Impact Report
- Version change: (template) → 1.0.0
- Principles added: I. Rust Only; II. Third-Party Content Lives in homebrew-private;
  III. Deterministic, Verified Extraction; IV. Explicit Errata; V. Faithful to the Source;
  VI. Scriptable CLI
- Sections added: Data Layout, Development Workflow, Governance
- Sections removed: none
- Derived from: ../oracle and ../dde-npc (Python, stdlib-only, pdftotext-based extract + roll CLI)
- Deferred TODOs: none
-->

# drow-names Constitution

## Core Principles

### I. Rust Only

- All code in this project MUST be written in Rust (stable toolchain, Cargo workspace).
- Python, shell, or other languages MUST NOT be introduced for application logic, extraction, or
  tests. A thin wrapper (e.g. a PATH symlink) is the only non-Rust artifact allowed.
- External tools (e.g. `pdftotext`/`pdfinfo` from poppler-utils) MAY be invoked as subprocesses;
  their presence MUST be checked with a clear error if missing.
- Dependencies MUST be kept minimal and justified; prefer the standard library plus well-known
  crates (`clap`, `serde`/`serde_json`, `rand`).

Rationale: the sibling tools (`oracle`, `dde-npc`) are Python; this project deliberately uses
Rust, and mixing languages would erode that decision.

### II. Third-Party Content Lives in homebrew-private (NON-NEGOTIABLE)

- `mytools` is a public repository. Any data that is not the user's own original work — tables,
  names, text, or anything extracted from a published book or PDF — MUST NOT be committed here.
- Such data MUST be written to and read from `~/src/homebrew-private/book/<slug>/` (e.g.
  `tables.json`). The base directory MUST be overridable by an environment variable and by a
  `--data`/`--out` flag.
- The extractor MUST refuse to write any output whose resolved path is inside this repository.
- Test fixtures MUST be synthetic (invented by the user or the code), never excerpts of a book.
- Source PDF paths MAY appear in code/config; their contents MUST NOT.

Rationale: copyright. This mirrors the guard in `oracle/extract.py` and `dde-npc/extract.py`.

### III. Deterministic, Verified Extraction

- Extraction from source documents MUST be deterministic (text extraction + parsing). No LLM is
  used to extract, structure, or correct data.
- Nothing is written unless every structural check passes: each dice table covers 1..N exactly
  once with no gaps or overlaps (unless an omission is recorded per Principle IV), and each
  expected section/table is present in order.
- Re-running extraction on the same input MUST produce byte-identical output.

Rationale: tables are precision data; a silent 10% error would poison every generated result.

### IV. Explicit Errata

- Printed mistakes in a source (wrong ranges, swapped page refs, mismatched wording) MUST be fixed
  only through an explicit, commented `ERRATA` table in code, each entry recording the printed
  value.
- Ranges the book omits MUST remain gaps; the generator rerolls on a gap.
- Errata and gaps MUST be stored in the output data and reported on every extraction run.

### V. Faithful to the Source

- Generation rules MUST follow the book as written (e.g. "roll twice", "reroll", conditional
  rows). Any rule the book does not sanction MUST be labelled a house option and be opt-in.
- Worked examples printed in the source, when present, MUST be reproduced by tests.

### VI. Scriptable CLI

- The tool is a CLI: args in, text to stdout, errors to stderr, non-zero exit on failure.
- It MUST support `-n` (count), `--seed` (reproducible rolls), `--json` (machine-readable
  output), and `--list` (show available tables/choices).
- Name arguments match exactly, then by prefix, then by unique substring; a miss MUST list the
  valid choices.

## Data Layout

- Code: `~/src/mytools/drow-names/` (Cargo project, public).
- Data: `~/src/homebrew-private/book/<slug>/tables.json` (private), one directory per source.
- A missing data file MUST produce an error that names the expected path and the extract command.

## Development Workflow

- `cargo fmt`, `cargo clippy -- -D warnings`, and `cargo test` MUST pass before commit.
- Tests run against synthetic fixtures; tests that need real extracted data MUST be `#[ignore]`d
  by default and skip cleanly when the data is absent.
- README documents setup (extract once), usage examples, and extraction notes (errata, gaps,
  what is not extracted).

## Governance

- This constitution supersedes other practices for this project. Amendments require updating this
  file, a version bump, and a Sync Impact Report.
- Versioning: MAJOR for principle removal/redefinition, MINOR for new principles or sections,
  PATCH for wording.
- Every plan and review MUST check compliance with Principles I and II explicitly.

**Version**: 1.0.0 | **Ratified**: 2026-11-23 | **Last Amended**: 2026-11-23
