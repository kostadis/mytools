# Source-selection pilot status

## Successful retry after the permission reset

Both pilot PDFs are now readable. A fresh scan and inspection completed with two inspected sources, zero failures, and zero coverage errors. The files are exact byte duplicates; the exported list retains `193137-Feats.pdf` and records one duplicate, one selected work, and one queue entry. No model calls or PDF conversions ran.

The share's filesystem identity changed after the reset, so the selector correctly refused to reuse the earlier state. New private state is under `/tmp/dmsguild-source-pilot-reset.J3jX4R`; `exports/current.json` points to the resulting generation. Earlier state was preserved.

This small pilot uses the individual product folder as its root. Its queue is diagnostic: it does not establish that this previously converted DM's Guild book needs conversion. Full-library baseline handling must use the expected publisher/product hierarchy and preserve the existing outputs. Issue #144 remains open for the broader reviewed list.

## Earlier attempts

After the user remounted the VirtualBox Google Drive share, the access-check script could read the PDF header of `193137-Feats.pdf` in `DriveThru/Dungeon Masters Guild/10 New Feats for 5th Edition D&D`.

The Rust implementation was restored from the committed `codex/rpg-source-selection` branch into this workspace and rebuilt successfully. Its earlier `/tmp` checkout and executable were no longer available.

Running `scripts/run_source_selection_pilot.sh` produced:

- Two PDFs inventoried as one candidate group, with no inventory errors.
- One source inspected successfully (1,725,885 input bytes).
- One source still unreadable: `193137-Feats.old-001.pdf` returned `Permission denied`.
- One unresolved review group, zero selections, and zero conversion queue entries.
- No model calls, duplicate rulings, or chronology assumptions.

Inspection exited 1 because one source was unreadable. Export still succeeded and recorded the failure. Private state and exports are under `/tmp/dmsguild-source-pilot`; `exports/current.json` identifies the current generation. That directory is temporary and may not survive cleanup or a restart.

This confirms that the current PDF can be read and inspected. It does not establish that both versions are equivalent, that the `.old` copy is older, or that the entire downloaded folder is readable. Neither source PDFs nor existing conversion outputs were modified. Issue #144 remains open for the broader reviewed-list pilot.

The earlier pilot of six Empire Builder Kit — Street & Road Names PDFs could not read any source before the remount. Its original report remains in the committed implementation branch. Representative ambiguous versions, cross-folder duplicates, distinct bundle works, and text-bearing play aids still need content-level validation.
