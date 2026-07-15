---
name: race-monster-typing-is-faction
description: "When a humanoid race/people is typed as \"monster\", treat it as a faction unless the content is physiology"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: e80f1121-fb80-41f3-bf90-f3c65fcc02c8
---

When a humanoid **race/people** name (duergar, drow, kuo-toa, myconid, derro, …) is extracted or typed as a `monster`, treat it as a **faction**, not a bestiary creature — unless the content is specifically about **physiology/anatomy/statblock** (e.g. innate invisibility mechanics, spore biology).

**Why:** Typing a humanoid people as a "monster" with a monolithic alignment is one of the game's more racist stereotypes. Humanoids vary in religion and alignment; "the duergar" as a hostile monolith is a mis-frame. In play the real referent is almost always "the <race> of <place>" — a specific society doing things — which is a faction.

**How to apply:** In `/ensemble-type-merge` (and similar dossier/entity work), merge a race's `monster` facet into its `faction` dossier with the **faction file as primary**, so the merged output stays framed as a people. Only keep a `monster` race-facet separate when it is purely physiological reference material. Established on the OOTA `duergar` group (2026-07-13), which resolved to "the Duergar of Gracklstugh." The heuristic is written into the `ensemble-type-merge` skill's Step 2 and the `entity-triage` skill.

**A race-faction must stay location-scoped — do NOT register the bare name.** The same race is a distinct faction per place (the Derro of Gracklstugh vs. derro elsewhere; the myconids of Neverlight Grove vs. of Blingdenstone), and CampaignGenerator's `facts_to_state` already splits it that way for free: any subject that is *not* a registry known-name is location-scoped into per-place bundles (`Derro (Gracklstugh)`, `Myconid (Neverlight Grove)`). **Registering a bare race name makes it a global known-bundle that collapses every location into one** — the opposite of what you want. So leave race names unregistered, or force them via a `--exclude-names` file (`docs/ensemble/location_scoped_races.md` in OOTA lists Derro/Myconid/Duergar/Drow/Kuo-toa). You can't register "Derro of Gracklstugh" to catch those facts — matching is by bare subject; the location split is derived from where facts occur. See [[generic-subject-names-need-qualifying]]. (GM ruling, OOTA 2026-07-13 — I added bare `Derro`/`Myconid` entities, which globalized them and collapsed the built-in location-scoping; reverted. Corrects an earlier version of this note that wrongly said "register it location-qualified.")
