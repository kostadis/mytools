mod chooser_mode;
mod cli;
mod document;
mod file_chooser;
mod html_table;
mod outline;
mod outline_panel;
mod panes;
mod preview_blocks;

use chooser_mode::{ChooserPreference, DisplayEnv};
use document::Document;
use eframe::egui;
use egui_commonmark::{CommonMarkCache, CommonMarkViewer};
use file_chooser::{AfterSave, ChooserRequest, Outcome, PendingAction, Purpose};
use outline_panel::OutlinePanel;
use std::path::PathBuf;

/// Preview font sizes for `#` through `######`, proportioned on a reference
/// rendering whose cap heights ran 43, 35, 32, 28 and 26 px for H1–H5 (H6
/// continues the trend). egui_commonmark spaces heading sizes evenly between
/// body and H1 size instead, so the preview draws headings itself.
const HEADING_SIZES: [f32; 6] = [32.0, 26.0, 24.0, 21.0, 19.5, 18.0];
/// Space above a heading, by level, separating it from the section before.
const HEADING_GAPS: [f32; 6] = [20.0, 18.0, 16.0, 14.0, 12.0, 12.0];
/// Bold system fonts for preview headings, tried in order; egui's bundled
/// fonts have no bold weight.
const HEADING_FONT_PATHS: &[&str] = &[
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
];

/// How a Save ended: written, failed, or waiting on a chooser that will
/// finish it on a later frame.
#[derive(Clone, Copy, Debug, PartialEq)]
enum SaveStatus {
    Saved,
    Failed,
    Choosing,
}

#[derive(Clone, Copy, PartialEq)]
enum Pane {
    Outline,
    Source,
    Preview,
}

struct MarkdownEditor {
    document: Document,
    preview_cache: CommonMarkCache,
    outline: OutlinePanel,
    show_outline: bool,
    /// Font family for preview headings: a loaded bold font, or Proportional.
    heading_family: egui::FontFamily,
    /// Byte offset the source pane should scroll to on its next draw.
    source_target: Option<(usize, egui::Align)>,
    /// Block and fraction of its height the preview should scroll to.
    preview_target: Option<(usize, f32)>,
    pending: Option<PendingAction>,
    /// The Open or Save As in progress, if any. Only one runs at a time.
    chooser: Option<ChooserRequest>,
    next_generation: u64,
    /// The `--chooser` option, applied to every Open and Save As.
    chooser_pref: ChooserPreference,
    error: Option<String>,
    show_preview: bool,
    allow_close: bool,
}

impl Default for MarkdownEditor {
    fn default() -> Self {
        Self {
            document: Document::default(),
            preview_cache: CommonMarkCache::default(),
            outline: OutlinePanel::default(),
            show_outline: true,
            heading_family: egui::FontFamily::Proportional,
            source_target: None,
            preview_target: None,
            pending: None,
            chooser: None,
            next_generation: 0,
            chooser_pref: ChooserPreference::Auto,
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
            PendingAction::New => {
                self.document.new_file();
                self.outline.reset();
            }
            PendingAction::Open => self.start_chooser(Purpose::Open, ctx),
            PendingAction::Quit => {
                self.allow_close = true;
                ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            }
        }
    }

    /// True while a confirmation or a chooser is open, so file actions and
    /// editing wait for it.
    fn busy(&self) -> bool {
        self.pending.is_some() || self.chooser.is_some()
    }

    fn start_chooser(&mut self, purpose: Purpose, ctx: &egui::Context) {
        if self.chooser.is_some() {
            return;
        }
        // Keys typed into the chooser must not reach a text field behind it.
        if let Some(id) = ctx.memory(|m| m.focused()) {
            ctx.memory_mut(|m| m.surrender_focus(id));
        }
        self.next_generation += 1;
        // Decided fresh for each request (FR-010).
        let decision = chooser_mode::decide(&DisplayEnv::from_env(), self.chooser_pref);
        self.chooser = Some(ChooserRequest::start(
            purpose,
            decision,
            self.next_generation,
            self.document.path(),
            ctx,
        ));
    }

    fn chooser_ui(&mut self, ctx: &egui::Context) {
        let Some(request) = &mut self.chooser else {
            return;
        };
        if let Some(outcome) = request.poll(ctx) {
            self.finish_chooser(outcome, ctx);
        }
    }

    fn finish_chooser(&mut self, outcome: Outcome, ctx: &egui::Context) {
        let Some(request) = self.chooser.take() else {
            return;
        };
        let Outcome::Chosen(path) = outcome else {
            return;
        };
        match request.purpose {
            Purpose::Open => self.open_path(path),
            Purpose::SaveAs { after } => match self.document.save_as(path) {
                Ok(()) => {
                    self.error = None;
                    if let AfterSave::Continue(action) = after {
                        self.perform(action, ctx);
                    }
                }
                Err(error) => self.error = Some(format!("Could not save file: {error}")),
            },
        }
    }

    fn open_path(&mut self, path: PathBuf) {
        match self.document.open(path) {
            Ok(()) => {
                self.error = None;
                self.outline.reset();
            }
            Err(error) => self.error = Some(format!("Could not open file: {error}")),
        }
    }

    fn save(&mut self, after: AfterSave, ctx: &egui::Context) -> SaveStatus {
        if self.document.path().is_none() {
            self.save_as(after, ctx);
            return SaveStatus::Choosing;
        }
        match self.document.save() {
            Ok(()) => {
                self.error = None;
                SaveStatus::Saved
            }
            Err(error) => {
                self.error = Some(format!("Could not save file: {error}"));
                SaveStatus::Failed
            }
        }
    }

    fn save_as(&mut self, after: AfterSave, ctx: &egui::Context) {
        self.start_chooser(Purpose::SaveAs { after }, ctx);
    }

    /// Bring the panes other than `from` to `fraction` of the way through block
    /// `block`, where 0 means its heading line.
    fn navigate(&mut self, from: Pane, block: usize, fraction: f32, ctx: &egui::Context) {
        let text = self.document.text();
        let blocks = self.outline.blocks();
        if block >= blocks.len() {
            return;
        }
        let span = outline::block_span(blocks, block, text.len());
        if from != Pane::Source {
            let mut pos = span.start;
            if fraction > 0.0 {
                let guess = span.start + (span.len() as f32 * fraction) as usize;
                let guess = text.floor_char_boundary(guess.min(span.end));
                pos = text[..guess]
                    .rfind('\n')
                    .map_or(0, |nl| nl + 1)
                    .max(span.start);
            }
            let align = if pos == span.start {
                egui::Align::TOP
            } else {
                egui::Align::Center
            };
            self.source_target = Some((pos, align));
        }
        if from != Pane::Preview {
            self.preview_target = Some((block, fraction));
        }
        if from != Pane::Outline {
            self.outline.reveal(block);
        }
        ctx.request_repaint();
    }

    fn source_editor(&mut self, ui: &mut egui::Ui) {
        let output = ui
            .add_enabled_ui(!self.busy(), |ui| {
                egui::TextEdit::multiline(self.document.text_mut())
                    .code_editor()
                    .desired_width(f32::INFINITY)
                    .desired_rows(40)
                    .show(ui)
            })
            .inner;
        let text = self.document.text();

        if let Some((pos, align)) = self.source_target.take() {
            let pos = text.floor_char_boundary(pos.min(text.len()));
            let cursor = egui::text::CCursor::new(text[..pos].chars().count());
            let rect = output.galley.pos_from_cursor(cursor);
            ui.scroll_to_rect(rect.translate(output.galley_pos.to_vec2()), Some(align));
        }

        if output.response.clicked()
            && let Some(range) = output.cursor_range
        {
            let pos = text
                .char_indices()
                .nth(range.primary.index.into())
                .map_or(text.len(), |(byte, _)| byte);
            self.outline.sync(text);
            let blocks = self.outline.blocks();
            if let Some(block) = outline::block_at(blocks, pos) {
                let span = outline::block_span(blocks, block, text.len());
                let heading_end = text[span.clone()]
                    .find('\n')
                    .map_or(span.end, |nl| span.start + nl);
                let fraction = if blocks[block].level > 0 && pos <= heading_end {
                    0.0
                } else {
                    (pos - span.start) as f32 / span.len().max(1) as f32
                };
                let ctx = ui.ctx().clone();
                self.navigate(Pane::Source, block, fraction, &ctx);
            }
        }
    }

    /// Render the preview one outline block at a time, so each block's place on
    /// screen is known for scrolling to it and for mapping clicks back to it.
    fn preview(&mut self, ui: &mut egui::Ui) {
        // Setext headings (`===` underlines) are not outline blocks and are
        // still drawn by egui_commonmark; give them the same H1 size.
        ui.style_mut().text_styles.insert(
            egui::TextStyle::Heading,
            egui::FontId::proportional(HEADING_SIZES[0]),
        );
        let text = self.document.text();
        if text.is_empty() {
            ui.weak("Your rendered Markdown will appear here.");
            return;
        }
        self.outline.sync(text);
        let blocks = self.outline.blocks();
        let links = outline::link_definitions(text);
        let target = self.preview_target.take();
        let click = ui.input(|i| {
            i.pointer
                .primary_clicked()
                .then(|| i.pointer.interact_pos())
                .flatten()
        });
        // A vertical scroll area clips only vertically, so its clip rect spans
        // the whole window; take the horizontal extent from the column itself,
        // or clicks in the outline and source panes register here too.
        let visible =
            egui::Rect::from_x_y_ranges(ui.max_rect().x_range(), ui.clip_rect().y_range());
        let click = click.filter(|&pos| {
            self.pending.is_none()
                && visible.contains(pos)
                && ui.ctx().layer_id_at(pos) == Some(ui.layer_id())
        });
        let mut clicked = None;

        for (i, block) in blocks.iter().enumerate() {
            let section = &text[outline::block_span(blocks, i, text.len())];
            let section = ui.push_id(i, |ui| {
                let mut body = section;
                let mut heading_bottom = None;
                if block.level > 0 {
                    if i > 0 {
                        ui.add_space(HEADING_GAPS[block.level as usize - 1]);
                    }
                    heading_bottom = Some(preview_heading(
                        ui,
                        &mut self.preview_cache,
                        &self.heading_family,
                        block.level,
                        &block.text,
                    ));
                    body = section.split_once('\n').map_or("", |(_, rest)| rest);
                }
                if !body.trim().is_empty() {
                    let mut source = html_table::tables_to_markdown(body).into_owned();
                    if !links.is_empty() {
                        source.push_str("\n\n");
                        source.push_str(&links);
                    }
                    CommonMarkViewer::new().show(ui, &mut self.preview_cache, &source);
                }
                heading_bottom
            });
            let rect = section.response.rect;

            if let Some((block, fraction)) = target
                && block == i
            {
                let y = rect.top() + rect.height() * fraction;
                let line = egui::Rect::from_x_y_ranges(rect.x_range(), y..=y + 1.0);
                let align = if fraction > 0.0 {
                    egui::Align::Center
                } else {
                    egui::Align::TOP
                };
                ui.scroll_to_rect(line, Some(align));
            }
            if let Some(pos) = click
                && rect.y_range().contains(pos.y)
            {
                let offset = pos.y - rect.top();
                let on_heading = section.inner.is_some_and(|bottom| pos.y <= bottom);
                let fraction = if on_heading {
                    0.0
                } else {
                    offset / rect.height().max(1.0)
                };
                clicked = Some((i, fraction));
            }
        }

        if let Some((block, fraction)) = clicked {
            let ctx = ui.ctx().clone();
            self.navigate(Pane::Preview, block, fraction, &ctx);
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
                self.save_as(AfterSave::Nothing, ctx);
            } else {
                self.save(AfterSave::Nothing, ctx);
            }
        }
    }

    fn toolbar(&mut self, ui: &mut egui::Ui, ctx: &egui::Context) {
        ui.horizontal(|ui| {
            ui.add_enabled_ui(!self.busy(), |ui| {
                if ui.button("New").on_hover_text("Ctrl/Cmd+N").clicked() {
                    self.request(PendingAction::New, ctx);
                }
                if ui.button("Open…").on_hover_text("Ctrl/Cmd+O").clicked() {
                    self.request(PendingAction::Open, ctx);
                }
                if ui.button("Save").on_hover_text("Ctrl/Cmd+S").clicked() {
                    self.save(AfterSave::Nothing, ctx);
                }
                if ui
                    .button("Save As…")
                    .on_hover_text("Ctrl/Cmd+Shift+S")
                    .clicked()
                {
                    self.save_as(AfterSave::Nothing, ctx);
                }
            });
            ui.separator();
            ui.checkbox(&mut self.show_outline, "Outline");
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
                    if ui.button("Save").clicked() {
                        self.pending = None;
                        // A chooser runs the action itself once it has saved.
                        if self.save(AfterSave::Continue(action), ctx) == SaveStatus::Saved {
                            self.perform(action, ctx);
                        }
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

impl MarkdownEditor {
    fn draw(&mut self, ui: &mut egui::Ui) {
        let ctx = ui.ctx().clone();
        if ctx.input(|i| i.viewport().close_requested())
            && !self.allow_close
            && self.document.is_dirty()
        {
            ctx.send_viewport_cmd(egui::ViewportCommand::CancelClose);
            // While a chooser is open, finish or cancel it before quitting.
            if self.chooser.is_none() {
                self.request(PendingAction::Quit, &ctx);
            }
        }
        self.outline.sync(self.document.text());
        if !self.busy() {
            self.shortcuts(&ctx);
            if self.show_outline {
                self.outline.shortcuts(&ctx, self.document.text_mut());
            }
        }

        ctx.send_viewport_cmd(egui::ViewportCommand::Title(self.document.title()));
        self.toolbar(ui, &ctx);

        ui.separator();
        let content_height = (ui.available_height() - 32.0).max(100.0);
        ui.allocate_ui_with_layout(
            egui::vec2(ui.available_width(), content_height),
            egui::Layout::top_down(egui::Align::Min),
            |ui| {
                if self.show_outline {
                    egui::Panel::left("outline")
                        .resizable(true)
                        .default_size(280.0)
                        .show(ui, |ui| {
                            ui.add_enabled_ui(!self.busy(), |ui| {
                                self.outline.ui(ui, self.document.text_mut());
                            });
                        });
                }
                if let Some(block) = self.outline.take_focus() {
                    self.navigate(Pane::Outline, block, 0.0, &ctx);
                }
                if self.show_preview {
                    ui.columns(2, |columns| {
                        columns[0].heading("Markdown");
                        egui::ScrollArea::vertical()
                            .id_salt("source")
                            .show(&mut columns[0], |ui| self.source_editor(ui));
                        columns[1].heading("Preview");
                        egui::ScrollArea::vertical()
                            .id_salt("preview")
                            .show(&mut columns[1], |ui| self.preview(ui));
                    });
                } else {
                    self.preview_target = None;
                    egui::ScrollArea::vertical()
                        .id_salt("source_only")
                        .show(ui, |ui| self.source_editor(ui));
                }
            },
        );

        ui.separator();
        let words = self.document.text().split_whitespace().count();
        let lines = self.document.text().lines().count().max(1);
        ui.horizontal(|ui| {
            let headings = self.outline.heading_count();
            ui.label(format!(
                "{words} words  ·  {lines} lines  ·  {headings} headings"
            ));
            if let Some(error) = &self.error {
                ui.separator();
                ui.colored_label(egui::Color32::RED, error);
                if ui.button("Dismiss").clicked() {
                    self.error = None;
                }
            }
        });
        self.confirmation(&ctx);
        self.chooser_ui(&ctx);
    }
}

impl eframe::App for MarkdownEditor {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        self.draw(ui);
    }
}

/// Draw one heading for the preview at its level's size, keeping inline
/// Markdown (emphasis, code, links) by rendering it as a bold paragraph in a
/// scope whose body text is heading-sized. Returns the bottom of the heading.
fn preview_heading(
    ui: &mut egui::Ui,
    cache: &mut CommonMarkCache,
    family: &egui::FontFamily,
    level: u8,
    text: &str,
) -> f32 {
    let font = egui::FontId::new(HEADING_SIZES[level as usize - 1], family.clone());
    ui.scope(|ui| {
        ui.style_mut()
            .text_styles
            .insert(egui::TextStyle::Body, font);
        CommonMarkViewer::new().show(ui, cache, &heading_markdown(text));
    });
    if level <= 2 {
        ui.separator();
    }
    ui.min_rect().bottom()
}

/// Heading text as a bold Markdown paragraph: an ATX closing sequence
/// (`## Title ##`) is dropped, and a leading character that would start a
/// list, quote or other block is escaped so it renders literally.
fn heading_markdown(text: &str) -> String {
    let mut text = text.trim_end();
    let unclosed = text.trim_end_matches('#');
    if unclosed.len() < text.len() && (unclosed.is_empty() || unclosed.ends_with([' ', '\t'])) {
        text = unclosed.trim_end();
    }
    if text.is_empty() {
        return String::new();
    }
    let digits = text.len() - text.trim_start_matches(|c: char| c.is_ascii_digit()).len();
    let escape_at = if text.starts_with(|c: char| c.is_ascii_punctuation()) {
        Some(0)
    } else if digits > 0 && text[digits..].starts_with(['.', ')']) {
        Some(digits)
    } else {
        None
    };
    let mut escaped = text.to_owned();
    if let Some(at) = escape_at {
        escaped.insert(at, '\\');
    }
    format!("**{escaped}**")
}

/// Register the first bold font found in `HEADING_FONT_PATHS` as its own
/// family, with the bundled fonts as fallback for missing glyphs, and return
/// that family; without one, headings stay in the regular font.
fn load_heading_font(ctx: &egui::Context) -> egui::FontFamily {
    let Some(bytes) = HEADING_FONT_PATHS
        .iter()
        .find_map(|path| std::fs::read(path).ok())
    else {
        return egui::FontFamily::Proportional;
    };
    let mut fonts = egui::FontDefinitions::default();
    fonts.font_data.insert(
        "heading-bold".to_owned(),
        std::sync::Arc::new(egui::FontData::from_owned(bytes)),
    );
    let family = egui::FontFamily::Name("heading".into());
    let mut chain = vec!["heading-bold".to_owned()];
    chain.extend(
        fonts.families[&egui::FontFamily::Proportional]
            .iter()
            .cloned(),
    );
    fonts.families.insert(family.clone(), chain);
    ctx.set_fonts(fonts);
    family
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
    file_chooser::install_logger();
    let args = match cli::parse(std::env::args_os().skip(1)) {
        Ok(cli::CliCommand::Run(args)) => args,
        Ok(cli::CliCommand::Help) => {
            print!("{}", cli::USAGE);
            return Ok(());
        }
        Err(cli::UsageError(message)) => {
            eprint!("error: {message}\n\n{}", cli::USAGE);
            std::process::exit(2);
        }
    };
    #[cfg(target_os = "linux")]
    use_software_gl_on_vmware();
    let mut app = MarkdownEditor {
        chooser_pref: args.chooser,
        ..MarkdownEditor::default()
    };
    if let Some(path) = args.file {
        app.open_path(path);
    }
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default().with_inner_size([1200.0, 800.0]),
        ..Default::default()
    };
    eframe::run_native(
        "markdown-editor",
        options,
        Box::new(|cc| {
            app.heading_family = load_heading_font(&cc.egui_ctx);
            Ok(Box::new(app))
        }),
    )
}

#[cfg(test)]
mod tests {
    use super::heading_markdown;

    #[test]
    fn heading_text_renders_as_a_literal_bold_line() {
        assert_eq!(heading_markdown("Room *A*"), "**Room *A***");
        assert_eq!(heading_markdown("Title ##"), "**Title**");
        assert_eq!(heading_markdown("C#"), "**C#**");
        assert_eq!(heading_markdown("1. Intro"), "**1\\. Intro**");
        assert_eq!(heading_markdown("- dash"), "**\\- dash**");
        assert_eq!(heading_markdown("##"), "");
    }
}

#[cfg(test)]
mod ui_tests {
    use super::*;

    const DOC: &str = "# A\n## A1\n## A2\n## A3\n# B\n";

    /// An editor that always uses the built-in chooser, so no test opens a
    /// real system dialog whatever display it runs on.
    fn editor() -> MarkdownEditor {
        MarkdownEditor {
            chooser_pref: ChooserPreference::Window,
            ..MarkdownEditor::default()
        }
    }

    fn frame(
        ctx: &egui::Context,
        app: &mut MarkdownEditor,
        events: Vec<egui::Event>,
        modifiers: egui::Modifiers,
    ) {
        let input = egui::RawInput {
            screen_rect: Some(egui::Rect::from_min_size(
                egui::Pos2::ZERO,
                egui::vec2(1200.0, 800.0),
            )),
            events: std::iter::once(egui::Event::ModifiersChanged(modifiers))
                .chain(events)
                .collect(),
            ..Default::default()
        };
        let mut output = ctx.run_ui(input, |ui| app.draw(ui));
        output.textures_delta.clear();
    }

    fn click(
        ctx: &egui::Context,
        app: &mut MarkdownEditor,
        pos: egui::Pos2,
        modifiers: egui::Modifiers,
    ) {
        let button = |pressed| egui::Event::PointerButton {
            pos,
            button: egui::PointerButton::Primary,
            pressed,
            modifiers,
        };
        frame(
            ctx,
            app,
            vec![egui::Event::PointerMoved(pos), button(true)],
            modifiers,
        );
        frame(ctx, app, vec![button(false)], modifiers);
        for _ in 0..3 {
            frame(ctx, app, vec![], egui::Modifiers::NONE);
        }
    }

    #[test]
    fn shift_click_in_the_outline_selects_a_range() {
        let ctx = egui::Context::default();
        let mut app = editor();
        *app.document.text_mut() = DOC.to_owned();
        frame(&ctx, &mut app, vec![], egui::Modifiers::NONE);
        let mut rows = Vec::new();
        // Start below the toolbar so the probe never clicks Open or Save.
        for y in (60..300).step_by(3) {
            click(
                &ctx,
                &mut app,
                egui::pos2(120.0, y as f32),
                egui::Modifiers::NONE,
            );
            if let Some(sel) = app.outline.selected_rows().first().copied()
                && rows.last().map(|&(i, _)| i) != Some(sel)
            {
                rows.push((sel, y as f32));
            }
        }
        eprintln!("rows: {rows:?}");
        let y_of = |i: usize| rows.iter().find(|r| r.0 == i).unwrap().1;
        click(
            &ctx,
            &mut app,
            egui::pos2(120.0, y_of(1)),
            egui::Modifiers::NONE,
        );
        assert_eq!(app.outline.selected_rows(), vec![1]);
        click(
            &ctx,
            &mut app,
            egui::pos2(120.0, y_of(3)),
            egui::Modifiers::SHIFT,
        );
        assert_eq!(app.outline.selected_rows(), vec![1, 2, 3]);
    }

    /// A fresh, empty folder under the system temp folder for one test.
    fn scratch(test: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "markdown-editor-test-{}-{test}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn ctrl(key: egui::Key) -> egui::Event {
        egui::Event::Key {
            key,
            physical_key: None,
            pressed: true,
            repeat: false,
            modifiers: egui::Modifiers::COMMAND,
        }
    }

    fn open_file(app: &mut MarkdownEditor, path: &std::path::Path, text: &str) {
        std::fs::write(path, text).unwrap();
        app.open_path(path.to_path_buf());
        assert_eq!(app.document.text(), text);
    }

    /// The constitution's VI.2 baseline document: at least 40,000 lines shaped
    /// like a long legal text. It has numbered headings nested down to H6, long
    /// paragraphs with cross-references and reference links, pipe tables with a
    /// long cell, HTML tables and fenced code blocks with a long line. It is
    /// built by arithmetic, not randomness, so every run times the same text.
    fn legal_fixture() -> String {
        const WORDS: [&str; 16] = [
            "the",
            "party",
            "shall",
            "notwithstanding",
            "provided",
            "agreement",
            "herein",
            "obligation",
            "pursuant",
            "to",
            "any",
            "clause",
            "of",
            "such",
            "termination",
            "licensee",
        ];
        const LEVELS: [usize; 17] = [1, 2, 3, 4, 5, 6, 6, 5, 4, 5, 6, 3, 4, 2, 3, 4, 5];
        let mut out = String::new();
        let mut lines = 0;
        let mut numbers = [0usize; 6];
        let mut k = 0usize;
        let (mut tables, mut html, mut code) = (0, 0, 0);
        while lines < 40_000 {
            let level = LEVELS[k % LEVELS.len()];
            numbers[level - 1] += 1;
            numbers[level..].iter_mut().for_each(|n| *n = 0);
            let number: Vec<String> = numbers[..level]
                .iter()
                .map(|n| n.max(&1).to_string())
                .collect();
            out.push_str(&format!(
                "{} {} Clause {k}\n\n",
                "#".repeat(level),
                number.join(".")
            ));
            lines += 2;
            for p in 0..1 + k % 2 {
                let len = 300 + (k * 37 + p * 101) % 500;
                let mut para = String::new();
                let mut w = k + p;
                while para.len() < len {
                    para.push_str(WORDS[w % WORDS.len()]);
                    para.push(' ');
                    w = w * 5 + 3;
                }
                out.push_str(&format!(
                    "{para}as set out in [the Act][ref{}]; see Section {}.{}.{}.\n\n",
                    k % 50,
                    1 + k % 9,
                    1 + k % 7,
                    1 + k % 5
                ));
                lines += 2;
            }
            if lines / 200 > tables {
                tables = lines / 200;
                out.push_str(&format!(
                    "| Clause | Effect |\n|---|---|\n| {k} | {}|\n| {} | short |\n\n",
                    "the licensee shall indemnify ".repeat(10),
                    k + 1
                ));
                lines += 5;
            }
            if lines / 500 > html {
                html = lines / 500;
                out.push_str("<table>\n<tr><th>Term</th><th>Meaning</th></tr>\n");
                out.push_str(&format!(
                    "<tr><td>T{k}</td><td>{}</td></tr>\n</table>\n\n",
                    "defined term ".repeat(12)
                ));
                lines += 5;
            }
            if lines / 300 > code {
                code = lines / 300;
                out.push_str(&format!(
                    "```\nlet clause_{k} = \"{}\";\n```\n\n",
                    "x".repeat(200)
                ));
                lines += 4;
            }
            k += 1;
        }
        for r in 0..50 {
            out.push_str(&format!("[ref{r}]: https://example.com/statute/{r}\n"));
        }
        out
    }

    fn median(mut times: Vec<f64>) -> f64 {
        times.sort_by(f64::total_cmp);
        times[times.len() / 2]
    }

    /// VI.2 timing check: the cold first frame, steady frames and frames that
    /// scroll the preview, on `legal_fixture`. Run with
    /// `cargo test --release -- --ignored preview_timing --nocapture`.
    #[test]
    #[ignore]
    fn preview_timing() {
        let ctx = egui::Context::default();
        let mut app = editor();
        let text = legal_fixture();
        eprintln!(
            "fixture: {} lines, {} bytes",
            text.lines().count(),
            text.len()
        );
        *app.document.text_mut() = text;
        let ms = |since: std::time::Instant| since.elapsed().as_secs_f64() * 1000.0;

        let start = std::time::Instant::now();
        frame(&ctx, &mut app, vec![], egui::Modifiers::NONE);
        let cold = ms(start);

        let warm = median(
            (0..30)
                .map(|_| {
                    let start = std::time::Instant::now();
                    frame(&ctx, &mut app, vec![], egui::Modifiers::NONE);
                    ms(start)
                })
                .collect(),
        );

        // Over the preview column, right of the outline and the source pane.
        let over_preview = egui::pos2(1000.0, 400.0);
        let scroll = median(
            (0..30)
                .map(|_| {
                    let wheel = egui::Event::MouseWheel {
                        unit: egui::MouseWheelUnit::Point,
                        delta: egui::vec2(0.0, -200.0),
                        phase: egui::TouchPhase::Move,
                        modifiers: egui::Modifiers::NONE,
                    };
                    let start = std::time::Instant::now();
                    frame(
                        &ctx,
                        &mut app,
                        vec![egui::Event::PointerMoved(over_preview), wheel],
                        egui::Modifiers::NONE,
                    );
                    ms(start)
                })
                .collect(),
        );
        eprintln!("preview_timing: cold {cold:.1} ms, warm {warm:.1} ms, scroll {scroll:.1} ms");
    }

    #[test]
    fn file_shortcuts_wait_while_a_chooser_is_open() {
        let ctx = egui::Context::default();
        let mut app = editor();
        *app.document.text_mut() = DOC.to_owned();
        app.start_chooser(Purpose::Open, &ctx);
        frame(
            &ctx,
            &mut app,
            vec![ctrl(egui::Key::N)],
            egui::Modifiers::COMMAND,
        );
        assert_eq!(app.document.text(), DOC);
        assert!(app.pending.is_none());
        assert!(app.chooser.is_some());
    }

    #[test]
    fn only_one_chooser_runs_at_a_time() {
        let ctx = egui::Context::default();
        let mut app = editor();
        app.start_chooser(Purpose::Open, &ctx);
        let first = app.chooser.as_ref().unwrap().generation;
        app.start_chooser(Purpose::Open, &ctx);
        assert_eq!(app.chooser.as_ref().unwrap().generation, first);
    }

    #[test]
    fn cancelling_open_keeps_the_document() {
        let ctx = egui::Context::default();
        let dir = scratch("cancel-open");
        let mut app = editor();
        open_file(&mut app, &dir.join("a.md"), "# A\n");
        app.start_chooser(Purpose::Open, &ctx);
        app.finish_chooser(Outcome::Cancelled, &ctx);
        assert!(app.chooser.is_none());
        assert_eq!(app.document.text(), "# A\n");
        assert_eq!(app.document.path(), Some(dir.join("a.md").as_path()));
    }

    #[test]
    fn choosing_a_file_opens_it() {
        let ctx = egui::Context::default();
        let dir = scratch("choose-open");
        let path = dir.join("plan.md");
        std::fs::write(&path, "# Plan\n").unwrap();
        let mut app = editor();
        app.start_chooser(Purpose::Open, &ctx);
        app.finish_chooser(Outcome::Chosen(path.clone()), &ctx);
        assert_eq!(app.document.text(), "# Plan\n");
        assert_eq!(app.document.path(), Some(path.as_path()));
        assert!(!app.document.is_dirty());
    }

    #[test]
    fn a_file_that_cannot_be_opened_keeps_the_document() {
        let ctx = egui::Context::default();
        let dir = scratch("bad-open");
        std::fs::write(dir.join("latin1.md"), b"caf\xe9\n").unwrap();
        let mut app = editor();
        open_file(&mut app, &dir.join("a.md"), "# A\n");
        for bad in ["missing.md", "latin1.md"] {
            app.start_chooser(Purpose::Open, &ctx);
            app.finish_chooser(Outcome::Chosen(dir.join(bad)), &ctx);
            assert_eq!(app.document.text(), "# A\n");
            assert!(
                app.error
                    .as_deref()
                    .unwrap()
                    .starts_with("Could not open file"),
                "{bad}"
            );
        }
    }

    #[test]
    fn open_over_unsaved_changes_asks_first() {
        let ctx = egui::Context::default();
        let mut app = editor();
        *app.document.text_mut() = DOC.to_owned();
        app.request(PendingAction::Open, &ctx);
        assert_eq!(app.pending, Some(PendingAction::Open));
        assert!(app.chooser.is_none());
        // What "Discard" does once the user agrees.
        app.pending = None;
        app.perform(PendingAction::Open, &ctx);
        assert_eq!(app.chooser.as_ref().unwrap().purpose, Purpose::Open);
    }

    fn save_as_new(app: &mut MarkdownEditor, ctx: &egui::Context, after: AfterSave) {
        *app.document.text_mut() = "hello\n".to_owned();
        assert_eq!(app.save(after, ctx), SaveStatus::Choosing);
        assert_eq!(
            app.chooser.as_ref().unwrap().purpose,
            Purpose::SaveAs { after }
        );
    }

    #[test]
    fn saving_a_new_document_writes_the_chosen_file() {
        let ctx = egui::Context::default();
        let path = scratch("save-new").join("new.md");
        let mut app = editor();
        save_as_new(&mut app, &ctx, AfterSave::Nothing);
        app.finish_chooser(Outcome::Chosen(path.clone()), &ctx);
        assert_eq!(std::fs::read_to_string(&path).unwrap(), "hello\n");
        assert_eq!(app.document.path(), Some(path.as_path()));
        assert!(!app.document.is_dirty());
    }

    #[test]
    fn cancelling_save_first_cancels_the_action() {
        let ctx = egui::Context::default();
        let dir = scratch("cancel-save");
        for action in [PendingAction::Quit, PendingAction::New, PendingAction::Open] {
            let mut app = editor();
            save_as_new(&mut app, &ctx, AfterSave::Continue(action));
            app.finish_chooser(Outcome::Cancelled, &ctx);
            assert!(!app.allow_close, "{action:?}");
            assert!(app.chooser.is_none(), "{action:?}");
            assert_eq!(app.document.text(), "hello\n", "{action:?}");
            assert!(app.document.is_dirty(), "{action:?}");
            assert_eq!(app.document.path(), None, "{action:?}");
        }
        assert_eq!(std::fs::read_dir(&dir).unwrap().count(), 0);
    }

    #[test]
    fn a_failed_save_keeps_the_document_and_drops_the_action() {
        let ctx = egui::Context::default();
        let path = scratch("failed-save").join("no-such-folder").join("new.md");
        let mut app = editor();
        save_as_new(&mut app, &ctx, AfterSave::Continue(PendingAction::Quit));
        app.finish_chooser(Outcome::Chosen(path), &ctx);
        assert!(
            app.error
                .as_deref()
                .unwrap()
                .starts_with("Could not save file")
        );
        assert!(app.document.is_dirty());
        assert!(!app.allow_close);
    }

    #[test]
    fn save_as_over_a_file_keeps_a_backup() {
        let ctx = egui::Context::default();
        let dir = scratch("save-backup");
        let path = dir.join("old.md");
        std::fs::write(&path, "old\n").unwrap();
        let mut app = editor();
        save_as_new(&mut app, &ctx, AfterSave::Nothing);
        app.finish_chooser(Outcome::Chosen(path.clone()), &ctx);
        assert_eq!(std::fs::read_to_string(&path).unwrap(), "hello\n");
        assert_eq!(
            std::fs::read_to_string(dir.join("old.md.bak")).unwrap(),
            "old\n"
        );
    }

    #[test]
    fn a_successful_save_first_runs_the_action() {
        let ctx = egui::Context::default();
        let path = scratch("save-then-new").join("kept.md");
        let mut app = editor();
        save_as_new(&mut app, &ctx, AfterSave::Continue(PendingAction::New));
        app.finish_chooser(Outcome::Chosen(path.clone()), &ctx);
        assert_eq!(std::fs::read_to_string(&path).unwrap(), "hello\n");
        assert_eq!(app.document.text(), "");
        assert_eq!(app.document.path(), None);
    }

    #[test]
    fn a_file_named_on_the_command_line_still_opens() {
        let dir = scratch("cli-open");
        let mut app = editor();
        open_file(&mut app, &dir.join("notes.md"), "notes\n");
        assert!(app.chooser.is_none());
    }
}
