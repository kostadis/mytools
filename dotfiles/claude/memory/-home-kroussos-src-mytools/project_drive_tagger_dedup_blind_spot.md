---
name: project_drive_tagger_dedup_blind_spot
description: drive-tagger Pass-1 dedup (/drive-consolidate) has two measured blind spots — empty-description categories embed on bare name (modality mismatch) and the 0.05 cosine threshold is too tight for genuine LLM paraphrase near-dupes — found via the Dungeon Generator/Generators/Generation Systems trio that survived Pass 1 untouched
metadata: 
  node_type: memory
  type: project
  originSessionId: 2c56de2c-5f13-476e-bd1c-0e2e797dadc3
---

Kostadis read a generated category report (2026-07-04) and spotted "Dungeon
Generation Systems" (16 docs), "Dungeon Generator" (7), "Dungeon Generators"
(16) as obvious near-duplicates that [[project_drive_tagger_pass2_faceting]]'s
Pass 1 (`/drive-consolidate`, `consolidate collect`/`apply` in
`src/drive_tagger/consolidate.py`) should have merged but didn't — all three
were singletons in `reports/consolidation/clusters.json`, never referenced in
`decisions.json` or `tail_decisions.json`.

**Measured root cause (two independent, compounding causes)** — pulled the
live stored vectors via `Store().all_categories_with_vectors()` (no network
needed, reading doesn't re-embed) and computed the 3x3 cosine distance matrix
under `DT_EMBED_PROVIDER=dgx DT_EMBED_DIM=1024`:

1. **Empty-description categories embed on bare name, not description** —
   `store.py:143`, `self.categories.upsert(documents=[description or name],
   ...)`. `"Dungeon Generators"` has `description: ""` in
   `reports/categories.json`, so its vector is a name-string embedding, while
   its two siblings (real paragraph descriptions) are description-embeddings.
   Different modality → systematically far apart even on the same topic:
   0.097 and 0.114 cosine distance, both way above the 0.05 threshold.
   **This is corpus-wide, not a one-off**: 367/1152 categories (32%) have
   `description: ""`. 235 are single-word Pass-2 facet tokens (Absurdist,
   Gothic — fine, the name IS the content), but **132 are ordinary multi-word
   categories with real member counts** (`Name Generators` 197 docs, `Urban
   Environments` 95, `Character Creation` 74, `Plot Hooks` 67, `Dungeon
   Generators` 16 among them) — these never got a description from the
   enrichment pipeline and it silently breaks their embedding-clustering
   ever since.

2. **0.05 threshold is calibrated too tight for real paraphrase pairs even
   when both sides HAVE descriptions.** `"Dungeon Generator"` vs `"Dungeon
   Generation Systems"` — both non-empty, both unambiguously the same concept
   described in different words — sit at cosine distance **0.0814**, still
   above threshold. The threshold doc comment in `config.py` calibrated 0.05
   from p5=0.049 nearest-neighbor distance and a chaining cliff at ~0.06, but
   a same-concept LLM-paraphrase pair can legitimately sit above that.

**Why to apply**: before trusting `/drive-consolidate` clustering output as
exhaustive, don't assume a category absent from `clusters.json`'s multi-member
groups is a true singleton — check whether it has an empty description first
(modality mismatch hides it), and treat the 0.05–0.10 band as "probably worth
a human glance," not "confirmed distinct." A durable fix needs both: (a)
backfill real descriptions for the 132 multi-word empty-description
categories so they embed in the same modality as their siblings, and (b) add
a cheap lexical/name-similarity fallback (edit distance, stem/plural
normalization, substring) alongside cosine distance — `/drive-consolidate`
currently has zero non-embedding signal, so a trivial "Generator" vs
"Generators" pair has no path to detection other than luck. Neither prompt
tuning nor consolidation reruns alone fix this — see
[[project_drive_tagger_prompt_vs_consolidation]] for the same
complementary-not-alternative pattern applied to a different root cause.

Full writeup with all measured distances and scan output lives at
`drive-tagger/reports/consolidation/DEDUP_BLIND_SPOTS.md`, cross-linked from
`HANDOFF.md` item 5. Confirmed via more examples Kostadis gave in the same
session: `Forgotten Realms` (empty desc, 23 docs) vs `Forgotten Realms
Campaign` (33) is mode-1; `System-Agnostic Sci-Fi` (212) vs `...Scenarios`
(38) is a third mode — prefix-containment pairs where one name is a literal
token-prefix of another. These split into two cases with no mechanical way
to tell them apart: legitimate Pass-2-style facet decomposition (`Call of
Cthulhu` + `Scenarios`/`Content`, `Legendary Games` + `Modules` — bare facet
+ genuinely orthogonal content-type) vs true duplicates (`System-Agnostic
Sci-Fi Scenarios` restates what the parent's own description already
covers). A corpus-wide scan found 20 such prefix pairs and 5 more
singular/plural pairs beyond the original trio (`Explorer's Journal(s)`,
`Floating City/Cities` at a startling 0.36 distance, `Gamemaster
Screen(s)`, `Smugglers' Lair(s)`).

Filed as GitHub sub-issues under parent #86 (github.com/kostadis/mytools,
already-open issue that originally proposed this exact embedding+lexical
detection work): #98 (backfill), #99 (lexical fallback), #100 (prefix
surfacing), #101 (threshold-comment guardrail). Followed
[[feedback_subissue_execution_workflow]] convention exactly (title format
`drive-tagger #86.N: ...`, native `gh api .../sub_issues` linking, no labels
— matches the precedent of #54's sub-issues #87-90).

Orchestration plan produced by an Opus Plan-agent (per Kostadis's explicit
ask to have Opus, not Sonnet, own planning/orchestration) at
`drive-tagger/reports/consolidation/ORCHESTRATION_PLAN.md`, cross-linked from
`HANDOFF.md` item 5. Sequencing: #101 (doc-only bootstrap) → #99 → #100
(share a `collect()` refactor + new `clusters.json` keys) → #98 (live-store
mutation, done last, benefits from #99/#100's detectors existing first).
Flags 7 open risks/decisions before execution starts, notably: #99's
singularizer must do `ies→y` then strip-`s` (NOT blanket `es`) or it misses
the flagship `Floating City`/`Cities` pair; #98 needs a scope decision
(one-off script vs. committed `consolidate backfill` subcommand) and DGX
endpoint availability check first; dirty working tree on the current
(unrelated) branch needs resolving before cutting the new branch.

Not yet done: nothing has been applied to the store or implemented in code —
this session ends at plan, matching the established workflow's confirm-gate
discipline (Sonnet implements each sub-issue only after human approval).
