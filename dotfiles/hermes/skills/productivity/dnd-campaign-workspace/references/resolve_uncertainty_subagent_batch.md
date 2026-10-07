# Resolving `## Uncertainty` via subagent batching (Phandalin variant)

## When to use this instead of the sidecar-JSON pipeline
- You want **narrative prose answers with chapter citations** in ONE consolidated
  markdown file, not structured sidecar JSON.
- The campaign's dossiers are **simple** (one YAML block per file; header carries
  `name/type/n_facts/chapters`), so no block-stacking gymnastics are needed.
- You have a capable interactive model — subagents *are* the LLM — and you want to
  parallelize across hundreds of dossiers.

This is a SECOND valid deliverable shape alongside the sidecar pipeline
(documented in `references/resolve_uncertainty.md`). Pick by what the user asked:
sidecar JSON for pipeline/mempalace use; consolidated markdown when the user says
"answer the questions and append to a file in ~/some-output".

## Layout facts (Phandalin)
- Dossiers: `docs/ensemble/state_dossiers/*.md` — **327 files, one block each**
  (NOT `merged_dossiers/`, and NOT stacked multi-block files).
- Header: `name:`, `type:` (npc/object/location/monster/faction), `n_facts:`,
  `chapters: <range>`.
- `## Uncertainty` section at the end = the question set (bullets).
- Chapters: `docs/chapters/chapter_NN_*.md`, N = 1..46. The dossier `chapters:`
  range maps **directly** to these NN indices. Unlike the merged_dossiers note in
  the main skill, these filenames are encounter-order-numbered and equal the
  dossier's chapter index (e.g. `chapters: 42-43` → chapter_42_*.md +
  chapter_43_*.md; `9-9` → chapter_09_*.md).

## Recipe (worked, Phandalin, 327 dossiers)
1. **Parse** all dossiers → JSON manifest (file, name, type, chapters, uncertainty
   text). Use `execute_code`/python: regex-split the header `^---\n...\n---\n` and
   capture the `## Uncertainty` block. Save to `OUT/manifest.json`.
2. **Slice** the manifest into ~30-dossier batches → `OUT/batches.json`
   (`batch_01`..`batch_11`). Keep stable dossier order.
3. **Dispatch subagents in WAVES of 3** (see Pitfalls). Each `delegate_task` call
   takes a `tasks` array of ≤3 goals. Each goal: read its batch's dossier files +
   ONLY the cited chapter files (expand the `chapters:` range to `chapter_NN_*.md`),
   resolve each uncertainty bullet with `chN` citations, write `OUT/batch_NN.md`
   using the Q:/A:/Status block format. Do NOT modify dossiers or chapters.
4. **Consolidate** with `scripts/consolidate_uncertainty_batches.py OUT_DIR`
   → merges all `batch_NN.md` in dossier order into `OUT/uncertainty_answers.md`
   with a resolved/partial/unresolved summary header.

## Range expansion (dossier `chapters:` → files)
The field can be `42-43`, `9-9`, or comma lists `1,3,5`. Expand to a set of ints
(`a-b` inclusive; comma-split), map each to `chapter_<NN>_*.md`. In Phandalin the
median range is 2 chapters (157 dossiers are single-chapter), but a few party/
monster dossiers span 40+ (Vukradin `1-45`, Cryovain `2-42`). Prefer reading ONLY
the cited range; let the subagent widen to other chapters only if a question is
unanswered within range. If the text contradicts itself (some dossiers note this),
state the contradiction and take a position from the preponderance of evidence.

## Output format per dossier (in each batch file)
```
## <dossier_filename>: <entity name>  [<type>]
Chapters cited: <list>

Q: <verbatim uncertainty bullet text>
A: <resolution, with chN citations>

(repeat Q/A for each bullet)

Status: [Resolved | Partially resolved | Unresolved]
```

## Pitfalls
- **`delegate_task` concurrency cap = 3.** A single call with all 11 batches fails:
  `Too many tasks: 11 provided, but max_concurrent_children is 3.` Dispatch in
  waves of 3 (4 waves for 11 batches, or 11 waves of 1). This is a STABLE limit of
  the deployment, not a transient error — design the wave loop up front.
- **Do NOT pre-dump all cited chapter text into per-dossier evidence files.**
  With wide ranges this explodes to ~58MB (327 dossiers × full chapter text) for
  nothing. Instead, let each subagent READ the chapter files on demand — it pulls
  only the chapters its dossiers cite. Much cheaper; citation grounding intact.
- **Single-block files here.** Unlike out-of-the-abyss `merged_dossiers`, there is
  exactly ONE block per file. Iterate files, not blocks. The main skill's
  "iterate blocks, not just files" warning is for the merged layout and does NOT
  apply to Phandalin `state_dossiers`.
- **Never modify dossiers or chapters.** Output goes to an external dir
  (e.g. `~/phandalin-output`). The "sidecars never edit" spirit still holds — the
  consolidated markdown is simply the deliverable the user requested.
- **Large `write_file` stalls** (also in main skill): a single write of >~30KB can
  stall the tool stream. Compose the per-batch files in the subagents (each is
  small); the consolidation script assembles the final file in-memory and writes
  it once, which is fine.
- **Cross-check against the chapters.** Pipeline dossiers can contain their own
  errors; flag contradictions and offer to fix the source dossier.