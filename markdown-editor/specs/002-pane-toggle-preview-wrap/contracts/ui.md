# UI Contract: Pane Toggles and Preview Layout

The editor exposes no API. Its contract is with the user and is checked by
headless egui tests and by the hand checks in [quickstart.md](../quickstart.md).

## Toolbar toggles

```
[New] [Open…] [Save] [Save As…] | [x] Outline  [x] Editor  [x] Preview | <file name>
```

- Three checkboxes in this order. **Editor** is new and sits between the existing two.
- A checkbox that is the only one ticked is drawn **disabled**, and hovering over
  it shows: *"At least one pane must stay visible"*.
- Toggles are mouse-only, as today. No new keyboard shortcut.
- Over `ssh -X` they are drawn in the editor window like the rest of the toolbar
  (II.5). This adds no new UI surface.

## Hiding the editor

| Event | Guarantee |
|---|---|
| Editor turned off | The editor's keyboard focus is released in the same frame. Any pending scroll for the source pane is dropped. Document text, dirty flag, file path and undo history are unchanged. |
| Editor turned on | Same cursor position and scroll position as when it was hidden, or the nearest valid ones if the text got shorter. It does not jump to the last outline or preview click. |
| Editor hidden + outline edit | Applied to the source text. The preview and outline update. |
| Editor hidden + Ctrl/Cmd+N/O/S/Shift+S, or window close | Same behaviour and prompts as with the editor shown. |
| Editor hidden + outline or preview click | The other visible pane follows (README "Synced panes"). |
| Outline is the only pane | The outline fills the content area. |

## Preview layout

| Content (top level of a section) | Behaviour |
|---|---|
| Paragraphs, headings, lists, block quotes, links, inline code | Wrap to the preview's width. A token wider than the pane is broken across lines. |
| Fenced or indented code block | Lines are never wrapped. The block has its own horizontal scroll bar when it is wider than the pane. Text is selectable. |
| Table (including converted HTML tables) | Keeps its natural column widths. It has its own horizontal scroll bar when it is wider than the pane. |
| Anything after a wide table or code block | Wraps at the pane's width, never the width of the wide element. |
| Code block or table *inside* a list item or block quote | Known limitation: a code block wraps, and a table is squeezed into narrow columns. Nothing is cut off. Documented in the README. |

Invariants, asserted in headless tests:
- The preview scroll area's content width never exceeds its viewport width
  by more than one pixel.
- No text shape in the preview extends past the viewport's right edge, except
  inside a code-block or table horizontal scroll area.
- A click anywhere in a section, including a wrapped line or inside a code or
  table scroller, maps to that section (FR-013).
