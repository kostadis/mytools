//! The Open and Save As choosers. The built-in chooser (egui-file-dialog) draws
//! inside the editor window, so it works over `ssh -X`. The system dialog
//! (rfd) runs on a worker thread so the editor keeps drawing, and can always
//! be abandoned for the built-in chooser. One request is active at a time,
//! and its result arrives on a later frame.

use crate::chooser_mode::{ChooserDecision, ChooserKind};
use eframe::egui;
use egui_file_dialog::{DialogState, FileDialog, Filter, KeyBinding, OpeningMode};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc::{self, Receiver, TryRecvError};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PendingAction {
    New,
    Open,
    Quit,
}

/// What to do once a Save As has written the file.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AfterSave {
    Nothing,
    Continue(PendingAction),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Purpose {
    Open,
    SaveAs { after: AfterSave },
}

/// Why the built-in chooser replaced the system dialog for a request.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FellBack {
    Failed,
    Abandoned,
}

#[derive(Debug, PartialEq, Eq)]
pub enum Outcome {
    Chosen(PathBuf),
    Cancelled,
}

/// A system-dialog reply: the request generation it belongs to, and the path.
type Reply = (u64, Option<PathBuf>);

enum State {
    InWindow(Box<FileDialog>),
    AwaitingSystem {
        reply: Receiver<Reply>,
        /// The rfd failure count when the dialog was opened.
        errors_before: u64,
    },
}

/// What the waiting panel's buttons asked for.
enum WaitChoice {
    UseBuiltIn,
    Cancel,
}

/// How a system-dialog reply is read: rfd returns nothing for both a cancel
/// and a failure, and only its log tells them apart (research R5).
#[derive(Debug, PartialEq, Eq)]
enum SystemResult {
    Chosen(PathBuf),
    Cancelled,
    Failed,
}

/// One Open or Save As interaction.
pub struct ChooserRequest {
    pub purpose: Purpose,
    pub decision: ChooserDecision,
    pub generation: u64,
    pub fell_back: Option<FellBack>,
    start_dir: PathBuf,
    file_name: String,
    state: State,
}

impl ChooserRequest {
    pub fn start(
        purpose: Purpose,
        decision: ChooserDecision,
        generation: u64,
        current: Option<&Path>,
        ctx: &egui::Context,
    ) -> Self {
        let (start_dir, file_name) = start_dir_and_name(current);
        let mut request = Self {
            purpose,
            decision,
            generation,
            fell_back: None,
            start_dir,
            file_name,
            state: State::InWindow(Box::new(FileDialog::new())),
        };
        match decision.kind {
            ChooserKind::Window => request.open_in_window(),
            ChooserKind::System => {
                request.state = State::AwaitingSystem {
                    errors_before: rfd_error_count(),
                    reply: spawn_system_dialog(
                        request.purpose,
                        &request.start_dir,
                        &request.file_name,
                        generation,
                        ctx.clone(),
                    ),
                };
            }
        }
        request
    }

    /// Switch to the built-in chooser. The system dialog's channel is dropped
    /// with the old state, so a late reply has nowhere to go.
    pub fn fall_back(&mut self, why: FellBack) {
        self.fell_back = Some(why);
        self.open_in_window();
    }

    fn open_in_window(&mut self) {
        let caption = self.caption();
        let mut dialog =
            in_window_dialog(&self.purpose, &self.start_dir, &self.file_name, &caption);
        match self.purpose {
            Purpose::Open => dialog.pick_file(),
            Purpose::SaveAs { .. } => dialog.save_file(),
        }
        self.state = State::InWindow(Box::new(dialog));
    }

    /// The mode and reason shown on the built-in chooser (FR-010g).
    fn caption(&self) -> String {
        match self.fell_back {
            Some(FellBack::Failed) => {
                "The system file dialog could not be opened; using the built-in chooser.".to_owned()
            }
            Some(FellBack::Abandoned) => "Built-in chooser — system dialog abandoned".to_owned(),
            None => format!("Built-in chooser — {}", self.decision.reason.describe()),
        }
    }

    /// Draw this frame's part of the request, and return its outcome once there is one.
    pub fn poll(&mut self, ctx: &egui::Context) -> Option<Outcome> {
        match &mut self.state {
            State::InWindow(dialog) => poll_in_window(dialog, ctx),
            State::AwaitingSystem { .. } => self.poll_system(ctx),
        }
    }

    fn poll_system(&mut self, ctx: &egui::Context) -> Option<Outcome> {
        match waiting_panel(ctx, self.decision) {
            Some(WaitChoice::UseBuiltIn) => {
                self.fall_back(FellBack::Abandoned);
                return None;
            }
            Some(WaitChoice::Cancel) => return Some(Outcome::Cancelled),
            None => {}
        }
        let State::AwaitingSystem {
            reply,
            errors_before,
        } = &self.state
        else {
            return None;
        };
        let errors_before = *errors_before;
        let path = match reply.try_recv() {
            Ok((generation, path)) if generation == self.generation => path,
            Ok(_) | Err(TryRecvError::Empty) => return None,
            // The worker ended without replying, so no dialog is coming.
            Err(TryRecvError::Disconnected) => {
                self.fall_back(FellBack::Failed);
                return None;
            }
        };
        match classify_system_reply(path, errors_before, rfd_error_count()) {
            SystemResult::Chosen(path) => Some(Outcome::Chosen(path)),
            SystemResult::Cancelled => Some(Outcome::Cancelled),
            SystemResult::Failed => {
                self.fall_back(FellBack::Failed);
                None
            }
        }
    }

    #[cfg(test)]
    fn is_awaiting_system(&self) -> bool {
        matches!(self.state, State::AwaitingSystem { .. })
    }
}

fn classify_system_reply(
    reply: Option<PathBuf>,
    errors_before: u64,
    errors_now: u64,
) -> SystemResult {
    match reply {
        Some(path) => SystemResult::Chosen(path),
        None if errors_now > errors_before => SystemResult::Failed,
        None => SystemResult::Cancelled,
    }
}

/// Open the system dialog on a worker thread. The reply comes back over the
/// channel, tagged with the request's generation, and wakes the UI.
fn spawn_system_dialog(
    purpose: Purpose,
    start_dir: &Path,
    file_name: &str,
    generation: u64,
    ctx: egui::Context,
) -> Receiver<Reply> {
    let (sender, receiver) = mpsc::channel();
    let dialog = rfd::AsyncFileDialog::new().set_directory(start_dir);
    let dialog = match purpose {
        Purpose::Open => dialog
            .add_filter("Markdown", &["md", "markdown", "mdown"])
            .add_filter("All files", &["*"]),
        Purpose::SaveAs { .. } => dialog
            .add_filter("Markdown", &["md"])
            .set_file_name(file_name),
    };
    std::thread::spawn(move || {
        let picked = pollster::block_on(async move {
            match purpose {
                Purpose::Open => dialog.pick_file().await,
                Purpose::SaveAs { .. } => dialog.save_file().await,
            }
        });
        let _ = sender.send((generation, picked.map(|file| file.path().to_path_buf())));
        ctx.request_repaint();
    });
    receiver
}

/// The panel shown while the system dialog is open, so a dialog that opened
/// on another screen never strands the user (FR-010e).
fn waiting_panel(ctx: &egui::Context, decision: ChooserDecision) -> Option<WaitChoice> {
    let mut choice = None;
    egui::Modal::new(egui::Id::new("system-file-dialog-wait")).show(ctx, |ui| {
        ui.heading("Waiting for the system file dialog…");
        ui.weak(format!(
            "System file dialog — {}",
            decision.reason.describe()
        ));
        ui.label("If it didn't appear on this screen, use the built-in chooser.");
        ui.horizontal(|ui| {
            if ui.button("Use built-in chooser instead").clicked() {
                choice = Some(WaitChoice::UseBuiltIn);
            }
            if ui.button("Cancel").clicked() {
                choice = Some(WaitChoice::Cancel);
            }
        });
    });
    choice
}

/// Writes warnings and errors to stderr, and counts the one error rfd logs
/// when no dialog could be shown at all: its zenity fallback failing. A
/// portal that can't be reached logs its own error first, but rfd then
/// always tries zenity, so counting that too would turn "zenity opened and
/// the user cancelled" into a failure (research R5).
pub struct RfdErrorLogger {
    errors: AtomicU64,
}

static LOGGER: RfdErrorLogger = RfdErrorLogger {
    errors: AtomicU64::new(0),
};

impl log::Log for RfdErrorLogger {
    fn enabled(&self, metadata: &log::Metadata) -> bool {
        metadata.level() <= log::Level::Warn
    }

    fn log(&self, record: &log::Record) {
        if !self.enabled(record.metadata()) {
            return;
        }
        let message = record.args().to_string();
        eprintln!("{} {}: {message}", record.level(), record.target());
        if is_dialog_failure(record.level(), record.target(), &message) {
            self.errors.fetch_add(1, Ordering::Relaxed);
        }
    }

    fn flush(&self) {}
}

fn is_dialog_failure(level: log::Level, target: &str, message: &str) -> bool {
    level == log::Level::Error
        && target == "rfd::backend::xdg_desktop_portal"
        && message.starts_with("Failed to ")
        && message.contains("with zenity")
}

/// Install the logger. Safe to call more than once.
pub fn install_logger() {
    let _ = log::set_logger(&LOGGER);
    // Without a max level the log crate drops every record.
    log::set_max_level(log::LevelFilter::Warn);
}

fn rfd_error_count() -> u64 {
    LOGGER.errors.load(Ordering::Relaxed)
}

/// The folder and file name a chooser starts with: the document's own, or
/// home and `Untitled.md` for a document that was never saved (FR-006).
fn start_dir_and_name(path: Option<&Path>) -> (PathBuf, String) {
    let home = || std::env::home_dir().unwrap_or_else(|| PathBuf::from("."));
    let Some(path) = path else {
        return (home(), "Untitled.md".to_owned());
    };
    let dir = match path.parent() {
        Some(parent) if !parent.as_os_str().is_empty() => parent.to_path_buf(),
        _ => home(),
    };
    let name = path.file_name().map_or_else(
        || "Untitled.md".to_owned(),
        |n| n.to_string_lossy().into_owned(),
    );
    (dir, name)
}

fn in_window_dialog(
    purpose: &Purpose,
    start_dir: &Path,
    file_name: &str,
    caption: &str,
) -> FileDialog {
    let verb = match purpose {
        Purpose::Open => "Open",
        Purpose::SaveAs { .. } => "Save As",
    };
    let mut dialog = FileDialog::new()
        .title(&format!("{verb} — {caption}"))
        .initial_directory(start_dir.to_path_buf())
        .opening_mode(OpeningMode::AlwaysInitialDir)
        .as_modal(true)
        .load_via_thread(true)
        .allow_file_overwrite(true)
        .allow_path_edit_to_save_file_without_extension(true)
        // The crate lists disks and canonicalises each mount on the UI
        // thread whenever it opens, so a hung network mount would freeze
        // the editor (FR-003).
        .show_devices(false)
        .show_removable_devices(false)
        .show_hidden_option(true);
    if let Purpose::Open = purpose {
        dialog = dialog
            .add_file_filter("Markdown", Filter::new(|p: &Path| is_markdown(p)))
            .default_file_filter("Markdown");
    } else {
        dialog = dialog.default_file_name(file_name);
    }
    dialog.storage_mut().show_hidden = false;
    dialog
        .config_mut()
        .keybindings
        .parent
        .push(KeyBinding::key(egui::Key::Backspace));
    dialog
}

/// The Open chooser's default filter (FR-007). The crate adds "All Files".
fn is_markdown(path: &Path) -> bool {
    path.extension().and_then(|e| e.to_str()).is_some_and(|e| {
        ["md", "markdown", "mdown"]
            .iter()
            .any(|m| e.eq_ignore_ascii_case(m))
    })
}

fn poll_in_window(dialog: &mut FileDialog, ctx: &egui::Context) -> Option<Outcome> {
    dialog.update(ctx);
    match dialog.state() {
        DialogState::Open => None,
        DialogState::Picked(_) => dialog.take_picked().map(Outcome::Chosen),
        _ => Some(Outcome::Cancelled),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::chooser_mode::ChooserReason;
    use std::sync::mpsc::Sender;

    /// A request waiting on a system dialog whose reply the test sends.
    fn awaiting(generation: u64) -> (ChooserRequest, Sender<Reply>) {
        let (sender, reply) = mpsc::channel();
        let request = ChooserRequest {
            purpose: Purpose::Open,
            decision: ChooserDecision {
                kind: ChooserKind::System,
                reason: ChooserReason::LocalDisplay,
            },
            generation,
            fell_back: None,
            start_dir: PathBuf::from("/"),
            file_name: String::new(),
            state: State::AwaitingSystem {
                reply,
                errors_before: rfd_error_count(),
            },
        };
        (request, sender)
    }

    fn poll(ctx: &egui::Context, request: &mut ChooserRequest) -> Option<Outcome> {
        let mut outcome = None;
        let mut output = ctx.run_ui(egui::RawInput::default(), |ui| {
            outcome = request.poll(ui.ctx());
        });
        output.textures_delta.clear();
        outcome
    }

    #[test]
    fn a_reply_for_another_request_is_ignored() {
        let ctx = egui::Context::default();
        let (mut request, sender) = awaiting(7);
        sender.send((6, Some(PathBuf::from("/old.md")))).unwrap();
        assert_eq!(poll(&ctx, &mut request), None);
        assert!(request.is_awaiting_system());
    }

    #[test]
    fn the_matching_reply_finishes_the_request() {
        let ctx = egui::Context::default();
        let (mut request, sender) = awaiting(7);
        assert_eq!(poll(&ctx, &mut request), None);
        sender.send((7, Some(PathBuf::from("/a.md")))).unwrap();
        assert_eq!(
            poll(&ctx, &mut request),
            Some(Outcome::Chosen(PathBuf::from("/a.md")))
        );
    }

    #[test]
    fn abandoning_the_system_dialog_drops_its_late_reply() {
        let ctx = egui::Context::default();
        let (mut request, sender) = awaiting(7);
        request.fall_back(FellBack::Abandoned);
        assert!(!request.is_awaiting_system());
        assert_eq!(request.fell_back, Some(FellBack::Abandoned));
        assert!(sender.send((7, Some(PathBuf::from("/late.md")))).is_err());
        assert_eq!(poll(&ctx, &mut request), None);
    }

    #[test]
    fn a_worker_that_ends_without_replying_falls_back() {
        let ctx = egui::Context::default();
        let (mut request, sender) = awaiting(7);
        drop(sender);
        assert_eq!(poll(&ctx, &mut request), None);
        assert_eq!(request.fell_back, Some(FellBack::Failed));
        assert!(!request.is_awaiting_system());
    }

    #[test]
    fn a_reply_is_classed_by_the_failure_count() {
        let path = PathBuf::from("/a.md");
        assert_eq!(
            classify_system_reply(Some(path.clone()), 3, 4),
            SystemResult::Chosen(path)
        );
        assert_eq!(classify_system_reply(None, 3, 3), SystemResult::Cancelled);
        assert_eq!(classify_system_reply(None, 3, 4), SystemResult::Failed);
    }

    #[test]
    fn the_logger_counts_only_zenity_failures() {
        // The messages rfd 0.17.2 logs, from src/backend/xdg_desktop_portal.rs
        // (~109 "Failed to pick file with zenity", ~275 "Failed to save file
        // with zenity", ~105 "Using zenity fallback") and
        // src/backend/xdg_desktop_portal/portal/libdbus.rs (~77).
        install_logger();
        let portal = "rfd::backend::xdg_desktop_portal";
        let count = rfd_error_count;
        let before = count();
        log::error!(target: portal, "Failed to pick file with zenity: no zenity");
        assert_eq!(count(), before + 1);
        log::error!(target: portal, "Failed to save file with zenity: no zenity");
        assert_eq!(count(), before + 2);
        log::error!(
            target: "rfd::backend::xdg_desktop_portal::portal::libdbus",
            "Can't connect to a portal: libdbus-1.so not found"
        );
        log::warn!(target: portal, "Using zenity fallback");
        log::error!(target: "eframe", "Failed to pick file with zenity: not rfd");
        assert_eq!(count(), before + 2);
    }

    #[test]
    fn the_built_in_chooser_says_why_it_is_shown() {
        let (mut request, _sender) = awaiting(1);
        request.decision = ChooserDecision {
            kind: ChooserKind::Window,
            reason: ChooserReason::SshSession,
        };
        assert_eq!(request.caption(), "Built-in chooser — SSH session detected");
        request.fell_back = Some(FellBack::Failed);
        assert!(
            request
                .caption()
                .starts_with("The system file dialog could not be opened")
        );
        request.fell_back = Some(FellBack::Abandoned);
        assert_eq!(
            request.caption(),
            "Built-in chooser — system dialog abandoned"
        );
    }

    #[test]
    fn an_unsaved_document_starts_at_home_with_untitled() {
        let (dir, name) = start_dir_and_name(None);
        assert_eq!(
            dir,
            std::env::home_dir().unwrap_or_else(|| PathBuf::from("."))
        );
        assert_eq!(name, "Untitled.md");
    }

    #[test]
    fn a_saved_document_starts_in_its_folder_with_its_name() {
        let (dir, name) = start_dir_and_name(Some(Path::new("/tmp/notes/plan.md")));
        assert_eq!(dir, PathBuf::from("/tmp/notes"));
        assert_eq!(name, "plan.md");
    }

    fn open_dialog() -> FileDialog {
        in_window_dialog(&Purpose::Open, Path::new("/"), "", "test")
    }

    #[test]
    fn the_chooser_hides_disks_and_hidden_files() {
        let mut dialog = open_dialog();
        let config = dialog.config_mut();
        assert!(!config.show_devices && !config.show_removable_devices);
        assert!(config.show_hidden_option);
        let backspace = config
            .keybindings
            .parent
            .iter()
            .any(|k| matches!(k, KeyBinding::Key(egui::Key::Backspace)));
        assert!(backspace);
        assert!(!dialog.storage_mut().show_hidden);
    }

    #[test]
    fn open_shows_markdown_by_default_and_offers_all_files() {
        let mut dialog = open_dialog();
        let config = dialog.config_mut();
        assert_eq!(config.default_file_filter.as_deref(), Some("Markdown"));
        assert!(config.show_all_files_filter);
        assert!(config.file_filters.iter().any(|f| f.name == "Markdown"));
        for name in ["a.md", "a.markdown", "a.mdown", "A.MD"] {
            assert!(is_markdown(Path::new(name)), "{name}");
        }
        for name in ["a.txt", "md", "a.md.bak"] {
            assert!(!is_markdown(Path::new(name)), "{name}");
        }
    }

    #[test]
    fn a_bare_file_name_starts_at_home() {
        let (dir, name) = start_dir_and_name(Some(Path::new("plan.md")));
        assert_eq!(
            dir,
            std::env::home_dir().unwrap_or_else(|| PathBuf::from("."))
        );
        assert_eq!(name, "plan.md");
    }
}
