# Continuous Markdown verification

The Rust coordinator publishes complete selected groups while unrelated metadata is still being read. The existing four-document pilot was repeated with an additional independent PDF whose metadata worker was held behind a file gate.

Before releasing the gate, all four cached selections were confirmed published beside their PDFs, with metadata at **18/19**, four groups resolved and one still pending. After release, the fifth book published and the run completed without extraction/publication failures. All **18 original pilot PDF hashes remained unchanged**. Verification is in the private `source-selection-data/continuous-pilot-03/verification.json`; logs and checkpoints are under its `output/` directory.

The final Rust suite passed **146 tests**, with two environment-specific tests ignored in that default invocation. The Poppler round-trip and mounted Google Drive filesystem round-trip passed separately. Formatting, strict Clippy and the locked release build passed.

One fresh Sol review identified authority, recovery, capacity and completion-accounting issues. Its single correction pass added regressions for persistent regroup fences, late joining hints, absent sources, revocation before sibling installation, failure while staging a replacement search view, mixed directory lineage, and record-only publication failures. The existing delayed-metadata, stable-output and review-hold integration tests also pass. A 4,000-page fixture converts with bounded space growth; cached complete books reserve assembly space from actual checkpoint sizes.

Current-only search keeps confirmed source-adjacent publications. Unknown prior lineage remains explicitly unverified; failed metadata is not authority to select another version. Known changed bytes fence the run until a refreshed inventory/group graph is supplied. Source PDFs, historical Markdown and manual edits are preserved.

See [operator workflow](searchable-markdown.md) for the command and persistent status/log paths.

The production transition preserved all 5,673 cached raw-metadata entries and 3,538 separately checkpointed hashes. The first deployed continuous run confirmed 16 published books with only 195/12,890 metadata checks accounted for, and later 29 with 448 checks, while two extraction workers remained active and no extraction failures were reported. Two source-adjacent files were independently matched to their directory-record hashes and embedded source hashes; private evidence is `full-library-markdown/first-publication-verification.json`.
