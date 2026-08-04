---
name: project-oota-corpus-remerged
description: OOTA 62-chapter corpus re-merged 2026-07-28 at embed/0.94 with quote_offset+scene_index; all downstream grounding docs are now stale
metadata: 
  node_type: memory
  type: project
  originSessionId: 5da2cfe0-1ee6-495d-b63b-518d214da5c5
  modified: 2026-07-29T02:56:49.221Z
---

On 2026-07-28 the live OOTA corpus at `~/out-of-the-abyss/out-of-the-abyss/docs/ensemble/`
(see [[reference-oota-live-corpus-path]]) was re-merged across all 62 chapters —
embed method, `qwen3-embedding:0.6b` on spark2:11434, threshold 0.94. No
re-extraction; the per-lens JSON was reused. 15,465 → 14,911 facts (−3.6%).

Every fact now carries four fields the previous subject-merged corpus lacked:
`quote_offset`, `scene_index`, `variants`, `subjects`. `scene_index` here is a
**6,000-char chunk index, not a true scene index** — every manifest records the
first pass as `chunk_size: 6000` with no `structural` key. True scene indices
need re-extraction with `--scene-chunks`.

Quote offsets locate on only **62%** of facts corpus-wide (range ~35–75% per
chapter); the gap is chunker-injected headers that aren't in the source `.md`.

**Why:** this landed the fixes from PRs #204–#209 (issues #197/#200/#202) onto the
live corpus, which had silently been getting the subject merge.

**Stages 2d + 2f re-run the same day.** `state_dossiers/` 553 → **517**
(31.9 min, 3.7 s/entity, both Sparks); `merged_dossiers/` → **424** after
`/ensemble-type-merge` (74 merged groups absorbing 93 files, 0 unaccounted).

**Preserving a hand-edit across a dossier rebuild** — the general technique:
delete every *other* `.md` and let `facts_to_state`'s resume-by-skip
(`facts_to_state.py:1278`; there is no `--force`) leave the kept file alone.
A plain re-run is a **no-op** because every dossier already exists. Verified by
md5: `npc_moziqodo.md` survived both stages untouched.

Three traps this run exposed:
1. **Neither stage clears its output dir.** `apply_type_merge.py` does
   `mkdir(exist_ok=True)` and only ever adds — 59 old-named files would have sat
   in `merged_dossiers/` beside their renamed twins, and Stage 3 reads every file
   in there. Back up + clear before applying.
2. **Resume-by-skip never deletes a dossier whose entity stopped existing**, so
   dossier dirs accumulate cruft (`npc_ellen.md` matched only the substring in
   "excellent" and existed in no corpus). Only a clean-slate rebuild sheds it.
3. **`.type_merge_decisions.json` self-heals; don't hand-edit it.**
   `apply_type_merge.py:82` filters members to files that exist, so stale refs
   (72 of 259 here) are inert; renamed entities get a new group key and resurface
   in the scanner for re-decision. Only 4 groups needed review.

Most of the 553→517 churn was the registry canonicalising names
(`npc_alaundo` → `npc_alaundo_the_seer`, `npc_jadgar` → `npc_jadger`) or
location-suffix shifts (`object_the_key_domed_rotunda` → `..._candlekeep`).
A few are re-*attribution* worth GM review (`object_caltrop_gracklstugh` →
`..._lost_tomb_of_khaem`).

**Still stale:** `threads.md`, `world_state.md` (mtime 2026-07-26) — Stage 3.
Backups: `per_chapter.bak-`, `merged.json.bak-`, `state_dossiers.bak-`,
`merged_dossiers.bak-remerge-20260728`.
See [[project-ensemble-grounding-investigation]].
