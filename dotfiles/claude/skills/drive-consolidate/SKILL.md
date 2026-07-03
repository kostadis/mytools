---
name: drive-consolidate
description: Review and merge near-duplicate categories produced by drive-tagger's deterministic pipeline. Interactive, one cluster at a time. Invoke as /drive-consolidate.
tools: Read, Bash, AskUserQuestion, TaskCreate, TaskUpdate
---

# Drive Consolidate

A drive-tagger pipeline run is deliberately liberal about creating categories
— over-generation is cheaper to fix after the fact than under-generation is
to detect. This skill runs the post-run cleanup: deterministically cluster
near-duplicate categories, review each cluster with the user one at a time,
then apply the approved merges.

"Claude" below means this Claude Code session, driven by `AskUserQuestion`.
There is no Anthropic API client anywhere in this flow and nothing here talks
to Drive directly — `consolidate.py` only touches the local turbovecdb store.

## Required inputs

Detect or ask:

1. **drive-tagger repo path** — the directory containing `pyproject.toml` and
   `src/drive_tagger/`. `mytools/` itself has no root `pyproject.toml`; every
   `uv run drive-tagger ...` / `uv run python ...` invocation below must `cd`
   into the drive-tagger repo first, or it will fail to find the project.
2. **Embedding config for the real store** — the existing `data/db` on disk
   was built with `DT_EMBED_PROVIDER=dgx` (1024-dim `qwen3-embedding:0.6b`
   vectors). The default config is `DT_EMBED_PROVIDER=local` (384-dim
   MiniLM) — opening the real store under the default config is a dimension
   mismatch, not a graceful fallback. **Every command below that touches the
   store must be prefixed** with:
   ```bash
   DT_EMBED_PROVIDER=dgx DT_EMBED_DIM=1024
   ```
   (Confirm with the user if they're pointing at a different `data/db` built
   under a different provider — adjust accordingly. Don't silently guess.)

## Workflow

### Phase 1 — collect (deterministic, no LLM)

```bash
cd <drive-tagger-repo> && DT_EMBED_PROVIDER=dgx DT_EMBED_DIM=1024 \
  uv run drive-tagger consolidate collect
```

Read `reports/consolidation/clusters.json`. Its shape:

```jsonc
{
  "generated_at": "...", "threshold": 0.05, "embed_provider": "dgx",
  "clusters": [
    {
      "id": "7c3a1f9e2b04",              // 12-hex _cluster_id — see Phase 4
      "members": [
        {"name": "...", "member_count": 130, "sample_docs": ["...", "..."]}
      ],
      "suggested_canonical": "...",       // highest member_count, ties broken by name
      "confidence": "high | medium | low",
      "reason": "cosine<=0.0500, intra-cluster [0.0002, 0.0047]",
      "min_distance": 0.0002, "max_distance": 0.0047
    }
  ],
  "singletons": [{"name": "...", "member_count": 0}]
}
```

`clusters` is already sorted highest-yield-first (confidence high→low, then
tightness). Walk it in that order in Phase 3 — don't re-sort.

**Sanity check** (mirrors vtt-spell-pass's `known_names_count` check): let
`n = singletons.length + sum(len(c.members) for c in clusters)` (total
categories reviewed). If `clusters` is empty and `n` is large (say >50),
something is wrong with the threshold or the data — say so and stop rather
than telling the user "nothing to review." If `n` itself is tiny (<20), there
may genuinely be nothing worth consolidating yet — that's a fine outcome, say
so and stop.

### Phase 2 — Claude pre-classifies each cluster (minimal filtering, surface when in doubt)

For each cluster, form an opinion before asking the user:
`agree-merge` / `regroup (split)` / `rename-canonical` / `not-a-merge`.

**Explicit hub/chain check** — this is the load-bearing mitigation for
single-linkage chaining (clustering here is transitive: A↔B↔C group even if
A and C are unrelated, as long as each edge is under threshold). Look at
`max_distance` vs `min_distance` and at the member list:

- A cluster where one member has a much higher `member_count` than the
  others **and** reads as a generic catch-all (e.g. `"Dungeons & Dragons
  Homebrew"`, `"Monster Bestiaries"`, `"Adventure Modules"`) is a likely
  **hub artifact** — the clusterer chained through it because it sits
  moderately close to many unrelated specific categories, not because those
  categories are duplicates of each other.
- `confidence: "low"` (`max_distance` > 2× threshold) is a strong hint of
  this. Treat a low-confidence hub cluster as **"probably split," not
  "probably reject"** — some sub-pairs inside it are often still genuine
  near-dupes worth keeping as their own smaller merge, even though the
  cluster as a whole isn't one coherent group.

**Bias, same as vtt-spell-pass: never silently merge distinct themes, never
silently drop a real merge candidate. When in doubt, surface it in Phase 3
rather than pre-filtering it out.** There is no auto-drop list here —
every multi-member cluster gets a Phase 3 turn. Phase 2 produces Claude's
*opinion* to show alongside the deterministic grouping; it is not a filter
that removes clusters from review.

### Phase 3 — ask the user, one cluster at a time, via `AskUserQuestion`

Use `TaskCreate` to enumerate the clusters (in `clusters.json` order — high
confidence first) so progress is trackable, then `AskUserQuestion` to walk
them one at a time.

For each cluster show: member names + `member_count` + up to 8 sample doc
names each, the deterministic `suggested_canonical` + `reason`, and Claude's
Phase 2 opinion side by side — this side-by-side IS the compare/contrast;
there's no separate proposal artifact.

```
Cluster 7c3a1f9e2b04  (3 members, confidence: high, cosine<=0.0500 intra-cluster [0.0002, 0.0047])
Deterministic suggestion: canonical = "Character Sheet Templates" (130 docs)
Claude's read: same concept, singular/plural + one synonym — clean merge.

Members:
  - Character Sheet Templates   130 docs   e.g. "Fillable PC Sheet.pdf", "Blank Character Sheet v3.pdf"
  - Character Sheet Template     31 docs   e.g. "5e Character Sheet.pdf"
  - Character Profiles            8 docs   e.g. "Character Profile Cards.pdf"

A) Approve merge -> "Character Sheet Templates"
B) Different canonical name (type it)
C) Split — not all the same; ask me about subgroups one at a time
D) Reject — keep all separate
E) Ignore forever (don't ask again)
```

**Hard rule: every merge requires explicit user confirmation before being
written to `decisions.json`.** The deterministic suggestion + Claude's
opinion are a *proposal* — the user always picks.

Before starting the walk, read any existing `reports/consolidation/decisions.json`
and drop any cluster whose `id` is already a key (any status) — this is what
makes re-invocation resumable (see Phase 4).

Mark the corresponding `TaskUpdate` completed after each decision.

### Phase 4 — persist every decision immediately (resumable)

Write to `reports/consolidation/decisions.json`, keyed by the cluster's `id`
from `clusters.json`. **This schema is the exact contract `consolidate.apply()`
reads — do not deviate from it:**

**How to write it.** The tools available to this skill are `Read` and `Bash`
— no `Write`/`Edit` — and the file is updated incrementally, once per
decision, so a naive overwrite (`echo '{...}' > decisions.json`) would
clobber every prior decision and silently break resumability. Always
read-merge-write via a short Python one-liner over `Bash`, passing the new
entry/entries as a JSON argument (one call can add multiple keys at once,
which the split flow needs):

```bash
cd <drive-tagger-repo> && python3 -c "
import json, sys
from pathlib import Path

path = Path('reports/consolidation/decisions.json')
decisions = json.loads(path.read_text()) if path.exists() else {}

new_entries = json.loads(sys.argv[1])
decisions.update(new_entries)

path.write_text(json.dumps(decisions, indent=2), encoding='utf-8')
print(f'Wrote {len(new_entries)} entrie(s); {len(decisions)} total.')
" '{"7c3a1f9e2b04": {"status": "approved", "canonical": "Character Sheet Templates", "sources": ["Character Sheet Template", "Character Profiles"], "decided_at": "2026-07-03T12:00:00"}}'
```

(Verified: running this twice with different keys accumulates rather than
clobbers.) This needs no `drive-tagger` import, so a plain `python3` is fine
— no `uv run` / venv activation required for this step, unlike the
`_cluster_id` call below, which does need the project's environment.

```jsonc
{
  "<cluster_id>": {
    "status": "approved | rejected | ignored | split",
    "canonical": "string — required iff status == approved",
    "sources": ["string", "..."],  // required iff status == approved;
                                     // members folding INTO canonical.
                                     // canonical itself may be included or
                                     // omitted — merge_categories() filters
                                     // it out defensively either way.
    "description": "optional — only used if status == approved; overwrites canonical's stored description",
    "decided_at": "ISO 8601 timestamp",
    "note": "optional human/Claude rationale string"
  }
}
```

`apply()` only acts on entries with `status == "approved"` (reading exactly
`status`, `canonical`, `sources`, `description` — nothing else); every other
status is inert to `apply()` but **must be present as a key** so Phase 1's
"skip already-decided" resumability check works on re-invocation.

Per option:

- **(A) Approve** → `{"status": "approved", "canonical": <suggested>, "sources": <all other member names>, "decided_at": <ts>}`.
- **(B) Different canonical** → same as (A) but `canonical` is the typed
  name (may be brand new — `merge_categories` creates it if it doesn't
  exist).
- **(C) Split** →
  1. Mark the **original** cluster id `{"status": "split", "decided_at": <ts>}` immediately (so it's never re-asked — `collect()` regenerates the same id from the same membership on the next run).
  2. Walk the user through naming subgroups (same AskUserQuestion pattern, scoped to this cluster's members).
  3. For each approved subgroup, synthesize a **new** entry with `status: "approved"`, keyed by the subgroup's own cluster id — computed with the **exact same hash function `consolidate._cluster_id`**, not a reimplementation. Invoke it directly rather than hand-rolling the hash in the prompt (sort-lowercase-join-sha256-truncate is easy to get subtly wrong by hand):
     ```bash
     cd <drive-tagger-repo> && uv run python -c "
     from drive_tagger.consolidate import _cluster_id
     print(_cluster_id(['Subgroup Member A', 'Subgroup Member B']))
     "
     ```
     (No `DT_EMBED_PROVIDER`/`DT_EMBED_DIM` needed here — `_cluster_id` is a
     pure hash over names, it never opens the store; verified by running it
     standalone.) Pass the subgroup's member names as they appear verbatim in
     `clusters.json` (case is normalized internally by `_cluster_id`, but
     pass them unmodified so the sort matches what a future `collect()`
     would produce for the same membership).
- **(D) Reject** → `{"status": "rejected", "decided_at": <ts>}`. Both/all
  categories stay separate. Re-running `collect` regenerates the same
  cluster id; the resumability check in Phase 3 keeps it from resurfacing.
- **(E) Ignore forever** → `{"status": "ignored", "decided_at": <ts>}`. Same
  resumability as reject; distinguished only for the user's own
  record-keeping (both are no-ops for `apply()`).

Write the file after **every** decision (not batched at the end) — if the
session is interrupted, decided clusters must not be re-asked.

### Phase 5 — apply

```bash
cd <drive-tagger-repo> && DT_EMBED_PROVIDER=dgx DT_EMBED_DIM=1024 \
  uv run drive-tagger consolidate apply
```

(Defaults to `reports/consolidation/decisions.json` when `--decisions` is
omitted.) `apply()` merges every `approved` entry via `store.merge_categories`
and then regenerates `reports/` itself — no separate `drive-tagger report`
re-run needed. Report the merge summary back to the user: which clusters
merged, into which canonical names, and how many were skipped (rejected /
ignored / split-markers / invalid).

## Important conventions

- **Never batch-write `decisions.json` at the end of the session.** Persist
  after each decision (Phase 4) — this is what makes the skill resumable
  across interrupted sessions, matching `clusters.json`'s stable `id`
  scheme.
- **Don't reimplement `_cluster_id`'s hash logic by hand.** Always shell out
  to the real function (Phase 4, split flow) so synthesized subgroup ids are
  guaranteed to match what a future `consolidate collect` run would produce
  for the same membership.
- **A cluster's `id` is derived purely from its member names** (sorted,
  lowercased, sha256, truncated to 12 hex chars) — not from cluster contents
  like `confidence` or `reason`. If the *set* of member category names is
  identical across two `collect()` runs, the id is identical too, which is
  the whole resumability mechanism.
- **Don't silently reject a low-confidence cluster.** A low-confidence /
  hub-anchored cluster is a signal to propose splitting, not a signal to
  auto-reject — auto-rejecting would silently drop real merge candidates
  buried inside a chained cluster.

## Why this design

The deterministic `collect()` step and `apply()` step are pure, reviewable,
re-runnable code — no LLM in either. The only place an LLM (this session)
touches the pipeline is Phase 2's *opinion* and Phase 3's *side-by-side
presentation*, and even there, nothing is written to `decisions.json` without
explicit `AskUserQuestion` confirmation from the user. This matches the
project's global LLM-pipeline rule: scope decisions (which categories are
"the same thing") are precision decisions, not draft/render work, so they get
a human checkpoint before the merge is ever applied to the store.
