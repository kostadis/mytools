# Contract: Chooser UI Behaviour

**Requirements**: FR-001–FR-012 | **Data model**: [ChooserRequest](../data-model.md#chooserrequest)

## Entry points

| Trigger | Precondition | Effect |
|---------|--------------|--------|
| Open button / Ctrl+O (Cmd+O) | No active request. Unsaved changes → existing confirmation first | Starts `ChooserRequest { purpose: Open }` |
| Save As button / Ctrl+Shift+S | No active request | Starts `SaveAs { after: Nothing }` |
| Save / Ctrl+S on an unsaved document | No active request | Starts `SaveAs { after: Nothing }` |
| "Save first" in the unsaved-changes confirmation, document never saved | — | Starts `SaveAs { after: Continue(New / Open / Quit) }` |

While a request is active, the toolbar file buttons and the file shortcuts
are disabled. The source, preview and outline still draw (FR-003).

## In-window chooser

| Item | Behaviour |
|------|-----------|
| Placement | A modal window inside the editor window, sized to fit it and kept fully visible when the window is resized |
| Title | "Open" or "Save As". The caption shows the mode and reason, for example *"Built-in chooser — SSH session detected"* (FR-010g) |
| Start folder | The current document's folder, or else home (FR-006) |
| File name (save) | The current file name, or `Untitled.md` (FR-006) |
| Filters (open) | **Markdown** (`md`, `markdown`, `mdown`, default) and **All files** (FR-007) |
| Hidden entries | Hidden; a "Show hidden" toggle (FR-009) |
| Path field | Typing a file path and pressing Enter picks it (open). A folder path opens that folder. A new name in an existing folder saves there (save) (FR-008) |
| Home | Home button in the sidebar, and the `~` key (FR-008) |
| Keyboard | ↑/↓ select, Enter opens a folder or confirms, Backspace or Alt+↑ goes to the parent, Esc cancels |
| Existing file (save) | "Replace *name*?" confirmation. Writes nothing unless confirmed (FR-005) |
| Unreadable folder | An inline message. The chooser stays usable |
| Loading | Folders load in the background with a loading indicator. Cancel always works |

## System dialog (when `decision.kind = System`)

While the system dialog is open, the editor shows a small modal panel:

> **Waiting for the system file dialog…**
> *System file dialog — local display* (or *— set with --chooser*; FR-010g)
> If it didn't appear on this screen, use the built-in chooser.
> [ Use built-in chooser instead ]   [ Cancel ]

| Event | Result |
|-------|--------|
| The dialog returns a path | `Chosen(path)` |
| The dialog returns nothing, no failure logged | `Cancelled` |
| The dialog returns nothing, failure logged (R5) | The in-window chooser opens with the banner *"The system file dialog could not be opened; using the built-in chooser."* |
| "Use built-in chooser instead" | The in-window chooser opens at once. A late reply from the system dialog is ignored (R4) |
| "Cancel" | `Cancelled`. A late reply from the system dialog is ignored |

## Outcomes

| Outcome | Open | Save As |
|---------|------|---------|
| Path chosen | `Document::open`. On error: message shown, current document kept (III.3) | `Document::save_as` (keeps `.bak`). On OK: title updated, not modified, then any follow-up action. On error: message shown, still modified, follow-up dropped |
| Cancelled | No change | No write. Name and modified state unchanged. Follow-up (New / Open / Quit) dropped (FR-012) |
