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

Install Rust with rustup and Xcode Command Line Tools (`xcode-select --install`), then run `cargo run --release` in this directory. The app uses the same Rust source on both platforms; macOS runtime testing remains to be done.

## Keyboard shortcuts

| Action | Linux | macOS |
| --- | --- | --- |
| New | Ctrl+N | Cmd+N |
| Open | Ctrl+O | Cmd+O |
| Save | Ctrl+S | Cmd+S |
| Save As | Ctrl+Shift+S | Cmd+Shift+S |

The editor reads and writes UTF-8 text files. Opening a different file preserves the current document if the new file cannot be read.

## Outline panel

The left panel lists the document's headings as a collapsible tree. Each row can promote or demote its heading, move the whole section up or down among its siblings, or delete the section; double-click a heading to rename it. Ctrl/Cmd-click and Shift-click select several rows for bulk promote, demote or delete. Headings inside fenced code blocks are ignored.

When the text editor does not have focus: `u`/`d` move, `[`/`]` promote/demote, Delete deletes, Esc clears the selection, Ctrl/Cmd+A selects all visible rows, and Ctrl/Cmd+Z / Ctrl/Cmd+Shift+Z undo and redo outline changes.

Saving over an existing file first copies it to `<name>.bak`.
