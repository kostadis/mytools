# Research: File Picker That Works Over SSH X11 Forwarding

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-10-25

## R1. Why the current dialog fails over `ssh -X`

**Finding** (read from `rfd-0.17.2/src/backend/xdg_desktop_portal.rs`): the
editor uses `rfd` with its default `xdg-portal` feature. `pick_file` sends a
request over D-Bus to `org.freedesktop.portal.FileChooser`, which is served
by `xdg-desktop-portal-gtk` in the user's **desktop login session**. An SSH
session usually reaches that same user bus (`/run/user/<uid>/bus`), so the
dialog opens on the remote machine's physical screen. If no desktop session
exists, `rfd` logs `warn!("Using zenity fallback")` and tries `zenity`. The
call is synchronous on the UI thread, so the editor freezes until the unseen
dialog is closed.

**Consequences for the design**

- The dialog cannot just be "made visible". The fix needs a chooser drawn by
  the editor itself (FR-001, FR-002).
- The synchronous call is a second bug (FR-003), and it exists locally too.
- `rfd` returns `None` for **both** cancel and failure. Errors are only
  logged (`error!("Failed to pick file with zenity: {err}")`, `"Can't
  connect to a portal: libdbus-1.so not found"`). FR-010d needs another way
  to tell the two apart (R5).

## R2. In-window chooser: library or hand-built

**Decision**: use `egui-file-dialog` 0.15.0 (MIT) with default features off
except `default_fonts`.

**Rationale**

- It targets `egui` 0.36.0. A trial `cargo check` in a scratch copy of the
  editor resolved to the editor's own `egui` 0.36.2, with no second egui
  version.
- It covers almost the whole spec out of the box:
  - **Folders load on a background thread** (`load_via_thread: true` on
    every non-wasm target). Slow or 10,000-entry folders don't freeze the
    window (edge cases, SC-003).
  - **Path edit field**: submitting a file path picks it, and submitting a
    folder path opens it (`submit_path_edit`). That covers FR-008 and US3
    scenarios 1–2.
  - **`~` key**: the default `home_edit_path` binding (`~` or Shift+\`)
    jumps to home and opens the path field (FR-008).
  - **Keyboard bindings** for submit, cancel, parent, back, forward and
    selection up/down (US3 scenario 3).
  - **"Show hidden" option**, off by default (FR-009).
  - **File filters** with a default filter, for Markdown versus all files
    (FR-007).
  - **Overwrite confirmation** for an existing file in save mode
    (`OverwriteFileModal`, FR-005).
  - **`initial_directory` and `default_file_name`** (FR-006).
  - **`allow_path_edit_to_save_file_without_extension`**: set to true so
    Save writes exactly the name typed (spec Assumption).
- Its new transitive dependencies are `directories`, `dunce` and `sysinfo`
  (disk listing for the sidebar). **Caveat (found in /speckit-analyze)**:
  the disk list is built synchronously in `FileDialog::refresh()` each time
  the dialog opens, with `sysinfo::Disks::new_with_refreshed_list()` and a
  canonicalise per mount. A hung NFS or SSHFS mount would block the UI
  thread (FR-003). The editor sets `show_devices = false`; home and the
  user folders in the sidebar are still shown. All are pure Rust or system-library
  wrappers that support Linux and macOS.

**Alternatives considered**

- **Hand-built chooser inside the editor**: no new crates, and full control
  over `~` expansion. But it means roughly 600–900 new lines: directory
  listing on a worker thread, keyboard navigation, overwrite modal, filters,
  odd names and symlinks. That's a large new surface, likely to break the
  IV.4 complexity limit, for behaviour the crate already has and tests.
  Rejected for now. It stays the fallback if the crate fails the quickstart
  checks.
- **`egui_file` 0.28** (MIT, also egui 0.36): not evaluated in depth. Its
  documented feature set is smaller, and `egui-file-dialog` already met
  every requirement on inspection.
- **Switch `rfd` to its `gtk3` backend**: GTK draws on `$DISPLAY`, so it
  would likely show up over forwarding. But it adds a GTK build dependency
  and keeps the dialog in a separate toolkit. It also still blocks the UI
  thread unless run asynchronously. Rejected because it doesn't give an
  in-window path, and II.5 needs one.

**Known gap (accepted 2026-10-25)**: typing a path that *starts* with `~/` into the path field is
not expanded. The crate canonicalises `PathBuf::from(text)` as typed. The
`~` key binding gives the same result (home folder, path field open, keep
typing). The quickstart checks that SC-004 is met this way. If it isn't, the
fix is a small wrapper that expands a leading `~/` before the dialog sees
the text, or an upstream patch.

**Decision (user, 2026-10-25)**: relax FR-008 to the `~` key plus typing a
home-relative path, document the gap in the README, and track the fix in
[kostadis/mytools#90](https://github.com/kostadis/mytools/issues/90).

## R3. Local versus remote detection (FR-010a/b)

**Decision**: a pure function `decide(env, platform, override) ->
ChooserDecision`, called fresh on each Open or Save As, using only
environment variables:

1. A command-line override wins (FR-010c).
2. `SSH_CONNECTION`, `SSH_CLIENT` or `SSH_TTY` set and non-empty →
   **Remote** ("started from an SSH session").
3. Linux, `WAYLAND_DISPLAY` set → **Local**. winit prefers Wayland when it
   is set, and Wayland sockets are local unless proxied by `waypipe`,
   which runs under SSH and so is caught by step 2.
4. Linux, `DISPLAY` set:
   - An empty host part (`:0`, `:1.0`) or `unix:` → **Local**.
   - Any other host part (`localhost:10.0` from `ssh -X`, `host:0`) →
     **Remote** ("display is a network connection").
5. Linux with neither variable, or a `DISPLAY` that can't be parsed →
   **Uncertain**, which uses the in-window chooser (FR-010b).
6. macOS with no SSH variables → **Local**. The editor's window is always
   drawn by the macOS window server.

**Rationale**: `ssh -X` always sets both an `SSH_*` variable and a TCP-style
`DISPLAY` (`localhost:10.0`), so either signal alone catches it. Two
independent signals make a false "local" unlikely. Every unclear case maps
to the in-window chooser. A false "remote" only costs the native dialog's
extras.

**tmux and screen**:

- **Pane opened after attaching over SSH**: tmux's default
  `update-environment` copies `SSH_CONNECTION` and `DISPLAY` into new panes,
  so this is detected as remote (SC-007).
- **Pane that kept a stale SSH environment but is now used locally**:
  detected as remote, which is the safe direction.
- **Pane that kept a stale local `DISPLAY=:0` but is attached over SSH**:
  the editor's *whole window* opens on the remote desktop, not just the
  dialog. That's a problem with the session, not the chooser, and is out of
  scope.

**Spec correction (applied 2026-10-25)**: the edge case "window later moved
to another display" can't happen on X11 or Wayland, because a window stays on
the display it was created on, so it was replaced in the spec by a note that
detection runs per Open or Save As. Detection still runs per Open or Save As as FR-010 asks. It's
cheap, and the answer is stable for the life of the process.

**Alternatives considered**: querying the X server (`XServerVendor`,
checking the socket peer), and asking D-Bus where the portal would draw.
Both are more code and need a new dependency, and they add no signal beyond
`DISPLAY` and `SSH_*` in the cases the spec cares about. Rejected.

## R4. Keeping the editor responsive while the system dialog is open (FR-003, FR-010e)

**Decision**: open the system dialog with `rfd::AsyncFileDialog` on a
background thread, driven by `pollster::block_on`. The thread sends the
result back over a `std::sync::mpsc` channel and calls
`egui::Context::request_repaint()`. While it waits, the editor draws a small
in-window "Waiting for the system file dialog…" panel, with **Use built-in
chooser instead** and **Cancel** buttons.

- **Abandoning** (FR-010e) bumps a request generation number and opens the
  in-window chooser. A late reply from the abandoned dialog has a stale
  generation number and is thrown away. The dialog may stay open on the
  other screen, and its thread exits when it closes. That's acceptable: it
  holds no editor state, and closing the editor ends the process.
- **macOS**: `AsyncFileDialog` sends the panel to the main thread itself, so
  waiting on a worker thread is the documented use. Written for macOS, not
  verified (II.1).

**Alternatives considered**: keeping the sync call on the UI thread (that's
the freeze), and a sync call on a worker thread (not allowed on macOS,
where `NSOpenPanel` must run on the main thread). Rejected.

## R5. Detecting a failed system dialog (FR-010d)

**Decision**: install a small `log::Log` implementation at startup and set
`log::set_max_level(Warn)` (the `log` crate drops every record until a max
level is set). It writes `warn` and higher to stderr, and counts only the
`error` record `rfd` logs when its zenity fallback fails (`target ==
"rfd::backend::xdg_desktop_portal"`, message `"Failed to … with zenity:
…"`). In `rfd` 0.17.2 every failure that leaves no dialog on screen ends
with that record: a portal that can't be reached logs its own error and
then always tries zenity. Counting the earlier portal errors as well would
class "portal failed, zenity opened, user cancelled" as a failure and
open the built-in chooser after a cancel. Each system-dialog request remembers the count
when it starts. If the reply is `None` **and** the count has gone up, the
request failed. The editor shows "The system file dialog could not be
opened; using the built-in chooser" and opens the in-window chooser for the
same action.

**Rationale**: it's the only signal `rfd` 0.17 exposes, and it covers the
documented failures: no libdbus, no portal, and the zenity fallback
failing. Log targets aren't a stable API, so a unit test pins the
behaviour and a quickstart step runs it with `zenity` hidden and no portal.
The **Use built-in chooser instead** button (R4) covers anything this
misses.

**Alternatives considered**: a timing heuristic ("None in under 200 ms
means failure"), which is fragile and confuses a fast Esc with a failure,
and probing D-Bus for the portal before calling `rfd`, which needs a D-Bus
crate and still misses zenity failures. Rejected.

## R6. Command-line option (FR-010c, FR-013)

**Decision**: parse arguments by hand in a pure `cli` module. No `clap`.

```
markdown-editor [--chooser=auto|system|window] [--help] [--] [FILE]
```

- `auto` is the default and applies R3.
- `system` forces the system dialog. The R4/R5 escape hatches still apply.
- `window` forces the in-window chooser.
- `--chooser system` (with a space) is also accepted.
- Unknown options or values print usage to stderr and exit with status 2.
  `--help` prints usage and exits 0.
- A single positional `FILE` opens as today (FR-013). `--` ends option
  parsing so files named like options can be opened.

**Rationale**: two options don't justify a parser dependency (IV.3), and a
pure function is easy to unit-test.

## R7. Save flow as a state machine (FR-011, FR-012)

**Finding**: today `save_as()` returns `bool` synchronously, and the unsaved
changes flow (`PendingAction::{New, Open, Quit}`) relies on that. With a
non-blocking chooser, the result arrives on a later frame.

**Decision**: replace the synchronous call with a chooser request that
records what to do once a path is chosen: `AfterSave::Nothing` or
`AfterSave::Continue(PendingAction)`. A chosen path runs `save_as(path)`, and
if that succeeds it carries on with the pending action. A cancel or failure
drops the pending action, and the document stays modified (FR-012). Open
requests follow the same pattern. Only one chooser request can be active at
a time, and Ctrl+O and Ctrl+S do nothing while one is open.

## R8. What stays the same

`Document::open`, `save`, `save_as` and `write_with_backup` are unchanged
(including the `.bak` copy and non-atomic writes, which belong to the
atomic-saves spec). Rendering over forwarded X11 already works (spec
Assumption). `README.md` keeps the Ubuntu portal and `zenity` packages,
because the local system dialog still uses them.
