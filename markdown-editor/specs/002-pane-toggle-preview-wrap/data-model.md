# Data Model: Hideable Editor Pane and Wrapping Preview

No on-disk data changes. The document text is untouched by both stories (FR-003,
FR-012, constitution III.1). These are in-memory, session-only values.

## Panes (pure, `src/panes.rs`)

Which of the three panes are shown.

| Field | Type | Initial |
|---|---|---|
| outline | bool | true |
| editor | bool | true |
| preview | bool | true |

**Invariant:** at least one field is true at all times (FR-007).

**Operations:**
- `is_shown(pane) -> bool`
- `can_hide(pane) -> bool`: false when `pane` is the only one shown.
- `set(pane, shown) -> bool`: applies the change and returns true, or leaves
  everything unchanged and returns false when it would hide the last pane.

**Transitions:** any state with at least one pane shown can reach any other such
state one toggle at a time. Hiding the editor triggers the side effects in
[contracts/ui.md](contracts/ui.md) (focus surrendered, pending source scroll
dropped).

**Lifetime:** created at start-up and never persisted (spec Assumptions). It
replaces the current `show_outline` / `show_preview` fields.

## PreviewChunk (pure, `src/preview_blocks.rs`)

One drawable run of a section body, after `html_table` conversion.

| Variant | Carries | Drawn as |
|---|---|---|
| `Prose(Range<usize>)` | byte range of one or more consecutive blocks that are not top-level code or tables | egui_commonmark, wrap forced |
| `Table(Range<usize>)` | byte range of one top-level table | egui_commonmark inside its own horizontal scroll area |
| `Code { range, content }` | full range of a top-level fenced or indented code block, and its literal content without fences or indentation | in-house monospace, non-wrapping, inside its own horizontal scroll area |

**Validation rules (unit-tested):**
- Chunk ranges are in order, do not overlap, and together cover the body exactly
  from start to end. Blank lines between blocks belong to the neighbouring
  prose chunk.
- Consecutive prose blocks merge into one `Prose` chunk, and there are never two
  `Prose` chunks in a row.
- Code blocks or tables inside list items, block quotes or footnote definitions
  stay inside their `Prose` chunk.
- `Code.content` equals the text pulldown-cmark reports for the block,
  byte for byte, including trailing whitespace on each line.
- Never panics on any input, including an empty body, an unclosed fence, or
  non-ASCII text (V.3).

## PreviewCache (UI, in `src/main.rs` next to `preview`)

Derived from the text, rebuilt only when the text changes (VI.2, IV.2).

| Field | Meaning |
|---|---|
| text | copy of the source text it was built from (same pattern as `OutlinePanel::parsed_text`) |
| links | `outline::link_definitions(text)`, computed once per change instead of once per frame |
| sections | for each outline block: the `html_table`-converted body (owned `String`) and its `Vec<PreviewChunk>` |

Each prose and table chunk gets `links` appended at draw time, as sections do
today, so reference-style links keep resolving.
