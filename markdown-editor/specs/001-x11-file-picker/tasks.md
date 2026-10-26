---
description: "Task list for the file picker that works over SSH X11 forwarding"
---

# Tasks: File Picker That Works Over SSH X11 Forwarding

**Input**: Design documents from `specs/001-x11-file-picker/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/cli.md](./contracts/cli.md), [contracts/chooser-ui.md](./contracts/chooser-ui.md), [quickstart.md](./quickstart.md)

**Tests**: Included. Constitution V.1 requires tests to ship with each change,
and the plan's Constitution Check commits to detection, CLI and
state-machine tests plus FR-012/III.3 data-safety tests.

**Organization**: Tasks are grouped by user story so each story can be
built and checked on its own.

All paths are relative to `markdown-editor/`. Tests live in `#[cfg(test)]`
modules inside the file they test, as the existing modules do.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: The user story the task belongs to (US1–US4)

## Interim behaviour between phases

US1–US3 always use the in-window chooser, with the fixed decision
`{ kind: Window, reason: Uncertain }`. That is allowed by FR-010b and
constitution II.5 (the in-window path is always acceptable). US4 replaces
the fixed decision with real detection, the system dialog and the
`--chooser` option. Until US4 lands, the local desktop also gets the
in-window chooser.

---

## Phase 1: Setup

**Purpose**: Add the dependencies and empty modules.

- [ ] T001 Add `egui-file-dialog = { version = "0.15.0", default-features = false, features = ["default_fonts"] }` to `[dependencies]` in `Cargo.toml`; run `cargo tree -i egui` and confirm only egui 0.36.2 is present (research R2)
- [ ] T002 Create empty modules `src/cli.rs`, `src/chooser_mode.rs` and `src/file_chooser.rs`, and declare them with `mod cli; mod chooser_mode; mod file_chooser;` at the top of `src/main.rs` next to the existing `mod` lines; confirm `cargo build` passes

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: The shared types and the request state machine that every story uses.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T003 [P] Define the pure types in `src/chooser_mode.rs` (no egui import, constitution IV.1): `ChooserPreference { Auto, System, Window }` with `Default = Auto`; `ChooserKind { System, Window }`; `ChooserReason { Override, LocalDisplay, SshSession, NetworkDisplay, Uncertain }`; `ChooserDecision { kind, reason }` (data-model.md). Add `ChooserReason::describe(&self) -> &'static str` returning the caption text, e.g. `SshSession` → "SSH session detected", `Uncertain` → "display could not be identified", `Override` → "set with --chooser", `LocalDisplay` → "local display", `NetworkDisplay` → "network display detected". Do not write `decide()` yet (T040)
- [ ] T004 [P] Move `PendingAction` out of `src/main.rs` into `src/file_chooser.rs` as `pub(crate) enum PendingAction { New, Open, Quit }` deriving `Clone, Copy, Debug, PartialEq, Eq`; import it back in `src/main.rs` so existing code compiles unchanged
- [ ] T005 Define the request types in `src/file_chooser.rs`: `AfterSave { Nothing, Continue(PendingAction) }`; `Purpose { Open, SaveAs { after: AfterSave } }`; `FellBack { Failed, Abandoned }`; `RequestState { InWindow, AwaitingSystem }`; `Outcome { Chosen(PathBuf), Cancelled }`; and `ChooserRequest { purpose, decision: ChooserDecision, state, generation: u64, start_dir: PathBuf, file_name: String, fell_back: Option<FellBack>, dialog: Option<egui_file_dialog::FileDialog> }` (data-model.md ChooserRequest) (depends on T003, T004)
- [ ] T006 Add `fn start_dir_and_name(path: Option<&Path>) -> (PathBuf, String)` in `src/file_chooser.rs`: the document's parent folder and file name when it has a path, otherwise the home folder (`std::env::home_dir()`, falling back to `"."` if `None`) and `"Untitled.md"` (FR-006); unit-test both branches plus a path with no parent in the same file
- [ ] T007 Add `fn in_window_dialog(purpose: &Purpose, start_dir: &Path, file_name: &str, caption: &str) -> egui_file_dialog::FileDialog` in `src/file_chooser.rs` that builds the dialog: `.title("Open")` or `.title("Save As")`, `.initial_directory(start_dir)`, `.default_file_name(file_name)` for save, `as_modal = true`, `load_via_thread = true`, `allow_file_overwrite = true` (the crate's own overwrite modal handles FR-005), `allow_path_edit_to_save_file_without_extension = true` (spec Assumption: save writes exactly the typed name), `show_devices = false` (the crate lists disks with `sysinfo` and canonicalises each mount **on the UI thread** every time the dialog opens, file_dialog.rs `refresh()`, so a hung NFS/SSHFS mount would freeze the editor, FR-003; research R2), and the open filters **Markdown** (`md`, `markdown`, `mdown`, set as default) and **All files** (FR-007). Show `caption` as the window title suffix, e.g. `"Open — Built-in chooser — display could not be identified"` (FR-010g) (depends on T005)
- [ ] T008 Add `fn poll_in_window(dialog: &mut FileDialog, ctx: &egui::Context) -> Option<Outcome>` in `src/file_chooser.rs`: call `dialog.update(ctx)`, then map `DialogState::Picked(path)` → `Some(Chosen(path))` (via `take_picked`), `Cancelled` or `Closed` → `Some(Cancelled)`, `Open` → `None`; keep the function under ~25 cognitive complexity (IV.4) (depends on T007)
- [ ] T009 In `src/main.rs`, add `chooser: Option<ChooserRequest>` and `next_generation: u64` fields to `MarkdownEditor` (initialised in `Default`), plus `fn start_chooser(&mut self, purpose: Purpose)` that builds a `ChooserRequest` with the interim decision `ChooserDecision { kind: Window, reason: Uncertain }`, increments `next_generation`, calls `start_dir_and_name(self.document.path())`, creates the dialog with `in_window_dialog` and calls `pick_file()` or `save_file()` on it. Does nothing if `self.chooser` is already `Some` (one request at a time) (depends on T006, T007)
- [ ] T010 In `src/main.rs`, add `fn finish_chooser(&mut self, outcome: Outcome, ctx: &egui::Context)` that takes `self.chooser`, then: `Open` + `Chosen(p)` → `self.open_path(p)`; `SaveAs { after }` + `Chosen(p)` → `self.document.save_as(p)`, and on `Ok` clear `self.error` and, if `after` is `Continue(action)`, call `self.perform(action, ctx)`; on `Err` set `self.error = Some(format!("Could not save file: {error}"))` and drop `after`; any `Cancelled` → drop `after`, leave the document untouched (data-model state transitions, FR-012, III.3). Must not call `perform` for anything other than a successful save (depends on T009)
- [ ] T011 In `src/main.rs`, add `fn chooser_ui(&mut self, ctx: &egui::Context)` that, when `self.chooser` is `Some` and its state is `InWindow`, calls `poll_in_window` and passes any outcome to `finish_chooser`; call it from `MarkdownEditor::draw` after `confirmation(ctx)`. Change the `if self.pending.is_none()` guard in `draw` that gates `self.shortcuts(&ctx)` to also require `self.chooser.is_none()`, and wrap the New/Open/Save/Save As toolbar buttons in `toolbar` with `ui.add_enabled(self.chooser.is_none(), …)` (contracts/chooser-ui.md entry points; data-model "one request at a time") (depends on T008, T010)
- [ ] T012 Unit tests in the `ui_tests` module of `src/main.rs` (reuse its `frame` helper): with `chooser` set to a fake request, a frame does not run Ctrl+N/Ctrl+O; `finish_chooser(Cancelled)` on an `Open` request leaves `document.text()` and `document.path()` unchanged; `start_chooser` while a request is active leaves the original request (same `generation`) (depends on T011)

**Checkpoint**: the plumbing compiles, tests pass, and nothing yet routes Open or Save through it.

---

## Phase 3: User Story 1 — Open a file over SSH (Priority: P1) 🎯 MVP

**Goal**: Open (toolbar or Ctrl+O) shows the in-window chooser and opens the picked file, without freezing the editor.

**Independent Test**: Over `ssh -X`, start the editor with no arguments, open `~/mdtest/deep/er/plan.md` using only the chooser, and confirm the source pane shows `# Plan` (quickstart Scenario 1).

### Tests for User Story 1

- [ ] T013 [P] [US1] In `src/main.rs` `ui_tests`: `finish_chooser(Chosen(path))` on an `Open` request for a temp file containing `# Plan\n` makes `document.text()` equal `"# Plan\n"`, sets `document.path()` to it and leaves the document not dirty
- [ ] T014 [P] [US1] In `src/main.rs` `ui_tests`: `finish_chooser(Chosen(path))` on an `Open` request for a missing file or a non-UTF-8 file keeps the previous document text and sets `self.error` to a message starting with "Could not open file" (FR-011, III.3, III.4)
- [ ] T015 [P] [US1] In `src/main.rs` `ui_tests`: with a dirty document, `request(PendingAction::Open, ctx)` sets `pending` and does **not** create a chooser; choosing **Discard** in `confirmation` then creates an `Open` chooser (US1 scenario 4, FR-011)

### Implementation for User Story 1

- [ ] T016 [US1] In `src/main.rs`, change the `PendingAction::Open` arm of `perform` to `self.start_chooser(Purpose::Open)` and delete `open_dialog()`; keep `perform`'s cognitive complexity at or below its current value (plan IV.4)
- [ ] T017 [US1] Confirm in `src/main.rs` that the command-line `FILE` path in `main()` still goes through `open_path` unchanged (FR-013); add a `ui_tests` case that `open_path` on a temp file still works without any chooser
- [ ] T018 [US1] Manual check: run quickstart Scenario 1 steps 1–5 over `ssh -X` and `ssh -Y`; record the result in a "Validation log" section appended to `specs/001-x11-file-picker/quickstart.md` (caption at this stage reads "display could not be identified", which is expected until US4)

**Checkpoint**: Open works over SSH. US1 is shippable on its own.

---

## Phase 4: User Story 2 — Save a new document, or save under a new name, over SSH (Priority: P1)

**Goal**: Save on an unsaved document, Save As, and "Save first" in the unsaved-changes prompt all go through the in-window save chooser; cancelling a "Save first" cancels the Quit, New or Open it belongs to.

**Independent Test**: Over `ssh -X`, Ctrl+N, type `hello`, Ctrl+S, save as `~/mdtest/new.md`, and `cat ~/mdtest/new.md` on the host prints `hello` (quickstart Scenario 2).

### Tests for User Story 2

- [ ] T019 [P] [US2] In `src/main.rs` `ui_tests`: `finish_chooser(Chosen(tmp/"new.md"))` on `SaveAs { after: Nothing }` writes the text to disk, sets `document.path()`, and clears dirty (US2 scenario 2)
- [ ] T020 [P] [US2] In `src/main.rs` `ui_tests`: `finish_chooser(Cancelled)` on `SaveAs { after: Continue(Quit) }` leaves `allow_close == false`, the document dirty, its path unchanged, and no file written (FR-012, US2 scenario 6). Repeat for `Continue(New)` (text unchanged) and `Continue(Open)` (no new chooser created)
- [ ] T021 [P] [US2] In `src/main.rs` `ui_tests`: `finish_chooser(Chosen(path_in_unwritable_dir))` on `SaveAs { after: Continue(Quit) }` sets an error starting with "Could not save file", keeps the document dirty and does not set `allow_close` (III.3, edge case "not writable"). Use a path under a non-existent directory so the test does not depend on permissions
- [ ] T022 [P] [US2] In `src/main.rs` `ui_tests`: `finish_chooser(Chosen(existing))` on `SaveAs` over an existing file leaves `existing.bak` holding the old contents (FR-011 `.bak` guard)
- [ ] T023 [P] [US2] In `src/main.rs` `ui_tests`: `finish_chooser(Chosen(p))` on `SaveAs { after: Continue(New) }` saves to `p` and then leaves an empty, untitled document (the follow-up ran)

### Implementation for User Story 2

- [ ] T024 [US2] In `src/main.rs`, replace `save_as(&mut self) -> bool` with `fn save_as(&mut self, after: AfterSave)` that calls `self.start_chooser(Purpose::SaveAs { after })`, removing the `rfd::FileDialog` code (the start folder and name now come from `start_dir_and_name`, T006)
- [ ] T025 [US2] In `src/main.rs`, change `save(&mut self) -> bool` to `fn save(&mut self, after: AfterSave) -> SaveStatus` with `enum SaveStatus { Saved, Failed, Choosing }`: a document with no path calls `save_as(after)` and returns `Choosing`; otherwise it writes as today and returns `Saved` or `Failed`
- [ ] T026 [US2] In `src/main.rs` `confirmation`, make **Save** call `self.save(AfterSave::Continue(action))`, then clear `self.pending` in all three cases and call `self.perform(action, ctx)` only on `Saved`; `Choosing` leaves the follow-up to `finish_chooser` (R7), `Failed` drops it
- [ ] T027 [US2] In `src/main.rs`, update the Ctrl+S / Ctrl+Shift+S handlers in `shortcuts` and the Save / Save As buttons in `toolbar` to call `save(AfterSave::Nothing)` and `save_as(AfterSave::Nothing)`; confirm with `cargo clippy --all-targets -- -D warnings` that no `bool` result is left unused
- [ ] T028 [US2] Manual check: run quickstart Scenario 2 steps 1–4 over `ssh -X`, including the "Replace new.md?" no/yes path and the `.bak` check; append results to the Validation log in `specs/001-x11-file-picker/quickstart.md`

**Checkpoint**: US1 and US2 both work over SSH. No path in the editor reaches `rfd` any more.

---

## Phase 5: User Story 3 — Move around quickly in the chooser (Priority: P2)

**Goal**: Typed paths, a one-step jump home, keyboard-only use, and hidden files off by default.

**Independent Test**: Over `ssh -X`, Ctrl+O, press `~`, type `mdtest/deep/er/plan.md`, press Enter, and the file opens without a click (quickstart Scenario 3).

### Tests for User Story 3

- [ ] T029 [P] [US3] In `src/file_chooser.rs` tests: the dialog built by `in_window_dialog` has `show_devices == false` (FR-003, T007), `show_hidden_option == true` and does not show hidden entries initially (its `FileDialogStorage::show_hidden` is `false`), and `keybindings.parent` contains both Alt+↑ and Backspace (T031)
- [ ] T030 [P] [US3] In `src/file_chooser.rs` tests: the open dialog's default filter is "Markdown" and accepts `a.md`, `a.markdown`, `a.mdown`, rejects `a.txt`; "All files" accepts `a.txt` (FR-007)

### Implementation for User Story 3

- [ ] T031 [US3] In `in_window_dialog` in `src/file_chooser.rs`, append `KeyBinding::key(egui::Key::Backspace)` to `config.keybindings.parent` (contracts/chooser-ui.md keyboard row; the crate's default is only Alt+↑). Check by hand that Backspace still deletes text while the path field or file-name field has focus; if it does not, remove the Backspace binding and record that Alt+↑ is the "up one folder" key in `README.md` (T051)
- [ ] T032 [US3] In `in_window_dialog` in `src/file_chooser.rs`, explicitly set `show_hidden_option = true` and the storage `show_hidden = false` so a saved preference can never turn hidden files on by default (FR-009); keep the crate's default `home_edit_path` (`~` / Shift+\`) binding (FR-008)
- [ ] T033 [US3] Manual check: run quickstart Scenario 3 steps 1–5 over `ssh -X` (step 5 covers the spec edge cases: unreadable folder, folder/file/broken symlinks, a non-UTF-8 name, and resizing while open), including the 10,000-entry folder (SC-003) and a non-existent typed path (chooser stays open with a message); append results to the Validation log in `specs/001-x11-file-picker/quickstart.md`
- [ ] T034 [US3] Confirm in the T033 run that the relaxed FR-008 holds: `~` then a home-relative path then Enter opens the file in under 5 seconds (SC-004), and a pasted absolute path works. Do **not** add `~/` expansion; that is [kostadis/mytools#90](https://github.com/kostadis/mytools/issues/90) (decision recorded in `specs/001-x11-file-picker/research.md` R2). Append the result to the Validation log in `specs/001-x11-file-picker/quickstart.md`

**Checkpoint**: The chooser is practical for daily use over SSH; the `~/` gap is accepted and tracked in mytools#90.

---

## Phase 6: User Story 4 — Native dialog locally, in-window chooser remotely (Priority: P3)

**Goal**: Detection picks the system dialog only on a confidently local display; the system dialog runs without blocking the UI thread, with a "Use built-in chooser instead" escape and an automatic fallback on failure; `--chooser=auto|system|window` overrides detection.

**Independent Test**: On the local desktop, Ctrl+O shows the system dialog and the waiting panel. Over `ssh -X`, Ctrl+O shows the in-window chooser captioned "SSH session detected". `--chooser=window` locally and `--chooser=system` over SSH each win (quickstart Scenarios 4–5).

### Tests for User Story 4

- [ ] T035 [P] [US4] In `src/chooser_mode.rs` tests, one test per data-model rule (R3) for `decide()`: preference `System`/`Window` → `Override` regardless of env; any non-empty `SSH_CONNECTION`/`SSH_CLIENT`/`SSH_TTY` → `Window`/`SshSession` (also with `DISPLAY=:0` and with `WAYLAND_DISPLAY` set); an empty `SSH_TTY` value is ignored; Linux `WAYLAND_DISPLAY=wayland-0` → `System`/`LocalDisplay`; `DISPLAY` `:0`, `:1.0`, `unix:0` → `LocalDisplay`; `localhost:10.0`, `host:0`, `10.0.0.5:0` → `Window`/`NetworkDisplay`; `DISPLAY` with no `:` or empty → `Uncertain`; nothing set on Linux → `Window`/`Uncertain`; macOS no SSH → `System`/`LocalDisplay`; macOS with SSH → `Window`/`SshSession`
- [ ] T036 [P] [US4] In `src/cli.rs` tests, one test per row of contracts/cli.md: no args; `notes.md`; `--chooser=window notes.md`; `--chooser window notes.md`; `notes.md --chooser=system`; `-- --chooser=window` (file named literally); `--help` and `-h` → `Help`; `--chooser=bogus` → error text `unknown chooser 'bogus' (expected auto, system or window)`; `--chooser` with no value → usage error; `--frobnicate` → `unknown option '--frobnicate'`; `a.md b.md` → `expected at most one file`; a non-UTF-8 `OsString` file name (built with `std::os::unix::ffi::OsStringExt`, under `#[cfg(unix)]`) is accepted as `FILE`
- [ ] T037 [P] [US4] In `src/file_chooser.rs` tests, after `install_logger()` (idempotent, so tests can share it; assert on count **deltas** because tests run in parallel): `log::error!(target: "rfd::backend::xdg_desktop_portal", "Failed to pick file with zenity: x")` and `"Failed to save file with zenity: x"` increment the count, going through the macro so a missing `set_max_level` fails the test; these do **not**: `log::error!(target: "rfd::backend::xdg_desktop_portal::portal::libdbus", "Can't connect to a portal: libdbus-1.so not found")` (portal failures are always followed by a zenity attempt, which logs its own error if it fails), `log::warn!(target: "rfd::backend::xdg_desktop_portal", "Using zenity fallback")`, and an `error!` with target `eframe`. Put the `rfd-0.17.2` source lines these strings come from (`xdg_desktop_portal.rs` ~109 and ~275, `portal/libdbus.rs` ~77) in a comment above the test (R5)
- [ ] T038 [P] [US4] In `src/file_chooser.rs` tests, for `fn classify_system_reply(reply: Option<PathBuf>, errors_before: u64, errors_now: u64) -> SystemResult` with `SystemResult { Chosen(PathBuf), Cancelled, Failed }`: `Some(p)` → `Chosen`; `None` with equal counts → `Cancelled`; `None` with a higher count → `Failed` (contracts/chooser-ui.md system-dialog table)
- [ ] T039 [P] [US4] In `src/main.rs` `ui_tests`: a system-dialog reply whose `generation` differs from the active request's is ignored (the request is still active, nothing opened); after "Use built-in chooser instead" the request is `InWindow` with `fell_back == Some(Abandoned)` and a late reply for the old generation does nothing; after **Cancel** the request is gone and a late reply does nothing (R4)

### Implementation for User Story 4

- [ ] T040 [US4] In `src/chooser_mode.rs`, add `Platform { Linux, MacOs }` with `Platform::current()` using `cfg(target_os = "macos")` (the only `cfg` branch for this feature, II.2); `DisplayEnv { ssh: bool, display: Option<String>, wayland_display: Option<String>, platform: Platform }` with `DisplayEnv::from_env()` reading `SSH_CONNECTION`, `SSH_CLIENT`, `SSH_TTY` (non-empty counts), `DISPLAY` and `WAYLAND_DISPLAY` through `std::env::var_os` (treat non-UTF-8 values as unparseable → uncertain); and `pub fn decide(env: &DisplayEnv, pref: ChooserPreference) -> ChooserDecision` implementing data-model rules 1–6 in order. No egui imports (IV.1) (depends on T003)
- [ ] T041 [US4] In `src/cli.rs`, implement `pub enum CliCommand { Run(CliArgs), Help }`, `pub struct CliArgs { chooser: ChooserPreference, file: Option<PathBuf> }`, `pub struct UsageError(String)`, `pub fn parse(args: impl IntoIterator<Item = OsString>) -> Result<CliCommand, UsageError>` (args without the program name) and `pub const USAGE: &str` containing the exact text in contracts/cli.md. Parse by hand, no new crate (R6); option names and values must be UTF-8, file names stay `OsString` (FR-013)
- [ ] T042 [US4] In `src/file_chooser.rs`, implement `struct RfdErrorLogger { errors: AtomicU64 }` implementing `log::Log`: `enabled` for `Warn` and above; `log` writes `warn`+ records to stderr as `"{level} {target}: {args}"` and increments `errors` only when `level == Error`, `target == "rfd::backend::xdg_desktop_portal"` and the message starts with `"Failed to "` and contains `"with zenity"` (the one error every no-dialog failure ends with; counting earlier portal errors would misclass a cancelled zenity dialog as a failure, research R5); plus `pub fn install_logger() -> &'static RfdErrorLogger` (a `static` + `log::set_logger`, ignoring an already-set error) **that also calls `log::set_max_level(log::LevelFilter::Warn)`** (without it the `log` crate drops every record and the fallback never fires), and `fn rfd_error_count() -> u64`. Add `log = "0.4"` to `Cargo.toml` (R5)
- [ ] T043 [US4] In `src/file_chooser.rs`, implement `fn spawn_system_dialog(purpose: &Purpose, start_dir: &Path, file_name: &str, generation: u64, ctx: egui::Context) -> mpsc::Receiver<(u64, Option<PathBuf>)>`: build `rfd::AsyncFileDialog` with the same filters as today (open: Markdown `md`/`markdown`/`mdown` + All files; save: Markdown `md`), `set_directory(start_dir)`, `set_file_name(file_name)` for save; on a `std::thread::spawn` worker run `pollster::block_on(dialog.pick_file())` or `.save_file()`, map the `FileHandle` to `PathBuf`, send `(generation, path)` and call `ctx.request_repaint()`. Add `pollster = "0.4"` to `Cargo.toml` (R4)
- [ ] T044 [US4] Implement `classify_system_reply` (T038) in `src/file_chooser.rs` and add `errors_before: u64` and `reply: Option<mpsc::Receiver<…>>` to `ChooserRequest`; `RequestState::AwaitingSystem` is entered when `decision.kind == System` (depends on T042, T043)
- [ ] T045 [US4] In `src/file_chooser.rs`, implement `fn waiting_panel(ctx: &egui::Context) -> Option<WaitChoice>` with `WaitChoice { UseBuiltIn, Cancel }`: a modal `egui::Window` titled "Waiting for the system file dialog…" with a weak line `"System file dialog — {reason.describe()}"` (FR-010g; take the `ChooserDecision` as a parameter), the text "If it didn't appear on this screen, use the built-in chooser." and buttons **Use built-in chooser instead** and **Cancel** (contracts/chooser-ui.md)
- [ ] T046 [US4] In `src/main.rs`, wire US4 in: store `chooser_pref: ChooserPreference` on `MarkdownEditor` (default `Auto`); in `start_chooser`, replace the interim decision with `decide(&DisplayEnv::from_env(), self.chooser_pref)` (fresh per request, FR-010) and, for `System`, record `errors_before = rfd_error_count()` and call `spawn_system_dialog`; in `chooser_ui`, for `AwaitingSystem`, show `waiting_panel` and `try_recv` the reply, dropping any reply whose generation is stale. `Chosen`/`Cancelled` go to `finish_chooser`; `Failed` switches the request to `InWindow` with `fell_back = Some(Failed)` and a fresh generation; `UseBuiltIn` does the same with `Abandoned`; `Cancel` calls `finish_chooser(Cancelled)`. Split into small helpers so no function exceeds ~25 cognitive complexity (IV.4) (depends on T040, T044, T045)
- [ ] T047 [US4] In `src/file_chooser.rs`, build the in-window caption (T007) from the request: `"Built-in chooser — {reason.describe()}"`, or for `fell_back == Some(Failed)` the banner "The system file dialog could not be opened; using the built-in chooser.", or for `Abandoned` "Built-in chooser — system dialog abandoned" (FR-010d, FR-010g)
- [ ] T048 [US4] In `src/main.rs` `main()`: call `install_logger()` first; replace `std::env::args_os().nth(1)` with `cli::parse(std::env::args_os().skip(1))`; on `Help` print `USAGE` to stdout and exit 0; on `UsageError(msg)` print `error: {msg}` then `USAGE` to stderr and `std::process::exit(2)`; on `Run(args)` set `app.chooser_pref = args.chooser` and open `args.file` with `open_path` as before (FR-010c, FR-013)
- [ ] T049 [US4] Manual check: run quickstart Scenarios 4 and 5 on the local Ubuntu desktop and over `ssh -X`, including the failure-fallback step (`env -u DBUS_SESSION_BUS_ADDRESS PATH=/nonexistent ./target/release/markdown-editor --chooser=system`, or stopping `xdg-desktop-portal` if libdbus still finds the bus) and SC-008 timing; append results to the Validation log in `specs/001-x11-file-picker/quickstart.md`
- [ ] T050 [US4] Manual check for SC-007: Open shows the in-window chooser captioned "SSH session detected" with no override in each of `ssh -X`, `ssh -Y`, `tmux` started after SSH, and `screen` started after SSH (10 runs total across these); append results to the Validation log in `specs/001-x11-file-picker/quickstart.md`

**Checkpoint**: All four stories work; the editor never blocks on a helper and is never stranded by one.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T051 [P] Update `README.md` (FR-014, II.4, VI.3, VII.1): Open and Save work over `ssh -X`/`ssh -Y`; the local-versus-remote rule from R3 in plain words; `--chooser=auto|system|window` and `--help`; the chooser's keys (`~` for home, Alt+↑ and, if kept by T031, Backspace for parent, Esc to cancel, "Show hidden"); the Ubuntu packages still needed for the system dialog locally (portal, `zenity`); that the chooser's sidebar does not list disks or mounts (type the path instead), because listing them can hang on a stalled network mount; a known-limitation note that a typed or pasted leading `~/` is not expanded (press `~` instead), linking mytools#90; and that macOS is written for but unverified
- [ ] T052 [P] Check cognitive complexity of every new or changed function in `src/main.rs`, `src/file_chooser.rs`, `src/chooser_mode.rs` and `src/cli.rs` with codebase-memory-mcp (`index_repository` then `query_graph`/`search_graph` on complexity) and confirm none exceeds ~25 and `MarkdownEditor::perform` did not grow (IV.4, plan Constitution Check)
- [ ] T053 Grep `src/` for `rfd::FileDialog` (sync) and confirm it is gone, and for `unwrap()`/`expect(` on user input or environment values in the new modules (V.3)
- [ ] T054 Run the merge gate from `markdown-editor/` (`Cargo.toml`): `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test` on Ubuntu; all must pass (V.2)
- [ ] T055 Draft the PR description notes (no PR is opened by this task): platforms run (Ubuntu local; Ubuntu over `ssh -X` and `ssh -Y`, from the Validation log), macOS written for but unverified with the four items listed in plan.md "macOS-unverified items", and the known violation III.2 (atomic saves) unchanged; save it as `specs/001-x11-file-picker/pr-notes.md`

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: none.
- **Foundational (Phase 2)**: needs Phase 1. Blocks every story.
- **US1 (Phase 3)**: needs Phase 2.
- **US2 (Phase 4)**: needs Phase 2. Independent of US1 in code, but both edit `src/main.rs`, so run them one after the other.
- **US3 (Phase 5)**: needs Phase 2 (it configures the dialog from T007). Its manual checks T033 and T034 need US1.
- **US4 (Phase 6)**: needs Phase 2. T046 needs the `start_chooser`/`finish_chooser` paths that US1 and US2 route through, so in practice it follows US2.
- **Polish (Phase 7)**: after the stories you plan to ship.

### Within phases

- T003 and T004 are parallel; T005 needs both; T006 and T007 need T005; T009 needs T006 and T007; T010 needs T009; T011 needs T008 and T010; T012 needs T011.
- In each story, write the tests first and confirm they fail, then implement.
- In US4, T040, T041, T042, T043 and T045 touch different items and can be written in parallel (T040 and T041 in different files; T042, T043 and T045 are separate functions in `src/file_chooser.rs`, so pair them only if you accept merge noise). T044 needs T042 and T043; T046 needs T040, T044 and T045; T047 needs T046; T048 needs T041 and T042.

### Parallel opportunities

- Phase 2: T003 ∥ T004.
- US1 tests: T013 ∥ T014 ∥ T015.
- US2 tests: T019 ∥ T020 ∥ T021 ∥ T022 ∥ T023.
- US3 tests: T029 ∥ T030.
- US4 tests: T035 ∥ T036 ∥ T037 ∥ T038 ∥ T039; implementation T040 ∥ T041.
- Polish: T051 ∥ T052.

## Parallel Example: User Story 4

```text
Task: "T035 decide() rule tests in src/chooser_mode.rs"
Task: "T036 CLI parsing tests in src/cli.rs"
Task: "T040 DisplayEnv, Platform and decide() in src/chooser_mode.rs"   # after T035
Task: "T041 cli::parse and USAGE in src/cli.rs"                         # after T036
```

## Implementation Strategy

### MVP (User Story 1)

1. Phases 1 and 2.
2. Phase 3 (US1): Open works over SSH.
3. Stop and validate with T018.

US1 alone still cannot save a new document remotely, so US2 should follow
before this is merged: the spec ranks both P1, and Article III treats losing
a new remote document as a data-safety failure.

### Incremental delivery

1. Setup + Foundational.
2. US1 → validate over SSH.
3. US2 → validate over SSH. **Mergeable point**: Open and Save work everywhere through the in-window chooser.
4. US3 → validate.
5. US4 → validate locally and over SSH; the local desktop gets its system dialog back.
6. Polish and the merge gate.

## Notes

- `src/document.rs`, `src/outline.rs`, `src/outline_panel.rs` and `src/html_table.rs` are not touched (R8).
- Commit messages use the `markdown-editor:` prefix (VII.3). Commit only when asked.
