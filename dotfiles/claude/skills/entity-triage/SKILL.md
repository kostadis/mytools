---
name: entity-triage
description: >
  Walk the UNKNOWN-surface-form queue emitted by CampaignGenerator's
  `registry.py triage-candidates` — proper nouns that appear in session outputs
  but aren't in the entity registry yet. For each candidate the GM decides:
  new entity, alias of an existing entity, not-an-entity, or defer. Positive
  rulings are written to docs/entity_registry.yaml through validated CLI verbs;
  not-an-entity/defer rulings live in a resumable skill-side state file so they
  don't re-surface. Invoke as /entity-triage [campaign-dir].
tools: Read, Write, Bash, AskUserQuestion, ToolSearch
---

# Entity Triage

Reconcile the campaign entity registry with the proper nouns that actually show
up in play. `registry.py triage-candidates` diffs the proper nouns in a
campaign's session outputs (summaries, scene extractions, merged facts, and
optionally a bible) against `docs/entity_registry.yaml` and emits a queue of
**UNKNOWN surface forms** — names/spellings the registry has never seen. This
skill walks that queue with the GM and records each decision.

## Why this exists

`triage-candidates` deliberately does **not** decide who is who — identity is a
scope decision, not a rendering decision (the repo's LLM Pipeline rule). It only
*surfaces* candidates and, for each, a `near_miss` hint (the closest existing
registry name, by string similarity). This skill is the human checkpoint: it
gathers evidence (a 5etools lookup, campaign-context lookups, the near-miss
hint), **recommends**, and then renders the GM's confirmed decision into a
deterministic, validated registry write. The hint and the 5etools verdict are
evidence for the GM — they are never auto-applied.

## The four rulings (and their write-backs)

Every candidate resolves to exactly one of:

| Ruling | Meaning | Write-back |
|---|---|---|
| **New entity** | A real entity the registry is missing | `registry.py add <dir> --name S --type T --yes` |
| **Alias of N** | A variant/typo/honorific of an existing entity N (the `near_miss` case) | `registry.py alias <dir> --to "N" "S"` |
| **Not an entity** | A generic noun, monster/spell/item type, scene role, or VTT artifact | skill-side state (`ignored`) — **no registry write** |
| **Defer** | GM isn't sure yet | skill-side state (`deferred`) — no registry write |

Special sub-case — **distinct-but-similar** (S looks like near-miss N but is a
*different* character, e.g. `Khalessa` vs `Khelessa Draga`): rule it **New
entity**, AND run `registry.py mark-distinct <dir> "S" "N"` so the near-miss
stops re-suggesting the pair on future runs.

Special sub-case — **do NOT register a bare race/collective as a global entity**: when
a candidate is a *people/race or generic collective* (`Derro`, `Myconid`, `Duergar`,
`Drow`, `Kuo-toa`, "the guards", "the cultists"), registering the bare name is the
**wrong** move — it makes the name a *global* known bundle, so `facts_to_state`
collapses every occurrence across the whole campaign into one place-blind dossier. What
you almost always want is the opposite: the same race is a *distinct faction in each
place*, and `facts_to_state` produces that for free — any subject that is **not** a
registry known-name is **location-scoped** into per-place bundles (`Derro (Gracklstugh)`,
`Myconid (Neverlight Grove)`, `Drow (Velkynvelve)`). So rule these **Not an entity**
(registry-wise) — leave them unregistered so location-scoping handles them — and if a
race name *is* already registered (or would otherwise read as known), add it to the
campaign's `--exclude-names` file (e.g. `docs/ensemble/location_scoped_races.md`) to
force location-scoping. You **cannot** register `Derro of Gracklstugh` and have it catch
Gracklstugh-derro facts: known-name matching is by *bare subject*, and the location split
is derived from where each fact occurs, not from a registry name. Register a race
globally only if you truly want one campaign-wide monolith (rare). *(GM ruling, OOTA
2026-07-13 — adding bare `Derro`/`Myconid` globalized them and collapsed the built-in
location-scoping; reverted. Corrects an earlier draft of this note that wrongly said
"add it location-qualified.")*

Special sub-case — **bare fragment of an already-registered multi-word name**
(e.g. `Wester` when `Harbin Wester` is registered, `Coster` when
`Lionshield Coster` is registered): `near_miss` frequently **misses these
entirely**. It scores whole-normalized-string similarity (`SequenceMatcher` on
`"wester"` vs `"harbinwester"`), which a short fragment of a long multi-word
name clears far less often than the near-miss threshold — so don't trust
`near_miss: none` alone to mean "no relationship to anything registered." For
any candidate with no `near_miss`, also check by eye whether it's a substring /
last-word / surname match against a registered name (skim `entity_registry.yaml`,
or grep it for the candidate); route a hit into the Converse lane even without
a hint.

Once you've found the candidate registry match, still **calibrate before
recommending alias** — a bare-word match is not enough on its own:
- **Distinctive word (surname, uncommon term)** — `Wester`, `Hallwinter`,
  `Coster`, `Yimek`(→`Yeemik`) — high confidence, recommend alias.
- **Ordinary English word that happens to be the tail of a registered name** —
  `Exchange` (of "Phandalin Miner's Exchange"), `Alliance` (of "Lords'
  Alliance"), `Enclave`, `Gauntlet`, `Trail`, `Manor`, `Coast`, `Tavern`,
  `Orchard`, `Hideout` — **too risky to alias from the bare match alone**, even
  with matching session-source context. A session mentioning "the alliance" or
  "an orchard" is far more likely using the word in its ordinary sense than
  invoking the registered proper noun. Default recommendation is **not an
  entity**, not alias — this reverses the instinct "it's a substring match, so
  it's probably the same thing." (GM correction, Obelisk 2026-07-18 — an
  earlier pass in this same run over-recommended alias for exactly this
  category before being corrected.)

Special sub-case — **fragment plausibly names a known family/group, but no
single registered entity is the right alias target** (e.g. `Dendar` — a likely
VTT mishearing of `Dendrar`, but the registry has four individually-registered
Dendrars — `Thel`, `Mirna`, `Nars`, `Nilsa` — and none of them alone is "the"
answer): don't force-alias to one arbitrary member. Rule it **New entity**,
type `faction`, name it as the collective (e.g. "Dendrar family"), and alias the
fragment to *that*:
```bash
python registry.py add <dir> --name "Dendrar family" --type faction \
  --aliases "Dendar" --provenance on_the_fly --yes
```

**Never put a not-an-entity into the registry.** `rejected_aliases` means "these
≥2 names are not aliases of *each other*" — a different claim from "this surface
form isn't an entity at all." Non-entities belong in this skill's state file, so
`triage-candidates` keeps surfacing them but this skill filters them out.

## Required information

1. **Campaign dir** — from the invocation arg, else the CWD if it contains
   `docs/entity_registry.yaml`, else ask. Resolve to an absolute path.
2. The registry must exist. If `docs/entity_registry.yaml` is absent, tell the
   GM to run `registry.py init <dir>` (and the importers) first — this skill
   triages against an existing registry; it does not bootstrap one.

If `AskUserQuestion` is not loaded, run `ToolSearch` with
`query: "select:AskUserQuestion"` first. Validation gotcha: every question needs
≥2 options. Always include a **"not an entity / scene-scoped"** and a **"defer"**
escape hatch — the GM must never be forced to classify something as a real
entity.

## Workflow

### Phase 0 — Pre-flight

1. Resolve the campaign dir; confirm `docs/entity_registry.yaml` exists.
2. **Check for `docs/party.yaml` (or `config/party.yaml`) — do not assume it exists.**
   `triage-candidates` only excludes PC/sidekick names if this file is present
   (`campaignlib.party.load_pc_names`); nothing bootstraps it automatically. If
   it's missing, generating the queue anyway will surface every PC/sidekick
   name (first name, full name, and any title/surname fragment separately —
   see the note in Phase 1) on *every* run, forever, not just this one. Before
   generating the queue:
   - Look for a source of campaign-original names: a module-inventory-style
     glossary's "campaign-original names" appendix, `docs/party.md`, or ask the
     GM directly.
   - Build `docs/party.yaml` as `characters: [{name: "..."}, ...]`. **List every
     surface form separately**, not just the full name — `Registry.known_names()`
     applies a multi-word first-token expansion to *registry* entities but
     **not** to `party.yaml` names passed in via `extra`, so `"Zenvon Foreput"`
     alone will not suppress a bare `"Zenvon"` candidate. For a PC "Zenvon
     Foreput", list both `"Zenvon Foreput"` and `"Zenvon"` (and any other form
     actually seen in play).
   - This is additive, not a blocker — if the GM wants to proceed without one,
     that's fine, but flag that PC names will need per-run `ignored` rulings
     instead of a permanent fix.
3. **Load or create the state file** at `<campaign-dir>/docs/.entity_triage_state.json`:
   ```json
   {
     "started_at": "ISO-8601",
     "updated_at": "ISO-8601",
     "ignored":   [{"surface": "Narrator", "norm": "narrator", "reason": "VTT artifact", "at": "ISO-8601"}],
     "deferred":  [{"surface": "the Pale Cloak", "norm": "thepalecloak", "note": "maybe a title?", "at": "ISO-8601"}],
     "resolved":  [{"surface": "Ilvarra", "ruling": "alias", "target": "Ilvara Mizzrym", "at": "ISO-8601"}]
   }
   ```
   `ignored` and `deferred` are the "don't re-ask me" lists. `resolved` is an
   audit log of registry writes made through this skill (handy on resume; the
   registry itself is the source of truth). Use `date -u +%Y-%m-%dT%H:%M:%SZ`
   for timestamps.
4. **Generate a fresh queue** (do not reuse a stale one — the registry may have
   changed since last run):
   ```bash
   python registry.py triage-candidates <campaign-dir> --out <campaign-dir>/docs/.triage_queue.json [--bible path/to/bible.md] [--min-count 2]
   ```
   Run from the campaign workspace (config auto-detects). `--min-count 2` is a
   good default to drop one-off mentions; confirm with the GM if the queue is
   huge or tiny. Both `.triage_queue.json` and `.entity_triage_state.json` are
   transient/local — suggest gitignoring them.

### Phase 1 — Load and subtract

Read `.triage_queue.json`. Its shape:
```json
{ "campaign": "...", "generated_from": ["summaries/..."],
  "candidates": [
    { "surface": "Ilvarra", "norm": "ilvarra", "count": 7,
      "sources": ["summaries/s03/session-summary.md"],
      "near_miss": { "name": "Ilvara Mizzrym", "ratio": 0.91 } } ] }
```
Subtract by `norm` every candidate already in the state file's `ignored` or
`deferred` lists. PCs *should* already be excluded upstream — `triage-candidates`
unions `party.yaml` names into "known" — but that only works if Phase 0 found a
complete `party.yaml`. If PC/sidekick names or fragments of them (first name,
title) still show up, don't register them: report it, and either fix
`party.yaml` (preferred — permanent, benefits every future run) or `ignore` them
in the state file this run and move on. Either way, never add a PC as a new
registry entity.

Also watch for **real out-of-fiction people's names** — a player's real name or
the GM's own name, typically from VTT speaker-diarization labels bleeding into
the fact corpus (e.g. "Nikhil", "Reddy", "Kostadis"). These are not PCs and
don't belong in `party.yaml` either — they're a `not an entity` case (see
Phase 3a), same bucket as "Narrator".

Report a one-line summary: `N candidates (M with near-miss hints); K suppressed
by prior rulings.` Then begin — do not dump the full list.

### Phase 2 — Auto-classify with 5etools (evidence, not decision)

For each remaining candidate, check whether the surface form matches a
**published generic entry** — a monster/creature type, spell, item, or condition
name — in the 5etools data. A match is strong evidence the form is *generic*
(e.g. `orc`, `fireball`, `longsword`) rather than a campaign-specific proper
noun (e.g. `Grazzt`, `Ilvara`).

- **Backbone (always available, deterministic):**
  ```bash
  python fivetools_catalog.py search "<surface>" --limit 5
  ```
  from the CampaignGenerator dir. It emits JSONL hits, each with a `type`
  (`monster`, `spell`, `item`, `condition`, …), `name`, and `score`. A
  high-score hit whose `name` matches the surface form and whose `type` is a
  generic category is strong evidence the form is generic. This is the local,
  deterministic answer to the GM's "is `orc` a monster or a name?" question,
  over the same 5etools data the MCP serves.
- **Optional accelerator:** the per-campaign 5etools MCP (`launch_5etools_mcp.py`)
  may also be connected — discover its tools via `ToolSearch query: "mcp__5etools"`.
  Its confirmed surface is source/TOC/section (`list_sources` / `get_toc` /
  `get_section`), which is **not** a name lookup; only use the MCP for this check
  if it exposes a name/bestiary search tool. If it doesn't, don't force it — the
  catalog backbone already answers the question.
- Record a per-candidate `generic?` verdict: `yes` (matches a published type),
  `no` (no match), or `unknown` (couldn't check). **Never block on tooling** —
  if the catalog can't be built (no 5etools data resolved) and the MCP has no
  lookup, mark `unknown` and let the GM decide from count/sources alone.

This is evidence-gathering. A `generic?: yes` verdict *suggests* "not an entity"
but does not decide it — a campaign can name an NPC "Orc" ironically. The GM
rules.

**Partition the queue into two lanes:**

- **Batch lane (shallow):** candidates with **no `near_miss`** *and no
  by-eye fragment match against the registry catalog* (see the bare-fragment
  sub-case above) — either `generic?: yes` (likely not-an-entity) or clearly a
  fresh proper noun (likely new entity). These are low-ambiguity; batch them.
- **Converse lane (stakes):** candidates **with a `near_miss` hint** (alias vs
  distinct-but-similar is a precision call), candidates that look like a bare
  fragment of a registered multi-word name even with `near_miss: none` (the
  algorithm's blind spot — see above), `generic?: unknown` on a high-`count`
  form, or anything spanning many sources. These get one-at-a-time reasoning.

### Phase 3a — Batch lane

Present 3–5 candidates per `AskUserQuestion`, one question per candidate, each
annotated with the evidence:

```
Candidate: "Narrator"  (count 12, in 4 sources; 5etools: no; near-miss: none)
Options:
  [ Not an entity ]  VTT/scene artifact — ignore, don't re-ask
  [ New entity ]     real entity the registry is missing (you'll pick a type)
  [ Defer ]          decide later
```
For a `generic?: yes` form, lead with **Not an entity**; for a fresh proper noun,
lead with **New entity**. Always include **Defer**. When the GM picks **New
entity**, ask its type in a follow-up (see Phase 3c).

### Phase 3b — Converse lane (near-miss / high-stakes)

One candidate at a time, like `ensemble-alias-review`:

1. **Gather context.** Look up both the candidate `S` and its `near_miss` name
   `N` in campaign docs (use the `mcp__campaign__*` tools if connected —
   `grounded_search`, `quick_search`, `search_document` — else read
   `docs/world_state.md`, `docs/planning.md`, dossiers). Note the 5etools verdict.
2. **Recommend**, with reasoning and a confidence level:
   ```
   ## "Ilvarra" vs registry "Ilvara Mizzrym"  (near-miss ratio 0.91)
   count 7 · sources: summaries/s03 · 5etools: no match

   Verdict: Alias of "Ilvara Mizzrym"  (high confidence — one-char VTT typo,
   same scenes ch. 3)
   ```
   Confidence bands: **high** (typo/VTT variant, same role/scenes) → recommend
   alias; **medium** (plausible variant, thin context) → recommend but flag;
   **low** (similar string, different role — retcon/namesake risk) → recommend
   distinct-but-similar, flag explicitly.
3. **Decide** via `AskUserQuestion` (≥2 options):
   - `Alias of N` → `registry.py alias <dir> --to "N" "S"`
   - `Distinct entity (looks like N, isn't)` → `add` as new **+**
     `mark-distinct <dir> "S" "N"`
   - `New unrelated entity` → `add` as new
   - `Not an entity` / `Defer`
   Offer "look up more context" as a natural-language path before deciding.

### Phase 3c — Executing a decision

Immediately run the matching CLI write (from the campaign workspace so config
auto-detects), then update the state file:

- **Alias of N:**
  ```bash
  python registry.py alias <dir> --to "Ilvara Mizzrym" "Ilvarra"
  ```
- **New entity** (ask type first — one of `npc location faction item deity event
  concept`; offer `--provenance module|supplement|on_the_fly` if known):
  ```bash
  python registry.py add <dir> --name "Sirac" --type npc --yes
  ```
- **Distinct-but-similar:** the `add` above, then:
  ```bash
  python registry.py mark-distinct <dir> "Sirac" "Sarith Kzekarit"
  ```
- **Not an entity:** append to state `ignored` (surface + norm + short reason).
  No registry write.
- **Defer:** append to state `deferred` (surface + norm + optional note). No
  registry write.

Each CLI verb validates before writing (they route through
`campaignlib.registry.validate`); if one errors (e.g. a collision the GM didn't
expect), surface the message and re-ask rather than forcing it. After each
decision (or each batch), **write the state file immediately** — the session is
resumable at any point. Confirm in one line, e.g. `✓ Ilvarra → alias of Ilvara
Mizzrym`.

### Phase 4 — Finish

When the queue is exhausted (or the GM says stop):

1. Report a tally: entities added, aliases attached, distinct pairs recorded,
   ignored, deferred.
2. Run `registry.py project <dir>` **before** `registry.py check <dir>`, not
   after — `project` regenerates `aliases.json`/`entity_inventory.md` from the
   registry, and `check` partly diffs against those same projected files. If
   `check` runs first, edits from this session (aliases attached, entities
   renamed) show up as false-positive drift against the *stale* projection,
   not real problems. `check` afterward confirms the new writes didn't
   introduce grouping drift or a fuzzy near-dup against `docs/ensemble/aliases.json`
   or similar legacy stores.
3. Leftover `deferred` entries persist for the next run; `ignored` entries keep
   those surface forms out of future queues.

## Renaming an existing registry entity (adjacent, not a candidate ruling)

This comes up when a GM ruling elsewhere (e.g. a module-inventory glossary's
"Rulings" section) says an already-registered entity's canonical name should
change — not a triage candidate at all, but the natural next step once you
notice the old name collides with something out-of-registry. `registry.py` has
**no dedicated rename verb**. The closest tool, `merge`, always keeps the folded
name as a **resolving alias** of the target:
```bash
python registry.py add <dir> --name "Tuck Stonehill" --type npc --yes
python registry.py merge <dir> "Pip" --into "Tuck Stonehill"
# registry now resolves "Pip" -> Tuck Stonehill
```
That's correct when the old name is just a spelling/form variant that should
keep working (the usual case). It's **wrong** when the old name needs to stop
resolving to the renamed entity going forward — e.g. "Pip" was the module NPC's
name, but at this table "Pip" unqualified always means a *different*, real,
intentionally-unregistered entity (a PC sidekick), so aliasing "Pip" → the
renamed module NPC would make the registry actively misattribute future session
facts. Confirm this distinction with the GM before deciding which way to leave
it — don't assume "keep the alias" is always right just because `merge` is the
only rename-shaped verb.

If the alias must be dropped, there's no CLI verb for that either — go through
the same validated load/save API every verb uses, since hand-editing the YAML
skips `validate()`:
```python
from pathlib import Path
from campaignlib.registry import load_registry, save_registry

path = Path("<dir>/docs/entity_registry.yaml")
reg = load_registry(path)
target = next(e for e in reg.entities if e.name == "Tuck Stonehill")
target.aliases = [a for a in target.aliases if a != "Pip"]
save_registry(reg, path)  # re-validates before writing
```

## Do not

- **Auto-decide a near-miss.** Alias-vs-distinct is a precision call — always
  present reasoning and let the GM rule. `near_miss` is a hint, not a verdict.
- **Write a non-entity into the registry.** Generic nouns / scene roles / VTT
  artifacts go to the state file's `ignored` list, never `add` or
  `rejected_aliases`.
- **Skip the generic-noun check for a plausibly-generic form** just because
  it's quick to guess — run `fivetools_catalog.py search`; but mark `unknown`
  and move on if no 5etools data resolves. Never block on tooling.
- **Reuse a stale queue.** Regenerate `triage-candidates` at the start of each
  run so it reflects the current registry.
- **Re-add a PC.** PCs come from `party.yaml` and are excluded upstream *only if
  that file exists and lists every surface form seen in play* — check for it in
  Phase 0 rather than assuming; if a PC/sidekick name (or a real person's name)
  appears in the queue anyway, report it and fix `party.yaml` — don't register
  it as a new entity either way.
- **Recommend alias just because a candidate is a substring of a registered
  name.** Check whether the matched fragment is a distinctive word (surname,
  uncommon term) or ordinary English vocabulary first — ordinary words default
  to **not an entity** even on an exact tail match (see the bare-fragment
  sub-case above).
- **Edit `entity_registry.yaml` by hand.** All writes go through the `registry.py`
  verbs, or (only when no verb covers the operation, e.g. dropping a single
  alias) the same validated `campaignlib.registry.load_registry`/`save_registry`
  API every verb uses — never a raw YAML edit that skips `validate()`.
