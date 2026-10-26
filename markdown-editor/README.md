# Markdown Editor

A small Rust desktop Markdown editor with a source pane and live rendered preview. It supports new, open, save, save as, and confirmation before closing or replacing an unsaved document.

## Run on Ubuntu

Install Rust with [rustup](https://rustup.rs/) and the Ubuntu libraries needed by eframe and native file dialogs:

```bash
sudo apt update
sudo apt install build-essential pkg-config libxkbcommon-dev libwayland-dev libx11-dev libxcursor-dev libxrandr-dev libxi-dev libgl1-mesa-dev xdg-desktop-portal-gtk zenity
cd markdown-editor
cargo run --release
```

To open a file at startup, pass its path after `--`, for example `cargo run --release -- notes.md`.

On a VMware virtual GPU, hardware OpenGL draws a blank window, so the app sets `LIBGL_ALWAYS_SOFTWARE=1` automatically when it detects one. Set `LIBGL_ALWAYS_SOFTWARE` yourself to override that choice.

The first build downloads Rust crates from crates.io. Use `cargo test` to run the document tests.

## macOS

Install Rust with rustup and Xcode Command Line Tools (`xcode-select --install`), then run `cargo run --release` in this directory. The app uses the same Rust source on both platforms.

Command Line Tools 26.6 ships a linker that cannot read the MacOSX 27 SDK (`unknown architecture arm64e.x1-macos`). `.cargo/config.toml` points `SDKROOT` at the MacOSX 26.5 SDK so `cargo run` links. Set `SDKROOT` yourself if you want a different SDK.

## Keyboard shortcuts

| Action | Linux | macOS |
| --- | --- | --- |
| New | Ctrl+N | Cmd+N |
| Open | Ctrl+O | Cmd+O |
| Save | Ctrl+S | Cmd+S |
| Save As | Ctrl+Shift+S | Cmd+Shift+S |

## Open and Save over SSH

Open and Save As work when the editor runs on a Linux box and its window is shown on another machine with `ssh -X` or `ssh -Y`. They use one of two choosers:

- **The system file dialog**, with its bookmarks and recent places. It is used only when the editor is confident its display is local: no `SSH_CONNECTION`, `SSH_CLIENT` or `SSH_TTY` in the environment, and either `WAYLAND_DISPLAY` is set or `DISPLAY` names a local socket such as `:0` or `unix:0`. On macOS, any session without those SSH variables counts as local.
- **The built-in chooser**, drawn inside the editor's own window, in every other case: over SSH, when `DISPLAY` is a network address such as `localhost:10.0`, or when the editor can't tell.

The chooser's title says which one is in use and why, for example *Built-in chooser — SSH session detected*. To force a choice for the whole run:

```bash
cargo run --release -- --chooser=window    # always the built-in chooser
cargo run --release -- --chooser=system    # always try the system dialog first
cargo run --release -- --help
```

While the system dialog is open, the editor keeps drawing and shows a *Waiting for the system file dialog…* panel. If the dialog appeared somewhere you can't see it, click **Use built-in chooser instead**. If the system dialog can't be opened at all, the editor switches to the built-in chooser and says so. The system dialog still needs `xdg-desktop-portal-gtk` or `zenity` from the package list above. The built-in chooser needs nothing extra.

In the built-in chooser:

| Action | Key |
| --- | --- |
| Go to your home folder and start typing a path | `~` |
| Up one folder | Backspace or Alt+↑ (when no text field has focus) |
| Move the selection | ↑ / ↓ |
| Open a folder, or confirm | Enter |
| Cancel | Esc |

It lists Markdown files (`.md`, `.markdown`, `.mdown`) by default, with an *All Files* filter, and hides hidden files until you turn on *Show hidden* in its menu. Saving over an existing file asks first.

Known limitations:

- Typing or pasting a path that starts with `~/` doesn't work, because `~` isn't expanded in the path field. Press `~` first, then type the rest of the path ([#90](https://github.com/kostadis/mytools/issues/90)).
- The sidebar doesn't list disks or mounts, because listing them can hang on a stalled network mount. Type the path instead.
- Warnings and errors from the editor's libraries are now printed to stderr.

Tested so far: the automated tests on Ubuntu. Checks by hand on the local desktop and over `ssh -X`/`ssh -Y` are still to be done. macOS is written for but not yet tested.

The editor reads and writes UTF-8 text files. Opening a different file preserves the current document if the new file cannot be read.

## Outline panel

The left panel lists the document's headings as a collapsible tree. Each row can promote or demote its heading, move the whole section up or down among its siblings, or delete the section; double-click a heading to rename it. Ctrl/Cmd-click and Shift-click select several rows for bulk promote, demote or delete; the ⏴ ⏵ buttons on a selected row act on the whole selection. Promote and demote always carry a section's subsections along, and are all-or-nothing: if any affected heading would go past H1 or H6, nothing moves. Headings inside fenced code blocks are ignored.

When the text editor does not have focus: `u`/`d` move, `[`/`]` promote/demote, Delete deletes, Esc clears the selection, Ctrl/Cmd+A selects all visible rows, and Ctrl/Cmd+Z / Ctrl/Cmd+Shift+Z undo and redo outline changes.

Saving over an existing file first copies it to `<name>.bak`.

## Synced panes

Clicking in any pane brings the other two to the same place: an outline row scrolls the source and preview to that heading, and a click in the source or preview selects the enclosing section in the outline and scrolls the remaining pane to match. Clicks on a heading line up exactly; clicks inside a section map proportionally within it. The preview is rendered one section at a time to make this possible, so footnotes defined in a different section do not resolve (reference-style links do).
