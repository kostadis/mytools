# Feature Specification: File Picker That Works Over SSH X11 Forwarding

**Feature Branch**: `markdown-editor/001-x11-file-picker`

**Created**: 2026-10-25

**Status**: Draft

**Input**: User description: "fix the file picker to work over an x11 session where the server is on a linux box, and I am connected over ssh"

## Context

A key way to use the editor (constitution II.5) is to start it on an Ubuntu
machine over `ssh -X`/`ssh -Y` and use its window on another machine. Editing,
scrolling and the outline already work that way, but **Open** and **Save As**
do not. The file chooser they open is drawn by a helper service in the remote
machine's own desktop session, so it shows up on that machine's physical
screen, or nowhere, instead of in front of the user. Meanwhile the editor
waits for a choice that never comes and looks frozen. The only way to open a
file remotely today is to name it on the command line, and a new document
cannot be saved at all.

This feature is the first fix for a known violation listed when the
constitution was ratified.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Open a file over SSH (Priority: P1)

The user SSHes into the Ubuntu box with X11 forwarding, starts the editor and
presses Open (toolbar or Ctrl+O). A file chooser appears inside the editor
window on the user's screen. They browse folders, pick a Markdown file, and it
opens in the editor.

**Why this priority**: Opening files is the first thing the remote workflow
needs, and today it cannot be done from the UI at all.

**Independent Test**: Over `ssh -X` from a second machine, start the editor
with no arguments, open a Markdown file two folders below the home directory
using only the chooser, and confirm its text shows in the source pane.

**Acceptance Scenarios**:

1. **Given** the editor is running over `ssh -X`, **When** the user chooses
   Open, **Then** a file chooser appears within the editor window on the
   user's display, within one second.
2. **Given** the chooser is open, **When** the user moves into a folder,
   back to its parent, and selects a file, **Then** that file opens and the
   chooser closes.
3. **Given** the chooser is open, **When** the user cancels (Cancel button or
   Esc), **Then** the chooser closes and the current document is unchanged.
4. **Given** the current document has unsaved changes, **When** the user
   chooses Open, **Then** the existing unsaved-changes confirmation appears
   first, and the chooser opens only if the user agrees to continue.
5. **Given** the chooser starts in a folder, **When** it opens, **Then** that
   folder is the current document's folder, or the user's home folder when
   the document has never been saved.

---

### User Story 2 - Save a new document, or save under a new name, over SSH (Priority: P1)

Over the same SSH session, the user chooses Save As (or Save on a document
that has never been saved). A save chooser appears inside the editor window.
They pick a folder, type a file name, and the document is written there.

**Why this priority**: Without it, any new document written remotely is lost
when the editor closes. That is a data-safety failure, and constitution
Article III forbids it.

**Independent Test**: Over `ssh -X`, create a new document, type some text,
press Ctrl+S, save it as `test.md` in the home folder, then confirm on the
remote machine that the file exists with that text.

**Acceptance Scenarios**:

1. **Given** an unsaved new document over `ssh -X`, **When** the user
   presses Save, **Then** a save chooser appears in the editor window with
   the name `Untitled.md` filled in.
2. **Given** the save chooser is open, **When** the user picks a folder,
   enters a name and confirms, **Then** the document is written to that path,
   the title bar shows the new name, and the document is no longer marked
   as modified.
3. **Given** the entered name matches an existing file, **When** the user
   confirms, **Then** the editor asks whether to replace that file, and
   writes nothing unless the user agrees.
4. **Given** a document that already has a file, **When** the user chooses
   Save As, **Then** the chooser starts in that file's folder with its name
   filled in.
5. **Given** the save chooser is open, **When** the user cancels, **Then**
   nothing is written and the document keeps its previous name and modified
   state.
6. **Given** the editor is quitting or replacing a document after the user
   chose "save first", **When** the save chooser is cancelled, **Then** the
   quit or replace is also cancelled and no text is lost.

---

### User Story 3 - Move around quickly in the chooser (Priority: P2)

Remote users often know exactly where a file is. In the chooser they can type
or paste a full path, jump to the home folder with one key and keep typing
from there, and work it fully from the keyboard.

**Why this priority**: Clicking through folders one at a time over a
forwarded display is slow. Typing a path makes the chooser practical to use
every day, not just functional.

**Independent Test**: Over `ssh -X`, open the chooser, press `~`, type
`notes/plan.md`, press Enter, and confirm the file opens without a single
click in the folder list.

**Acceptance Scenarios**:

1. **Given** the chooser is open, **When** the user types a path to a file
   and presses Enter, **Then** that file is chosen.
2. **Given** the user types a path to a folder and presses Enter, **Then**
   the chooser shows that folder.
3. **Given** the chooser is open, **When** the user uses the arrow keys,
   Enter and Backspace (or an equivalent "up one folder" key), **Then** they
   can move through folders and choose a file without the mouse.
4. **Given** a folder holds hidden files (names starting with `.`), **When**
   it is listed, **Then** they are hidden by default and can be shown with a
   toggle.

---

### User Story 4 - Native dialog locally, in-window chooser remotely (Priority: P3)

When the editor runs on the local desktop, Open and Save As keep using the
system's own file dialog, with its bookmarks and recent places. When the
editor is shown on a remote display, or when it cannot tell, it uses the
in-window chooser. The user can always override that choice.

**Why this priority**: The remote case is what is broken. Keeping the native
dialog locally preserves the local experience, but only if a wrong guess
never strands the user.

**Independent Test**: On the local Ubuntu desktop, confirm Open shows the
system dialog. Over `ssh -X`, confirm Open shows the in-window chooser. Then
start the editor with the command-line option for each mode, in both
settings, and confirm the option wins.

**Acceptance Scenarios**:

1. **Given** the editor runs on the local Ubuntu desktop, **When** the user
   chooses Open or Save As, **Then** the system's file dialog appears.
2. **Given** the editor was started from an SSH session with a forwarded
   display, **When** the user chooses Open or Save As, **Then** the
   in-window chooser appears.
3. **Given** the editor cannot tell whether its display is local, **When**
   the user chooses Open or Save As, **Then** the in-window chooser appears.
4. **Given** the editor was started with the command-line option for either
   mode, **When** the user chooses Open or Save As, **Then** that mode is
   used no matter what was detected.
5. **Given** the command-line option is given together with a file path,
   **When** the editor starts, **Then** the file opens as before and the
   option still applies.
6. **Given** the system dialog was chosen but cannot be started or reports
   an error, **When** the user chooses Open or Save As, **Then** the
   in-window chooser appears instead, and the user sees that a fallback
   happened.
7. **Given** the system dialog was chosen, **When** the user wants the
   in-window chooser anyway (for example, because the system dialog
   appeared on another screen), **Then** they can reach it from the editor
   window without restarting.

---

### Edge Cases

- **Folder cannot be read** (no permission, removed while open): the chooser
  shows a readable message and stays usable, so the user can go back up or
  type another path.
- **Very large folder** (10,000+ entries): the listing appears within one
  second and scrolls smoothly (constitution VI.2).
- **Typed path does not exist**: Open says so and stays open. Save treats it
  as a new file name in an existing folder, or reports that the folder does
  not exist.
- **Save target folder is not writable**: the save fails with a readable
  error, the document keeps its modified state, and nothing is lost
  (constitution III.3).
- **File and folder names that are not valid UTF-8**: they are listed in a
  readable form and can still be chosen. Opening a non-UTF-8 file is refused
  (constitution III.4).
- **Symbolic links**: links to folders can be entered, links to files can be
  opened, and broken links are shown but cannot be opened.
- **Window resized while the chooser is open**: the chooser stays fully
  visible and usable.
- **Detection guesses wrong**: an SSH session is mistaken for local, or
  `tmux`/`screen` started locally is reattached over SSH. The user is never
  stranded, thanks to FR-010d, FR-010e and the override in FR-010c.
- **When detection runs**: it runs fresh each time Open or Save As starts
  a chooser, not once at startup (FR-010).
- **The user's display connection drops while the chooser is open**: this
  behaves the same as losing the display during normal editing, and the
  chooser adds no new failure mode.
- **Very slow or network-mounted folder**: a slow listing does not freeze the
  editor window. The chooser shows that it is loading and can still be
  cancelled.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Open and Save As MUST show a file chooser that appears in the
  editor's own window on whatever display the editor is shown on, including
  a display forwarded over `ssh -X`/`ssh -Y`.
- **FR-002**: The chooser MUST NOT depend on any helper program, desktop
  service or session service running on the remote machine.
- **FR-003**: While the chooser is open, the editor window MUST keep
  repainting and responding. The editor MUST NOT freeze while it waits for a
  choice.
- **FR-004**: The open chooser MUST let the user browse folders, go to the
  parent folder, choose a file, and cancel.
- **FR-005**: The save chooser MUST let the user browse to a folder, enter a
  file name, confirm, and cancel. It MUST ask before replacing an existing
  file.
- **FR-006**: The chooser MUST start in the current document's folder, or the
  home folder when the document has no file. The save chooser MUST fill in
  the current file name, or `Untitled.md`.
- **FR-007**: The open chooser MUST show Markdown files (`.md`,
  `.markdown`, `.mdown`) and folders by default, and MUST offer a switch to
  show all files.
- **FR-008**: The chooser MUST accept a typed or pasted absolute path, MUST
  offer a one-step jump to the home folder (the `~` key) after which a path
  relative to home can be typed, and MUST be fully usable from the keyboard.
  Expanding a typed or pasted leading `~/` is deferred to
  [kostadis/mytools#90](https://github.com/kostadis/mytools/issues/90), and
  the README lists it as a known limitation.
- **FR-009**: Hidden entries MUST be hidden by default, with a toggle to
  show them.
- **FR-010**: The editor MUST choose between the system file dialog and the
  in-window chooser as follows:
  - **FR-010a**: The system dialog is used only when the editor is confident
    its display is local, meaning it was not started from an SSH session and
    its display is on the same machine.
  - **FR-010b**: In every other case, including when it cannot tell, it MUST
    use the in-window chooser. When in doubt, it treats the display as
    remote.
  - **FR-010c**: The user MUST be able to force either mode with a
    command-line option when starting the editor. The option overrides
    detection for the whole run, and the editor's help output lists it.
  - **FR-010d**: If the system dialog cannot be started or reports an error,
    the editor MUST fall back to the in-window chooser for that action and
    tell the user it did so.
  - **FR-010e**: While a system dialog is open, the editor window MUST offer
    a way to cancel it and use the in-window chooser instead, so a dialog
    that appeared on another screen never strands the user.
  - **FR-010f**: The in-window chooser MUST be fully supported on Linux
    and macOS, even where the system dialog is the default.
  - **FR-010g**: The mode the editor chose (system or in-window) and the
  reason (detected local, detected remote, uncertain, override, fallback)
    MUST be visible to the user, for example in the chooser or a status
    line, so a wrong guess can be diagnosed.
- **FR-011**: All existing guards MUST still hold: the unsaved-changes
  confirmation before Open, New or Quit, keeping the current document when a
  file cannot be opened, the `.bak` copy when overwriting, and a readable
  error on any failure.
- **FR-012**: Cancelling a save chooser that was opened as part of Quit, New
  or Open MUST cancel that whole action, and the document MUST keep its
  modified state.
- **FR-013**: Opening a file named on the command line MUST keep working
  unchanged.
- **FR-014**: The README MUST say that Open and Save work over `ssh -X`,
  explain the local-versus-remote rule and the command-line option that
  overrides it, and say which
  Ubuntu packages are still needed for the system dialog locally.

### Key Entities

- **Chooser mode decision**: which chooser was used (system or in-window)
  and why (detected local, detected remote, uncertain, override, fallback).
  It is made fresh for each Open or Save As.
- **Chooser session**: one Open or Save As interaction. It holds its purpose
  (open, or save), the current folder, the visible entries, the typed name
  or path, the filter and hidden-files settings, and the action to resume
  afterwards (none, or quit, new or open after a save). It ends with a chosen
  path or a cancel.
- **Folder entry**: one listed item. It has a display name, a kind (folder,
  file, link, broken link), and whether it is hidden or matches the filter.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Over `ssh -X` from a second machine, a user can open an
  existing Markdown file and save a new document using only the chooser,
  succeeding in 10 out of 10 attempts.
- **SC-002**: The chooser appears within 1 second of choosing Open or Save
  As, both locally and over `ssh -X` on a typical LAN.
- **SC-003**: A folder with 10,000 entries lists within 1 second and scrolls
  without visible stutter over `ssh -X`.
- **SC-004**: A user who knows a file's path can open it in under 5 seconds
  by typing that path.
- **SC-005**: No Open or Save As action makes the editor stop responding.
  The window keeps redrawing through every chooser interaction.
- **SC-006**: Across all chooser and save scenarios above, no user text is
  lost and no existing file is replaced without explicit confirmation.
- **SC-007**: In 10 out of 10 SSH sessions (`ssh -X` and `ssh -Y`, started
  from a plain shell, `tmux` and `screen`), Open shows the in-window
  chooser without any override set.
- **SC-008**: A user whose system dialog appears somewhere they cannot see it
  can get to a working chooser in under 10 seconds, without restarting the
  editor.

## Assumptions

- The editor's main window already draws and responds correctly over
  `ssh -X`. Only the file chooser is broken. Rendering over forwarded X11 is
  not in scope unless testing shows otherwise.
- The remote machine is Ubuntu, reached with `ssh -X` or `ssh -Y`. Other
  remote-display setups (VNC, Xpra, X2Go) are expected to work because the
  chooser lives inside the editor window, but they are not acceptance
  targets.
- Files are on the machine running the editor. Browsing the viewing
  machine's files is out of scope.
- Save writes exactly the name the user typed. No extension is added
  automatically.
- Atomic saving (constitution III.2) is a separate spec. This feature keeps
  the current write behaviour, including the `.bak` copy.
- Recent files, bookmarks, drag-and-drop and previewing a file inside the
  chooser are out of scope for this spec.
- macOS behaviour is written for but unverified (constitution II.1/II.4).
  macOS is treated like Linux: the system dialog when local, and the
  in-window chooser when remote or uncertain.

## Constitution Alignment

Constitution 1.1.0, II.5: the system file dialog is a helper and is allowed
as the default only when the editor is confident the session is local. Each
condition II.5 sets maps to a requirement here:

| II.5 condition | Requirement |
|----------------|-------------|
| Every UI surface has an in-window path, always available | FR-001, FR-010f |
| In-window path when not confident; treat doubt as remote | FR-010a, FR-010b |
| Command-line option forces either path | FR-010c |
| Fall back and tell the user if the helper fails | FR-010d |
| Editor stays responsive; can abandon the helper | FR-003, FR-010e |
| A helper is never the only path | FR-010b, FR-010f |
