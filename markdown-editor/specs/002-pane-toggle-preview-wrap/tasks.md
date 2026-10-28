---

description: "Task list for Hideable Editor Pane and Wrapping Preview"
---

# Tasks: Hideable Editor Pane and Wrapping Preview

**Input**: Design documents from `specs/002-pane-toggle-preview-wrap/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ui.md, quickstart.md

**Tests**: Required. Constitution V.1 makes tests part of every change: unit tests
next to core code, and headless egui tests for UI behaviour. Constitution VI.2
requires a timing check before and after. Write each story's tests first and
watch them fail before implementing.

**Organization**: Tasks are grouped by user story so each story can be built,
tested and merged on its own.

All paths are relative to `markdown-editor/`. Headless UI tests go in the
existing `#[cfg(test)] mod ui_tests` in `src/main.rs` and reuse its `editor()`,
`frame()` and `click()` helpers.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 = preview wrapping (P1), US2 = hideable editor (P2)

---

## Phase 1: Setup

**Purpose**: Add the dependency and create the two new module files.

- [X] T001 Add `pulldown-cmark = { version = "0.13.4", default-features = false }` to `[dependencies]` in `Cargo.toml`, matching the version already locked as egui_commonmark's parser (research R4). Run `cargo build` and confirm `Cargo.lock` gains no new package (`git diff Cargo.lock` shows only the dependency edge).
- [X] T002 [P] Create empty `src/preview_blocks.rs` and `src/panes.rs`, each with a `//!` module comment saying it is pure core logic with no egui dependency (constitution IV.1). Register both with `mod preview_blocks;` and `mod panes;` in `src/main.rs`, keeping the module list alphabetical.

---

## Phase 2: Foundational — VI.2 timing baseline (blocks both stories)

**Purpose**: The constitution requires a timing check before and after any
change that touches whole-document work. No fixture exists, so build it and
record the baseline **before any preview or layout code changes**.

**⚠️ CRITICAL**: T003–T005 must run against the unmodified preview and layout code.

- [X] T003 Add `fn legal_fixture() -> String` to `mod ui_tests` in `src/main.rs`. It deterministically generates a document of at least 40,000 lines, shaped like legal text (constitution VI.2): thousands of numbered headings nested H1 to H6 (`# Article 1`, `## 1.1`, … `###### 1.1.1.1.1.1`), long paragraphs (300 to 800 chars), cross-references such as "see Section 4.2.1", a reference-style link definition block, a pipe table every ~200 lines with one cell of 40+ words, an HTML `<table>` every ~500 lines, and a fenced code block with a 200-char line every ~300 lines. Use a fixed-seed arithmetic pattern rather than a random crate, so the fixture is identical on every run.
- [X] T004 Add `#[test] #[ignore] fn preview_timing()` to `mod ui_tests` in `src/main.rs`. Load `legal_fixture()` into `editor()` and use a 1200×800 `frame()`. Time the first frame (cold), then the median of 30 further frames with no input (warm), then the median of 30 frames while scrolling the preview with `egui::Event::MouseWheel` over its column. Print all three in ms with `eprintln!`. It asserts nothing, because it is a measurement.
- [X] T005 Run `cargo test --release -- --ignored preview_timing --nocapture` on the unmodified code. Create `specs/002-pane-toggle-preview-wrap/pr-notes.md` with a "Timing — before" table holding the three numbers, the commit hash and the machine. Commit T001–T005 as `markdown-editor: add legal-shaped fixture and preview timing baseline`.

**Checkpoint**: The baseline is recorded, and either story can start.

---

## Phase 3: User Story 1 — Read long lines in the preview (Priority: P1) 🎯 MVP

**Goal**: Nothing in the preview runs past the pane's right edge. Prose wraps.
Top-level tables and code blocks keep their lines whole and scroll sideways
on their own. A wide table or code block no longer widens anything after it.

**Independent Test**: quickstart.md by-hand step 1 with `wrap-test.md`, plus
the headless tests T011–T013 passing.

### Tests for User Story 1 (write first, must fail)

- [X] T006 [P] [US1] Write unit tests in `#[cfg(test)] mod tests` of `src/preview_blocks.rs` for `split(body: &str) -> Vec<PreviewChunk>` (data-model.md). They should fail until T008:
  (a) a plain paragraph gives one `Prose` covering the whole body;
  (b) paragraph, fenced code, paragraph gives `Prose`, `Code`, `Prose`, where `Code.content` is the fence's inner text byte for byte;
  (c) a top-level pipe table gives a `Table` whose range slices to exactly the table lines;
  (d) an indented (4-space) code block gives `Code`;
  (e) a fence or table inside `- list item` or `> quote` stays inside `Prose`;
  (f) two paragraphs separated by blank lines merge into one `Prose`, so there are never two `Prose` chunks in a row;
  (g) for every case and a mixed sample, the chunk ranges are in order, don't overlap, and together cover `0..body.len()` (III.1);
  (h) no panic on `""`, an unclosed fence, `|` alone, CRLF line endings, and multi-byte UTF-8 near chunk boundaries (V.3);
  (i) a `~~~` fence and a fence with an info string (```` ```rust ````) are `Code` with the info string excluded from `content`.
- [X] T007 [P] [US1] Add a headless test helper to `mod ui_tests` in `src/main.rs`. `fn preview_overflow(app, width) -> (f32, f32)` runs `frame()` at the given window width and returns the preview scroll area's viewport width and content width. To get them, store the `ScrollAreaOutput` `inner_rect.width()` and `content_size.x` from the preview `show` call in a `#[cfg(test)]` field on `MarkdownEditor` (for example `last_preview_extent: (f32, f32)`), set in `draw`.

### Implementation for User Story 1

- [X] T008 [US1] Implement `PreviewChunk` and `split` in `src/preview_blocks.rs` per data-model.md and research R4:
  - Parse with `pulldown_cmark::Parser::new_ext(body, OPTIONS).into_offset_iter()`, where `OPTIONS = ENABLE_TABLES | ENABLE_TASKLISTS | ENABLE_STRIKETHROUGH | ENABLE_FOOTNOTES | ENABLE_DEFINITION_LIST`. This matches egui_commonmark 0.25's `parser_options()`; say so in a comment.
  - Track depth with `Start`/`End` events. At depth 0, a `Start(Tag::CodeBlock)` or `Start(Tag::Table)` begins a cut at its range. Collect `Text` events inside a code block into `content`.
  - Extend each `Prose` range to cover the gaps between cuts, so the chunks tile the body exactly.

  Keep `split` under cognitive complexity ~25 (IV.4), using a helper to push or merge prose. T006 must pass.
- [X] T009 [US1] Add `struct PreviewCache { text: String, links: String, sections: Vec<(String, Vec<PreviewChunk>)> }` with `fn sync(&mut self, text: &str, blocks: &[outline::Block])` in `src/main.rs`, next to `preview`. It is a no-op when `text == self.text`. Otherwise it recomputes `links = outline::link_definitions(text)` and, per block, the body as `preview` slices it today (heading line removed for `level > 0`), `html_table::tables_to_markdown(body).into_owned()`, then `preview_blocks::split` of that converted string. Add a `preview_blocks: PreviewCache` field to `MarkdownEditor` with a `Default`. This moves `link_definitions` and `tables_to_markdown` out of the per-frame path (research R5).
- [X] T010 [US1] Rewrite the body-drawing part of `fn preview` in `src/main.rs`. Call `self.preview_blocks.sync(text, blocks)` once, then for section `i` draw each chunk under `ui.push_id((i, j), …)`:
  - `Prose`: in `ui.scope`, set `ui.style_mut().wrap_mode = Some(egui::TextWrapMode::Wrap)` and draw `CommonMarkViewer` on the chunk text with `links` appended as today. Comment that this stops a nested table from widening the pane (research R2).
  - `Table`: `egui::ScrollArea::horizontal().id_salt(("table", i, j)).auto_shrink([false, true])`, then the same viewer, with wrap mode not forced.
  - `Code`: a new `fn preview_code_block(ui, content)` that draws an `egui::Frame` styled like egui_commonmark's code block (`extreme_bg_color`, noninteractive `bg_stroke`, `corner_radius`) holding `egui::ScrollArea::horizontal().id_salt(("code", i, j))` with `egui::Label::new(RichText::new(content).monospace()).extend().selectable(true)`.

  Leave `preview_heading`, the section rect, the click-to-section mapping and `scroll_to_rect` logic unchanged, so FR-013 still holds. Skip chunks whose text is only whitespace, as `body.trim().is_empty()` does today.
- [X] T011 [US1] Headless test `preview_wraps_after_wide_table` in `mod ui_tests`, `src/main.rs`. Use a document with a paragraph, a pipe table with a 40-word cell, then a 500-char paragraph. With `preview_overflow` at window width 900, assert `content <= viewport + 1.0`. Then use the output shapes from `ctx.run_ui` to assert that the last paragraph's text galleys all end before the viewport's right edge. Watch it fail with T010 reverted, then pass.
- [X] T012 [US1] Headless test `preview_code_and_url_stay_in_pane` in `src/main.rs`: a 200-char fenced code line and a 200-char URL with no spaces. At widths 600, 900 and 1200, `content <= viewport + 1.0`. The URL's text galley has more than one row. The code galley has exactly one row, so it does not wrap (clarification B).
- [X] T013 [US1] Headless test `preview_click_on_wrapped_line_selects_section` in `src/main.rs`: two sections, the second a long wrapped paragraph after a wide table. Click on the paragraph's third wrapped row in the preview column and assert that the outline selects block 1 (FR-013). Use the existing `click()` helper. Find the row's y position from the output shapes rather than hard-coding it.
- [X] T014 [US1] Add a "Preview layout" paragraph under "Synced panes" in `README.md` (VII.1, VI.3): prose wraps to the pane width; tables and code blocks keep their lines whole and scroll sideways on their own; there is no copy button on code blocks, so select and press Ctrl/Cmd+C instead. **Known limitation:** a code block or table inside a list item or block quote is still drawn inline, so the code wraps and the table is squeezed into narrow columns. Nothing is cut off.

**Checkpoint**: US1 is complete. `cargo test` passes and quickstart step 1 works.
It can be merged without US2.

---

## Phase 4: User Story 2 — Hide the source editor (Priority: P2)

**Goal**: An Editor toggle hides the source pane. The rest of the panes fill the
window, the editor's cursor and scroll position survive, and at least one pane
always stays visible.

**Independent Test**: quickstart.md by-hand steps 3 to 5, plus the headless tests
T016 and T022–T024 passing.

### Tests for User Story 2 (write first, must fail)

- [ ] T015 [P] [US2] Move `enum Pane { Outline, Source, Preview }` from `src/main.rs` into `src/panes.rs` as `pub enum Pane`, and import it in `main.rs`. No behaviour change; `cargo test` stays green.
- [ ] T016 [P] [US2] Write unit tests in `#[cfg(test)] mod tests` of `src/panes.rs` for `Panes` (data-model.md). They should fail until T017:
  - the default shows all three panes;
  - `set(Source, false)` returns true and hides it;
  - with only Preview shown, `set(Preview, false)` returns false and changes nothing, and `can_hide(Preview)` is false;
  - each of the 7 non-empty combinations can reach each of the others one `set` at a time, and no sequence reaches all-false.

### Implementation for User Story 2

- [ ] T017 [US2] Implement `#[derive(Clone, Copy, PartialEq, Debug)] pub struct Panes { outline: bool, editor: bool, preview: bool }` in `src/panes.rs`, with `Default` (all true), `is_shown(Pane)`, `can_hide(Pane)`, `set(Pane, bool) -> bool`, and a `shown_count()` helper. Fields are private, so the invariant can only change through `set`. T016 must pass.
- [ ] T018 [US2] Replace `show_outline` and `show_preview` with `panes: Panes` in `MarkdownEditor` in `src/main.rs`, and update every read (`draw`, outline shortcuts gating) to `self.panes.is_shown(…)`. No behaviour change yet.
- [ ] T019 [US2] Rewrite the pane checkboxes in `fn toolbar` in `src/main.rs`: three checkboxes, in the order Outline, Editor, Preview (contracts/ui.md). Each one reads `is_shown` into a local bool, is drawn with `ui.add_enabled(self.panes.can_hide(p) || !shown, egui::Checkbox::new(…))` and `.on_disabled_hover_text("At least one pane must stay visible")`, and on change calls a new `fn set_pane(&mut self, pane, shown, ctx)`.
- [ ] T020 [US2] Implement `fn set_pane` in `src/main.rs`. It calls `self.panes.set`. Hiding the editor runs `ctx.memory_mut(|m| m.surrender_focus(SOURCE_EDIT_ID))` and sets `self.source_target = None`. Hiding the preview sets `self.preview_target = None`, which moves today's `else` branch here. In `fn navigate`, only set `source_target` when the editor is shown and `preview_target` when the preview is shown (research R6), so showing a pane again restores its position rather than jumping.
- [ ] T021 [US2] Give the editor's widgets stable Ids in `src/main.rs`:
  - Add `const SOURCE_EDIT_ID: &str = "source_text";` and use `.id(egui::Id::new(SOURCE_EDIT_ID))` on the `TextEdit` in `fn source_editor`.
  - Use one `id_salt("source")` for the source `ScrollArea` in every layout, which removes `"source_only"`.
  - Use one `id_salt("preview")` for the preview `ScrollArea` in every layout.

  Comment that egui keys the persisted cursor and scroll state by these Ids (research R6).
- [ ] T022 [US2] Extract the content-area layout from `fn draw` into `fn panes_ui(&mut self, ui, ctx)` in `src/main.rs`, implementing the research R7 table:
  - The outline is a left `Panel` when it is shown and anything else is shown. When it is the only pane, `self.outline.ui` fills the area directly.
  - Editor and preview: `ui.columns(2)` as today. Editor only: the source scroll area fills. Preview only: the preview scroll area fills, with its "Preview" heading kept.

  Keep the `take_focus` and `navigate` call between the outline and the other panes. `draw` calls `panes_ui` inside the existing `allocate_ui_with_layout`. Keep the function under cognitive complexity ~25 (IV.4).
- [ ] T023 [US2] Headless test `hiding_editor_keeps_text_dirty_and_cursor` in `mod ui_tests`, `src/main.rs`:
  - Load a 300-line document and mark it dirty.
  - Put the cursor on line 150 by storing a `TextEditState` with a `CCursorRange` through `TextEditState::store` with `SOURCE_EDIT_ID`, and set the source `ScrollArea` offset by clicking or wheeling.
  - Hide the editor with `set_pane(Source, false)` and run 3 frames. Assert that the text, dirty flag and file path are unchanged and that no widget has focus (`ctx.memory(|m| m.focused())` is `None`).
  - Click an outline row while the editor is hidden (it must not move the editor later).
  - Show the editor again and run 3 frames. Assert that `TextEditState::load` returns the same cursor and that the source scroll offset is unchanged (FR-003, FR-004, SC-003).
- [ ] T024 [US2] Headless test `last_visible_pane_cannot_be_hidden` in `src/main.rs`. Hide the outline and the editor, then try to hide the preview through `set_pane`: the preview stays shown. Run one frame and assert the toolbar's Preview checkbox is disabled, by clicking it with the existing `click()` helper and checking that `panes` is unchanged (FR-007).
- [ ] T025 [US2] Headless test `outline_edit_with_editor_hidden_updates_text` in `src/main.rs`. Hide the editor, then trigger an outline promote with the existing outline shortcut `]` on a selected row (as in the shift-click test's setup), and assert that the source text changed accordingly. Also assert that `Ctrl+S` with the editor hidden goes through the same save path, using the built-in chooser test pattern from the existing save tests (FR-005).
- [ ] T026 [US2] Update `README.md` (VII.1): the "Synced panes" or a new "Panes" paragraph names the three toolbar toggles, says one must stay on (the last one is greyed out, with a hover reason), says the editor keeps its cursor and scroll position while hidden, and says visibility is not remembered between runs.

**Checkpoint**: US2 is complete. `cargo test` passes and quickstart steps 3 to 5 work.

---

## Phase 5: Polish & Cross-Cutting

- [ ] T027 Run `cargo test --release -- --ignored preview_timing --nocapture` on the finished branch and add a "Timing — after" table to `specs/002-pane-toggle-preview-wrap/pr-notes.md`, next to T005's numbers. If warm or scroll time regressed, stop and report it. Do not tune silently (VI.2, SC-004).
- [ ] T028 Run the merge gate: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test` (V.2). Fix all findings. Then check every `unwrap` or `expect` added outside tests either is gone or has a comment naming its invariant (V.3).
- [ ] T029 Run quickstart.md by-hand steps 1 to 6 on the local Ubuntu desktop, and record the result in `specs/002-pane-toggle-preview-wrap/pr-notes.md`. **Needs the maintainer**: this is a by-hand check.
- [ ] T030 Run quickstart.md step 7 (all steps over `ssh -X` from another machine) and record it in `pr-notes.md` (II.5). **Needs the maintainer.**
- [ ] T031 Add a "Platforms" section to `specs/002-pane-toggle-preview-wrap/pr-notes.md`: Ubuntu local and `ssh -X` as actually run, and macOS "written for, unverified" (II.4).

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (T001–T002)**: no dependencies.
- **Foundational (T003–T005)**: after Setup. **Blocks both stories**, because the baseline must be measured on unmodified code.
- **US1 (T006–T014)** and **US2 (T015–T026)**: both depend only on Phase 2. They are independent of each other.
- **Polish (T027–T031)**: after the stories being shipped are done.

### Within US1

T006 and T007 come first. T008 needs T006 and T001. T009 needs T008. T010 needs
T009. T011–T013 need T010 and T007, and can be written early to watch them fail.
T014 can be done at any point.

### Within US2

T015 and T016 come first. T017 needs T016. T018 needs T017. T019 and T021 need
T018. T020 needs T019 and T021. T022 needs T018 and T021. T023–T025 need T020
and T022. T026 can be done at any point.

### Shared-file caution

Both stories edit `src/main.rs`. US1 touches `fn preview`, a new `PreviewCache` and
`preview_code_block`. US2 touches the struct fields, `toolbar`, `navigate`,
`source_editor` ids and `draw`'s layout. T021 also changes the preview
`ScrollArea` id_salt that T010's surrounding code uses. If both stories run in
parallel, merge US1 first and rebase US2.

## Parallel Opportunities

- T001 ∥ T002.
- US1: T006 (`preview_blocks.rs`) ∥ T007 (`main.rs` test helper).
- US2: T015 ∥ T016 (both in `panes.rs`, but T015 only adds the enum. Do T015 first if one agent does both).
- Across stories: the whole of US1's `preview_blocks.rs` work (T006, T008) ∥ US2's `panes.rs` work (T016, T017).
- T014 ∥ T026 are both README edits in different sections. Make them sequential if one agent does both.

### Example: starting both stories together

```text
Agent A: T006 → T008            (src/preview_blocks.rs)
Agent B: T015 → T016 → T017     (src/panes.rs)
then main.rs work, serialised: T009 → T010 → T011–T013, then T018 → … → T025
```

## Implementation Strategy

### MVP (US1 only)

1. Phase 1 and Phase 2: dependency, modules, fixture and baseline timing.
2. Phase 3: the reported truncation bug is fixed.
3. Validate with quickstart step 1. Run T027 and T028, then merge.

### Incremental

1. Setup + baseline, then US1, then merge. This fixes the bug that blocks reading.
2. US2, then merge. This adds the reading layout.
3. Polish: timing after the change, `ssh -X` run, platform notes.

## Notes

- Commits are prefixed `markdown-editor:` and explain why (VII.3). Suggested
  commit points are the end of Phase 2, after T010, after T014, after T022 and after T026.
- The known limitation (nested code and tables) was accepted by the maintainer
  on 2026-10-28. It is documented in T014 and is not a task to fix.
- T029 and T030 need a person at a display. An implementing agent stops there
  and reports, and does not mark them done.
