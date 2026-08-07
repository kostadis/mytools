---
name: drive-consolidate-links
description: Review and merge near-synonym file-to-file link relations produced by drive-tagger. Interactive, one relation family at a time. Invoke as /drive-consolidate-links.
tools: Read, Bash, AskUserQuestion, TaskCreate, TaskUpdate
---

# Drive Consolidate Links

drive-tagger records typed file-to-file edges (`supersedes`, `part-of`,
`duplicate-of`, `references`, `related-to`) in `graph.sqlite`. The MCP agent
path lets the LLM invent relation strings freely, so the vocabulary drifts —
dozens of near-synonyms (`complements`, `complementary`, `complementary-to`,
`series-member`, `sequel-to`, `version-of`, `print-version-of`, …) fragment the
graph. This skill runs the post-run cleanup: deterministically group the rogue
relations into candidate families, review each with the user one at a time, then
apply the approved relation-merges. It is the link-graph counterpart of
`/drive-consolidate` (which does the same for category names).

"Claude" below means this Claude Code session, driven by `AskUserQuestion`.
Nothing here talks to an Anthropic API or to Drive — `link_consolidate.py` only
touches the local `graph.sqlite`.

## The target vocabulary (decide per-family — the vocabulary can EXPAND)

The 5 relations above are the *inherited* controlled set, but the rogue
relations carry real signal (`complements` = 198 edges, `series-member` = 116).
Consolidation is **not** "roll everything up into the 5." For each family the
user decides the canonical, and it may be:

- an existing canonical-5 relation (e.g. `similar-theme` → `related-to`), OR
- a **promoted rogue** that becomes a new canonical (e.g. keep `complements`,
  fold `complementary`/`complementary-to`/… into it) — expanding the vocabulary
  to preserve a distinction the 5-set can't express.

Preserve information; don't collapse a real distinction just because it's not in
the original 5. That is the user's call, per family.

## Required inputs

1. **drive-tagger repo path** — the dir with `pyproject.toml` and
   `src/drive_tagger/`. `mytools/` has no root `pyproject.toml`; every
   `uv run ...` below must `cd` into the drive-tagger repo first.
2. **Embedding config** — `collect-links` reads only `graph.sqlite` (no vectors),
   but `apply-links` regenerates reports, which opens the turbovecdb store built
   with `DT_EMBED_PROVIDER=dgx` (1024-dim). **Prefix every `apply-links` (and any
   store-touching) command** with `DT_EMBED_PROVIDER=dgx DT_EMBED_DIM=1024`.
   (Confirm if the user points at a different `data/` built under another
   provider. Don't silently guess.)

## Workflow

### Phase 1 — collect (deterministic, no LLM)

```bash
cd <drive-tagger-repo> && uv run drive-tagger consolidate collect-links
```

Read `reports/consolidation/link_clusters.json`. Its shape:

```jsonc
{
  "generated_at": "...", "threshold": 0.34,
  "canonical_counts": {"supersedes": 80, "part-of": 1874, "duplicate-of": 1299,
                       "references": 1459, "related-to": 17226},
  "clusters": [
    {
      "id": "44680695af70",                 // 12-hex _cluster_id — see Phase 4
      "members": [
        {"relation": "complements", "count": 198,
         "sample_notes": ["Game master screen provides quick-reference tables…"]}
      ],
      "suggested_canonical": "complements", // highest-count member, or null (see below)
      "confidence": "high | medium | low",
      "reason": "string<=0.34, intra-cluster [0.0000, 0.2308]",
      "min_distance": 0.0, "max_distance": 0.23,
      "warning": "…"                        // present only for antonym families (see Phase 2)
    }
  ],
  "singletons": [
    {"id": "…", "relation": "similar-theme", "count": 11, "sample_notes": [...]}
  ]
}
```

`clusters` is sorted highest-yield-first (confidence high→low, then tightness).
`canonical_counts` is the current 5-relation vocabulary, for context.

**Both `clusters` AND `singletons` are reviewed here** — unlike the category
skill, a link singleton is a *rogue* relation that string-grouping couldn't
family, but it still usually wants mapping to a canonical (e.g. `variant-of` →
`duplicate-of`). Do not skip singletons.

**Sanity check:** if `clusters` and `singletons` are both empty, the relation
vocabulary is already clean — say so and stop. If `n_rogue_types` is large but
`clusters` is empty, the threshold is likely too tight — flag it.

### Phase 2 — Claude pre-classifies each family (opinion, not a filter)

For each cluster and singleton, form an opinion before asking: which canonical
best fits, drawing on the member relation names and their `sample_notes`. State
whether the family is coherent or looks like a chain (string distance can group
by spelling, not meaning — e.g. it will NOT group `series-member` with
`sequel-to`; you may suggest the user merge those two families).

**Hub/chain check** (same single-linkage caveat as the category skill): a
`confidence: "low"` family (`max_distance` > 2× threshold) may be string-chained
across two meanings — treat as "probably split," not "probably reject."

**Directional-antonym trap (critical — string tightness ≠ semantic safety).**
String grouping is blind to *direction*: it groups `sequel-to` with `prequel-to`
(and would group `predecessor`/`successor`, `supersedes`/`superseded`) at
`confidence: high`, because they're spelled almost identically — but they are
**opposites**. Folding them onto one canonical silently reverses half the edges.
`collect_relations` detects these and emits `suggested_canonical: null` plus a
`warning` field. For any family with a `warning` / null suggestion: **never
approve as-is.** Propose **(C) Split** — put each direction under its own
canonical (e.g. keep `sequel-to` and `prequel-to` separate) — or **(B)** remap
the whole family to a *non-directional* canonical (`part-of` or `related-to`)
where direction doesn't matter. Surface the reversal risk to the user explicitly.

Never silently drop a rogue relation from review. Every cluster and singleton
gets a Phase 3 turn.

### Phase 3 — ask the user, one family at a time, via `AskUserQuestion`

`TaskCreate` to enumerate clusters then singletons (in file order); walk one at a
time. For each, show: member relation(s) + edge counts + a couple of
`sample_notes`, the `suggested_canonical`, and Claude's Phase-2 opinion side by
side.

```
Family 44680695af70  (6 relations, confidence: medium)
Deterministic suggestion: canonical = "complements" (198 edges)
Claude's read: companion/expansion resources — keep "complements" as a new
canonical (the 5-set can't express "goes with"), fold the rest in.

Members:
  - complements             198   e.g. "GM screen provides quick-reference tables that expand on…"
  - complementary            25
  - complementary-version    19
  - complementary-to         16
  - complementary-resource    4
  - supplements               1

A) Approve merge -> "complements"   (promotes it to a canonical relation)
B) Different canonical (type it — e.g. an existing "related-to", or another name)
C) Split — not all the same; ask me about subgroups
D) Reject — leave these relations as-is
E) Ignore forever (don't ask again)
```

For a **singleton**, present the same way with one member; the natural choices
are B (map to a canonical, e.g. `variant-of` → `duplicate-of`) or D (leave it).

**Hard rule: every merge requires explicit user confirmation before being
written to `link_decisions.json`.**

Before the walk, read any existing `reports/consolidation/link_decisions.json`
and drop any family/singleton whose `id` is already a key (any status) —
resumability.

`TaskUpdate` completed after each decision.

### Phase 4 — persist every decision immediately (resumable)

Write `reports/consolidation/link_decisions.json`, keyed by each family's/
singleton's `id`. **This schema is the exact contract `apply_relations()`
reads.** The skill has no `Write`/`Edit`, and the file is updated once per
decision, so always **read-merge-write** via a Python one-liner over `Bash`
(never `echo > file`, which clobbers prior decisions):

```bash
cd <drive-tagger-repo> && python3 -c "
import json, sys
from pathlib import Path
path = Path('reports/consolidation/link_decisions.json')
decisions = json.loads(path.read_text()) if path.exists() else {}
decisions.update(json.loads(sys.argv[1]))
path.write_text(json.dumps(decisions, indent=2), encoding='utf-8')
print(f'{len(decisions)} total decisions.')
" '{"44680695af70": {"status": "approved", "canonical": "complements", "sources": ["complementary", "complementary-version", "complementary-to", "complementary-resource", "supplements"], "decided_at": "2026-07-04T09:00:00"}}'
```

(No `drive-tagger` import → plain `python3`, no `uv run`.)

```jsonc
{
  "<id>": {
    "status": "approved | rejected | ignored | split",
    "canonical": "relation string — required iff approved",
    "sources": ["rogue relation", "..."],  // required iff approved; the
                                            // relations folding INTO canonical.
                                            // canonical may be included or
                                            // omitted — merge_relations filters
                                            // it out either way.
    "decided_at": "ISO 8601 timestamp",
    "note": "optional rationale"
  }
}
```

`apply_relations()` acts only on `status == "approved"` (reading `status`,
`canonical`, `sources`); every other status is inert but must be present as a key
for resumability.

Per option:

- **(A) Approve** → `{"status":"approved","canonical":<suggested>,"sources":<the other members>,"decided_at":<ts>}`. If the suggested canonical is itself a rogue relation, this *promotes* it (expands the vocabulary).
- **(B) Different canonical** → same, `canonical` = the typed relation (a
  canonical-5, or any name). Folds the whole family onto it.
- **(C) Split** →
  1. Mark the original id `{"status":"split","decided_at":<ts>}` immediately.
  2. Walk subgroups via `AskUserQuestion` scoped to this family's members.
  3. Each approved subgroup → a **new** `approved` entry keyed by the subgroup's
     own id, computed with the real hash (never reimplemented):
     ```bash
     cd <drive-tagger-repo> && uv run python -c "
     from drive_tagger.consolidate import _cluster_id
     print(_cluster_id(['relation-a', 'relation-b']))"
     ```
     Pass the member relation strings verbatim from `link_clusters.json`.
- **(D) Reject** → `{"status":"rejected","decided_at":<ts>}`. Relations left as-is.
- **(E) Ignore forever** → `{"status":"ignored","decided_at":<ts>}`.

Write after **every** decision.

### Phase 5 — apply (back up the graph first — apply is destructive)

```bash
cd <drive-tagger-repo> \
  && cp -a data/graph.sqlite "backups/graph-pre-linkcons-$(date +%Y%m%d-%H%M%S).sqlite" \
  && DT_EMBED_PROVIDER=dgx DT_EMBED_DIM=1024 uv run drive-tagger consolidate apply-links
```

(Defaults to `reports/consolidation/link_decisions.json`.) `apply_relations()`
rewrites each approved family's source relations via `graph.merge_relations`,
deduping edges that collide on `UNIQUE(src,dst,relation)`, then regenerates
`reports/` (the `## Relations` table in `DRIVE-TAGS.md` is your verification
surface). Report back: which families merged into which canonical, how many
edges were rewritten vs deduped, and skip counts.

**Restore** (if a merge was wrong): `cp -a backups/graph-pre-linkcons-<ts>.sqlite data/graph.sqlite`.

## Important conventions

- **Never batch-write `link_decisions.json`.** Persist after each decision —
  resumability.
- **Don't reimplement `_cluster_id`.** Shell out to the real function (split
  flow) so synthesized subgroup ids match a future `collect-links` run.
- **A family's `id` derives purely from its member relation names** (sorted,
  lowercased, sha256, 12-hex) — the resumability mechanism.
- **Review singletons too** — they are rogue relations, not clean leftovers.
- **The vocabulary may grow** — promoting a high-signal rogue to a canonical is a
  valid, encouraged outcome, not a failure to "clean up."

## Why this design

`collect_relations()` and `apply_relations()` are pure, reviewable, re-runnable
code — no LLM in either. The only LLM touch is Phase 2's opinion and Phase 3's
presentation, always gated by explicit `AskUserQuestion` confirmation. Choosing
which relations are "the same" is a precision decision, so it gets a human
checkpoint before the graph is mutated — matching the project's global
LLM-pipeline rule and the `/drive-consolidate` sibling.
```
