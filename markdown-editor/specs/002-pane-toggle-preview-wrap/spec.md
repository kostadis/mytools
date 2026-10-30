# Feature Specification: Hideable Editor Pane and Wrapping Preview

**Feature Branch**: `markdown-editor/002-pane-toggle-preview-wrap`

**Created**: 2026-10-28

**Status**: Draft

**Input**: User description: "the ui has three panes, an outline, an editor and preview. I can not make the editor disappear. I can make the other two disappear. And the preview editor doesn't support line-wrap as a result if the number of characters exceeds the size of the view, the line gets truncated"

## Context

The editor window has three panes: the **outline** (heading tree), the
**source editor** (Markdown text) and the **preview** (rendered Markdown). The
toolbar lets the user hide the outline and the preview, but the source editor
is always shown. A user who only wants to read the rendered document, or to
restructure it from the outline while reading the result, cannot get the
source pane out of the way. The preview then has only part of the window.

The preview also cuts off long lines. When a rendered line is wider than the
preview pane, the part past the right edge is not shown and cannot be
reached. The user cannot read the whole document in the preview.

## Clarifications

### Session 2026-10-28

- Q: Should long code-block lines wrap like prose, or stay on one line and scroll sideways inside the block? → A: Keep each line whole. The code block scrolls sideways on its own, and prose still wraps (Story 1 scenario 3, FR-010).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Read long lines in the preview (Priority: P1)

The user opens a document with long paragraphs, long unbroken tokens (URLs,
file paths, identifiers) and code blocks. Everything in the preview fits the
pane's width or can be reached. Prose wraps onto further lines at the pane's
edge, and nothing is cut off. When the user widens or narrows the pane or the
window, the text wraps again to the new width.

**Why this priority**: Content the user cannot see is a correctness bug in
the preview, not a layout preference. Without this fix, the preview cannot
be trusted for long documents, the editor's core use case (constitution
VI.2).

**Independent Test**: Open a document with a 500-character paragraph, a
200-character URL with no spaces, and a code block with a 200-character line.
Show the preview at about a third of the window width. Every character of
each item can be read in the preview, and the paragraph and URL take several
lines.

**Acceptance Scenarios**:

1. **Given** a paragraph longer than the preview's width, **When** the preview
   is shown, **Then** the paragraph wraps at word boundaries within the pane
   and no text lies past its right edge.
2. **Given** a single word or URL wider than the preview pane, **When** the
   preview is shown, **Then** it is broken across lines so all of it is
   visible.
3. **Given** a code block whose lines are wider than the pane, **When** the
   preview is shown, **Then** each line stays whole and unwrapped, and the
   block scrolls sideways on its own, so every character can be read without
   the rest of the preview moving.
4. **Given** wrapped text in the preview, **When** the user resizes the
   window or a pane divider, **Then** the text wraps again to the new width
   with nothing cut off.
5. **Given** wrapped text, **When** the user clicks in the preview or selects
   a heading in the outline, **Then** the panes stay in sync as they do
   today (a click on a wrapped line selects the section that line belongs
   to).

---

### User Story 2 - Hide the source editor (Priority: P2)

The user turns off the source editor from the toolbar, as they can already do
for the outline and the preview. The remaining panes take up the freed space.
Turning it back on restores the editor with the same text, cursor position
and scroll position as before.

**Why this priority**: It gives the user a reading layout (preview only) and
a restructuring layout (outline plus preview). It matters less than Story 1
because the preview is still usable, just narrower, while the editor shows.

**Independent Test**: With a document open, hide the editor. Only the
outline and preview show, and the preview fills the space the editor used.
Hide the outline too, and the preview fills the window. Show the editor
again, and the cursor and scroll position are where they were.

**Acceptance Scenarios**:

1. **Given** all three panes are shown, **When** the user turns off the
   editor, **Then** the editor disappears and the outline and preview fill
   the window.
2. **Given** the editor is hidden, **When** the user turns it back on,
   **Then** it shows the current text, with the cursor and scroll position it
   had before it was hidden.
3. **Given** the editor is hidden, **When** the user changes the document from
   the outline (promote, demote, move, rename, delete), **Then** the change is
   applied to the source text and shows in the preview and, once the editor
   is shown again, in the editor.
4. **Given** the editor is hidden and the document has unsaved changes,
   **When** the user saves, opens, starts a new document or closes the
   window, **Then** it behaves the same as with the editor shown (save writes
   the current text, and unsaved changes trigger a prompt first).
5. **Given** the editor is hidden, **When** the user clicks an outline row
   or in the preview, **Then** the other visible pane moves to the same
   place.
6. **Given** only one pane is shown, **When** the user tries to hide it,
   **Then** the editor keeps it shown, so the window never goes empty.

---

### Edge Cases

- **Every pane turned off**: the last visible pane cannot be turned off. Its
  toggle stays on and shows why when the user hovers over it.
- **Empty document with the editor hidden**: the preview shows its existing
  placeholder, and the user can still turn the editor back on to start
  typing.
- **Keyboard focus in the editor when it is hidden**: focus leaves the editor,
  so typed keys are not sent to a hidden text field. Outline shortcuts work
  as they do whenever the editor lacks focus (constitution VI.1).
- **A very narrow preview** (a few characters wide): text still wraps and
  stays reachable, and nothing panics or loops.
- **Content that cannot be broken**, such as an image or a wide table: it
  stays reachable (it is scaled or scrolls sideways) and is never cut off
  with no way to see it.
- **Huge documents** (constitution VI.2 baseline, about 40,000 lines):
  wrapping in the preview and hiding or showing the editor keep the editor
  interactive. Hiding the editor does not make the app process the whole
  document again on every frame.
- **Over `ssh -X`**: the new toggle and the wrapped preview behave the same as
  on a local display.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The toolbar MUST offer a show/hide toggle for the source editor
  that sits with the existing Outline and Preview toggles and works like them.
- **FR-002**: When the editor is hidden, the visible panes MUST fill the
  space it used.
- **FR-003**: Hiding the editor MUST NOT change the document text, its
  unsaved-changes state, its undo history, or the file it is tied to.
- **FR-004**: Showing the editor again MUST restore its cursor and scroll
  position from before it was hidden, as long as the text still contains
  that position (otherwise the nearest valid one).
- **FR-005**: While the editor is hidden, outline edits, file operations
  (New, Open, Save, Save As), unsaved-changes prompts and their shortcuts
  MUST work as they do when it is shown.
- **FR-006**: While the editor is hidden, clicking in the outline or the
  preview MUST keep the remaining visible panes in sync, as the Synced panes
  section of the README describes.
- **FR-007**: At least one pane MUST stay visible at all times. Turning off
  the last visible pane MUST be refused, and the toggle MUST say why.
- **FR-008**: Prose in the preview (paragraphs, list items, block quotes,
  headings, table cells) MUST wrap to the pane's current width, at word
  boundaries where possible.
- **FR-009**: A single word, URL or other token wider than the preview MUST
  be broken across lines, never cut off.
- **FR-010**: Preview code blocks MUST NOT wrap. A code block with lines
  wider than the pane MUST scroll sideways on its own, so every character can
  be reached. Prose around it keeps wrapping to the pane width, and the
  preview as a whole never scrolls sideways.
- **FR-011**: When the preview's width changes (window resize, divider drag,
  or another pane being shown or hidden), the preview MUST wrap again to the
  new width.
- **FR-012**: Wrapping MUST be applied only to how the preview is drawn. It
  MUST NOT insert line breaks or otherwise change the source text
  (constitution III.1).
- **FR-013**: Clicking a wrapped line in the preview MUST map to the same
  section as clicking anywhere else in that section, and scrolling the
  preview to a section MUST still land on that section.
- **FR-014**: The README MUST describe the editor toggle, the rule that one
  pane always stays visible, and how the preview handles long lines and code
  blocks (constitution VII.1).

### Key Entities

- **Pane visibility**: a show/hide flag for each of the three panes (outline,
  editor, preview), with the rule that at least one is on. It lasts for the
  session only, like the existing toggles.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the Story 1 test document, at any preview width from 20
  characters up to the full window, 100% of the text can be read in the
  preview, and nothing is clipped at the right edge.
- **SC-002**: The user can switch from the three-pane layout to a
  preview-only layout in two clicks and back in two clicks, with no change
  to the document.
- **SC-003**: After hiding and then showing the editor, its cursor and scroll
  position match what they were before in 100% of cases where the text did
  not change in between.
- **SC-004**: With the constitution's 40,000-line baseline document,
  scrolling the wrapped preview and toggling the editor feel as responsive as
  scrolling the preview does today. The timing check shows no regression,
  locally or over `ssh -X`.
- **SC-005**: A document saved after any number of editor toggles and preview
  resizes is byte-for-byte identical to one saved without them.

## Assumptions

- "Preview editor" in the request means the rendered preview pane. The source
  editor already wraps long lines to its pane's width.
- Pane visibility, including the new editor toggle, is not remembered
  between runs, just as the Outline and Preview toggles are not today.
  Remembering layout is a separate feature.
- The new toggle is a toolbar control like the existing two. A keyboard
  shortcut for pane toggles is out of scope.
- Images and wide tables in the preview are covered only by "never cut off
  with no way to reach them". Changing how tables are rendered is out of
  scope.
- The behaviour is shared code with no platform-specific branch. It is
  written for macOS but not verified there (constitution II.1, II.4).
- Over `ssh -X`, this feature adds no new UI surface beyond a toolbar toggle
  in the existing window. It still needs the forwarded-display run before
  merge, as constitution II.5 requires.
