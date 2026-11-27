# Preview: block quotes inside list items hide the rest of the section

Date: 2026-11-26
Branch: `markdown-editor-nested-quote-fix`

## Symptom

I am building a markdown-editor github.com/kostadis/mytools 

This markdown: 

```markdown
- **Read aloud:** [§171.30] [§171.31]
  > The assault upon the North Gate was furious …

  > Catching a breather just past the fighting, …
- **Do:** the farms are a main food source, …
```

Did not generate correctly. 


## What was actually happening

The content was drawn, just thousands of pixels further down. Rendering the
file in an offscreen egui frame (700px wide) and recording where each piece of
text landed showed, for 3a:

| Text | x | y |
|---|---|---|
| `Read aloud:` | 17 | 53 |
| first quote | **208** | 53 (same line as the label) |
| second quote | **685** | 76 (about 13px of width left) |
| `Do:` | 17 | **5562** |

The second quote got about 13px of width, so it wrapped roughly one character
per line, grew about 5,500px tall, and pushed everything after it out of view.

## Cause

I think this may be a bug in egui_commonmark 0.25.0, the library the preview uses to draw
Markdown. 

egui_commonmark lays out each list item's content in one `horizontal_wrapped`
row. `Tag::List` turns `should_start_newline` and `should_end_newline` off, so
inside a list item the `self.line.try_insert_start(ui)` call at the top of
`fn blockquote` does nothing. The quote's `Frame` is then placed after the
item's text in whatever width is left on that line.

There was an upstream fix the same bug for code blocks in lists in
lampsitter/egui_commonmark#105 (released in 0.26). The block quote case is
still unfixed on upstream main as of 2026-11-26.

## Fix

I wired this fix to get my life moving, so sharing if you are curious. 

egui_commonmark is copied into `vendor/egui_commonmark/` and wired in with
`[patch.crates-io]` in `Cargo.toml`. The only change is in `fn blockquote` in
`src/parsers/pulldown.rs`, written the same way as #105:

- Before the quote: `self.line.try_insert_start(ui)` became
  `if !self.line.should_not_start_newline_forced { newline(ui); }`.
- After the quote: `self.line.try_insert_end(ui)` became
  `if self.line.should_end_newline_forced { newline(ui); }`.
