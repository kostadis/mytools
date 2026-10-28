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
