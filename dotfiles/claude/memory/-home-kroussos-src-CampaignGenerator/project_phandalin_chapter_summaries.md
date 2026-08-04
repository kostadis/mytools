---
name: project-phandalin-chapter-summaries
description: "Phandalin's bible is ~5 narrative models layered over each other; provenance is recorded in the repo at Phandalin/docs/chapter_provenance.md. Do not use summaries/<N>/ (fabricated), and do not try to infer scene boundaries."
metadata: 
  node_type: memory
  type: project
  modified: 2026-08-02T18:55:32.890Z
  originSessionId: e3d1726f-81c6-4814-9cb5-54df5b008fcd
---

**Read `~/Phandalin/Phandalin/docs/chapter_provenance.md` first.** It carries
the per-chapter table (model, person, heading shape, word count, 1p/3p
density), the model definitions A–F, known defects, and recording coverage.
Landed via campaigns PR #108. Don't re-derive any of it here.

What that file can't tell you, and this note exists for:

## Two dead ends — do not retry

**1. Inferring scene boundaries.** `scene_map`/`scene_anchor`
(CampaignGenerator PR #227) anchored a derived summary's scene list into
chapter prose. It reported 147/148 anchored (99%); the true figure was **129
distinct boundaries from 148 scenes (87%)** — 18 anchors landed on positions
another scene already held and silently collapsed them, and the `span < 400`
flag structurally could not see a collision because a collision produces no
span. **PR #227 closed as obsolete; `specs/007-scene-anchored-summaries` went
with it and never reached main.** A sharper matcher does not help: across
models B/C/D the summary scenes were never asked to correspond to locatable
prose, so it finds non-existent boundaries more confidently.

**2. Routing extraction to the summary rung.** An earlier version of this note
recommended hand-writing `summary_map` rows for ch1–30 and approving them.
Wrong on two counts: `summaries/<N>/session-summary.md` (the 2026-08-01
numbered batch) is **LLM-generated from the prose with no recording behind
it** — fabricated quotes, novel proper nouns, module-canon backfill — and the
`## Scenes` body is only **26% of the chapter's word count** (14,100 vs
55,036), so routing there trades three quarters of the source for a scene key.
The verified alternative is `summaries/haiku/<NNN>-<slug>/`, produced by the
`chapter-summarise` skill.

## What actually solved it

The GM authored `## CC.SS <POV> <in-world date>` headings directly into the
bible for the model-A chapters — 95 scenes, globally unique, sequence
unbroken. `chunk_by_scenes` reads them with **no code change**. That is the
precision decision the heuristic was approximating, made by a human at the
source.

## Still open

- **kostadis/campaigns#107** — establish recording coverage, then regenerate.
  Blocker: there is no chapter→session mapping anywhere (no
  `<!-- chapter: N | session: … -->` markers, no `session:` frontmatter).
  14 session dirs, 20 VTTs across 13 sessions, audio in Zoom cloud only,
  45 chapters. `old/20260324/` has extraction artifacts but no transcript, so
  the local VTT set is already known incomplete.
- **CampaignGenerator PR #226 is unaffected and still wanted** —
  `compose_summary_scenes` fixes a real H2/H3 defect in the ladder's summary
  rung, and OOTA still uses upstream summaries where that rung is correct.

## Gotchas

- **Chapter numbers shifted 2026-08-02.** A chapter was removed from the 20s
  and everything above moved down one. Any chapter number from before that
  date is suspect.
- **`docs/chapters/` goes stale against the bible.** Run `split_chapters`
  before anything reads a chapter file.
- If extraction ever runs on the `CC.SS` blocks: `--scene-chunks` is opt-in
  and **OFF**, and `scene_index` derives from the *first* pass's `chunk_size`
  (`ensemble_merge.reference_chunking` reads `p0` — the `small` pass at 6000),
  so scene 16.01 at 7204 chars sub-splits and desyncs from its authored id.
  Use a `--plan` YAML with `chunk_size: 12000`.
- Run the suite with `~/.venvs/main/bin/python -m pytest`; a bare `python`
  resolves console scripts to `/usr/bin/` and yields ~40 phantom failures.
  Baseline is **1 failure** (`test_mempalace_client`, environment-dependent).

Related: [[project_ensemble_replaces_claude_extraction]],
[[project_ensemble_grounding_investigation]], [[reference_shared_venv]].
