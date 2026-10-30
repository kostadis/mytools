# PR Notes: Hideable Editor Pane and Wrapping Preview

## Timing (constitution VI.2)

Fixture: `legal_fixture()` in `src/main.rs` `ui_tests`, which generates 40,062 lines and 7.2 MB.
Command: `cargo test --release -- --ignored preview_timing --nocapture`.
The test is headless: one 1200×800 frame with all three panes shown.
Machine: AMD Ryzen 9 5900XT (16 cores, x86_64), Ubuntu, local (no `ssh -X`).

### Timing — before (base `cc700fa`, preview and layout code unmodified)

| Run | Cold first frame | Warm frame (median of 30) | Scrolling frame (median of 30) |
|---|---|---|---|
| 1 | 3446 ms | 336 ms | 336 ms |
| 2 | 3402 ms | 330 ms | 331 ms |

At about 330 ms per steady frame, the editor is already far from interactive at the
baseline size, before this change. This confirms the "unmeasured at
ratification" suspects in VI.2. That is pre-existing and out of this feature's scope.
This feature's obligation is not to make it worse.

### Timing — after US1 (preview wrapping)

| Run | Cold | Warm | Scrolling |
|---|---|---|---|
| 1 | 3491 ms | 284 ms | 280 ms |
| 2 | 3580 ms | 302 ms | 305 ms |

The first US1 build *regressed* warm frames to about 386 ms (+15%). Two experiments
located the cost, each worth about 40 ms:
- **(A)** Every chunk was given the document's full set of link definitions,
  formatted and re-parsed every frame. There are now more chunks than sections.
- **(B)** Each top-level table now has its own horizontal scroll area, about
  280 in the fixture.

Fixing (A): the per-edit cache now builds each chunk's Markdown once, with
only the definitions that chunk references (`preview_blocks::with_used_links`,
unit-tested). That more than pays for (B), so warm frames end about 10–15%
*faster* than before. (B) is the price of FR-010 and the table scrolling, and is kept.

Deviation from tasks.md T009: the cache field is `preview_sections` (the name
`preview_blocks` is taken by the module), and it stores each chunk's drawable
Markdown rather than a body plus a shared `links` string.

### Timing — after (US1 + US2, `a11e42c`)

| Run | Cold | Warm | Scrolling |
|---|---|---|---|
| 1 | 3450 ms | 281 ms | 282 ms |
| 2 | 3399 ms | 281 ms | 283 ms |

**No regression:** steady and scrolling frames are about 15% faster than the
baseline (330–336 ms → 281 ms). The cold first frame is unchanged, within noise. This
is still nowhere near interactive at 40k lines. Getting there needs a
virtualised preview and source pane (VI.2), which this feature does not attempt.

## Merge gate (V.2)

- `cargo fmt --check`: pass
- `cargo clippy --all-targets -- -D warnings`: pass
- `cargo test`: 82 passed, 1 ignored (`preview_timing`)
- V.3 audit: every `unwrap`/`expect` added by this branch is in test code. Preview
  slicing uses pulldown-cmark offsets, which fall on character boundaries. A unit
  test covers multi-byte text at chunk edges.

## Tests that guard the fixes

- `preview_wraps_after_wide_table`, `preview_code_and_url_stay_in_pane` and
  `preview_click_on_wrapped_line_selects_section` all fail with the old
  rendering restored. Checked by temporarily reverting `preview_chunk`.
- `hiding_editor_keeps_text_dirty_and_cursor` fails without the fixed-id pane
  scopes: hiding the preview reset the editor's scroll position from 2000 to 0.

## Behaviour differences a reader might not expect

- With the preview hidden, the source pane now shows its "Markdown" heading,
  as it does in the two-column layout. Before, it had none.
- Code blocks in the preview have no copy icon. Select the text and press Ctrl/Cmd+C.
- Toggling the preview no longer resets the editor's scroll position, and
  vice versa.

## Manual checks (maintainer, 2026-10-30)

- [x] quickstart.md steps 1–6 on the local Ubuntu desktop (T029): pass
- [x] quickstart.md step 7, all steps over `ssh -X` from another machine (T030, II.5): pass

## Platforms (II.4)

- Ubuntu, local: automated tests, headless timing run and the by-hand run.
- Ubuntu over `ssh -X`: by-hand run passed.
- macOS: written for, **unverified**. There is no platform-specific code; everything
  is shared egui code.
