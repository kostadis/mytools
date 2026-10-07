---
name: dnd-campaign-workspace
description: Navigate and work inside CampaignGenerator + mempalace D&D 5e campaign repos (e.g. ~/src/campaigns). Covers directory layout, the merged_dossiers schema, the canonical `## Uncertainty` open-questions artifact, mempalace mining order, and per-campaign commit isolation. Load when the user points you at a campaign directory, asks to list/inspect campaign docs, mine the palace, prep a session, or resolve open lore questions.
---

# D&D Campaign Workspace

The user maintains several D&D 5e campaign repos managed with the
**CampaignGenerator** toolkit and a **mempalace** semantic-search palace.
Canonical layout and hard rules live in the repo-root `CLAUDE.md` and each
campaign's own `CLAUDE.md` — read those first for campaign-specific detail.
This skill captures the *workflow* and the non-obvious *schema facts* that
aren't obvious until you actually open a file. Do not duplicate the CLAUDE.md
content here; link to it.

## When this applies
- Path is under `~/src/campaigns/*` (or `~/campaigns/*`), or the request
  references `CampaignGenerator`, `mempalace`, `prep.py`, `distill.py`,
  `party.py`, `split_chapters.py`.
- User asks to list/inspect campaign docs, mine the palace, prep a session,
  or resolve contradictory / unspecified lore.

## Phandalin module corpus (docs/background/ + published spine)
`Phandalin/` keeps its adventure *source modules* as separate files in
`docs/background/` (NOT one big file like `obelisk.md`), and the narrative bible
split is at `docs/chapters/` (there is no top-level `chapters/` dir). The four
Essentials Kit books in `docs/background/` form a verifiable published spine
(Dragon of Icespire Peak → Storm Lord's Wrath → Sleeping Dragon's Wake → Divine
Contention), with homebrew overlays (Lost Mine of Phandelver + the Carver, War of
the Giants, War of the Dragons, Neverwinter/KP). Full file list, spine table,
overlay mapping, and the hand-authored-vs-generated docs convention are in
`references/phandalin_module_corpus.md` — read it before any chronology /
lore-map / faction-from-adventure task in Phandalin.

## Module-source corpus repos (e.g. `obelisk/`) — a SEPARATE layout
Some campaign repos do NOT use CampaignGenerator/mempalace. The `obelisk/`
repo adapts a published module whose full text is ONE big markdown file
(`docs/background/obelisk.md`, 6,078 lines); outputs are hand-curated
`.md` in `docs/background/`. No `merged_dossiers/`, no `mempalace.yaml`.
When the user asks you to NAME / ENRICH / RECLASSIFY monsters or NPCs across
such a module, follow the multi-agent corpus pipeline below. The canonical
phase deliverable rule (Kostadis, out-of-band) is: **one markdown file per
phase in `docs/background/`** (e.g. `monsters_phase1_scan.md`,
`monsters_phase2_descriptions.md`, `monsters_phase3_hierarchy.md`,
`monsters_cr_reference.md`).

### Authoritative files to read FIRST (skip or you will re-name existing canon)
- `docs/background/obelisk.md` — full module text (source of truth).
- `docs/background/name_glossary.md` — **campaign canon**: pre-existing named
  NPCs/creatures + Kostadis rulings ("Greska the orc" → Grista the dwarf is a
  module typo; module "Pip" Stonehill → campaign rename Tuck).
- `docs/background/obelisk-inventory.md` — **staging inventory** from a prior
  parallel-LLM chunk pass (NPCs, creatures, factions, locations).
These already NAME most plot creatures. A new naming pass MUST consult them
or it will re-name Klarg, Ruxithid, Brughor, Agatha, etc.

### The user-designed multi-agent pattern (for big corpus passes)
1. **Phase 1 — scan (delegate to parallel subagents).** Split the module by
   chapter ranges; spawn 2–3 scanner agents in ONE `delegate_task` call
   (`tasks` array) running in parallel. Each writes a `_scan_A.md` / `_scan_B.md`
   / `_scan_C.md` partial. Give each agent: exact line range, monster types to
   include, the EXISTING authoritative name lists (so it skips already-named
   creatures), grouping rules, and exact output schema.
2. **Main agent merges** the partials into one scan file — cross-chapter dedup
   happens here (same tribe in ch1 and ch3 = one entry; list each area + count).
   Subagents can't see each other's output, so they CANNOT dedup — the merge is
   non-delegable.
3. **Phase 2 — enrich (delegate one describer agent).** Feed it the merged
   scan; it assigns tribe names, individual names, distinguishing features,
   descriptions. Keep mechanical creation out of the main loop.
4. **Phase 3 — relational/judgment synthesis (main agent, NOT delegated).** The
   user kept the hierarchy/boss-tier logic in the main agent because it needs
   judgment (CR thresholds) + a single coherent worldview. Build the CR table
   yourself (5e Monster Manual + module Appendix A) and apply the tier rule.

### Boss-tier rule (user-specified)
Given tribe A and boss B: gap = CR(B) − CR(rank-and-file of A).
- gap **< 4** → **nominal boss** (leader in name only, small threat jump).
- gap **> 4** → **hard boss** (genuinely more dangerous than the rank-and-file).
If a tribe has multiple unnamed tiers (e.g. psi brawlers CR 1/4, psi commanders
CR 1/2), use the HIGHEST rank-and-file CR for the conservative (smallest-gap)
comparison and note the range.

### PITFALL — `search_files` regex in this workspace
`search_files` here does NOT honor `^` line anchors or `\\d` char classes
reliably: `^# Chapter \\d+:` → 0 matches (silent failure); literal `# Chapter 2:`
→ matches. Workaround: search the literal heading string, or `outcome_mode=content`
and grep by hand. Don't waste turns on anchored/class regexes.

### PITFALL — `search_files` COUNT mode also returns false zeros
Independent of the regex bug above, `search_files` with `output_mode=count`
reported `0` for "bandit" across every chapter file *even though the text
contained the word* (verified by reading the files). Do NOT use `search_files`
count mode to decide whether a term appears. For reliable frequency + candidate
discovery across all chapters, use a `terminal` loop:
```bash
cd /home/kostadis/src/campaigns/Phandalin/docs/chapters
for f in chapter_*.md; do n=$(grep -ioE '\b(bandit|brigand|thug|enforcer)\b' "$f" | wc -l); [ "$n" -gt 0 ] && echo "$n  $f"; done
```
Then read the candidate chapters' actual text to confirm, not just grep hits.

## Splitting a generic-monster catch-all into per-chapter dossiers
Recurring Phandalin task: the user has a catch-all (`monster_thugs.md`,
`monster_orcs.md`, …) and wants one dossier per chapter that contains the
encounter, written to `~/phandalin-output/answers/monster_<type>_chNN.md` plus a
`~/phandalin-output/<type>_split_manifest.md`. Full method, grain rule, exclusion
table, dossier schema, and pitfalls are in
`references/split_generic_monster_dossiers.md` (read it before running this kind
of task). Key points:
- **GRAIN: coarse — exactly one dossier per chapter, NOT per individual fate.**
  A prior thug pass over-split into ~20 individual-fate files (`_beheaded`,
  `_net_thrower`, …) and the user deleted them. One file per chapter, always.
- **Verify from source, not the catch-all's `chapters:` range.** Grep-sweep all
  chapters for role synonyms, then READ each candidate to confirm it is a genuine
  generic-enforcer *combat* encounter (not a passing mention or retrospective
  reference to an already-named NPC like Corbin).
- **Exclusions:** orcs and ogres go to their own dossiers; named lieutenants
  (Borg, Jax, Sylvine, the Carver, Sister Kaella/Kayla) are NPCs; named captives
  that become NPCs (Skippy → npc_skippy, the ch4 spare → npc_corbin) are flagged,
  not duplicated.
- **Do NOT edit the catch-all.** Record its errors (scope too narrow, unsupported
  "loyalty" allegiance, wrong possessions — e.g. ch33 explicitly gives a thug a
  net) in the manifest's "Existing-dossier correction" section and offer to fix.
- The `search_files` count-mode false-zero above is the trap that bites this task
  first; use the `terminal` grep loop instead.

### Chapter line boundaries (obelisk.md, verified)
Ch1 `A Dangerous Journey` L235; Ch2 `Trouble in Phandalin` L552; Ch3 `The
Spider's Web` L1146; Ch4 `Wave Echo Cave` L1747; Ch5 `Paths of Peril` L2140;
Ch6 `The Shattered Obelisk` L2919; Ch7 `Rifts in Reality` L4080; Ch8 `Beyond a
Lightless Star` L4943; end L6078. (Re-derive with literal `# Chapter N:`
searches if the file changes.)

### Scanner output schema (per group)
```
## [Monster type] — [existing tribe label]
- Chapters: ch1, ch2
- Areas & counts: H2 (2 goblins + 1 goblin boss, line 390); H3 (1d4 goblins on alarm, line 407)
- Total unnamed count (as written): ...
- Module descriptors: ...
- Named leader already in module? yes/no — [name]
- Notes: ...
```

## Directory orientation (per campaign)
- `docs/` — grounding docs (`campaign_state`, `world_state`, `planning`,
  `party`) + `chapters/` (narrative wing: per-chapter bible splits),
  `distill_extractions/` (chronicle wing), `npcs/`, `ensemble/`, plus
  campaign-specific sets (e.g. `gauntlgrym/`).
- `docs/ensemble/merged_dossiers/` — **merged entity dossiers**, one `.md`
  per entity, filename prefixed by type: `npc_`, `location_`, `faction_`,
  `object_`, `monster_`.
- `summaries/` — raw session data by date (`YYYYMMDD/`, VTT transcripts).
- `voice/`, `notes/`, `examples/`, `logs/` — excluded from palace mining.
- `mempalace.yaml`, `.mempalaceignore`, `.mcp.json` — palace + MCP config.
- `docs/chapters/` holds `chapter_01..NN.md` (bible split by encounter
  order, NOT by source heading number; decimal sub-chapters become
  whole-numbered output files).

## merged_dossiers schema (NON-OBVIOUS — discovered this session)
- **Filename type prefix ≠ the only entity type inside the file.** A single
  `*.md` can **stack multiple merged blocks** for the same entity under
  different types. Each block has its own YAML frontmatter (`---` … `---`)
  and a `<!-- source: <original>.md -->` comment divider. Example:
  `faction_the_ember_vanguard.md` contains faction + monster + object blocks,
  each with its own facts and its own uncertainty list. So block count >
  file count. When counting or aggregating, iterate blocks, not just files.
- **Every dossier carries a `## Uncertainty` section** — a heading followed
  by `- ` bullet open questions about contradictions, unspecified facts, or
  ambiguous phrasing in the source. This is the canonical **open-questions
  artifact** and is present in ~100% of dossiers (300/300 files, 390 blocks
  in out-of-the-abyss). Use it as the source of truth for "what's unresolved"
  when prepping a session or auditing canon.
- To aggregate all open questions across a campaign:
  `bash scripts/extract_uncertainties.sh <merged_dossiers_dir>`
  (scoped awk that captures only bullets inside `## Uncertainty` blocks).

## mempalace mining (ORDER MATTERS)
Subdir wings BEFORE root, every time: **chronicle → narrative → abyss**.
Root mining excludes subdirs via `.mempalaceignore` to avoid double-mining.
Embedding runs on **CPU** (`onnxruntime`) — do not swap to a GPU build
(the `onnxruntime-gpu` wants CUDA 12 libs that conflict with torch's CUDA 13).

## Hard rules (from campaign CLAUDE.md)
- **One campaign per commit / PR.** Never bundle changes from multiple
  campaign dirs. Run `git status` and check directory prefixes before
  committing. Only root-level shared infra (root `CLAUDE.md`,
  `MEMPALACE_HOWTO.md`, root `.gitignore`) may ship in a cross-cutting commit.
- `.mempalaceignore` filename rule is fragile: it references
  `docs/TheUnderdark.md` (NO space). If anyone reverts the space, the bible
  re-mines into the abyss wing and pollutes every search.
- `split_chapters.py` **wipes `docs/chapters/mempalace.yaml`**. Restore from
  git before re-mining: `git show HEAD:out-of-the-abyss/docs/chapters/mempalace.yaml > docs/chapters/mempalace.yaml`.
- Trust hierarchy: session summaries / VTT transcripts = **authoritative**;
  `distill_extractions/` = search accelerator (narrow window, then verify);
  grounding docs (`world_state.md`, `planning.md`, NPC dossiers) = working
  reference. Verify against authoritative when precision matters.
- Voice files are **authoritative** for character speech/personality; read
  the voice file before writing a character's dialogue. Players are the
  ultimate authority on their PCs' psychology.

## Canonical references (read these, don't mirror them)
- Repo-root `CLAUDE.md` (campaign isolation rule, shared architecture,
  CampaignGenerator + mempalace command reference).
- Each campaign `CLAUDE.md` (e.g. `out-of-the-abyss/CLAUDE.md`) for
  campaign-specific gotchas, MCP tools, and re-mine workflows.
- `MEMPALACE.md` / `MEMPALACE_HORIZON.md` inside a campaign for palace usage
  and the current horizon marker.

## Resolving `## Uncertainty` blocks (open lore questions)
When the user wants the open questions actually ANSWERED (not just listed),
use the resolve_uncertainty agent. Full detail, the canonical implementation
paths, and the non-obvious pitfalls are in `references/resolve_uncertainty.md`
(read it before building or running). Key points: parse into merged blocks →
retrieve evidence from `docs/chapters/` **scoped to the block's `chapters:`
range + explicit `(chNN)` refs** → form a cited opinion per question.

**Hard deliverable rule: sidecars, never dossier edits.** Answers go in a
`<entity>.answers.json` sidecar next to the dossier; the dossier stays
byte-identical. A separate `*.resolved.md` is an optional render built FROM
the sidecar. For a single entity run
`docs/ensemble/resolve_uncertainty.py merged_dossiers/<file>.md` (scaffold-only
if no LLM; supply `--base-url <openai-compat>/v1 --model <name>` to LLM-fill).
For all 300 use `docs/ensemble/orchestrate_batch.py --scaffold --fill
--workers 8` (resumable; re-run skips filled). The 28 dossiers whose
uncertainty is literally `None.` need `--none-pass` to get a sidecar.

No LLM backend in the env? Run the script with no `--base-url`: it writes the
sidecar scaffold (evidence retrieved, `opinion: null`). A human or the live
agent then fills `opinion` (never fabricate an API call). Cross-check opinions
against the chapters — **pipeline dossiers can contain their own errors**
(e.g. Zuggtmoy npc block wrongly claims Zalthir is infected; ch50 proves he
is not) — flag and offer to fix the source.

## Resolving `## Uncertainty` via subagent batching (narrative markdown deliverable)
When the user wants prose answers with chapter citations in ONE consolidated
file (e.g. "answer the questions and append to a file in ~/some-output"), use a
subagent-batch variant rather than the sidecar-JSON pipeline. Full recipe, batch
dispatch prompt shape, range expansion, and pitfalls are in
`references/resolve_uncertainty_subagent_batch.md`. Key points:
- **Layout:** Phandalin `docs/ensemble/state_dossiers/*.md` are 327 SIMPLE
  one-block-per-file dossiers (header `name/type/n_facts/chapters` + `## Uncertainty`).
  This is NOT the `merged_dossiers` stacked-block layout — iterate files, not blocks.
- **Batch:** parse to a manifest, slice into ~30-dossier batches (`batches.json`),
  dispatch one subagent per batch that reads ONLY the cited `chapter_NN_*.md` files
  and writes `batch_NN.md` (Q:/A:/Status blocks).
- **`delegate_task` concurrency cap = 3.** A single call with all batches fails
  ("Too many tasks ... max_concurrent_children is 3"). Dispatch in WAVES of 3.
- **Do NOT pre-dump all cited chapters into per-dossier evidence files** — wide
  ranges explode to ~58MB for nothing. Let subagents read chapters on demand.
- Merge with `scripts/consolidate_uncertainty_batches.py OUT_DIR`.
- Never modify dossiers/chapters; output goes to an external dir.

- **Lightweight single-agent alternative (one batch / small corpus).** When the deliverable is a SINGLE `batch_NN.md` (not all batches at once), you do NOT need subagents or `delegate_task`. From one `execute_code` call, load **every** `chapter_NN_*.md` in `docs/chapters/` into a dict keyed by chapter number — not just the cited ranges — then define search helpers and run targeted searches per dossier. This keeps all chapters resident across calls and is far cheaper than re-reading files per question. Used successfully for batch_03 (30 dossiers) and batch_02 (30 dossiers). Reuse snippets:
  ```python
  import os, re
  cd = "/home/kostadis/src/campaigns/Phandalin/docs/chapters/"
  ch = {int(re.search(r'chapter_(\d+)_', f).group(1)): open(cd+f).read()
        for f in os.listdir(cd) if f.startswith('chapter_') and f.endswith('.md')}
  # single term across a list of chapter numbers
  def find(term, nums, ctx=250, maxn=3):
      for n in nums:
          for m in re.finditer(term, ch[n], re.I):
              s, e = max(0, m.start()-ctx), min(len(ch[n]), m.end()+ctx)
              yield n, ch[n][s:e]
  # MULTI-TERM across a CHAPTER RANGE — better when each dossier has its own
  # keyword set; returns first max_per hits per (chapter, term) keyed dict
  def search_range(nmin, nmax, terms, context=1, max_per=3):
      out = {}
      for n in range(nmin, nmax+1):
          if n not in ch: continue
          lines = ch[n].split("\n")
          for i, line in enumerate(lines):
              for t in terms:
                  if t.lower() in line.lower():
                      out.setdefault(f"ch{n}:{t}", []).append(
                          "\n".join(lines[max(0,i-context):min(len(lines),i+context+1)]))
                      break
      return out
  ```
  The whole Phandalin bible is ~890KB and loads into one dict fine; the dict persists across `execute_code` calls in the session, so load once at the top and reuse. Total chapter count for Phandalin batch_02 = 47 files.

- **PITFALL — one giant extraction call gets stdout-truncated.** Loading the dict once is right, but if you then `print` keyword windows for ~10 chapters in a SINGLE `execute_code` call, the harness caps stdout (observed: "~74,000 bytes omitted" on a combined ch9/41/44/39/42/38/30/31/10/16 pass). Either (a) keep each call to a FEW chapters with narrow windows (pad≈120, a handful of terms), or (b) accumulate results into a Python list/dict and print a compact per-dossier summary rather than raw window dumps. Multiple small calls beat one fat call — the context you save is your own.
- **Explicit output-path single batch.** When the user says "resolve batch_NN and write `<path>/batch_NN.md`", do NOT route through `consolidate_uncertainty_batches.py` (that's for the subagent-batch variant). Write the consolidated markdown directly to the named path using the batch_NN shape: one `## <file>.md: <name> [type]` heading per dossier, a `Chapters cited:` line, then `Q:`/`A:` blocks for each `## Uncertainty` bullet, and `Status: Resolved` (or `Resolved (no open questions)` for `None.`) at the end of each. Finish with a campaign-wide summary (dossiers processed, fully-resolved count, list of `None.` dossiers). This is exactly what batch_01.md used and it matches the shape `consolidate_uncertainty_batches.py` expects, so the two variants stay interop-mergeable.

- **PITFALL — cited `chapters:` range can be SILENT, but the answer exists LATER. Do not declare a dossier unresolved too early.** A dossier's header range (e.g. `12-33`) may describe the entity's *state* without ever stating its *fate*; the resolution often lands in a later chapter where the arc concludes. Because all chapters are resident in the single-agent approach, scan FORWARD past the cited range when the range is silent. Confirmed example from batch_02: `location_clearing.md` cites ch12-33 and is silent on the corrupted Treant's outcome, but ch38 (outside the range) states the party *killed* the metastasized treant — so the resolution is ch38, flagged as a cross-range citation. Other batch_02 dossiers were resolvable within range (e.g. `falcon_s_hunting_lodge.md` ch17-45; `dragonbarrow.md` ch31-38). Rule: answer from the cited range first; if silent, scan forward to the next chapter that plausibly concludes the entity's arc, and mark the citation as outside the dossier's stated range.

- **PITFALL — dossier header field is `name:`, NOT `title:`.** State_dossiers blocks use YAML `name: <Entity>` / `type:` / `n_facts:` / `chapters:`. A `title:` regex matches **nothing** (returns `?`); use `name:`. The merge into the output should use `name:` for the heading, not a `title:` guess.

- **Batch-processing tip.** In batch_03, 13/30 and again in batch_02, 13/30 dossiers had an empty/`None.` `## Uncertainty` section. Skip retrieval work for those, but still emit a one-line `Resolved (no open questions)` entry (with the entity `name:`) so the consolidated file stays complete. The consolidated batch_02 output used this shape: one `## <file>.md: <name> [type]` heading per dossier, a `Chapters cited:` line, then `Status: Resolved` for `None.` dossiers and Q/A/Status blocks for the rest, ending with a campaign-wide summary (dossiers processed, fully-resolved vs partially-unresolved counts, and the list of `None.` dossiers). Reuse that shape for consistency with `consolidate_uncertainty_batches.py`.

- **PITFALL — cited `chapters:` ranges can span DISTINCT entities.** A dossier's header range may point at more than one structure. Example: `location_tower.md` cites ch8 (the **Tower of Storms** — sea-cliff, harpies, Moesko the Orc Anchorite) AND ch36 (the mountain **Icespire Hold** — Cryovain + the Carver's "body-snatching alien intelligence"). Its "is the harpy nest still present?" question is misfiled against ch36; the harpies belong to ch8. Always confirm the cited chapters actually describe the SAME entity before answering, and call out conflations explicitly in the output. (Extends the earlier warning that dossiers can contain their own errors — here the error is a wrong chapter→entity mapping, not just a factual slip.)

- **PITFALL — the dossier's own `Current status:` header line can be WRONG (not just the uncertainty bullets).** The `## Uncertainty` questions sometimes restate a status the cited chapter directly contradicts. Confirmed in batch_05: `monster_orc_scout.md` asserts "Dead" but ch20 states the scout "managed to escape into the woods" → alive; `monster_thugs.md` says "one escaped" but ch33 has Brewbarry "felled" the last fleeing thug → none escaped; `monster_unnatural_creature.md` says "Alive" but ch4 has Soma "finishes it off … is no more" → dead. When a header status contradicts the chapter, RESOLVE in favor of the chapter and explicitly correct the dossier status (e.g. "corrects dossier 'Dead' — ch20 shows it escaped"), then offer to fix the source. This is a sharper instance of "pipeline dossiers can contain their own errors" — the error is in the status field, not just a reasoning slip.

- **PITFALL — one dossier name can span MULTIPLE distinct groups/incarnations across its range.** Don't force a single identity. Example from batch_05: `monster_ogre.md` (ch2–30) actually covers (a) the ch2/ch3 solitary ogres — confirmed distinct because ch2's halberd *missed* and the bard fled (no death recorded), while ch3's ogre is finished by Vukradin — and (b) the ch29/ch30 ogres identified in ch30 as "a tribe previously allied with … the Carver," a separate group linked to each other by ch29's "recognized the party as those who had killed their tribesmen." Likewise `monster_orcs.md` spans ch19 raiders → ch40 ridge orcs → ch45 converted orcs. Resolve per-group and only link groups the TEXT links. Extends the earlier "distinct entities" warning: there it was a wrong chapter→entity mapping within one range; here it's same-name, multiple incarnations over time.

- **PITFALL — the cited `chapters:` figure may be ENTIRELY ABSENT from the cited chapter text.** A dossier can cite a chapter that simply does not contain the referenced person/thing. Confirmed in batch_06: `npc_anchorite_half_orc.md` cites ch21 (The Spiral's Grasp), but ch21 as retrieved contains only a Talosian orc raiding party and a drow among them — there is NO "half-orc anchorite claiming 'their forest.'" The dossier's facts (self-identified Talos cleric; warned the party to leave "their forest") cannot be grounded in the cited text. Don't manufacture an answer from adjacent chapters — mark it `Unresolved` and explicitly note that the cited chapter lacks the referenced figure (the dossier/source may itself be mis-filed or generated against a different chapter version). This is sharper than the "wrong chapter→entity mapping" pitfall: there, the entity existed but at the wrong chapter; here, it exists nowhere in the cited range.

- **PITFALL — `## Uncertainty` "contradiction" bullets often dissolve into SAME-NAME / SAME-TYPE DISTINCT entities.** Before declaring a genuine in-world contradiction, verify the two sides are actually the same entity — they frequently are not. batch_06 examples:
  - `npc_anchorites_of_talos.md`: the "ch40 killed by Brewbarry's halberd vs ch44 killed by Valphine's Doom Sphere" is NOT a contradiction — ch40 is the Circle-of-Thunder anchorite, ch44 is the boar-shapeshifting Woodland-Manse anchorite. Two different people. The gender "she" (ch40) vs "he" (ch44) attaches to separate characters, not one inconsistent one.
  - `npc_corrin.md`: the "tall and short" conflict is a misread — "a tall man in a coat" (ch44:9) is Rimardo; Corrin is separately described as "a short, silent performer" (ch44:245). Two performers, not one contradictory body.
  - `npc_drow.md`: ch2–4 "the drow" = Valphine (party PC, cleric of Lathander); ch21 "a drow among them" = a separate, unnamed enemy with the Talosian orcs. No continuity.
  - `npc_elara.md`: the "Corbin's deceased wife (ch05) vs alive & married to Jarek (ch07)" conflict is spurious — ch5's windmill woman is Adabra (chapter "saving_adabra"), and the "Elara = Corbin's wife" claim does not appear in the retrieved ch5 text; ch7 Elara is a living merchant traveling with Jarek. Two different characters. Rule: when a contradiction bullet hinges on identity, check the actual citations before assuming the world is inconsistent.

- **PITFALL — verify quoted phrases / specific claims actually APPEAR in the cited chapters.** A dossier's uncertainty bullet may reference a quote or a specific claim that the cited chapter text does not contain (a dossier-generation artifact, not a real source). When a bullet hinges on such a phrase, search the cited chapters for the exact wording; if absent, flag it as a likely dossier error and answer only on what the text actually supports. batch_06 examples: `npc_chief_accountant.md` asserts the Chief Accountant called Valphine "sister of the sun," but that phrase is absent from ch27–29; `npc_aletra.md` claims "the Chief Accountant believed Aletra 'likely killed her,'" but no such text exists in ch27–29. Report the missing evidence rather than reasoning from it.

- **REQUIRED — every `batch_NN.md` MUST end with a campaign-wide summary.** After the last dossier block, append: total dossiers processed, count fully `Resolved` vs `Partially resolved` vs `Unresolved` vs `None.` (no open questions), and the explicit list of `None.` dossiers. (batch_05 example: 30 dossiers / 25 Resolved / 5 Partially resolved / 0 with `None.`, plus a note that 3 dossiers were corrected against the chapter text. batch_06 example: 30 dossiers / 3 Resolved / 26 Partially resolved / 1 Unresolved / 3 with `None.`.) Omitting this summary breaks interop with `consolidate_uncertainty_batches.py` and any downstream audit. Do NOT leave the summary only in the chat reply — it belongs inside the file.

- **Status taxonomy per dossier (use these exact labels):**
  - `Resolved` — every `## Uncertainty` bullet is answerable from the cited chapters (after identity/entity disambiguation where needed).
  - `Resolved (no open questions)` — the dossier's `## Uncertainty` is `None.`/empty; emit a one-line entry with the entity `name:` so the file stays complete.
  - `Partially resolved` — some bullets answered, some remain genuinely open (no citation exists, or the text is truly silent and the arc is unresolved within the corpus).
  - `Unresolved` — the dossier cannot be grounded at all against its cited chapters (e.g. the referenced figure/event is absent from the cited text). Reserve this for cases where even best-effort retrieval yields nothing usable, and explicitly state WHY (e.g. "cited ch21 as retrieved contains no such figure"). Do NOT apply `Unresolved` to single-open-question dossiers — those are `Partially resolved`.

## Campaign digest workflow (histories/_digests)
The user keeps running notes + digests in `~/histories/_digests/`:
- `_notes_<campaign>.md` = incremental running notes; determine the LAST
  chapter covered there, then read ONLY the remaining `docs/chapters/*.md`
  files (don't re-read covered chapters — the notes are dense enough).
- Deliverable `_digests/<campaign>_digest.md` uses a four-section shape:
  (1) chronological event list, one bullet per major event, each tagged
  `[ch: chapter_NN_slug.md]`; (2) NPC roster (1–3 factual sentences +
  chapter citations, grouped by arc); (3) location gazetteer with citations;
  (4) factions/organizations & arcs as short prose subsections. Neutral,
  factual tone; verify length with `wc -w` and report absolute path + count.
- PITFALL: chapter FILENAMES can disagree with the `# Chapter NN` title
  inside the file (stormgiants ch78–84 are offset). Cite the actual
  filename, and cross-check tags after writing.
- PITFALL: a single `write_file` with the whole digest (>~8K tokens of
  args) can stall the tool stream and the write never lands. Write large
  deliverables in numbered parts (`/tmp/x_partN.md`), then
  `cat part1 … partN > final && wc -w final`. `patch` small fixes into the
  parts rather than rewriting them.

## Persona-voiced documents from digests (single-agent variant)

When the user wants persona-voiced historical documents (e.g. "as THE HISTORIAN OF CANDLEKEEP") produced directly from existing `_digests/` files — without the full 3-phase subagent pipeline — follow this pattern:

1. Read the relevant digest(s). They contain all facts and `[chNN]` citations.
2. Write documents in the persona's voice, preserving every `[chNN]` citation.
3. Fence opinion from fact with `**Historian's Assessment**` blocks, signed (e.g. "— The Historian of Candlekeep").
4. Compose large files as `/tmp` pieces and `cat` them together (see pitfall below).
5. Verify with `wc -w` (target 3000-6000 words per file) and a citation-count check.

This variant was used successfully in July 2026 to produce three files (chronology, events, NPCs) from three digest files in a single session, totaling ~12,000 words with 220+ `[chNN]` citations.

### PITFALL — large write_file stalls (reinforced)
Single `write_file` calls with >~30KB of content can stall the tool stream and the write never lands. Always compose large deliverables in numbered parts (`/tmp/x_partN.md`), then `cat part1 … partN > final && wc -w final`. Use `patch` for small fixes into the parts rather than rewriting them.

## Session-summary narrative refactor (docs/summaries/)
Move `## Summary` narrative paragraphs under their matching `### Scene` heads
with zero content change (pure reordering). Verified working on Phandalin's
50 summary files 2026-09-20. Reuse `scripts/refactor_summaries.py` (dry-run
JSON + `--apply` with built-in verify) and read
`references/summary_narrative_refactor.md` FIRST — it carries the DP-alignment
pitfalls (no argmax, EMPTY_PEN inside the DP, first-scene slicing bug) and the
4-point verification gate.

**Pass 2 (2026-09-20, same corpus): section splices.** "Move ## Memorable
Moments to after Scenes and before NPCs" — pure section splice (lift the `## `
block, re-insert before the target heading, collapse 3+ blank runs). Key
inventory finding: the Phandalin summaries have ~12 DISTINCT `## ` section
orderings; MM sat BEFORE Scenes in 36 files and after Items (i.e. after NPCs)
in 9; 9 files have no MM section at all (skip + byte-identical check). The
transform must carry an "already ordered" guard (Scenes idx < MM idx < NPCs
idx → skip) so the script is idempotent — the dry-run AFTER applying must
report moved=0/skip=all. Verify per file against `git show HEAD:<rel>` by
non-blank-line multiset (Counter), not by the script's own self-check.
Canonical scripts now live IN the repo at
`~/phandalin/scripts/summaries-refactor/` (refactor_summaries.py,
refactor_memorable.py, README.md with corpus stats + pitfalls) — committed on
branch `summaries-restructure`, PR kostadis/campaigns#279. Reuse THAT copy;
`scripts/refactor_summaries.py` here is a snapshot.
General class technique lives in skill `markdown-corpus-refactor`.

## Entity registry triage (mytools skill review)
The user's Claude Code skill `entity-triage` (in `~/src/mytools/dotfiles/claude/skills/`)
governs registry queue-walking; "registry-triage" is how the user refers to it.
Condensed review — mechanics verified against registry.py, GM-ruling design
rules, known discrepancies — in `references/entity_triage_skill_review.md`.

## Scripts
- `references/split_generic_monster_dossiers.md` — per-chapter split of a
  generic-monster catch-all into `monster_<type>_chNN.md` + split manifest
  (grain rule, grep-sweep method, exclusions, schema, pitfalls). Read before
  any "one dossier per chapter" monster-split task.
- `references/phandalin_module_corpus.md` — Phandalin `docs/background/` file
  map, the verified four-book Essentials Kit published spine + connection lore,
  the homebrew overlay modules, and the hand-authored-vs-generated docs
  convention. Read before chronology / lore-map / faction tasks in Phandalin.
- `scripts/extract_uncertainties.sh DIR` — pull every `## Uncertainty`
  question from a merged_dossiers directory (block-scoped, file-prefixed).
- `scripts/consolidate_uncertainty_batches.py OUT_DIR [N]` — merge
  `batch_NN.md` files (subagent-batch variant) into one
  `OUT_DIR/uncertainty_answers.md` with a resolved/partial/unresolved summary.
- `docs/ensemble/resolve_uncertainty.py` — per-dossier agent (parse →
  retrieve → sidecar; optional render). Stdlib-only.
- `docs/ensemble/orchestrate_batch.py` — batch runner over all 300 dossiers
  (`--scaffold` / `--fill` / `--none-pass`; concurrent, resumable, backend via
  `BACKEND_URL`/`BACKEND_MODEL`/`BACKEND_KEY` env or top-of-file constants).
- `scripts/orchestrate_uncertainty_batch.md` — condensed batch recipe:
  two-phase scaffold/fill/none-pass, backend config, progress tracking,
  gotchas (272 vs 28 sidecars, block-buffered stdout).
- Reference: `references/resolve_uncertainty.md` — uncertainty-resolution
  agent: parse/retrieve/render flow, canonical scripts, and PITFALLS
  (`## Uncertainty: None.` producing no sidecar, `--render` clobber bug,
  `---` fence collision, unscoped retrieval dumping the bible, trusting
  dossier errors, opinion-key scheme, vLLM/OpenAI-compat backend quirks,
  block-buffered stdout).
