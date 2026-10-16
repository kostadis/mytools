mod document;

use document::Document;
use eframe::egui;
use egui_commonmark::{CommonMarkCache, CommonMarkViewer};
use std::path::PathBuf;

/// Font size of a level-1 heading in the preview; lower levels step down toward body size.
const PREVIEW_H1_SIZE: f32 = 32.0;

#[derive(Clone, Copy)]
enum PendingAction {
    New,
    Open,
    Quit,
}

struct MarkdownEditor {
    document: Document,
    preview_cache: CommonMarkCache,
    pending: Option<PendingAction>,
    error: Option<String>,
    show_preview: bool,
    allow_close: bool,
}

impl Default for MarkdownEditor {
    fn default() -> Self {
        Self {
            document: Document::default(),
            preview_cache: CommonMarkCache::default(),
            pending: None,
            error: None,
            show_preview: true,
            allow_close: false,
        }
    }
}

impl MarkdownEditor {
    fn request(&mut self, action: PendingAction, ctx: &egui::Context) {
        if self.document.is_dirty() {
            self.pending = Some(action);
        } else {
            self.perform(action, ctx);
        }
    }

    fn perform(&mut self, action: PendingAction, ctx: &egui::Context) {
        match action {
            PendingAction::New => self.document.new_file(),
            PendingAction::Open => {
                if let Some(path) = Self::open_dialog() {
                    self.open_path(path);
                }
            }
            PendingAction::Quit => {
                self.allow_close = true;
                ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            }
        }
    }

    fn open_dialog() -> Option<PathBuf> {
        rfd::FileDialog::new()
            .add_filter("Markdown", &["md", "markdown", "mdown"])
            .add_filter("All files", &["*"])
            .pick_file()
    }

    fn open_path(&mut self, path: PathBuf) {
        match self.document.open(path) {
            Ok(()) => self.error = None,
            Err(error) => self.error = Some(format!("Could not open file: {error}")),
        }
    }

    fn save(&mut self) -> bool {
        if self.document.path().is_none() {
            return self.save_as();
        }
        match self.document.save() {
            Ok(()) => {
                self.error = None;
                true
            }
            Err(error) => {
                self.error = Some(format!("Could not save file: {error}"));
                false
            }
        }
    }

    fn save_as(&mut self) -> bool {
        let mut dialog = rfd::FileDialog::new().add_filter("Markdown", &["md"]);
        if let Some(path) = self.document.path() {
            if let Some(parent) = path.parent() {
                dialog = dialog.set_directory(parent);
            }
            if let Some(name) = path.file_name() {
                dialog = dialog.set_file_name(name.to_string_lossy());
            }
        } else {
            dialog = dialog.set_file_name("Untitled.md");
        }
        let Some(path) = dialog.save_file() else {
            return false;
        };
        match self.document.save_as(path) {
            Ok(()) => {
                self.error = None;
                true
            }
            Err(error) => {
                self.error = Some(format!("Could not save file: {error}"));
                false
            }
        }
    }

    fn shortcuts(&mut self, ctx: &egui::Context) {
        let shortcut = |key| ctx.input(|i| i.modifiers.command && i.key_pressed(key));
        if shortcut(egui::Key::N) {
            self.request(PendingAction::New, ctx);
        } else if shortcut(egui::Key::O) {
            self.request(PendingAction::Open, ctx);
        } else if shortcut(egui::Key::S) {
            if ctx.input(|i| i.modifiers.shift) {
                self.save_as();
            } else {
                self.save();
            }
        }
    }

    fn toolbar(&mut self, ui: &mut egui::Ui, ctx: &egui::Context) {
        ui.horizontal(|ui| {
            ui.add_enabled_ui(self.pending.is_none(), |ui| {
                if ui.button("New").on_hover_text("Ctrl/Cmd+N").clicked() {
                    self.request(PendingAction::New, ctx);
                }
                if ui.button("Open…").on_hover_text("Ctrl/Cmd+O").clicked() {
                    self.request(PendingAction::Open, ctx);
                }
                if ui.button("Save").on_hover_text("Ctrl/Cmd+S").clicked() {
                    self.save();
                }
                if ui
                    .button("Save As…")
                    .on_hover_text("Ctrl/Cmd+Shift+S")
                    .clicked()
                {
                    self.save_as();
                }
            });
            ui.separator();
            ui.checkbox(&mut self.show_preview, "Preview");
            ui.separator();
            ui.label(
                self.document
                    .path()
                    .map(|p| p.display().to_string())
                    .unwrap_or_else(|| "Untitled.md".to_owned()),
            );
            if self.document.is_dirty() {
                ui.label("● Unsaved");
            }
        });
    }

    fn confirmation(&mut self, ctx: &egui::Context) {
        let Some(action) = self.pending else { return };
        egui::Window::new("Unsaved changes")
            .collapsible(false)
            .resizable(false)
            .anchor(egui::Align2::CENTER_CENTER, [0.0, 0.0])
            .show(ctx, |ui| {
                ui.label("Save your changes before continuing?");
                ui.horizontal(|ui| {
                    if ui.button("Save").clicked() && self.save() {
                        self.pending = None;
                        self.perform(action, ctx);
                    }
                    if ui.button("Discard").clicked() {
                        self.pending = None;
                        self.perform(action, ctx);
                    }
                    if ui.button("Cancel").clicked() {
                        self.pending = None;
                    }
                });
            });
    }
}

impl eframe::App for MarkdownEditor {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let ctx = ui.ctx().clone();
        if ctx.input(|i| i.viewport().close_requested())
            && !self.allow_close
            && self.document.is_dirty()
        {
            ctx.send_viewport_cmd(egui::ViewportCommand::CancelClose);
            self.request(PendingAction::Quit, &ctx);
        }
        if self.pending.is_none() {
            self.shortcuts(&ctx);
        }

        ctx.send_viewport_cmd(egui::ViewportCommand::Title(self.document.title()));
        self.toolbar(ui, &ctx);

        ui.separator();
        let content_height = (ui.available_height() - 32.0).max(100.0);
        ui.allocate_ui_with_layout(
            egui::vec2(ui.available_width(), content_height),
            egui::Layout::top_down(egui::Align::Min),
            |ui| {
                if self.show_preview {
                    ui.columns(2, |columns| {
                        columns[0].heading("Markdown");
                        egui::ScrollArea::vertical().id_salt("source").show(
                            &mut columns[0],
                            |ui| {
                                ui.add_enabled(
                                    self.pending.is_none(),
                                    egui::TextEdit::multiline(self.document.text_mut())
                                        .code_editor()
                                        .desired_width(f32::INFINITY)
                                        .desired_rows(40),
                                );
                            },
                        );
                        columns[1].heading("Preview");
                        egui::ScrollArea::vertical().id_salt("preview").show(
                            &mut columns[1],
                            |ui| {
                                // egui_commonmark sizes headings between the Body and
                                // Heading text styles; widen that span so each level
                                // is visibly distinct.
                                ui.style_mut().text_styles.insert(
                                    egui::TextStyle::Heading,
                                    egui::FontId::proportional(PREVIEW_H1_SIZE),
                                );
                                if self.document.text().is_empty() {
                                    ui.weak("Your rendered Markdown will appear here.");
                                } else {
                                    CommonMarkViewer::new().show(
                                        ui,
                                        &mut self.preview_cache,
                                        self.document.text(),
                                    );
                                }
                            },
                        );
                    });
                } else {
                    egui::ScrollArea::vertical()
                        .id_salt("source_only")
                        .show(ui, |ui| {
                            ui.add_enabled(
                                self.pending.is_none(),
                                egui::TextEdit::multiline(self.document.text_mut())
                                    .code_editor()
                                    .desired_width(f32::INFINITY)
                                    .desired_rows(40),
                            );
                        });
                }
            },
        );

        ui.separator();
        let words = self.document.text().split_whitespace().count();
        let lines = self.document.text().lines().count().max(1);
        ui.horizontal(|ui| {
            ui.label(format!("{words} words  ·  {lines} lines"));
            if let Some(error) = &self.error {
                ui.separator();
                ui.colored_label(egui::Color32::RED, error);
                if ui.button("Dismiss").clicked() {
                    self.error = None;
                }
            }
        });
        self.confirmation(&ctx);
    }
}

/// VMware's virtual GPU renders a blank window with hardware OpenGL, so fall
/// back to Mesa's software renderer there unless the user already chose.
#[cfg(target_os = "linux")]
fn use_software_gl_on_vmware() {
    const VMWARE_VENDOR_ID: &str = "0x15ad";
    if std::env::var_os("LIBGL_ALWAYS_SOFTWARE").is_some() {
        return;
    }
    let on_vmware = std::fs::read_dir("/sys/class/drm")
        .into_iter()
        .flatten()
        .flatten()
        .filter_map(|entry| std::fs::read_to_string(entry.path().join("device/vendor")).ok())
        .any(|vendor| vendor.trim() == VMWARE_VENDOR_ID);
    if on_vmware {
        // SAFETY: called at the start of main, before any other threads exist.
        unsafe { std::env::set_var("LIBGL_ALWAYS_SOFTWARE", "1") };
    }
}

fn main() -> eframe::Result {
    #[cfg(target_os = "linux")]
    use_software_gl_on_vmware();
    let mut app = MarkdownEditor::default();
    if let Some(path) = std::env::args_os().nth(1) {
        app.open_path(PathBuf::from(path));
    }
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default().with_inner_size([1200.0, 800.0]),
        ..Default::default()
    };
    eframe::run_native(
        "markdown-editor",
        options,
        Box::new(|_cc| Ok(Box::new(app))),
    )
}
