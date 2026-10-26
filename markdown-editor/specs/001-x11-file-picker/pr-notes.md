# PR Notes: 001 File Picker That Works Over SSH X11 Forwarding

Draft notes for the PR description (constitution V.2, II.4). No PR has been
opened yet.

## What changed

- Open and Save As now go through one chooser request at a time
  (`src/file_chooser.rs`). Its result arrives on a later frame, so the
  editor keeps drawing.
- **Built-in chooser** (`egui-file-dialog` 0.15.0), drawn inside the editor
  window. Used over SSH, on a network `DISPLAY`, and whenever the editor
  can't tell.
- **System file dialog** (`rfd::AsyncFileDialog` on a worker thread), used
  only on a confidently local display. A waiting panel offers "Use built-in
  chooser instead" and Cancel. A failed system dialog falls back to the
  built-in chooser and says so.
- **Detection** (`src/chooser_mode.rs`, pure) and **`--chooser=auto|system|window`**
  with `--help` (`src/cli.rs`, pure, parsed by hand).
- "Save first" in the unsaved-changes prompt now finishes the Quit, New or
  Open after the chooser saves, and cancelling the chooser cancels it.
- `src/document.rs` is unchanged.

## Dependencies

`egui-file-dialog` 0.15.0 (MIT), `pollster` 0.4 (MIT/Apache-2.0), `log` 0.4
(MIT/Apache-2.0). Only one egui version is in the tree (0.36.2). See
plan.md, Dependencies.

## Platforms run

- **Ubuntu, automated**: `cargo fmt --check`, `cargo clippy --all-targets
  -- -D warnings` and `cargo test` (62 tests) pass.
- **Ubuntu, local desktop, by hand**: _not yet run_ (quickstart Scenario 4).
- **Ubuntu over `ssh -X`, by hand**: tried on 2026-10-26 and reported
  working. The quickstart steps weren't recorded one by one, so T018, T028,
  T033, T034 and T050 stay open (`ssh -Y`, tmux, screen, the 10,000-entry
  folder and the edge cases).
- **macOS**: written for, unverified. Unverified items:
  - `rfd::AsyncFileDialog` driven from a worker thread with `pollster`.
  - Detection returning "local display" on macOS when no SSH variables are set.
  - The `egui-file-dialog` sidebar (`directories` user folders; disks are off).
  - Cmd+O and Cmd+S while the chooser is open.

## Known violations and limitations

- III.2 atomic writes: pre-existing, unchanged, tracked by its own spec.
- A typed or pasted leading `~/` isn't expanded in the path field (FR-008
  relaxed; #90).
- The chooser's disk sidebar is off, because the crate lists mounts on the
  UI thread.
