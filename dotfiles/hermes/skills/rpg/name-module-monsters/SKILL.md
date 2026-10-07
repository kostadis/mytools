---
name: name-module-monsters
description: >-
  Name and tribalize every unnamed/generic monster in a D&D 5e adventure module
  (e.g. "for each chapter, give every generic orc a name, tribe, and
  distinguishing feature so they're not just 'orcs' but 'orcs of tribe X'"),
  then build a boss hierarchy using a Challenge-Rating-difference rule
  (boss ΔCR < 4 = NOMINAL, > 4 = HARD). Use when a user wants to flavorize
  stat-block monsters in a module, give monsters tribes, or produce a
  boss→tribe chain of command. Works for any module: Phandelver/Shattered
  Obelisk, Curse of Strahd, Descent into Avernus, homebrew, etc.
---

# Name Module Monsters (scan → describe → hierarchy)

A four-phase pipeline that turns the generic stat-block monsters in a module into
named, tribed, characterized creatures, then classifies each tribe's boss as
NOMINAL or HARD by CR gap. Built for reuse across modules.

## When to use
- "Name every unnamed monster in `<module>.md` and give them tribes + features."
- "Don't call them just 'orcs' — make them 'orcs of tribe X' with distinguishing traits."
- "Build a monster hierarchy: given tribe A, who is the bigger bad, and is it a nominal or hard boss?"
- Any request to flavorize, tribalize, or hierarchize a module's monsters.

## Inputs / setup
- **Module source**: a plain-text or markdown dump of the module (e.g. `docs/background/obelisk.md`, 6078 lines). If you only have a PDF, extract text first (`pdftotext` or web_extract on a PDF URL). Large modules (3000+ lines) should be split into chapter chunks.
- **Existing name inventory** (optional but recommended): if the campaign already has a `name_glossary.md` or a proper-noun inventory, load it FIRST — it tells you which "monsters" are actually *named NPCs* (e.g. Agatha the banshee, Venomfang the dragon) that must be EXCLUDED from the unnamed pool and never renamed.
- **Output dir**: `<campaign>/docs/background/` (or wherever the module lives).

## Phase 0 — Build the CR reference table (`monsters_cr_reference.md`)
Source of truth for the Phase 3 boss math. One table of `Monster | CR | Notes`.
- Pull CR from the *Monster Manual* and the module's own **Appendix A: Bestiary** (modules like PaBTSO add variant stat blocks — e.g. `Goblin Psi Brawler 1/4`, `Encephalon Cluster 5`). Where a module variant differs from MM, list BOTH and label the appendix one.
- Note the boss-tier rule and the gap-of-4 edge convention at the top (see Phase 3).
- If the campaign has 5etools MCP available, you can verify CRs against it; otherwise the standard MM + appendix table is sufficient.
- Keep a compact starter table inline in this skill's `references/cr_starter.md` for the most common humanoids/beasts/aberrations; extend it per module.

## Phase 1 — Scan & group (the "scan agent")
Goal: a FAITHFUL inventory of unnamed monsters, grouped, with citations. Do NOT invent or rename here.

For large modules, **delegate this to a subagent per chapter-chunk** (e.g. `_scan_A.md` ch1–2, `_scan_B.md` ch3–5, `_scan_C.md` ch6–8), then merge. For small modules do it inline. The agent prompt:
> "Scan lines X–Y of `<module>.md`. For every generic/unnamed creature stat-block
> reference, record: monster type, the tribe/faction it belongs to (use the module's
> own labels — Cragmaw, Redbrands, Sawplee, etc.), chapter, area + line number,
> and the verbatim count/die expression (e.g. `1d4`, `2d4`, `about fifteen`).
> Merge cross-chapter appearances of the same (tribe, type) into ONE entry.
> Exclude named individuals (cross-check `name_glossary.md`). Write the grouped
> scan to `<out>/_scan_<X>.md`."

Then consolidate all `_scan_*.md` into **`monsters_phase1_scan.md`**:
- One section per TRIBE ("TRIBE 1 — Cragmaw band", etc.), each with numbered
  sub-groups `1.1 Goblins`, `1.2 Goblin Boss`, …
- Each group: **Chapters**, **Areas & counts** (with line citations), **Total**
  (fixed + random dice preserved verbatim), **Module descriptors** (quoted flavor
  from the text), **Named-leader flag** (YES → who; NONE if leaderless).
- End with a **MASTER SUMMARY TABLE** (one row per group: #, Tribe, Type, Chapters,
  crude fixed count) and a count of total consolidated groups (e.g. "71 groups").
- End with an **EXCLUDED NAMED INDIVIDUALS** list (so Phase 2 never renames them).
- **Faithfulness rule**: this file must not change counts, invent monsters, or add
  flavor. It is the audit trail.

## Phase 2 — Named descriptions (the "description agent")
Goal: for every group from Phase 1, assign a tribe name, individual names with
distinguishing features, and flavor. **Never rename a module's named NPC** — only
name their unnamed subordinates.

Delegate per tribe (or do inline for small modules). The agent prompt:
> "For each group in `monsters_phase1_scan.md`, write a section in
> `monsters_phase2_descriptions.md` with: a flavorful FULL tribe name (keep the
> module's label, e.g. 'Cragmaw band — the Jagged-Tooth Tribe'), CR (from
> `monsters_cr_reference.md`), the named-module leader preserved verbatim with a
> note that it is NOT renamed, then 3–8 NAMED INDIVIDUALS for that group, each with
> a concrete distinguishing feature (scar, missing ear, glowing hand, pet, tic),
> and a group-flavor paragraph quoting the module. Truly untribed monsters get an
> invented D&D-style warren/lair/pack name."

Conventions that made the obelisk run clean:
- **Named individuals**: 1–2 word names with a feature, e.g. `Zark — filed his
  four front teeth into broken shards; left ear missing; carries a notched javelin.`
- **Counts vs names**: name a representative sample, not every one of 31 goblins.
- **Group flavor** paragraph ties the tribe to the module's own descriptors.
- End with a **COVERAGE NOTE** asserting every Phase-1 group was named (e.g. "All 71
  consolidated groups named above").

## Phase 3 — Boss hierarchy (CR-difference classification)
Goal: for each tribe, identify the bigger bad and classify NOMINAL vs HARD.

Write **`monsters_phase3_hierarchy.md`**:
- State the rule up top:
  - Δ = CR(boss) − CR(rank-and-file). Use the **highest rank-and-file CR** for the
    conservative (smallest-gap) comparison when a tribe has multiple tiers.
  - **Δ < 4 → NOMINAL** (leader in name only).
  - **Δ > 4 → HARD** (genuinely more dangerous).
  - **Δ == exactly 4 → NOMINAL+ (borderline-hard)** — flag for review, never silently call "hard".
- **Tribes with a named-module boss** (keep the name; do NOT rename): compute Δ for
  each. Note meta-chains (e.g. Sawplees → Ruxithid NOMINAL → fanatics HARD).
- **Leaderless / ambient tribes**: either NOMINATE a boss you named in Phase 2 (e.g.
  the grick alpha, the quaggoth thonot, the intellect devourer in its host) and
  compute Δ, or mark **NO BOSS — ambient/independent** (stirges, owlbear, violet
  fungi, intellect snares, psychic gray oozes, solo apex predators).
- **Apex creatures that command no tribe** (infected elder brain, a lone behir, the
  godlet Ilvaash): mark as apex/HARD *threat* but NOT a "tribe boss."
- End with: a **hierarchy tree** (ASCII: boss → tribe, with classification),
  a **summary table** (Tribe | Boss | Rank CR | Boss CR | Δ | Classification), and a
  **bottom-line** count of HARD vs NOMINAL+ vs NOMINAL bosses.

## Verification (before declaring done)
- [ ] `monsters_phase1_scan.md` covers every generic monster in the module; counts
      and line citations preserved verbatim; named individuals excluded.
- [ ] `monsters_phase2_descriptions.md` names every Phase-1 group (coverage note
      present); no module-named NPC was renamed.
- [ ] `monsters_phase3_hierarchy.md` classifies every tribe; gap-of-4 cases flagged
      NOMINAL+, not silently HARD; multi-tier tribes use highest rank CR.
- [ ] All four output files present in the output dir.
- [ ] (If in the campaigns repo) commit is scoped to ONE campaign per the
      repo's isolation rule — do NOT bundle across campaigns.

## Pitfalls (learned the hard way)
- **Faithfulness in Phase 1**: the scan must be auditable. Don't let the LLM
  "helpfully" merge or re-count. Keep dice expressions (`2d4`) as-is.
- **Named-leader exclusion**: the module may itself contradict names (e.g. ch2 says
  orc "Greska" runs the Sleeping Giant, ch5 says dwarf "Grista" — a module typo, not
  your concern at naming time). At the *naming* stage, trust the existing
  `name_glossary.md` rulings; only name the unnamed subordinates.
- **Multi-tier rank CR**: a tribe with goblin (1/4) AND psi commander (1/2) AND
  ashenwight (2) — compare the boss against the **highest** rank CR (2) so the gap
  is understated (conservative). Note the range.
- **Boss weaker than rank**: sometimes the "boss" is LOWER CR than an elite
  subordinate (e.g. Ruxithid CR1 vs psionic ashenwight CR2). That's a real finding —
  report the negative Δ, it's a NOMINAL/peer result, not an error.
- **Apex ≠ boss**: a CR-14 elder brain or CR-23 kraken is a HARD *threat* but may
  command no tribe of its own. Distinguish "apex creature" from "tribe boss."
- **Module CR ≠ MM CR**: PaBTSO/appendix variants differ. Build the CR table from
  the module's own appendix first.
- **Chunked scans drift**: when merging `_scan_*.md`, de-dupe cross-chapter groups
  (a goblin appearing in ch1 and ch5 is ONE entry with both areas listed).

## Worked example (obelisk / Phandelver and Below)
The reference run lives at
`/home/kostadis/src/campaigns/obelisk/docs/background/`:
`monsters_phase1_scan.md` (71 groups, 18 tribes), `monsters_phase2_descriptions.md`
(all 71 named with tribe + individuals + features), `monsters_phase3_hierarchy.md`
(4 HARD bosses — Hamun Kost, Nezznar the Spider, the three fanatics over their
goblin minions, Ghaluzesh over the epilogue enforcers — + 2 NOMINAL+ + the rest
NOMINAL), and `monsters_cr_reference.md`. Read these as a format template before
running on a new module.
