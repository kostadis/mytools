# Splitting a catch-all entity into per-instance dossiers

Sometimes a dossier collapses many distinct appearances of a generic entity
(e.g. "orc", "boar", "blight", "bandit") into ONE file, while the campaign
chapters actually track several different individuals/groups across scenes.
The dossier's own `## Uncertainty` often admits this ("no clear identity
linkage", "unknown who this is"). This is the workflow to split it.

## Trigger
The user says something like "there are really many different X that appear
and die in different scenes — can we split X by location/chapter?" The catch-all
dossier's `## Uncertainty` will usually flag the identity problem itself.

## Deliverable choice (ask first)
- **Ledger report only** — one doc: per chapter, list the X group(s), location,
  count, features, fate, plus a "linked individuals" section for X the text
  connects across scenes. Stays in the output dir as analysis.
- **New per-instance dossier files** in the campaign's `state_dossiers/` (or
  `merged_dossiers/`) following the EXISTING naming convention, so they become
  queryable alongside the other dossiers. THIS IS WHAT THE USER USUALLY WANTS
  ("queryable alongside").
- **Both.**
- **Only split the catch-all** — leave already-individualized dossiers alone.

## Steps (per-instance dossier variant)
1. **Inventory existing dossiers for that entity type.** Glob the dossier dir
   for `*<entity>*` (e.g. `*orc*`). Some individuals are ALREADY split out
   (`orc_scout.md`, `orc_with_necklace_of_bones.md`, `six_dead_orcs.md`, …).
   You must NOT overwrite those — treat them as already-handled. The catch-all
   (`monster_orc.md`) is what you are splitting.
2. **Read ALL source chapters** (the authoritative corpus, e.g. ch1–ch46).
   Do NOT rely on the existing dossiers for facts — verify against chapters.
   Search every chapter for the entity term + combat/death/dialogue/sighting.
   For each appearance record: chapter number, scene/location, count,
   distinguishing features (equipment, scars, role, speech, allegiance),
   actions, and fate (killed by whom/how, fled, captured, alive, unknown).

   **Fastest sweep that actually fits in context** (46 chapters ≈ 154k words —
   do NOT read chapters one by one, and do NOT dump them):
   ```bash
   cd <chapters_dir> && grep -in -B1 -A1 'orc' *.md \
     | sed 's/^chapter_\([0-9]*\)_[^:]*/ch\1/' > /tmp/orcctx.txt
   ```
   One command → every mention with ±1 line of context, chapter-labelled, ~1100
   lines for a whole campaign. Then `read_file` it in 3–4 paged chunks of
   330–420 lines. That is the entire evidence base for the split; you only need
   targeted follow-up greps afterwards (named individuals, cross-refs like
   `grep -n 'vorga\|prutha\|drubbak'`).

   **PITFALL — verify grep counts, don't trust a single search path.** In this
   run `search_files(pattern="(?i)orc", output_mode="count")` returned
   `total_count: 0` with a zero for every one of the 46 files, while
   `grep -ic orc *.md` immediately returned 41 non-zero files. A zero/empty
   result on a term you have strong reason to believe is present is a signal to
   re-check with a second method (shell `grep`) before concluding the corpus is
   clean. Never build a split — or an "entity not present" claim — on one
   unverified negative.

   **PITFALL — substring false positives.** A bare case-insensitive `orc` also
   matches `force`, `forced`, `Orcus`, `orchard`, `Orca`, `torch`, `scorch`.
   Several chapters match ONLY on these. Rule them out by eye during the paged
   read and record them in the manifest's Method note, so a later reader knows
   those chapters were checked and genuinely contain nothing.
3. **Cluster into distinct instances.** A distinct instance = an entity the
   text treats as a coherent unit (same scene, same features, same fate) OR is
   explicitly linked across chapters (e.g. "the scout who fled ch19 reappears
   in ch20"). Keep groups scene-bounded unless the text explicitly connects
   them. Aim for defensible clusters — do NOT over-split (don't make 50
   one-creature files) and don't under-split (don't re-dump everything into
   one). For a 46-chapter corpus, ~12–25 distinct dossiers is a good target.
4. **Write NEW dossier files** matching the schema of the existing ones exactly:
   ```
   ---
   name: <short descriptive name>
   type: <monster|npc>
   n_facts: <N>
   chapters: <chapter range e.g. 19-20>
   ---

   ### <name>

   **Current status:** <Alive/Dead/Unknown/Dispersed>
   **Current location:** <...>
   **Allegiance/faction:** <...>
   **Current possessions / notable items:** <...>
   **Current assignment / role:** <...>
   **Defining recent actions:** <...>
   **Revealed motivations or secrets:** <...>

   ## Uncertainty
   - <open question, grounded in what the text does NOT say>
   - <open question 2>
   ```
   - File naming: lowercase, descriptive, collision-free, prefixed to avoid
     clashing with existing files: `orc_ch02_ridge_ambush.md`,
     `orc_ch19_necklace_party.md`, `orc_ch29_spectral_slain.md`,
     `orc_ch40_ridge_ten.md`, `orc_ch43_anchorite_killer.md`.
   - `chapters` field = the ACTUAL chapter range where that instance appears.
   - Cite chapter numbers (chN) in the body facts so they are grounded.
5. **Do NOT modify/delete/overwrite any existing dossier.** Only CREATE new
   files. If the catch-all (`monster_orc.md`) should be retired, say so in the
   manifest — do NOT delete it (per workspace rules, notes are staging and
   human review precedes promotion).
6. **Produce a MANIFEST** (e.g. `orc_split_manifest.md`) listing:
   - Every new dossier: name, chapters, one-line summary, status.
   - A "Mapping" section: which NEW dossier(s) correspond to the appearances
     previously collapsed in the catch-all, and which existing individualized
     dossiers (scout, necklace, raider, six_dead, etc.) correspond to which
     clusters.
   - Any appearances you could NOT confidently assign.
   - "Existing dossier corrections": if an existing same-entity dossier is
     factually wrong vs the chapters (e.g. `orc_scout` marked "Dead" but ch20
     says it escaped), NOTE it here — do NOT edit those files.

## Hard rules
- Read all chapters; verify against source, never against the existing dossier.
- Create-only; never touch existing dossiers (collision = the point).
- **Verify create-only mechanically before reporting.** `git status --short`
  the dossier dir and confirm zero ` M` lines — every write must show as an
  untracked create. Say the verification result in your reply; don't just
  assert "no existing files modified".
- If a `delegate_task` subagent does this, brief it with the existing schema
  sample and the explicit "do not overwrite" + "produce a manifest" steps.
- This generalizes beyond orcs: boars, blights, bandits, anchorites, thugs,
  talosians, etc. — any generic entity the dossiers collapse.

## Writing the files: chunk your tool calls
A 20-dossier split is ~40 KB of new markdown. Writing it in one giant
`execute_code`/`write_file` call **stalls the stream mid-call and the writes
never land**. Keep every tool call under ~8K tokens of arguments: batch **2–3
dossiers per `write_file` turn** (issue them as parallel calls in one turn) and
write the manifest as its own separate call. This session lost a full pass to
one oversized call before re-doing it chunked.

## Cluster types worth carving out (learned from the orc split)
Beyond scene-bounded combat groups, these recur and are worth their own files:
- **Named individuals the catch-all never separated** — a converted follower, a
  contract killer, a warchief. Give each their own dossier with full arc span
  (`chapters: 40-46`), not just their debut scene.
- **A "background pressure" container** for the entity as *reported threat* —
  the dialogue mentions that drive quests, food shortages and council argument
  but never resolve to a fought encounter (Phandalin: farm raids ch02–38).
  Without this, dozens of mentions have nowhere to go and look unassigned.
- **Off-screen / never-confronted occupiers** — an entity group reported to hold
  a location that the party never engages (Falcon's Lodge ch31). Status is
  legitimately `Unknown`; say so rather than inferring a fate.
- **Corpse-state and site clusters** — abandoned quarters, bodies killed by a
  third party. These carry real state (who killed them, what it proves).

## Where the new dossiers LIVE, and how to NAME them (placement iteration)
The deliverable choice (above) assumes the new dossiers go into the campaign
`state_dossiers/` to be queryable. The user may then iterate on placement and
naming — encode the observed sequence so you don't re-ask:

1. **Create** in `state_dossiers/` (collision-free names, matching existing
   convention). Prove create-only via `git status --short` (all `??`, zero ` M`).
2. **Copy** into the analysis output dir (`~/phandalin-output/answers/`) so the
   source tree stays untouched (if the user insists on leaving originals intact).
3. **Remove** the `state_dossiers/` copies once present in `answers/` (plain
   `rm` — untracked, no history impact).
4. **Rename** to follow the ensemble naming, then fix word order if an entity
   word must appear. Orc example this session: created `orc_chNN_*.md` → user
   wanted `monster_` prefix → `monster_chNN_*` → user wanted "orc" in the name →
   `monster_orc_chNN_*`. Leave pre-existing same-entity dossiers
   (`monster_orc_scout.md`, `monster_orc_raider_the_orc_ambush_ch_20.md`) alone —
   they already matched the prefix and are collision-free. Update the manifest's
   filename + path references at each rename step (one-pass regex over the
   manifest: `orc_ch` → `monster_orc_ch`, and bare `orc_regional_*` →
   `monster_orc_regional_*`).

## The manifest is where the analytical value lands
The dossiers are inventory; the manifest is the findings. Beyond the required
sections, this run produced high-value output by adding:
- **Resolutions of the catch-all's own open questions.** `monster_orc.md` asked
  "who killed the Anchorite in ch43 — unknown who this is"; the chapter text
  names the convert doing it. Splitting the entity often *answers* the
  uncertainties that motivated the split — call those out explicitly.
- **Numbered, specific corrections to existing dossiers.** Not "may contain
  errors" — quote the dossier's claim, quote the contradicting chapter line.
  Example: `monster_orc_scout.md` says "Dead" but ch20 says "the scout managed
  to escape into the woods"; it also credits the bear form to the wrong PC and
  invents a bow that appears nowhere in the text. Still never edit those files.
- **Preserved source contradictions.** Where two chapters genuinely disagree
  (who holds a location; a character's gender flipping between chapters), record
  the contradiction in the dossier's `## Uncertainty` rather than silently
  picking one reading. Papering over it destroys the signal the GM needs.
- **An explicit retire recommendation** for the catch-all, justified fact-by-fact
  ("every fact it holds is now carried by a scene-bounded dossier; its status
  field 'Alive (some), Dead (many)' is not usable state"). Recommend, never
  delete.
