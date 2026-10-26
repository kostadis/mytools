# Data Model: File Picker That Works Over SSH X11 Forwarding

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)

These are in-memory types only. Nothing new is stored on disk. The core
types (`ChooserPreference`, `DisplayEnv`, `ChooserDecision`, `CliArgs`) are
plain Rust with no egui (constitution IV.1).

## ChooserPreference

The value of `--chooser` (R6).

| Value | Meaning |
|-------|---------|
| `Auto` (default) | Decide from the environment (R3). |
| `System` | Always try the system dialog first. |
| `Window` | Always use the in-window chooser. |

## DisplayEnv

A snapshot of the variables that detection reads. It is built from
`std::env` in `main`, or by hand in tests.

| Field | Source |
|-------|--------|
| `ssh` | `true` if any of `SSH_CONNECTION`, `SSH_CLIENT`, `SSH_TTY` is non-empty |
| `display` | `DISPLAY` (optional string) |
| `wayland_display` | `WAYLAND_DISPLAY` (optional string) |
| `platform` | `Linux` or `MacOs`, from `cfg(target_os)` |

## ChooserDecision

The result of `decide(&DisplayEnv, ChooserPreference)`. The editor shows it
to the user (FR-010g).

| Field | Values |
|-------|--------|
| `kind` | `System` or `Window` |
| `reason` | `Override`, `LocalDisplay`, `SshSession`, `NetworkDisplay`, `Uncertain` |

Rules (R3), applied in order:

1. `Override` when the preference isn't `Auto`.
2. `SshSession` → `Window`.
3. Linux `WAYLAND_DISPLAY` set → `LocalDisplay` → `System`.
4. Linux `DISPLAY`:
   - an empty host part or `unix` → `LocalDisplay` → `System`;
   - any other host part → `NetworkDisplay` → `Window`.
5. Otherwise on Linux → `Uncertain` → `Window`.
6. macOS without SSH → `LocalDisplay` → `System`.

A fallback after a system-dialog failure (FR-010d) or an abandon (FR-010e)
is not a new decision. It is recorded on the request (below) as
`FellBack(Failed | Abandoned)`.

## CliArgs

| Field | Type | Notes |
|-------|------|-------|
| `chooser` | `ChooserPreference` | default `Auto` |
| `file` | `Option<PathBuf>` | at most one, opened at startup (FR-013) |

`parse(args) -> Result<CliCommand, UsageError>`, where `CliCommand` is
`Run(CliArgs)` or `Help`. A `UsageError` prints usage and exits with
status 2.

## ChooserRequest

The single active Open or Save As interaction, held by `MarkdownEditor`.
`None` when idle.

| Field | Type | Notes |
|-------|------|-------|
| `purpose` | `Open` or `SaveAs { after: AfterSave }` | `AfterSave` is `Nothing` or `Continue(PendingAction)` (R7) |
| `decision` | `ChooserDecision` | made when the request starts |
| `state` | see below | |
| `generation` | `u64` | used to drop late system-dialog replies (R4) |
| `start_dir`, `file_name` | `PathBuf`, `String` | FR-006 |
| `fell_back` | `Option<Failed or Abandoned>` | FR-010d/e, shown to the user |

### State transitions

```text
                 ┌──────────── decision.kind = Window ────────────┐
 Open / Save As ─┤                                                ▼
                 └─ System ─► AwaitingSystem ─┬─ Some(path) ─► Chosen(path)
                                              ├─ None, no rfd error ─► Cancelled
                                              ├─ None, rfd error ─► InWindow (fell_back = Failed)
                                              └─ "Use built-in" ───► InWindow (fell_back = Abandoned)
                                                                      │
                                         InWindow ─┬─ picked ─► Chosen(path)
                                                   └─ cancel ─► Cancelled

 Chosen(path):  Open  → Document::open(path); error keeps the current document (III.3)
                SaveAs → Document::save_as(path) ─┬─ Ok  → run AfterSave::Continue(action), if any
                                                  └─ Err → show error; drop the action; stay modified
 Cancelled:     drop any AfterSave action; document unchanged (FR-012)
```

Rules:

- **One request at a time.** Toolbar buttons and Ctrl+N/O/S are disabled
  while a request is active.
- **Late replies are dropped.** A system-dialog reply is ignored unless its
  generation matches the active request.
- **Open over unsaved changes.** It still goes through the existing
  confirmation first (FR-011). The request starts only after the user
  agrees, or after the save that the confirmation started has finished.

## Relationships

```text
CliArgs.chooser ──► decide(DisplayEnv, preference) ──► ChooserDecision
                                                          │
MarkdownEditor ── owns 0..1 ──► ChooserRequest ── holds ──┘
       │                              │
       └── Document (unchanged API) ◄─┘ (open / save_as on Chosen)
```
