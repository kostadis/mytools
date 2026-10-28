# Quickstart: Validating Hideable Editor and Wrapping Preview

## Prerequisites

The Ubuntu packages in the README, and a stable Rust ≥ the `rust-version` in
`Cargo.toml`. For the remote check you also need a second machine with an X server.

## Automated

```bash
cd markdown-editor
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test                                   # unit + headless UI tests
cargo test --release -- --ignored preview_timing --nocapture   # VI.2 timing check
```

Expected:
- `preview_blocks` unit tests pass: chunks cover the body exactly, top-level
  code and tables split out, nested ones left in prose, no panic on odd input.
- `panes` unit tests pass: the last visible pane cannot be hidden.
- The headless tests pass: preview content stays within the viewport for the
  Story 1 document, the editor keeps its cursor and scroll after being hidden and
  shown, and hiding it keeps the text and dirty flag.
- `preview_timing` prints the cold (cache build) and warm (steady frame) preview
  times for the 40,000-line fixture. Record them in `pr-notes.md` next to the
  numbers from the commit before this change. Warm time must not regress.

## By hand (local, then over `ssh -X`)

Make `wrap-test.md`:

````markdown
# Wrap test

lorem ipsum dolor sit amet lorem ipsum dolor sit amet lorem ipsum dolor sit amet lorem ipsum dolor sit amet lorem ipsum dolor sit amet lorem ipsum dolor sit amet lorem ipsum dolor sit amet

https://example.com/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

| clause | text |
|---|---|
| 1.1 | word word word word word word word word word word word word word word word word word word word word word word word word word word word word |

This paragraph comes after the wide table and must wrap at the pane edge, not run off it.

```
let a_very_long_line = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";
```

## Second section
Text after the code block wraps too.
````

1. `cargo run --release -- wrap-test.md`. Drag the divider so the preview is
   about a third of the window.
   - The paragraph and URL wrap, and the URL breaks mid-token.
   - The table and code block each get their own horizontal scroll bar and are
     readable end to end.
   - The paragraph after the table and the text in "Second section" wrap at the pane edge. **This was the reported bug.**
   - Resize the window: everything wraps again to the new width.
2. Click "Second section" in the preview. The outline selects it and the editor
   scrolls to it.
3. Put the cursor mid-way down the editor and scroll a little. Untick **Editor**.
   The outline and preview fill the window.
   - Promote a heading in the outline. The preview updates.
   - Click an outline row. The preview follows.
   - Untick **Outline**. The preview fills the window, and **Preview** is now
     greyed out and its hover text says why.
   - Ctrl+S saves. Closing with unsaved changes asks first.
4. Tick **Editor** again. The cursor and scroll position are where you left them,
   and the earlier promote shows in the text.
5. Untick **Editor** and **Preview** with **Outline** ticked. The outline fills
   the whole area.
6. Save the file and compare it with `git diff --no-index` against a copy saved
   without any toggling. There should be no difference (SC-005).
7. Repeat steps 1–6 over `ssh -X` from another machine and note it in the PR
   (II.5, V.2).
