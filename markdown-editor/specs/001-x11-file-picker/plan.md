# Implementation Plan: File Picker That Works Over SSH X11 Forwarding

**Branch**: `markdown-editor/001-x11-file-picker` | **Date**: 2026-10-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-x11-file-picker/spec.md`

## Summary

Open and Save As currently block the UI thread on `rfd`'s xdg-portal dialog.
Over `ssh -X`, the portal draws that dialog on the remote machine's own
desktop, so the editor looks frozen and nothing can be opened or saved. The
fix has four parts:

1. An **in-window chooser** (`egui-file-dialog` 0.15), drawn inside the
   editor's own window.
2. **Local/remote detection** from `SSH_*`, `DISPLAY` and `WAYLAND_DISPLAY`.
   It picks the system dialog only on a confidently local display, and the
   in-window chooser otherwise.
3. A **non-blocking system dialog** (`rfd::AsyncFileDialog` on a worker
   thread). It has a "Use built-in chooser instead" escape, and falls back
   automatically when `rfd` logs a failure.
4. A **`--chooser=auto|system|window`** command-line override.

The Open and Save flows become a single-request state machine, so Quit,
New and Open after "Save first" still behave correctly when the chooser
answers on a later frame. Details are in [research.md](./research.md).

## Technical Context

**Language/Version**: Rust 2024 edition, `rust-version = "1.95"` (toolchain on the host: 1.98.1)

**Primary Dependencies**:
- Existing: `eframe` 0.36.2 (glow, x11, wayland), `egui_commonmark` 0.25, `rfd` 0.17.2.
- New: `egui-file-dialog` 0.15.0 (no default features except `default_fonts`), `pollster` 0.4 (already in the lock file through `rfd`), `log` 0.4 (already in the lock file).

**Storage**: Local files through the existing `Document` API. No new persisted state.

**Testing**: `cargo test`: unit tests in each module (`#[cfg(test)]`), plus headless egui tests like the existing `ui_tests`. The manual checks are in [quickstart.md](./quickstart.md), run locally and over `ssh -X`/`ssh -Y`.

**Target Platform**: Ubuntu LTS on X11 and Wayland, locally and over SSH X11 forwarding, is the primary target. macOS is written for but unverified.

**Project Type**: Single-binary desktop application.

**Performance Goals**:
- The chooser is visible within 1 s of Open or Save As (SC-002).
- A 10,000-entry folder lists within 1 s and scrolls smoothly (SC-003).
- The editor never stops redrawing (SC-005).

**Constraints**:
- No UI may depend only on a helper process (II.5).
- No new blocking calls on the UI thread.
- No regression in the `.bak` copy or the unsaved-changes guards.

**Scale/Scope**: Two flows (Open and Save As), one command-line option, and about 5 files touched. Estimated at roughly 500–700 lines including tests.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution version **1.1.0**.

| Article | Requirement | Status | How |
|---------|-------------|--------|-----|
| I.1 Native Rust | One binary, no web view or server | ✅ | The new crates are pure Rust egui and std code |
| I.2 Plain text | No sidecar or hidden state | ✅ | `egui-file-dialog`'s `serde` feature is off, so it saves nothing |
| II.1 Targets | Ubuntu verified; macOS written for | ✅ | The quickstart runs on Ubuntu, locally and over SSH. The macOS-unverified items are listed below |
| II.2 Platform code isolated | `cfg` in small named places | ✅ | Platform branches live only in `chooser_mode.rs` (`Platform` from `cfg(target_os)`) |
| II.3 Degrade, don't fail | Fallbacks, user override wins | ✅ | Failure → in-window chooser (R5). `--chooser` beats detection |
| II.4 Evidence-based claims | The README states what was tested | ✅ | The README update says what was run over SSH and marks macOS unverified |
| II.5 Remote display | In-window path always available; helper only on a confident local display; CLI override; fall back on failure; responsive with an escape | ✅ | See the spec's Constitution Alignment table. R3, R4, R5 and R6 implement each condition |
| III.1 Text is sacred | No change to the text | ✅ | Only *where* files are opened or saved changes, not *what* is written |
| III.2 Backups, atomic writes | Keep `.bak`; writes atomic | ⚠️ Pre-existing | `.bak` is kept. Atomic writes are the known 1.0.0 violation, handled by its own spec. This plan doesn't make it worse |
| III.3 Failure leaves state intact | A cancelled or failed save keeps the document modified | ✅ | The R7 state machine. FR-012 is unit-tested |
| III.4 UTF-8 | Refuse files that aren't UTF-8 | ✅ | `Document::open` is unchanged (`read_to_string`) |
| IV.1 Pure core | No egui in the core | ✅ | `cli.rs` and `chooser_mode.rs` have no egui. Only `file_chooser.rs` touches the UI |
| IV.2 Source is the truth | — | ✅ | Not affected |
| IV.3 Deliberate dependencies | Justify every crate, licence, Linux/macOS, works over X11 forwarding | ✅ | See [Dependencies](#dependencies) |
| IV.4 Complexity under ~25 | New functions stay small | ✅ (watch) | The state machine is split into `start`, `poll` and `finish` functions. `MarkdownEditor::perform` must not grow past its current 10 |
| V.1 Tests | Unit tests next to the code; data-safety tests | ✅ | Detection, CLI and state-machine tests. FR-012 and III.3 tests |
| V.2 Merge gate | fmt, clippy -D warnings, test; record platforms and SSH | ✅ | The quickstart's last section |
| V.3 No panics | No `unwrap` on user input | ✅ | Paths and env values are handled as `Option`/`OsString` |
| VI.1 Native conventions | Ctrl/Cmd, focus rules | ✅ | Existing shortcuts are kept. The chooser's own bindings apply only while it is open |
| VI.2 Large documents | Per-frame work scales with what's visible | ✅ | Folder listing is threaded and virtualised by the crate. No per-frame whole-document work is added |
| VI.3 Limitations documented | README | ✅ | The R2 `~/` gap is accepted (FR-008 relaxed) and documented in the README; fix tracked in mytools#90 |
| VII.1 README | Behaviour, shortcuts, limits | ✅ | FR-014 |
| VII.3 Commits | `markdown-editor:` prefix | ✅ | — |

**Gate result: PASS.** The III.2 row is a violation that predates this
feature and is tracked by its own spec. This feature adds no new violation.

**Post-design re-check (after Phase 1): PASS.** The data model and contracts
add no new crates, platform branches or persisted state beyond those listed
above.

### Dependencies

| Crate | Why | Licence | Linux/macOS | Over X11 forwarding |
|-------|-----|---------|-------------|---------------------|
| `egui-file-dialog` 0.15.0 | The in-window chooser. A hand-built one would be about 600–900 new lines, with a high complexity risk (R2) | MIT | Yes (`directories`, `dunce`, `sysinfo`) | Yes: it draws with egui inside the editor window |
| `pollster` 0.4 | Runs `rfd::AsyncFileDialog` on a worker thread (R4) | MIT/Apache-2.0 | Yes, no dependencies | n/a (no UI) |
| `log` 0.4 | Spots `rfd` failures, since `rfd` returns `None` for errors too (R5) | MIT/Apache-2.0 | Yes | n/a |

### macOS-unverified items (II.4)

- Running `rfd::AsyncFileDialog` from a worker thread with `pollster` (R4).
- Detection returning `LocalDisplay` on macOS when no SSH variables are set (R3).
- The `egui-file-dialog` sidebar (`sysinfo` disks, `directories` user folders).
- Cmd+O and Cmd+S while the chooser is open.

## Project Structure

### Documentation (this feature)

```text
specs/001-x11-file-picker/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── cli.md           # --chooser, --help, FILE
│   └── chooser-ui.md    # In-window chooser + system-dialog wait panel
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks; not created here)
```

### Source Code (markdown-editor/)

```text
Cargo.toml               # + egui-file-dialog, pollster, log
README.md                # SSH usage, --chooser, local vs remote rule (FR-014)
src/
├── main.rs              # Parse CliArgs; install the logger; hold the active ChooserRequest;
│                        #   route Open/Save/Save As/"Save first" through it; disable
│                        #   file actions while it is active
├── cli.rs               # NEW, pure: parse() -> CliCommand | UsageError; usage text
├── chooser_mode.rs      # NEW, pure: DisplayEnv, ChooserPreference, ChooserDecision, decide()
├── file_chooser.rs      # NEW, UI: ChooserRequest state machine; drives egui-file-dialog;
│                        #   spawns the rfd worker; wait panel; rfd error-count logger
├── document.rs          # unchanged
├── outline.rs           # unchanged
├── outline_panel.rs     # unchanged
└── html_table.rs        # unchanged
```

**Structure Decision**: this stays a single Cargo binary with flat modules
under `src/`, as it is today. The two new core modules have no egui (IV.1).
The UI glue goes in its own `file_chooser.rs` rather than growing `main.rs`
(currently 725 lines). Tests stay next to the code in each module, as the
existing modules do.

## Complexity Tracking

No new constitution violations, so nothing to justify. The III.2 row in the
Constitution Check is tracked by the constitution's own known-violations
list and its separate spec.
