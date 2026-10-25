# Quickstart: Validating the File Picker Fix

**Feature**: [spec.md](./spec.md) | **Contracts**: [cli.md](./contracts/cli.md), [chooser-ui.md](./contracts/chooser-ui.md)

## Prerequisites

- An Ubuntu machine (the **host**) with the editor checked out, and a second
  machine (the **viewer**) with an X server: another Linux box, or a Mac
  with XQuartz.
- `ssh -X` (and `ssh -Y`) from the viewer to the host working: `xclock`
  shows up on the viewer.
- The Ubuntu packages from `README.md` installed on the host.
- Test files on the host:
  ```bash
  mkdir -p ~/mdtest/deep/er ~/mdtest/big ~/mdtest/.hidden
  printf '# Plan\n\nhello\n' > ~/mdtest/deep/er/plan.md
  printf 'x\n' > ~/mdtest/.hidden/secret.md
  for i in $(seq 1 10000); do : > ~/mdtest/big/f$i.md; done
  ```

## Automated checks (host)

```bash
cd markdown-editor
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
```

Expected: all pass. `cargo test` includes:

- **Detection** for each row of the [ChooserDecision](./data-model.md#chooserdecision)
  rules: `:0`, `unix:0`, `localhost:10.0`, `host:0`, Wayland, SSH variables,
  nothing set, and the macOS rows.
- **CLI parsing** for every row in [cli.md](./contracts/cli.md).
- **The request state machine**: a cancelled save drops the follow-up, a
  failed save keeps the document modified, a stale reply is dropped, and a
  logged `rfd` error is classed as a failure.

## Scenario 1: Open over SSH (US1, SC-001, SC-002, SC-005)

On the viewer: `ssh -X host`, then `cd markdown-editor && cargo run --release`.

1. Press Ctrl+O. **Expect**: the in-window chooser appears within a second,
   with the caption *"Built-in chooser — SSH session detected"*.
2. Go to `~/mdtest/deep/er`, select `plan.md` and confirm. **Expect**: the
   source pane shows `# Plan`.
3. Press Ctrl+O again, then Esc. **Expect**: the document is unchanged.
4. Type into the document, then press Ctrl+O. **Expect**: the
   unsaved-changes confirmation comes first.
5. While the chooser is open, check that the editor still redraws behind it
   (for example, resize the window).

Repeat steps 1–2 with `ssh -Y`, and inside `tmux` started after you SSH in
(SC-007).

## Scenario 2: Save over SSH (US2, SC-006)

1. Ctrl+N, type `hello`, then Ctrl+S. **Expect**: a save chooser with
   `Untitled.md` filled in.
2. Save as `~/mdtest/new.md`. **Expect**: the title shows `new.md` and is
   not marked modified. On the host, `cat ~/mdtest/new.md` prints `hello`.
3. Edit, then Save As `new.md` again. **Expect**: a "Replace new.md?"
   prompt. Say no and check that the file is unchanged. Say yes and check
   that it is replaced, with `new.md.bak` holding the old text.
4. Type unsaved text, close the window, choose "Save first", then cancel the
   chooser. **Expect**: the editor stays open, the text is intact and still
   marked modified.

## Scenario 3: Keyboard and paths (US3, SC-003, SC-004)

1. Ctrl+O, press `~`, type `mdtest/deep/er/plan.md` and press Enter.
   **Expect**: it opens in under 5 seconds with no mouse use. Typing
   `~/mdtest/...` directly into the path field is a known gap (FR-008,
   mytools#90) and is not expected to work.
2. Ctrl+O, go to `~/mdtest`. **Expect**: `.hidden` isn't listed until you
   turn on "Show hidden".
3. Go to `~/mdtest/big`. **Expect**: the 10,000 entries list within a second
   and scroll smoothly.
4. Type a path that doesn't exist. **Expect**: a message, and the chooser
   stays open.

## Scenario 4: Local desktop and overrides (US4, SC-008)

On the host's own desktop session:

1. `cargo run --release`, then Ctrl+O. **Expect**: the system dialog
   appears. The editor shows the "Waiting for the system file dialog…"
   panel and keeps redrawing.
2. Click **Use built-in chooser instead**. **Expect**: the in-window chooser
   opens at once. Close the system dialog afterwards and check that nothing
   happens in the editor.
3. `cargo run --release -- --chooser=window`. **Expect**: the in-window
   chooser opens locally.
4. Over SSH: `cargo run --release -- --chooser=system`. **Expect**: the
   waiting panel appears in the editor, and **Use built-in chooser
   instead** gets you to a working chooser within 10 seconds (SC-008).
5. Failure fallback (FR-010d), locally: build first, then run the binary
   directly so `cargo` isn't affected by the empty `PATH`:
   `env -u DBUS_SESSION_BUS_ADDRESS PATH=/nonexistent ./target/release/markdown-editor --chooser=system`.
   If libdbus still finds the session bus (for example through
   `/run/user/$UID/bus`), stop `xdg-desktop-portal` for the test instead.
   **Expect**: the banner "The system file dialog could not be opened;
   using the built-in chooser." and the in-window chooser.

## Scenario 5: Command line (FR-013, contracts/cli.md)

```bash
cargo run --release -- --help             # usage, exit 0
cargo run --release -- --chooser=bogus    # error and usage, exit 2
cargo run --release -- ~/mdtest/deep/er/plan.md   # opens as before
```

## Record in the PR (constitution V.2, II.4)

- **Platforms run**: Ubuntu locally, Ubuntu over `ssh -X` and `ssh -Y`.
- **macOS**: written for, unverified. List the macOS-unverified items from
  plan.md.
