# Local patch

This is egui_commonmark 0.25.0 from crates.io with one change, in
`src/parsers/pulldown.rs`, `fn blockquote`:

- Before the quote: `self.line.try_insert_start(ui)` became
  `if !self.line.should_not_start_newline_forced { newline(ui); }`.
- After the quote: `self.line.try_insert_end(ui)` became
  `if self.line.should_end_newline_forced { newline(ui); }`.

`Tag::List` turns `should_start_newline` / `should_end_newline` off, so inside
a list item `try_insert_start` did nothing and the quote was drawn after the
item's text in the width left on that line. A second quote in the same item got
a few pixels, wrapped a letter per line, and pushed the rest of the preview
thousands of pixels down. Top-level quotes render as before.

Upstream fixed the same bug for code blocks the same way in
lampsitter/egui_commonmark#105 (released in 0.26). The block quote case is
still unfixed on upstream main as of 2026-11-26. Drop this directory and the
`[patch.crates-io]` entry in `../../Cargo.toml` once a release fixes it.

Regression test: `quotes_in_a_list_item_start_on_their_own_line_at_full_width`
in `src/main.rs`.
