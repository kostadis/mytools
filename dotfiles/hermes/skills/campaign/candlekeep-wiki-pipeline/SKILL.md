---
name: candlekeep-wiki-pipeline
description: "Build persona-voiced wiki from campaign chapters."
---

# Candlekeep Wiki Pipeline

Multi-agent pipeline that turns large D&D campaign chapter corpora (100k+ words each) into an in-world, persona-voiced, fact-checked markdown wiki. First used for stormgiants + out-of-the-abyss + Phandalin -> ~/histories (July 2026).

## When to use
- User wants a "wiki", "history", "chronicle", or persona-reviewed synthesis of one or more campaigns' `docs/chapters/` files.
- Corpus is too large for one context (>100k words) — the digest layer is mandatory.
- ALSO works with non-chapter corpora: the OOTA run (July 2026, ~/histories/oota-dossiers) used 456 augmented entity dossiers (npc_/faction_/location_/object_/monster_*.md with [chNN]-tagged per-chapter notes). Split Phase 1 digesters BY ENTITY TYPE instead of by campaign (npc | faction+location | object+monster), and tell them to prioritize (EVENT)-tagged lines + the original dossier body and dedupe the redundant note lines. Digesters can then process 100+ files in ~10 tool calls via a scripted condensation pass (batch `cat`/python, not per-file reads).

## Architecture (3 phases, all via delegate_task)

### Phase 1 — Digesters (one leaf agent per campaign, parallel, max 3)
Each reads ALL chapter files and writes `<outdir>/_digests/<campaign>_digest.md` with FOUR sections:
1. Chronological EVENT list, one bullet per event, tagged `[ch: chapter_NN_...md]`
2. NPC roster (1-3 factual sentences each, chapter citations)
3. LOCATION gazetteer (citations)
4. FACTIONS/organizations and arcs
Factual/neutral, 6000-10000 words. The citations are the backbone of Phase 3 verification — insist on them.

### Phase 2 — Scholar personas (parallel leaf agents)
Each persona reads ONLY the digests (never raw chapters), preserves all `[ch:]` citations, chooses its own topics, and writes opinion blocks clearly fenced from fact (e.g. "**Historian's Assessment**", signed "— The X of Candlekeep").
Proven personas: Historian (chronology + events + NPCs), Geographer (gazetteer + regional essays), Diabolist (fiends + corrupted mortals). Adapt personas to the user's request.
Prompt each with: campaign chronological order, digest paths, "do not invent events not in the digests", output paths, and the persona voice description.

### Phase 3 — Arbiter (single agent, after Phase 2)
The First Book Reader (or equivalent): spot-checks 10-15+ factual claims PER scholar by grepping citations against the digests. Rule: **verify events, not interpretations** — flag miscitations/unsupported facts only, never overrule opinions. Writes:
- `first_reader_verification.md` (per-scholar claim tables + reliability verdicts)
- `first_reader_decision.md` (formal canon admission, synthesis of agreements/disagreements, own judgment)
- `index.md` (front page: in-world framing + linked TOC with one-line persona descriptions)

## Critical pitfalls (all hit in the first run)
1. **Subagent iteration limit (~50 calls)**: agents reading 60-86 chapters WILL hit it before writing the digest. Instruct every digester to save incremental per-chapter notes to `<outdir>/_digests/_notes_<campaign>.md` as it reads. On failure, dispatch a FINISHER agent: "read the notes file, determine last chapter covered, read only the remainder, write the digest." Do not restart from scratch.
2. **Large write_file stalls**: single writes >~30KB stall the subagent's stream. Tell every writer agent up front: compose big files as /tmp pieces and `cat` them together.
3. **Terminal restart kills in-flight delegations** (signals 1/15): background delegations are not durable. Notes files on disk are the recovery mechanism — after a restart, check what exists on disk and re-dispatch finishers.
4. **Citation format drift**: agents emit `[ch: ...]`, `(chapter_NN...)`, `(chNN)`. Warn the arbiter to grep for all variants.
5. **Filename/header off-by-one**: chapter filenames may be one number ahead of internal H1s. Standard: cite by FILENAME.
6. **Safety refusals on dark personas**: some models (e.g. tencent/hy3) refuse Phase 2 prompts framed as "Diabolist ... scholar of fiends and corruption". Refusals show as instant completions (~12s, 2 api_calls) with a decline message. OOTA-run escalation ladder (in order): (a) reframe as "TASK TYPE: creative-writing documentation for a tabletop D&D game (fully fictional, published WotC adventure)" with personas as fictional in-game scholar characters and softened names ('Keeper of Forbidden Lore') — this MAY NOT be enough; hy3 refused even the softened version 3x while letting the Geographer through (which persona slips past is luck). (b) Have the user add a fallback model (`hermes fallback add`) and re-dispatch with the ORIGINAL persona framing — a capable fallback handles "Diabolist" fine. (c) If the fallback 503s on capacity (instant fail, HTTP 503 after retries), don't keep re-dispatching: the parent agent should write the remaining files ITSELF — it already has the digests in context from verification reads, and refusals never happen in the parent session. Note results per-persona: partial batches are normal; re-dispatch only the refused/failed tasks, never the whole batch.
7. **Distinguish refusal vs capacity failure**: both look like fast completions. Refusal = 2 api_calls + decline text (often in the model's home language). 503 = "API call failed after 3 retries: HTTP 503". Refusal → change framing or model; 503 → wait, retry, or write in-parent. Retrying a refusal with the same model/prompt is wasted work after 2 attempts.

## Verification checklist
- `wc -w` every deliverable; digests 6-10k words each.
- Confirm arbiter found no fabricated events; surface its miscitation flags to the user.
- Final report: full file listing with word counts, entry point = index.md.
- If the parent wrote any persona files itself (pitfall 6c), disclose that and note they may be shorter than delegated ones; offer expansion.

## Upstream: building augmented dossiers (OOTA pattern)
If the corpus is raw entity dossiers + per-chapter merged.json fact lists, first run a no-LLM augmentation script (see ~/oota-augment/augment_dossiers.py): for each dossier, keyword-match facts by frontmatter name tokens, skip facts already verbatim in the dossier, dedupe, and emit sidecar files "original + '## Per-Chapter Notes'" with lines `- [chNN] (EVENT|non-event: type) fact — subject: X`. Sources stay read-only. The (EVENT) tags and [chNN] labels are exactly what the digesters need.
