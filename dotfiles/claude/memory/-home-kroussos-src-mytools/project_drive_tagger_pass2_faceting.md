---
name: project_drive_tagger_pass2_faceting
description: "drive-tagger category cleanup has TWO passes — Pass 1 dedup-merge (the /drive-consolidate skill) and Pass 2 facet-decomposition (compound category names → tone facet + subject tag), which is NOT a merge"
metadata: 
  node_type: memory
  type: project
  originSessionId: f7706a61-2895-4d3b-a399-091dc04ec75c
---

drive-tagger category consolidation is two distinct operations, do not conflate:

**Pass 1 — dedup merge** = the `/drive-consolidate` skill + `consolidate collect`/`apply`.
Merges near-duplicate categories (singular/plural, synonyms) via
`store.merge_categories`. Deletes the source category. Done for the 19 clusters
on 2026-07-03 (1197→1175 cats).

**Pass 2 — facet decomposition** (Kostadis's reframe, 2026-07-03): compound
category names like `"Absurdist Feline"` are really TWO orthogonal facets mashed
into one string — a tone/genre facet (`Absurdist`) + a subject (`Feline`). The
fix is to split, NOT roll up. Rollup (fold `Absurdist Feline` into
`Absurdist Monsters`) is WRONG — it deletes the `Feline` information. Decompose
instead: the doc carries BOTH `Absurdist` and `Feline` as separate reusable tags.

**How Pass 2 executes** (no CLI exists; scripted from tested Store primitives):
for each compound `C = "Facet Subject"`, `assign_categories(doc, [subject])` on
C's docs, then `merge_categories([C], into="Facet")` to add the facet + strip and
delete C. Regenerate reports with `report_mod.generate()` after closing the Store.
Only apply to families where the FIRST WORD is a genuine tone/genre facet
(Absurdist, Gothic, Cosmic) — NEVER to atomic multiword categories
("Campaign Setting Guides" is one concept, not Campaign+Setting Guides).

Absurdist pilot done: 33 compounds → `Absurdist` facet (319 docs) + 31 subject
tags; Traps/Possession merged into pre-existing standalones.

DO NOT prune subject tags by frequency. Kostadis's rule (2026-07-03): high count
≠ noise. `Fantasy`(185), `Horror`, `Encounters` are FACET DIMENSIONS
(setting/genre/content-type); their value is the contrast they draw. Among the
319 absurdist docs, 185 are Fantasy-set and 37 are sci-fi-ish — deleting
`Fantasy` would erase fantasy-vs-scifi, the SAME information loss as rollup. Only
delete genuinely degenerate tags (e.g. the truncated 0-doc `Absur`). Known
limitation, not a bug: `Fantasy` is only on the 319 ex-absurdist docs, not
library-wide — full setting-faceting is an upstream enrichment job.

Not every adjective-first family is a clean tone+subject split. Two shapes seen:
(a) clean 2-facet (Absurdist, Feywild, Underwater, Post-Apocalyptic); (b) 3-part
mashup `<Aesthetic> Horror <ContentType>` (Gothic, Cosmic) → split into
aesthetic + `Horror` genre facet + content-type; the shared `Horror` facet
unifies across families (457 docs). Use an EXPLICIT per-compound mapping dict
(dry-run then --apply), not a mechanical first-word rule. Normalize plurals
(Campaigns→Campaign). Execution per compound: assign non-first facets to its
docs, then `merge_categories([compound], into=first_facet)`; regen reports.

GENRE PASS COMPLETE (2026-07-03): all 14 families done — Absurdist, Gothic,
Cosmic, Feywild, Underwater, Post-Apocalyptic, Cyberpunk, Elemental, Mythic,
Epic, Arcane, Infernal, Weird, Dark. Store 1175→1159 cats. Each batch ran with a
`backups/db-pre-pass2-*` backup (all under drive-tagger/backups/).

Shared cross-family facets emerged: Horror(457), Adventures, Campaign, Tomes(149,
= Grimoires+Tomes+Codex unified), RPG, Fantasy. Aesthetic facets: Absurdist,
Gothic, Cosmic, Cyberpunk, Arcane(magical), Infernal(diabolical), Feywild,
Underwater, Post-Apocalyptic, Epic, Mythic, Elemental. Kostadis's rulings during
the pass: Arcane≠Infernal (magical vs diabolical, never merge); Grimoires=Tomes=
Codex (one book subject 'Tomes'); `Infernal Themes` kept WHOLE; `Weird West` &
`Weird Fiction` are atomic subgenres (no `Weird` facet); `Dark` is a grab-bag,
minimal touch only, proper-noun title `Dark Days in Stoneholme` protected.

0-doc cleanup DONE: deleted `Absur`, `Forgotten Realms: Moonshae Isles`,
`Haunted Ship` (all empty). Store 1159→1156 cats.

TAIL FACET-TOKEN SWEEP DONE (2026-07-03): the tail is NOT unplaceable orphans —
it's hidden compounds. Grouped tail (<=2 doc) categories by shared facet TOKEN
(trailing/leading segment that is/should-be a tag), walked 61 token-groups with
Kostadis (accept/skip per group, then recommend+veto for the small tail). 32
groups accepted -> 190 categories decomposed into qualifier + facet; 29 skipped
(vague facets like World/Content/Play, garbage-qualifier groups, proper-noun
mangling). Artifacts: reports/consolidation/tail_agenda.json (all 61 groups +
members) and tail_decisions.json (per-token accept/skip/canonical) — both drive
resume. Apply recipe: assign qualifier to each doc, then merge_categories([cat],
into=facet). merge_categories is SLOW (rescans all docs per call); 190 calls
exceeded a 2-min foreground limit — re-run is idempotent (done cats are gone ->
no-op), finished on resume. Store now 1156->1158 cats (count is not the metric;
reuse is — Horror facet=500, Lore=66, qualifiers like Feline/Call of Cthulhu
reconnect across sources). Full handoff at drive-tagger/reports/consolidation/
HANDOFF.md.

Still open (NOT done): the ~24 SKIPPED tail groups (left whole by choice, can
revisit); the residual atomic/proper-noun singletons (no facet token — correctly
left alone); noun families (Dungeon/Adventure/Monster/NPC — decomposition N/A);
and the durable prompt fix below (the curated facet vocabulary in
tail_decisions.json is its seed).

DURABLE fix still open: update enrichment prompt in `prompts.py` to emit facet
tags so future scans don't regenerate compounds.

Every store mutation gets a timestamped `backups/db-*/db` copy first (cp -a,
verify byte count). Store built under `DT_EMBED_PROVIDER=dgx DT_EMBED_DIM=1024`.
Related: [[feedback_subissue_execution_workflow]].
