---
name: Preserve .dedup_state.json across runs
description: When running /dossier-merge, never delete the .dedup_state.json file at the end — it's needed to pin past decisions for future runs
type: feedback
originSessionId: 044d56ee-a230-4e04-88b4-7060e060202a
---
When running `/dossier-merge` (or any dossier dedup workflow), do NOT delete `<dossier-dir>/.dedup_state.json` at the end of the run. Leave it in place.

**Why:** The state file records `clusters_confirmed` (merges already done), `clusters_rejected` (pairs the user said are different NPCs and should never be re-proposed), and `clusters_deferred`. Future `/dossier-merge` runs read this file in Phase 0/2 to skip already-handled clusters and avoid re-asking the user about pairs they've already adjudicated. Deleting it forces the user to re-adjudicate every "keep both" decision on every run.

**How to apply:** When finishing a dossier-merge run, the only artifact to suggest deleting is the backup tarball (once the user confirms they're satisfied). Always preserve `.dedup_state.json` in the dossier directory. If a phase or summary mentions "cleanup", that means tarball only — not the state file.
