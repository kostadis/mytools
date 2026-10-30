# Research: Hideable Editor Pane and Wrapping Preview

All findings below were measured on 2026-10-28 with a headless probe built against
the exact locked versions (egui 0.36.2, egui_commonmark 0.25.0). The probe rendered
Markdown samples into the right-hand column of a `ui.columns(2)` inside a vertical
`ScrollArea`, exactly as `MarkdownEditor::draw` does, at a 900 px window (446 px
preview viewport). It recorded the scroll area's content width against its
viewport width, and the screen position of every text shape.

## R1 — What actually truncates in the preview

**Finding.** Only **tables** overflow by themselves. Paragraphs, 200-character URLs
with no spaces, inline code, list items, block quotes, link text, bold headings and
fenced code blocks all wrapped inside the viewport:

| Sample | Content width (viewport 446) |
|---|---|
| 500-char paragraph | 442 |
| 200-char bare URL | 444 |
| 200-char code line, no spaces | 446 |
| 200-char inline code | 446 |
| table with one long cell | **1369 (clipped)** |

**The cascade (the user's symptom).** A paragraph drawn *after* a wide table wrapped
at **1363 px** instead of 421 px. A wide table grows the preview's `Ui` past the
viewport (egui grows `max_rect` with content), and every later section,
including those rendered through `ui.push_id`, inherits that width. So one wide
table anywhere cuts off every line below it. Tables are common here because
`html_table` turns HTML tables into pipe tables, and legal documents have many.

**Why tables.** egui_commonmark lays out each table cell with `ui.horizontal`, and
`Ui::wrap_mode()` returns `Extend` for a non-wrapping horizontal layout. Cell text
therefore never wraps.

**Why code blocks already wrap.** egui_commonmark draws code blocks as a read-only
`TextEdit` with `desired_width(max_width)` and a layouter that sets
`job.wrap.max_width`. It has no option to turn wrapping off.

## R2 — Containing wide tables

| Option | Result | Verdict |
|---|---|---|
| Force `style.wrap_mode = Wrap` on the preview | Nothing cut off and no cascade, but egui's `Grid` gives each column about 34 px. A 40-word cell becomes a 40-row strip, one word per line; 8 columns of 60 chars become 12-row strips | Rejected as the main fix: legal tables would be unreadable |
| Each top-level table in its own `ScrollArea::horizontal` | Table keeps its natural layout and scrolls sideways; the content after it wraps at 421 px | **Chosen** |
| The whole section in `ScrollArea::horizontal` | The section's prose wraps at the widened width (1363 px) | Rejected |

**Decision.** Top-level tables are rendered alone inside their own horizontal scroll
area, matching the spec's clarified code-block behaviour (option B). Prose runs are
rendered with `wrap_mode = Wrap` forced, as a safety net so that a table nested
inside a list item or block quote (which egui_commonmark still draws inline)
cannot start the cascade. A nested table is squeezed into narrow columns but stays
readable and contained. This is documented as a known limitation (VI.3).

## R3 — Non-wrapping code blocks (clarification B)

**Decision.** Pull top-level code blocks (fenced and indented) out of each
section and draw them in-house: a framed, monospace, selectable `Label` set to
`extend()`, inside its own `ScrollArea::horizontal`. The probe confirmed that a
200-char line drawn this way stays inside a 446 px viewport and does not widen
what follows.

**Rationale.** egui_commonmark always wraps code blocks (R1). The editor builds
egui_commonmark without its syntax-highlighting feature, so code is plain
monospace today, and drawing it ourselves loses no highlighting.

**Deliberate differences from today's code blocks:**
- No copy icon. Text is selectable, so Ctrl/Cmd+C still works.
- Code blocks nested in list items or block quotes are still drawn by
  egui_commonmark and still wrap. This is a known limitation, documented in the
  README.

**Alternatives considered.** Forking or patching egui_commonmark to add a no-wrap
option was rejected: it means a vendored crate for one flag. Wrapping code like
prose was option A, which the maintainer rejected.

## R4 — Splitting a section into prose, code and tables

**Decision.** Use `pulldown-cmark` 0.13.4 directly, with the same options
egui_commonmark enables (`ENABLE_TABLES | ENABLE_TASKLISTS | ENABLE_STRIKETHROUGH |
ENABLE_FOOTNOTES | ENABLE_DEFINITION_LIST`). Walk `into_offset_iter()`, track
nesting depth, and cut the body at the byte ranges of depth-0 `CodeBlock` and
`Table` events. Consecutive other blocks merge into one prose run.

**Rationale.** It is the parser that egui_commonmark already runs, so "what is a
table or a code block" matches the renderer exactly, including the edge cases a
hand-written fence scanner would get wrong (fences in list items, indented code,
tables that are actually paragraphs).

**Dependency justification (IV.3).** pulldown-cmark 0.13.4 is already in
`Cargo.lock` as egui_commonmark's parser, so no new code is compiled or downloaded.
It is MIT-licensed and pure Rust with no platform or display code, so it works on
Linux and macOS and is unaffected by X11 forwarding. It is added with
`default-features = false` (dropping `getopts` and `html`), and the version is
pinned to match the lock.

**Alternative.** Extending `outline.rs`'s fence detection was rejected: it only
knows about fences, not tables or indented code, and doesn't know list context.

## R5 — Cost (VI.2)

- Splitting is whole-document work, so it runs **only when the text changes**.
  It is cached against the text, the same pattern as `OutlinePanel::sync`.
- That cache also takes over two jobs the preview does on *every frame* today:
  `html_table::tables_to_markdown` per section and `outline::link_definitions`
  over the whole text. Per-frame preview work should therefore go down, not up.
- No large-document fixture or timing check exists yet, although VI.2 requires
  one. This feature adds a deterministic generator for the 40,000-line legal-shaped
  fixture and an `#[ignore]`d headless timing test. It is run before the change (on
  the current code) and after, and the numbers go in `pr-notes.md`.

## R6 — Hiding the editor without losing its state

**Findings (egui 0.36.2 source).**
- `TextEditState` and `ScrollArea` state are stored with `insert_persisted` under the
  widget's `Id` and are not cleared when a widget is not drawn, so cursor and
  scroll survive hiding **as long as the Ids are the same when it is shown again**.
- Today they are not: the source `ScrollArea` uses `id_salt("source")` in the
  two-column layout and `"source_only"` without the preview, and the `TextEdit` id
  comes from its parent `Ui`, which differs between the two layouts. Toggling the
  *preview* already resets the editor's scroll position.
- egui's focus "dead-man's switch" (`Memory::end_pass`) clears focus from a widget
  that was not drawn in a frame.

**Decision.** Give the source `TextEdit` an explicit `Id` and its `ScrollArea` one
`id_salt` in every layout. Do the same for the preview's scroll area. When the editor
is hidden, call `surrender_focus` on it explicitly rather than relying on the
one-frame dead-man's switch, and drop any pending `source_target`, as the
preview drops `preview_target` when it is hidden. On being shown again, the
editor returns to where it was, not to the last outline click (FR-004).

## R7 — Layout with any combination of panes

| Outline | Editor | Preview | Layout |
|---|---|---|---|
| on/off | on | on | outline side panel (if on) + two columns, as today |
| on/off | on | off | outline side panel (if on) + editor fills |
| on/off | off | on | outline side panel (if on) + preview fills |
| on | off | off | outline fills the whole area (not a 280 px side panel next to blank space) |
| off | off | off | impossible (FR-007) |

**Decision.** A small pure `Panes` value holds the three flags and refuses to turn
off the last visible one. The toolbar draws each toggle disabled, with a hover
reason, when it is the last one on. `draw` dispatches on the combination through
one extracted method, so the layout logic doesn't grow `draw` (IV.4).
