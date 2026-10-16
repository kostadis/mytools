//! Collapsible heading-outline panel, modelled on pdf-translators' Markdown
//! editor: move whole sections, promote/demote, rename, delete, multi-select,
//! and an undo history for those operations. Every operation rewrites the
//! document text, which stays the single source of truth.

use crate::outline::{self, Block};
use eframe::egui;
use std::collections::BTreeSet;

const HISTORY_LIMIT: usize = 100;

#[derive(Clone)]
struct Snapshot {
    text: String,
    collapsed: BTreeSet<usize>,
    selection: BTreeSet<usize>,
    selected: Option<usize>,
}

struct Rename {
    idx: usize,
    value: String,
    focused: bool,
}

enum Action {
    Click { idx: usize, ctrl: bool, shift: bool },
    ToggleCollapse(usize),
    Level(usize, i8),
    MoveUp(usize),
    MoveDown(usize),
    Delete(usize),
    StartRename(usize),
    FinishRename { commit: bool },
    LevelSelected(i8),
    DeleteSelected,
    ClearSelection,
    Undo,
    Redo,
}

#[derive(Default)]
pub struct OutlinePanel {
    parsed_text: String,
    blocks: Vec<Block>,
    collapsed: BTreeSet<usize>,
    selection: BTreeSet<usize>,
    /// Keyboard focus row; the anchor for shift-click ranges.
    selected: Option<usize>,
    anchor: Option<usize>,
    rename: Option<Rename>,
    undo: Vec<Snapshot>,
    redo: Vec<Snapshot>,
    scroll_to_selected: bool,
    pending_offset: Option<f32>,
    clicked: Option<usize>,
}

impl OutlinePanel {
    /// Forget everything about the previous document.
    pub fn reset(&mut self) {
        *self = Self::default();
    }

    pub fn blocks(&self) -> &[Block] {
        &self.blocks
    }

    /// The row the user clicked since the last call, if any.
    pub fn take_clicked(&mut self) -> Option<usize> {
        self.clicked.take()
    }

    /// Select block `idx`, expanding any collapsed sections that hide it, and
    /// scroll it into view.
    pub fn reveal(&mut self, idx: usize) {
        let mut level = self.blocks[idx].level;
        for j in (0..idx).rev() {
            let parent = self.blocks[j].level;
            if parent > 0 && parent < level {
                self.collapsed.remove(&j);
                level = parent;
            }
        }
        self.select(idx);
        self.scroll_to_selected = true;
    }

    pub fn heading_count(&self) -> usize {
        self.blocks.iter().filter(|b| b.level > 0).count()
    }

    /// Re-parse after the text changed. Per-row state is index based, so it is
    /// dropped when typing adds or removes a heading.
    pub fn sync(&mut self, text: &str) {
        if self.parsed_text == text {
            return;
        }
        let count = self.blocks.len();
        self.parsed_text = text.to_owned();
        self.blocks = outline::parse(text);
        if self.blocks.len() != count {
            self.clear_row_state();
        }
    }

    fn clear_row_state(&mut self) {
        self.collapsed.clear();
        self.selection.clear();
        self.selected = None;
        self.anchor = None;
        self.rename = None;
    }

    fn visible(&self) -> Vec<usize> {
        outline::visible_indices(&self.blocks, &self.collapsed)
    }

    // ── History ──────────────────────────────────────────────────────────────

    fn snapshot(&self, text: &str) -> Snapshot {
        Snapshot {
            text: text.to_owned(),
            collapsed: self.collapsed.clone(),
            selection: self.selection.clone(),
            selected: self.selected,
        }
    }

    fn restore(&mut self, snapshot: Snapshot, text: &mut String) {
        *text = snapshot.text;
        self.parsed_text = text.clone();
        self.blocks = outline::parse(text);
        self.collapsed = snapshot.collapsed;
        self.selection = snapshot.selection;
        self.selected = snapshot.selected;
        self.anchor = snapshot.selected;
        self.rename = None;
        self.scroll_to_selected = true;
    }

    /// Undo and redo save the current state on the other stack first, so text
    /// typed since the last outline operation can always be redone back.
    fn undo(&mut self, text: &mut String) {
        if let Some(snapshot) = self.undo.pop() {
            self.redo.push(self.snapshot(text));
            self.restore(snapshot, text);
        }
    }

    fn redo(&mut self, text: &mut String) {
        if let Some(snapshot) = self.redo.pop() {
            self.undo.push(self.snapshot(text));
            self.restore(snapshot, text);
        }
    }

    /// Run a structural operation and write the result back into `text`.
    /// Collapse and selection state follow their blocks to their new indices.
    fn apply(&mut self, text: &mut String, op: impl FnOnce(&mut Vec<Block>) -> bool) {
        let mut blocks = self.blocks.clone();
        if !op(&mut blocks) {
            return;
        }
        self.undo.push(self.snapshot(text));
        if self.undo.len() > HISTORY_LIMIT {
            self.undo.remove(0);
        }
        self.redo.clear();

        let new_index = |old: usize| blocks.iter().position(|b| b.id == old);
        let remap = |set: &BTreeSet<usize>| set.iter().filter_map(|&i| new_index(i)).collect();
        self.collapsed = remap(&self.collapsed);
        self.selection = remap(&self.selection);
        self.selected = self.selected.and_then(new_index);
        self.anchor = self.anchor.and_then(new_index);

        *text = outline::serialize(&blocks);
        self.parsed_text = text.clone();
        self.blocks = outline::parse(text);
        // An unclosed code fence moved above other headings swallows them.
        if self.blocks.len() != blocks.len() {
            self.clear_row_state();
        }
        self.scroll_to_selected = true;
    }

    // ── Selection ────────────────────────────────────────────────────────────

    fn select(&mut self, idx: usize) {
        self.selection = BTreeSet::from([idx]);
        self.selected = Some(idx);
        self.anchor = Some(idx);
    }

    /// Ctrl/Cmd toggles one row; Shift selects the visible range from the anchor.
    fn click(&mut self, idx: usize, ctrl: bool, shift: bool) {
        if shift && let Some(anchor) = self.anchor {
            let visible = self.visible();
            let from = visible.iter().position(|&i| i == anchor);
            let to = visible.iter().position(|&i| i == idx);
            if let (Some(from), Some(to)) = (from, to) {
                self.selection = visible[from.min(to)..=from.max(to)].iter().copied().collect();
                self.selected = Some(idx);
                return;
            }
        }
        if ctrl {
            if !self.selection.remove(&idx) {
                self.selection.insert(idx);
            }
            self.selected = Some(idx);
            self.anchor = Some(idx);
            return;
        }
        self.select(idx);
    }

    fn perform(&mut self, action: Action, text: &mut String) {
        match action {
            Action::Click { idx, ctrl, shift } => {
                self.click(idx, ctrl, shift);
                self.clicked = Some(idx);
            }
            Action::ToggleCollapse(idx) => {
                if !self.collapsed.remove(&idx) {
                    self.collapsed.insert(idx);
                }
            }
            Action::Level(idx, delta) => {
                self.apply(text, |b| outline::change_level(b, &BTreeSet::from([idx]), delta))
            }
            Action::MoveUp(idx) => self.apply(text, |b| outline::move_up(b, idx)),
            Action::MoveDown(idx) => self.apply(text, |b| outline::move_down(b, idx)),
            Action::Delete(idx) => {
                self.apply(text, |b| outline::delete_sections(b, &BTreeSet::from([idx])))
            }
            Action::StartRename(idx) => {
                self.rename = Some(Rename {
                    idx,
                    value: self.blocks[idx].text.clone(),
                    focused: false,
                })
            }
            Action::FinishRename { commit } => {
                if let Some(rename) = self.rename.take()
                    && commit
                {
                    self.apply(text, |b| outline::rename(b, rename.idx, &rename.value));
                }
            }
            Action::LevelSelected(delta) => {
                let selection = self.selection.clone();
                self.apply(text, |b| outline::change_level(b, &selection, delta));
            }
            Action::DeleteSelected => {
                let selection = std::mem::take(&mut self.selection);
                self.apply(text, |b| outline::delete_sections(b, &selection));
                self.selected = None;
                self.anchor = None;
            }
            Action::ClearSelection => self.selection.clear(),
            Action::Undo => self.undo(text),
            Action::Redo => self.redo(text),
        }
    }

    // ── Keyboard ─────────────────────────────────────────────────────────────

    /// Outline shortcuts; they apply only while no text field has focus.
    pub fn shortcuts(&mut self, ctx: &egui::Context, text: &mut String) {
        if ctx.text_edit_focused() {
            return;
        }
        let command = egui::Modifiers::COMMAND;
        let mut actions = Vec::new();
        ctx.input_mut(|i| {
            if i.consume_key(command | egui::Modifiers::SHIFT, egui::Key::Z)
                || i.consume_key(command, egui::Key::Y)
            {
                actions.push(Action::Redo);
            } else if i.consume_key(command, egui::Key::Z) {
                actions.push(Action::Undo);
            }
            if i.consume_key(command, egui::Key::A) {
                self.selection = self.visible().into_iter().collect();
            }
            if i.consume_key(egui::Modifiers::NONE, egui::Key::Escape) {
                actions.push(Action::ClearSelection);
            }
            let Some(sel) = self.selected.filter(|&s| self.blocks.get(s).is_some_and(|b| b.level > 0))
            else {
                return;
            };
            if i.consume_key(egui::Modifiers::NONE, egui::Key::Delete) {
                actions.push(Action::DeleteSelected);
            }
            for event in &i.events {
                if let egui::Event::Text(typed) = event {
                    match typed.as_str() {
                        "u" => actions.push(Action::MoveUp(sel)),
                        "d" => actions.push(Action::MoveDown(sel)),
                        "[" => actions.push(Action::LevelSelected(-1)),
                        "]" => actions.push(Action::LevelSelected(1)),
                        _ => {}
                    }
                }
            }
        });
        for action in actions {
            self.perform(action, text);
        }
    }

    // ── UI ───────────────────────────────────────────────────────────────────

    pub fn ui(&mut self, ui: &mut egui::Ui, text: &mut String) {
        let mut actions = Vec::new();

        ui.horizontal(|ui| {
            ui.heading("Outline");
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if ui
                    .add_enabled(!self.redo.is_empty(), egui::Button::new("Redo"))
                    .on_hover_text("Redo outline change (Ctrl/Cmd+Shift+Z outside the editor)")
                    .clicked()
                {
                    actions.push(Action::Redo);
                }
                if ui
                    .add_enabled(!self.undo.is_empty(), egui::Button::new("Undo"))
                    .on_hover_text("Undo outline change (Ctrl/Cmd+Z outside the editor)")
                    .clicked()
                {
                    actions.push(Action::Undo);
                }
            });
        });

        if self.selection.len() > 1 {
            ui.horizontal_wrapped(|ui| {
                ui.label(format!("{} selected", self.selection.len()));
                if ui.small_button("⏴ Promote").on_hover_text("[").clicked() {
                    actions.push(Action::LevelSelected(-1));
                }
                if ui.small_button("Demote ⏵").on_hover_text("]").clicked() {
                    actions.push(Action::LevelSelected(1));
                }
                if ui.small_button("✖ Delete").on_hover_text("Delete").clicked() {
                    actions.push(Action::DeleteSelected);
                }
                if ui.small_button("Clear").on_hover_text("Esc").clicked() {
                    actions.push(Action::ClearSelection);
                }
            });
        }
        ui.separator();

        if self.blocks.is_empty() {
            ui.weak("Headings will appear here.");
        }
        let visible = self.visible();
        let row_height = ui.spacing().interact_size.y;
        let row_pitch = row_height + ui.spacing().item_spacing.y;
        let mut scroll = egui::ScrollArea::vertical().id_salt("outline").auto_shrink(false);
        if let Some(offset) = self.pending_offset.take() {
            scroll = scroll.vertical_scroll_offset(offset);
        }
        let target = std::mem::take(&mut self.scroll_to_selected)
            .then(|| self.selected.and_then(|s| visible.iter().position(|&i| i == s)))
            .flatten();
        scroll.show_rows(ui, row_height, visible.len(), |ui, range| {
            // Only drawn rows can scroll themselves into view; jump to an
            // off-screen row by offset on the next frame instead.
            if let Some(pos) = target
                && !range.contains(&pos)
            {
                self.pending_offset = Some((pos as f32 * row_pitch - 80.0).max(0.0));
                ui.ctx().request_repaint();
            }
            for pos in range {
                let response = self.row(ui, visible[pos], row_height, &mut actions);
                if target == Some(pos) {
                    response.scroll_to_me(None);
                }
            }
        });

        for action in actions {
            self.perform(action, text);
        }
    }

    fn row(
        &mut self,
        ui: &mut egui::Ui,
        idx: usize,
        height: f32,
        actions: &mut Vec<Action>,
    ) -> egui::Response {
        let blocks = &self.blocks;
        let block = &blocks[idx];
        let (rect, response) =
            ui.allocate_exact_size(egui::vec2(ui.available_width(), height), egui::Sense::click());
        if self.selection.contains(&idx) {
            ui.painter().rect_filled(rect, 2.0, ui.visuals().selection.bg_fill);
        } else if response.hovered() {
            ui.painter().rect_filled(rect, 2.0, ui.visuals().widgets.hovered.weak_bg_fill);
        }
        if response.clicked() {
            let modifiers = ui.input(|i| i.modifiers);
            actions.push(Action::Click {
                idx,
                ctrl: modifiers.command,
                shift: modifiers.shift,
            });
        }
        if response.double_clicked() && block.level > 0 {
            actions.push(Action::StartRename(idx));
        }

        let mut ui = ui.new_child(
            egui::UiBuilder::new()
                .max_rect(rect)
                .layout(egui::Layout::left_to_right(egui::Align::Center)),
        );
        ui.add_space(block.level.saturating_sub(1) as f32 * 14.0 + 2.0);
        let toggle_width = 18.0;
        if outline::has_children(blocks, idx) {
            let icon = if self.collapsed.contains(&idx) { "⏵" } else { "⏷" };
            if ui
                .add_sized([toggle_width, height], egui::Button::new(icon).frame(false))
                .clicked()
            {
                actions.push(Action::ToggleCollapse(idx));
            }
        } else {
            ui.add_space(toggle_width);
        }
        let badge = if block.level == 0 {
            "P".to_owned()
        } else {
            format!("H{}", block.level)
        };
        ui.add(egui::Label::new(egui::RichText::new(badge).monospace().weak()).selectable(false));

        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            if block.level > 0 {
                let mut button = |ui: &mut egui::Ui, icon, tip, enabled, action| {
                    if ui
                        .add_enabled(enabled, egui::Button::new(icon).small().frame(false))
                        .on_hover_text(tip)
                        .clicked()
                    {
                        actions.push(action);
                    }
                };
                button(ui, "✖", "Delete section", true, Action::Delete(idx));
                let can_down = outline::next_sibling(blocks, idx).is_some();
                button(ui, "⬇", "Move down (d)", can_down, Action::MoveDown(idx));
                let can_up = outline::prev_sibling(blocks, idx).is_some();
                button(ui, "⬆", "Move up (u)", can_up, Action::MoveUp(idx));
                button(ui, "⏵", "Demote (])", block.level < 6, Action::Level(idx, 1));
                button(ui, "⏴", "Promote ([)", block.level > 1, Action::Level(idx, -1));
            }
            ui.with_layout(egui::Layout::left_to_right(egui::Align::Center), |ui| {
                match &mut self.rename {
                    Some(rename) if rename.idx == idx => {
                        let edit = ui.add(
                            egui::TextEdit::singleline(&mut rename.value)
                                .desired_width(ui.available_width()),
                        );
                        if !rename.focused {
                            edit.request_focus();
                            rename.focused = true;
                        }
                        if edit.lost_focus() {
                            let cancelled = ui.input(|i| i.key_pressed(egui::Key::Escape));
                            actions.push(Action::FinishRename { commit: !cancelled });
                        }
                    }
                    _ => {
                        let label = match block.level {
                            0 => egui::RichText::new("(preamble)").italics().weak(),
                            _ if block.text.is_empty() => egui::RichText::new("(empty)").weak(),
                            _ => egui::RichText::new(&block.text),
                        };
                        ui.add(egui::Label::new(label).truncate().selectable(false))
                            .on_hover_text(&block.text);
                    }
                }
            });
        });
        response
    }
}
