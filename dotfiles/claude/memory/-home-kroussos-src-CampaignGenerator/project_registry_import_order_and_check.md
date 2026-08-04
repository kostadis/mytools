---
name: project_registry_import_order_and_check
description: Entity-registry importers — load-bearing import order (inventory→dedup→frontmatter) and the two-pronged check design (grouping-drift + fuzzy) needed to catch fragmentation.
metadata: 
  node_type: memory
  type: project
  originSessionId: d46f1423-7d20-4794-8880-450536506402
---

Building the campaign-entity registry (issues #128/#129/#130, plan `~/.claude/plans/virtual-swimming-castle.md`, branch `feat/entity-registry-phase1`). Two non-obvious findings from running the importers on the real out-of-the-abyss corpus (149-dossier dedup + full module inventory):

**1. Import order is load-bearing: inventory → dedup → frontmatter.**
`import-dedup` blanket-types every entity `npc` and derives canonical names from dossier filenames. `import-inventory` carries real types (from `## Heading` sections) and published canonical spellings. If dedup runs first, its `npc` type and filename-stem canonical win, and the inventory's better data loses (e.g. Demogorgon stuck as npc not deity; `Sarith`/`Sarith Kzekarit` fragment). Inventory-first lets dedup clusters merge *into* the established canonicals. The Phase-5 recipe already specifies this order — it is not arbitrary.

**2. `check` must be two-pronged: grouping-drift (primary, exact) + fuzzy near-dup (secondary, noisy).**
The importers correctly refuse to guess identity and report every collision, but the *outcome* can still be a fragmented registry:
- **Grouping drift (exact, high-confidence):** when a store explicitly links two surface forms (dedup cluster, inventory slash-alias, alias_decisions group) but they end up as two separate registry entities (because one spelling was already a standalone entity, so the incoming alias collided and was discarded). Presence-based drift MISSES this — both names *exist* in the registry, just ungrouped. `check` must compare *groupings*, not just presence.
- **Fuzzy near-dup (difflib ≥ ~0.85):** the *silent* case — two spellings with no shared alias (`Khalessa`/`Khelessa Draga`, `Faerun`/`Faerûn` where norm_subject strips the accent to different keys) produce ZERO conflict and both entities are created. Only a fuzzy scan catches these. But fuzzy is noisy (`East`/`West Cleft District`, `+1`/`+2 shortsword`, three real `Circle of Sowers/Sporers/Growers`) → GM-review surface only, never auto-merge. `check` must suppress pairs already recorded in `distinct`/`rejected_aliases` so GM rulings stick.

Resolution of fragmentation is Phase-5/GM + Phase-3b triage work; `check` only SURFACES. See [[project_alias_fragmentation]] (the bug this registry kills) and [[feedback_never_assume_answers]] (identity = a human checkpoint).
