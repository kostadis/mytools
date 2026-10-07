# entity-triage skill (~/src/mytools) — examined 2026-09-20, no edits

Location: `~/src/mytools/dotfiles/claude/skills/entity-triage/SKILL.md`
(single file, 404 lines, NO support scripts of its own — unlike its sibling
`registry-cleanup` which ships audit_aliases.py / strip_aliases.py).
There is NO skill literally named "registry-triage" — if the user says that,
they mean `entity-triage` (walks the registry triage queue); `registry-cleanup`
is the repair sibling (garblings parked as aliases).

## What it is
The interactive human-checkpoint half of campaign entity-registry maintenance.
CampaignGenerator's `registry.py triage-candidates` deterministically diffs
proper nouns from session outputs against `docs/entity_registry.yaml` and emits
a queue of UNKNOWN surface forms (surface, norm, count, sources, near_miss
hint). The skill walks the queue WITH the GM and renders rulings into
validated `registry.py` writes. It never decides identity itself.

## Core mechanics (verified against ~/src/CampaignGenerator/entity_registry/registry.py)
- Four rulings: New entity (`registry.py add`), Alias of N (`registry.py alias`),
  Not-an-entity (skill-side state, NO registry write), Defer (state only).
  Plus distinct-but-similar: `add` + `mark-distinct` so the pair stops
  re-suggesting (`_suppressed_pairs` honors distinct + rejected_aliases).
- State file `<campaign>/docs/.entity_triage_state.json`
  (ignored / deferred / resolved) — resumable, filters settled non-entities.
- Phase 0 checks `docs/party.yaml` (PC names excluded upstream via
  `load_pc_names` as `extra` to `known_names` — only if the file lists EVERY
  surface form; party.yaml gets no first-token expansion).
- Two lanes: batch (3-5 per AskUserQuestion, no hint) vs converse (one at a
  time, near-miss / high-stakes).
- Phase 4: `registry.py project` BEFORE `check` — check diffs against the
  projections, so running it first reports this session's own edits as drift.

## Design rules baked in (GM rulings, dated)
- NEVER register a bare race/collective (Derro, Myconid, Drow) — it globalizes
  the name and collapses facts_to_state's per-place location-scoping; leave
  unregistered or use the exclude-names file (OOTA 2026-07-13, self-corrects
  an earlier wrong draft).
- near_miss blind spot: bare fragments of registered multi-word names
  (Wester vs Harbin Wester) fall below the SequenceMatcher threshold —
  `near_miss: none` does NOT mean unrelated; eyeball substring/surname hits.
- But a bare-word tail match is NOT alias evidence: distinctive surname ->
  alias; ordinary English tail-word (Exchange, Alliance, Orchard) -> default
  NOT an entity (Obelisk 2026-07-18).
- Family/group fragment (Dendar -> four registered Dendars): create the
  collective as a faction and alias to that, never force-pick a member.
- No `rename` verb exists; `merge` keeps the old name as a resolving alias —
  wrong when the old name means a different entity at this table.
  Drop-alias fallback goes through campaignlib.registry load/save (validated),
  never raw YAML.

## Source-truth facts (registry.py)
- triage-candidates sources: ensemble merged.json (top-level + per_chapter)
  when present; raw summaries ONLY as legacy fallback for no-ensemble
  campaigns (summaries are upstream of the ensemble — scanning both would
  re-derive from noisy prose + archived `summaries/old`).
- near-miss = SequenceMatcher over normalized whole strings vs every
  registered name+alias, threshold-gated, GM-settled pairs suppressed.

## Discrepancies found (minor)
1. Phase 2 says run `python fivetools_catalog.py search ...` "from the
   CampaignGenerator dir" — the file lives at
   `~/src/CampaignGenerator/pipelines/rlm/fivetools_catalog.py`, NOT repo
   root; the command as written fails from the directory it names.
2. `--exclude-names` (location-scoped races) lives downstream in
   facts_to_state, not in the registry CLI — findable only via that pipeline.
