---
name: generic-subject-names-need-qualifying
description: Merged dossiers with generic subject names should be flagged for re-subject with an owner/place qualifier
metadata: 
  node_type: memory
  type: feedback
  originSessionId: e80f1121-fb80-41f3-bf90-f3c65fcc02c8
---

When an ensemble dossier's subject is a **generic name** — a common item, structure, role, or org label that could collide with other instances (`bag of holding`, `inner circle`, `high tower`, `miners guild`, `temple of oghma`, `poison`, `spider`, …) — the merge may still be correct, but the *name* needs qualifying by its owner or parent context so downstream synthesis doesn't conflate it with a different instance.

**Why:** A bare "Bag of Holding" or "Inner Circle" reads as a class, not the specific one in play. Two different bags/circles/towers would otherwise be indistinguishable to Stage 3 synthesis.

**How to apply:** In `/ensemble-type-merge`, do **not** rename in place (verbatim concatenation only). Record a `"note"` on the group flagging it as a RE-SUBJECT CANDIDATE for entity-triage/alias tooling, with the suggested qualified name — `owner's <item>` or `<place>_<structure>`. Surface the suggestion to the GM; they may want a specific qualifier. Established rulings (OOTA, 2026-07-13): `bag of holding` → "Glabbagool's Bag of Holding"; `inner circle` → "neverlight_grove_inner_circle". Now written into the `ensemble-type-merge` skill's Step 4. Related: [[race-monster-typing-is-faction]].
