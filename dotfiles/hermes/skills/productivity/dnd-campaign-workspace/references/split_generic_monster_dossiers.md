# Splitting a generic-monster catch-all into per-chapter dossiers

## When this applies
The user has a generic-monster **catch-all** dossier (e.g. `monster_thugs.md`,
`monster_orcs.md`, `monster_bandits.md`) that lumps an entity role across many
chapters, and asks you to "write one dossier per chapter into
`~/phandalin-output/answers/monster_<type>_chNN.md`" (or similar per-chapter grain).

This is a recurring Phandalin workflow: `orc_split_manifest.md` and
`thug_split_manifest.md` already exist in `~/phandalin-output/`, so the user
repeats it for each monster type. The pattern below is the proven shape.

## GRAIN RULE (the one that got the first attempt deleted)
**COARSE: exactly one dossier per chapter that contains the encounter. Do NOT
split per individual fate** (no `_beheaded`, `_spider_bitten`, `_net_thrower`,
`_fleeing_felled`). The prior thug pass produced ~20 individual-fate files; the
user deleted them and asked for one-per-chapter instead. If the same role appears
in multiple scenes inside one chapter, it is STILL one file for that chapter.

## Output locations (do not guess — match the existing convention)
- New per-chapter dossiers: `~/phandalin-output/answers/monster_<type>_chNN.md`
  (NN = the chapter number, zero-padded if the existing files are).
- Manifest: `~/phandalin-output/<type>_split_manifest.md` (e.g.
  `thug_split_manifest.md`, `orc_split_manifest.md`).
- **The catch-all itself (e.g. `answers/monster_thugs.md` and
  `src/.../ensemble/state_dossiers/monster_thugs.md`) is NOT edited.** It stays
  as the source of truth. If it has errors (scope too narrow, wrong allegiance),
  record them in the manifest's "Existing-dossier correction" section and offer
  to fix — do not silently rewrite it.

## Verification method (read the source, don't trust the catch-all's chapter range)
1. Read the catch-all to learn the role definition and its candidate `chapters:`.
2. **Grep sweep across ALL chapter files** for role synonyms. In the thug pass the
   sweep terms were: `thug, thugs, bandit(s), brigand, mook, enforcer, ruffian,
   henchman/henchmen, goon, veteran, gang, Jax, Borg, Skippy, "Carver's crew"`.
   Use a bash `grep -ioE` loop, **not** `search_files` — see pitfall below.
3. **Read each candidate chapter's actual text** to confirm it is a genuine
   generic-enforcer *combat encounter* (unnamed humanoid mooks the party fights),
   not a passing mention.
4. Exclude anything that is NOT this role:
   - **Orcs** (ch7 "delightful ambush", ch20 orc ambush, Butterskull orcs) →
     belong with the orc dossiers, not thugs.
   - **Ogres / Rot-Tusk Ogres** → `monster_rot_tusk_ogre`, not thugs.
   - **Named lieutenants / principals**: Borg the Hammer ("half-orc enforcer" is
     still a named lieutenant), Jax, Sylvine Wintermoon, the Carver, Sister
     Kaella/Kayla → these are NPCs, excluded.
   - **Named captives that become NPCs**: Skippy → `npc_skippy`; the ch4 spared
     survivor is Corbin → `npc_corbin`. Flag the overlap, don't duplicate.
   - **Retrospective mentions**: ch5/ch13/ch38 "the bandit"/"ex-bandit" all refer
     back to Corbin; ch2/ch10 are rhetoric/background ("adventurers are glorified
     thugs", "bandits besieging the town") with no scene. None qualify as a new
     fight.
5. Write one dossier per qualifying chapter; the manifest lists every candidate
   with status, plus an "Considered but excluded" table with the reason for each.

## Dossier schema (match the existing answers/ format exactly)
```
---
name: <role> encounter chNN (<descriptor>)
type: monster
n_facts: <int>
chapters: NN-NN
---

### <same title>

**Current status:** ...
**Current location:** ...
**Allegiance/faction:** ...   # per-chapter, not blanket — see pitfall
**Current possessions / notable items:** ...
**Current assignment / role:** ...
**Defining recent actions:** ...
**Revealed motivations or secrets:** ...

## Uncertainty
- <genuine open question with chapter citation>
```
Note the `name:` header field (NOT `title:` — see the parent skill's PITFALL).

## Manifest shape
- Header: source of truth, sweep terms, split target (the untouched catch-all).
- "New dossiers" table: file | chapters | summary | status.
- "Scope notes": qualifying chapters (with VERIFIED tag) + "Considered but
  excluded" with reasons.
- "Existing-dossier correction": corrections to the catch-all (scope too narrow,
  unsupported allegiance, wrong possessions) — recorded, not applied.

## PITFALLS
- **`search_files` count mode returned false zeros** in this workspace (it
  reported 0 hits for "bandit" across files that clearly contained the word).
  The parent skill already warns `search_files` mishandles anchors/char classes;
  here the COUNT mode also lies. Use `terminal` `grep -ioE '\b(bandit|brigand|...)\b'`
  in a loop for reliable frequency + candidate discovery, then read the files.
- **Don't over-split per individual fate** — coarse one-per-chapter only.
- **Don't edit the catch-all** — corrections go in the manifest.
- **Don't blanket the allegiance.** No thug in the text expresses loyalty; the ch4
  survivor said he "just worked with Jax" (a reporting line, not fealty) and the
  ch36 crew treated it as a job ("more money to be found elsewhere"). State
  allegiance per-chapter (Carver's agents via Jax; Sylvine's crew; etc.).
- **Cite the real chapter for possessions.** ch33 explicitly gives a thug a net —
  the catch-all's "None specified" was wrong; verify from text, don't repeat the
  catch-all's gap.
