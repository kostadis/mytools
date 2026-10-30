# Implementation Plan: Hideable Editor Pane and Wrapping Preview

**Branch**: `markdown-editor/002-pane-toggle-preview-wrap` | **Date**: 2026-10-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-pane-toggle-preview-wrap/spec.md`

## Summary

**Preview truncation (P1).** The truncation has one root cause, measured in
[research.md](research.md) R1: egui_commonmark lays out table cells without
wrapping, so a wide table grows the preview's `Ui` past the pane. Every section
drawn after it then wraps at the widened width, so its lines run off the edge.
Paragraphs, URLs and code wrap correctly by themselves.

The fix splits each section body, once per text change, into top-level **prose**,
**table** and **code** chunks using pulldown-cmark, the parser egui_commonmark
already uses:
- Tables are drawn inside their own horizontal scroll area.
- Code blocks are drawn in-house as non-wrapping monospace in their own
  horizontal scroll area (clarification B).
- Prose is drawn by egui_commonmark with wrapping forced, as a safety net
  against tables nested in lists or quotes.

**Hiding the editor (P2).** A pure `Panes` value replaces the two show flags. It
adds an Editor toggle and refuses to hide the last visible pane. The source
`TextEdit` and the scroll areas get stable Ids, so hiding and showing a pane keeps
its cursor and scroll position.

## Technical Context

**Language/Version**: Rust, edition 2024, `rust-version = "1.95"`

**Primary Dependencies**:
- eframe/egui 0.36.2 and egui_commonmark 0.25.0 (existing)
- **pulldown-cmark 0.13.4, newly direct**: already locked as egui_commonmark's
  parser, added with `default-features = false`; justification in research R4

**Storage**: N/A. No on-disk format change. Files are written exactly as before.

**Testing**: `cargo test`. Unit tests next to the code; headless egui tests in
`main.rs` `ui_tests` using the existing `frame`/`click` helpers; one `#[ignore]`d
timing test.

**Target Platform**: Ubuntu LTS (X11, Wayland, `ssh -X`) is primary. macOS is
written for but unverified (II.1).

**Project Type**: Native desktop app, a single binary crate.

**Performance Goals**: Typing, scrolling and preview stay interactive on the
40,000-line baseline. Per-frame preview cost must not regress against the
pre-change timing.

**Constraints**: No change to the source text (III.1); egui UI only; works over
X11 forwarding (II.5).

**Scale/Scope**: About 4 files touched, 2 new small modules, and a README update.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Article | Applies because | Status |
|---|---|---|
| I.1 Native Rust, no web view | New rendering stays in egui | ✅ |
| I.2 Plain text is the product | No sidecar file or hidden state; pane flags are session-only | ✅ |
| II.1 / II.4 Platforms | Shared code only, no platform branch. The PR records "unverified on macOS" | ✅ |
| II.2 Platform code isolated | None added | ✅ |
| II.5 Remote display | Changes a UI surface (toolbar, preview). Quickstart step 7 is the `ssh -X` run, recorded in the PR | ✅ (to be exercised before merge) |
| III.1 Text is sacred | Splitting and wrapping are preview-only. A unit test checks chunk ranges cover the body exactly. SC-005 is a byte-identical save check | ✅ |
| III.3 Failure leaves state intact | Hiding the editor keeps the text, dirty flag and undo. Headless test | ✅ |
| IV.1 Pure core, thin UI | `preview_blocks` and `panes` have no egui dependency | ✅ |
| IV.2 Source is the single truth | `PreviewCache` is derived from the text and rebuilt when it changes | ✅ |
| IV.3 Minimal dependencies | pulldown-cmark justified in R4: already compiled, MIT, portable, no display code | ✅ |
| IV.4 Bounded complexity | Layout dispatch pulled out of `draw` into its own method; chunker is one linear walk | ✅ |
| V.1 Tests | Unit tests for chunker and panes; headless tests for wrap, hide/show and state | ✅ |
| V.2 Merge gate | fmt, clippy `-D warnings`, test; PR records local + `ssh -X` | ✅ |
| V.3 No panics | Chunker fuzz-style inputs in unit tests; no new `unwrap` outside tests | ✅ |
| VI.1 Native conventions | No new shortcuts. Outline shortcuts already apply when the editor lacks focus, and a hidden editor never has focus | ✅ |
| VI.2 Massive documents | Adds cached whole-document work (one parse per edit) and moves two existing per-frame whole-document jobs into that cache. The fixture and timing check are created by this feature, because none exists yet | ✅ with the timing task first |
| VI.3 Known limitations | Nested code and tables: README entry | ✅ |
| VII.1 README | Toggle, one-pane rule, wrapping and limitation | ✅ |
| VII.3 Commits | `markdown-editor:` prefix | ✅ |

**Gate result: PASS.** No violations, and Complexity Tracking is empty.

**Post-design re-check:** the design in data-model.md and contracts/ui.md adds no
crate beyond R4, no platform code and no on-disk state. PASS.

## Project Structure

### Documentation (this feature)

```text
specs/002-pane-toggle-preview-wrap/
├── spec.md
├── plan.md              # this file
├── research.md          # probe results R1–R7
├── data-model.md        # Panes, PreviewChunk, PreviewCache
├── quickstart.md        # automated + by-hand validation
├── contracts/ui.md      # toolbar and preview layout contract
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks (not yet created)
```

### Source Code

```text
markdown-editor/
├── Cargo.toml            # + pulldown-cmark = { version = "0.13.4", default-features = false }
├── README.md             # editor toggle, one-pane rule, preview wrapping, limitation
└── src/
    ├── panes.rs          # NEW, pure: Panes { outline, editor, preview }, set/can_hide + tests
    ├── preview_blocks.rs # NEW, pure: split(body) -> Vec<PreviewChunk> + tests
    ├── main.rs           # Panes replaces show_*; toolbar toggles; layout dispatch;
    │                     # stable TextEdit/ScrollArea ids; focus surrender;
    │                     # PreviewCache; chunked preview drawing; code-block widget;
    │                     # headless tests + legal fixture generator + preview_timing
    └── outline_panel.rs  # only if the outline-fills-area case needs a hook (expected: none)
```

**Structure Decision**: Keep the existing single-crate layout. The two new pure
modules follow the `html_table.rs` / `outline.rs` pattern: core logic, no egui,
tests inline. The UI wiring stays in `main.rs`, where the preview and layout
already live.

## Implementation order (for /speckit-tasks)

1. **Timing baseline first (VI.2).** Add the fixture generator and the `#[ignore]`d
   `preview_timing` test. Run it on the *current* code and record the numbers.
2. **P1:** `preview_blocks` with tests, then `PreviewCache`, then chunked drawing
   (prose with wrap forced, table scroller, code widget), then the headless
   wrap tests from the contract invariants.
3. **P2:** `panes` with tests, then the toolbar, layout dispatch, stable Ids,
   focus and target handling, then the headless hide/show tests.
4. README, `preview_timing` after the change, quickstart by hand locally and over
   `ssh -X`, then `pr-notes.md`.

P1 and P2 touch different parts of `main.rs` and can be built and merged in
either order.

## Complexity Tracking

No constitution violations. Nothing to justify.
