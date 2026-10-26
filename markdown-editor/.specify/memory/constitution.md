<!--
SYNC IMPACT REPORT
==================
Version change: 1.0.0 → 1.1.0
Bump type: MINOR (II.5 expanded: adds a permitted case and the conditions
on it; no principle removed)

Modified principles:
  - II.5 Remote Display: helper-drawn UI (portals, session services,
    external dialog programs) may now be the DEFAULT for sessions the editor
    is confident are local, not only an opt-in. Conditions: in-window path
    when not confident, command-line override, fall back on helper failure,
    responsive editor with an escape to the in-window path while the helper
    is open. Every UI surface must still have an in-window path, and a
    helper is never the only path.

Driven by: specs/001-x11-file-picker (FR-010, option C chosen by the
maintainer 2026-10-25).

Templates reviewed:
  ✅ .specify/templates/plan-template.md: no change; plans cite II.5.
  ✅ .specify/templates/spec-template.md: no change.
  ✅ .specify/templates/tasks-template.md: no change.

Known violations: unchanged from 1.0.0 (below).

----- Ratification (1.0.0) -----

Version change: (none, blank template) → 1.0.0
Bump type: initial ratification

Added sections: Preamble; Articles I–VII; Governance.

Known violations at ratification (each to be fixed by its own spec):
  - II.5 Remote display: open/save use rfd's xdg-portal backend, so the
    dialogs never reach a display forwarded with `ssh -X`.
  - III.2 Atomic saves: write_with_backup calls fs::write directly on the
    target path.
  - VI.2 Massive documents: the 40,000-line baseline is unmeasured; the
    single TextEdit, per-frame preview layout and per-frame
    link_definitions scan are the first suspects.

Templates reviewed:
  ✅ .specify/templates/plan-template.md: the Constitution Check gate is a
     per-feature placeholder; plans fill it by citing Articles I–VII.
  ✅ .specify/templates/spec-template.md: no constitution references.
  ✅ .specify/templates/tasks-template.md: no constitution references.

Deferred items: none.
-->

# Markdown Editor Constitution

## Preamble

This constitution governs every specification, plan, task and change for the
Markdown Editor: a native desktop Markdown editor written in Rust. It is
cross-platform, but Unix-like desktops come first: **Ubuntu and macOS are the
supported targets**. When a spec, plan or task conflicts with this
constitution, the constitution wins and the artifact MUST be revised.

## Article I — Product Identity

### I.1 A Native Rust Editor

The editor is one native Rust binary built with Cargo on stable Rust (the
`rust-version` in `Cargo.toml` is the floor). It MUST NOT need a browser
engine, an embedded web view, a background server, a network connection or a
language runtime other than the binary itself. It opens fast, edits local
files and gets out of the way.

### I.2 Plain Text Is the Product

Users edit Markdown source. The outline and the preview are views of that
source. The editor MUST NOT bring in a proprietary document format, a sidecar
metadata file or hidden state that changes what is written to disk.

## Article II — Platform Support

### II.1 Supported Targets

- **Ubuntu (current LTS), X11 and Wayland**: primary target. Every feature
  MUST build, pass tests and be exercised by hand here before merge.
- **macOS (current release, Apple Silicon)**: design target, not yet
  verified. No macOS build machine is available yet, so macOS builds and runs
  are not a merge requirement. Instead, a change MUST stay macOS-ready: shared
  code uses portable APIs and egui's command modifier, and any behaviour that
  needs platform-specific code (fonts, shortcuts, file dialogs, rendering,
  window lifecycle) gets a macOS branch or fallback written alongside the
  Linux one. The spec or plan MUST list it as "unverified on macOS". When a
  macOS machine or CI runner becomes available, this clause is amended to
  require a macOS build before merge.
- **Other Unix-likes and Windows**: not supported, but not excluded on
  purpose. A change MUST NOT add Unix-only assumptions to shared code when a
  portable standard-library API exists.

### II.2 Platform Code Is Isolated and Gated

Platform-specific behaviour (GPU workarounds, system font paths, modifier
keys, desktop-portal quirks) MUST sit behind `#[cfg(target_os = ...)]` or an
equivalent explicit check, in a small named function with a comment that
explains which platform problem it works around. Platform branches MUST NOT
be scattered through the editing logic.

### II.3 Degrade, Do Not Fail

When a platform resource is missing (a system font, a GPU feature, a portal),
the editor MUST fall back to working behaviour, as the heading font fallback
chain and the VMware software-GL fallback already do. A user-set environment
override MUST always beat an automatic platform choice.

### II.4 Platform Claims Are Evidence-Based

The README and specs MUST say which platforms a behaviour has actually been
run on. "Written for macOS", "builds on macOS" and "works on macOS" are
different claims. Until macOS verification exists, the README and specs MUST
NOT claim anything stronger than "written for macOS, unverified". Each
spec's macOS-unverified items are collected so they can be checked in one
pass once a Mac is available.

### II.5 Remote Display Is a First-Class Use Case (NON-NEGOTIABLE)

A key way to use the editor is to start it on one machine and display it on
another, typically `ssh -X`/`ssh -Y` into the Ubuntu box with the window
forwarded to the local X server. The editor MUST be fully usable that way:

- Every UI surface (file open/save pickers, confirmations, errors, menus,
  pop-ups) MUST have an implementation that draws in the editor's own
  window, or through a mechanism that is guaranteed to draw on the editor's
  `$DISPLAY`. That in-window path MUST always be available.
- A helper process or session service that may draw somewhere else or not
  at all (an xdg-desktop-portal, a D-Bus session service, a
  desktop-environment daemon, or a separately launched dialog program) MAY
  be used as the default **only** for sessions the editor is confident are
  local, and only when all of the following hold:
  - when the editor is not confident the session is local, it uses the
    in-window path (when in doubt, it treats the session as remote);
  - the user can force either path with a command-line option;
  - if the helper fails to start or reports an error, the editor falls back
    to the in-window path and tells the user;
  - while the helper's UI is open, the editor stays responsive and offers a
    way to abandon the helper and use the in-window path, so a helper that
    draws on another screen never strands the user.
- A helper MUST NOT be the only path for any UI surface.
- Rendering MUST work over a forwarded X11 connection, falling back to
  software rendering where hardware GL is not available (see II.3).
- Any change that adds or alters a UI surface MUST be exercised over
  `ssh -X` from another machine before merge, and the PR records that run.

**Known violation at ratification:** open and save use `rfd`'s default
`xdg-portal` backend, so the dialogs open on the remote machine's own session
and not on the forwarded display. Fixing this is the first spec under this
constitution.

## Article III — Data Safety (NON-NEGOTIABLE)

### III.1 The User's Text Is Sacred

No feature may lose, reorder or silently rewrite the user's text. In
particular:

- Structural operations (outline parse → edit → serialize) MUST round-trip
  untouched content byte for byte, including line endings (LF and CRLF),
  heading separators and trailing whitespace.
- Preview-only transforms (such as HTML tables rendered as pipe tables) MUST
  NOT change the source buffer.
- Multi-target operations are all-or-nothing: if any part would be invalid
  (for example a heading pushed past H1 or H6), nothing changes.

### III.2 Saving Never Destroys the Previous Version

Overwriting an existing file MUST keep the previous contents recoverable
(today `<name>.bak`). Writes MUST be atomic, so a crash, a dropped SSH
session or a full disk mid-save cannot leave a truncated or half-written
file. Write the new contents to a temporary file in the same directory,
flush and `fsync` it, then rename it over the target. The original file's
permissions are kept. If any step fails, the target file is left as it was.

**Known violation at ratification:** `write_with_backup` calls `fs::write`
directly on the target path.

### III.3 Failure Leaves State Intact

A failed open, save or parse MUST leave the current document and its dirty
state as they were and show the user a readable error. Closing, opening or
starting a new document over unsaved changes MUST ask the user first.

### III.4 Encoding

The editor reads and writes UTF-8. Input that is not valid UTF-8 MUST be
refused with an error, never decoded lossily and saved back.

## Article IV — Architecture

### IV.1 A Pure Core, a Thin UI

Document logic (the text model, outline parsing and editing, Markdown
transforms such as `html_table`) MUST be plain Rust with no dependency on
`egui`/`eframe`, so it can be tested without a window. UI modules turn user
input into core operations and draw results; they MUST NOT own document
semantics.

### IV.2 The Source Is the Single Source of Truth

The outline and preview are derived from the source text every time they are
needed, or cached against it. No pane may hold an independent copy of the
document that can drift. Pane synchronisation (scroll and selection) is
expressed as byte offsets and block indices into the source.

### IV.3 Minimal, Deliberate Dependencies

Every new crate MUST be justified in the plan: what it does, why the standard
library or an existing dependency is not enough, its licence, that it
supports Linux and macOS, and, for anything that touches UI or the display,
that it works over X11 forwarding (II.5). Default crate features stay off unless needed.
Pinned versions in `Cargo.lock` are committed.

### IV.4 Bounded Complexity

New functions SHOULD stay readable at a glance. A function whose cognitive
complexity passes roughly 25 (by the codebase-memory-mcp graph) MUST be
justified in the plan or split. Existing hotspots (`OutlinePanel::row`,
`OutlinePanel::perform`, `OutlinePanel::shortcuts`) are not precedent for new
code.

## Article V — Quality Gates

### V.1 Tests Are Part of the Change

- Every core behaviour change ships with unit tests next to the code
  (`#[cfg(test)] mod tests`).
- Every data-safety guarantee in Article III has a test that would fail if
  the guarantee broke (round-trip, all-or-nothing, failed open keeps state,
  backup on save).
- UI interaction bugs get a headless egui test where practical, like the
  shift-click range-selection test.
- Tests that touch the filesystem use unique temporary paths and clean up.

### V.2 Merge Gate

Before merge: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`
and `cargo test` MUST pass on Ubuntu. The PR MUST record which platforms the
change was run on, and whether it was run locally, over `ssh -X`, or both.

### V.3 No Panics on User Input

Production code MUST NOT panic on any document content or file-system state.
`unwrap`/`expect` outside tests are allowed only where an invariant makes
failure impossible, with a comment naming that invariant.

## Article VI — User Experience

### VI.1 Native Conventions

Shortcuts follow platform conventions (Ctrl on Linux, Cmd on macOS) through
egui's command modifier. Text-editing shortcuts belong to the text editor
when it has focus. Pane shortcuts apply only when it does not.

### VI.2 Massive Documents Are a Core Use Case

The editor is built for very large Markdown documents, not only notes.

- **Baseline:** a 1,000-page legal document, about 40,000 lines and a few
  megabytes of text. Typing, scrolling, outline operations and preview
  rendering MUST stay interactive at that size, measured over `ssh -X` as
  well as locally. This is a floor, not a ceiling. A design that only just
  reaches the baseline is not enough.
- **Per-frame work scales with what is on screen, not with document size.**
  Whole-document work (parsing, scanning, layout) runs only when the text
  changes, is cached against the text, and is incremental where possible.
  Anything that can grow with the document (outline rows, preview sections,
  source lines) MUST be virtualised.
- **Measured, not assumed.** A large-document fixture shaped like legal text
  lives in the repo with a repeatable timing check. It has at least 40,000
  lines, long paragraphs, deeply nested numbered sections (thousands of
  outline entries down to H5/H6), cross-references, tables and some code
  blocks. Specs for features that touch whole-document work
  MUST state their cost and show the timing check before and after.

**Unmeasured at ratification:** the source pane is a single
`egui::TextEdit` over the whole text, the preview lays out every section on
every frame, and `outline::link_definitions` rescans the whole text on every
frame. These are the first suspects when the baseline is measured.

### VI.3 Known Limitations Are Documented

Behaviour that departs from the CommonMark rendering a user expects (for
example footnotes that do not resolve across preview sections) MUST be
written down in the README when it ships, not found by users.

## Article VII — Documentation and Workflow

### VII.1 The README Describes Behaviour

Every user-visible feature updates `README.md` in the same change: what it
does, its shortcuts, its limits, and any platform setup it needs (Ubuntu
packages, macOS prerequisites).

### VII.2 Spec Before Plan Before Code

Specs describe what and why, with no implementation detail. Plans make the
technical choices and are checked against this constitution. Tasks are
small, ordered and independently verifiable.

### VII.3 Commits

Commits are prefixed `markdown-editor:` and explain why, not only what,
including any behaviour that differs from what the reader would assume.
Ported behaviour names its origin (for example "ported from
pdf-translators") and lists deliberate differences.

## Governance

- This constitution overrides other practice for this project. Every plan's
  Constitution Check gate MUST cite the Articles it touches.
- Amendments are made by editing this file with a Sync Impact Report comment
  at the top. Versioning is semantic: MAJOR for removing or redefining a
  principle, MINOR for adding one, PATCH for wording.
- A deviation needs a written justification in the plan's Complexity
  Tracking table, approved by the maintainer before implementation starts.

**Version**: 1.1.0 | **Ratified**: 2026-10-25 | **Last Amended**: 2026-10-25
