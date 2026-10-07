---
name: campaign-entity-summaries
description: Use when summarizing entity events across campaign chapters.
---

# Campaign Entity Summaries (registry → per-entity chapter digests)

Turn campaign chapter prose into one summary file per entity, organized by chapter.

## Inputs
- `docs/entity_registry.yaml` — flat list of `- name:` entries, each with optional `aliases:` and `note:`. Single source of truth for what counts as an entity.
- `docs/chapters/chapter_NN_<slug>.md` — chapter files; frontmatter has `chapter:` and `title:`; body sections are `## NN.MM <POV> <date>`.

## Workflow
1. **Parse the registry with a small hand-rolled parser** (`execute_code`) — the file is simple: `- name:` starts an entry, indented `- ` under `aliases:` appends an alias.
2. **Match each entity against each chapter**: case-insensitive regex `\b<escaped name-or-alias>\b` over lowercased text; escape spaces as literal `\ `. First matching name OR alias counts as a hit.
3. **Audit suspicious matches before trusting them** (see Pitfalls). Print the ~60-char context around each hit for borderline aliases.
4. **Read every chapter in range** before writing anything — summaries must be authored from actual content, not inferred from hit lists. Read sequentially via `execute_code` printing slices (~15–20KB per call works).
5. **Write output files** `<Entity Name>.md`, one section per chapter in numeric order: `## Chapter N: <title>` followed by bullets covering only that entity's events in that chapter. Skip chapters where the entity doesn't appear.

## Orchestration for large chapter ranges (user-preferred pattern)
When the chapter count is large (e.g. 40+), the user explicitly corrected a 3-subagent-per-range fan-out to **one subagent per chapter**, with the parent acting as orchestrator:
- Each chapter gets its own subagent writing per-entity files into `parts/chNN/` — the output dir encodes chapter order, so the merge step is trivial and ordering can never be wrong.
- **Delegation concurrency is capped at 3** for this user, so dispatch in waves of 3 (last wave may be smaller); dispatch the next wave as each returns.
- Per-chapter scoping also mitigates the iteration-limit failure mode: a range-batch subagent that burns its budget on match auditing produces NOTHING (observed: 16-chapter batch completed analysis, wrote zero files). A single-chapter agent almost always finishes its writes.
- Ranges already covered by a successful batch (e.g. 110 entity files in `parts/b/` for ch17–32) can be kept as-is; only re-run the failed/missing chapter ranges per-chapter.
- **Final merge**: concatenate `parts/chNN/<Entity>.md` in chNN order into one `<Entity>.md` at the scan root, so each entity file grows chronologically; then discard the parts/ tree.

## Pitfalls
- **Normalize apostrophes/spelling before matching.** Chapter prose may use curly quotes (`Lord’s Alliance`) and variant spellings vs. the registry (`Menozberranzan` for Menzoberranzan, `Faerzess` for Faerzress, `Grazz’t`/`Zugtomy` for Graz'zt/Zuggtmoy). Normalize NFKD + `\u2019`→`'` on both sides; if an entity still misses but its concept clearly appears under a variant spelling, note it in the completion report.
- **Exclude alias-only matches.** If an entity's only hit comes through an *alias* while the entity's own name never appears (e.g., `Jimble the Unmoved` hit only because alias `Vukradin` matched), drop it unless the context genuinely refers to that entity.
- **No registry entry ≠ entity absent.** Chapters may name things with no registry entry (ch1: Kraken Society, Everlund, Silvery Marches, demon lords, Toril) — no files by design; mention gaps in the completion report so they're visible.
- **Registry parser gotcha:** alias lines and `note:` continuation lines both start with `  - ` — only treat `  - ` as an alias when inside an `aliases:` block (track a flag), or you'll ingest note text as aliases.
- **Registry tail sections are NOT entity entries.** The file ends with `distinct:` (entries like `- - Meril's Staff` with rejected aliases) and `rejected_aliases:` (blocks like `- - boars / - boar / - talking boar`, meaning those terms were REJECTED as aliases). Stop parsing at the first top-level key that isn't part of the entry schema — a parser keyed on `- name:` handles this automatically, but don't "fix" it to ingest those blocks or you'll match on rejected generic terms (`boar`, `cleric`, `tower`) and mass-false-positive. Verified in the ch43 run.
- **Generic-word aliases cause mass false positives.** Real examples from this registry: `cleric` (Anchorites of Talos), `courtyard` (Falcon's Hunting Lodge), `woman` (Jenna). Always context-audit aliases that are common nouns; drop generic hits.
- **Two-letter aliases collide with incidental initials** (e.g., `KP` vs "Kazneporium Ketternopappux"). Flag, don't auto-include.
- **Race/species entries can be legitimate entities too** (e.g., `Tortle` alongside NPC Soma who is a tortle) — check whether the registry has separate entries before merging hits.
- **Tool-call budget: write output files EARLY and INCREMENTALLY.** Reading 16 chapters plus auditing matches consumed the entire iteration allowance once, leaving zero calls to write any deliverables. If the task spans many chapters, write partial outputs after every few chapters rather than batching everything to the end. When chapters are read in bulk via `execute_code`, a single script that loops `write_file` calls to emit all entity files at once is a safe and budget-efficient pattern — just ensure reading/auditing completes before any writes in the same script. (Better still for large ranges: one subagent per chapter — see Orchestration above.)
- **Chapter filenames sort correctly with plain `sorted(glob(...))` thanks to zero-padded NN prefixes.**
- **One entity per write.** Never pack several entities' sections into a single hand-authored `write_file` call (e.g. dumping Harbin/Lyra/etc. under `Valphine.md` in the ch37 run) — you'll burn calls on a cleanup split pass and risk header corruption. Either write one file per entity, or author all bodies as Python strings in ONE `execute_code` script that loops file writes.
- **Chapter heading format varies — read the actual headings before writing.** Documented format is `## NN.MM <POV> <date>`, but some chapters use `## <POV> — <Title>` with no numeric IDs (e.g. ch45). The `(NN.MM)` citation convention applies only when IDs exist; don't fabricate them.
- **For a single-chapter hand-authored run, skip the parser+matcher pipeline**: grep `docs/entity_registry.yaml` for each candidate name/alias, then author all bodies as Python strings in ONE execute_code loop (verified: ch45 run, 30 files, zero cleanup passes). Reserve full pipeline for large multi-chapter ranges.
- **Registry spellings can drift from chapter prose**
- **Party-member files absorb closely-tied non-party entities.** In this campaign's convention, Falcon the Hunter's events went into `Vukradin.md`, and Meril + Meril's Staff into `Soma.md`/`Meril.md`. Flag any absorbed entity explicitly in your completion report so the merge step doesn't miss it.
- **`search_files` regex alternation (`a|b|c`) is UNRELIABLE in this workspace — it returns 0 matches even when the words clearly exist.** Workaround: search ONE word per call and fire many such calls in a single parallel batch. Verified across multiple sessions (obelisk scanning, entity extraction): single-word search works fine; multi-term alternations consistently fail. Do not use `search_files` with `|` patterns for entity alias auditing — enumerate aliases individually instead.

## Output conventions
- One file per entity in the requested output dir; filename = entity name.
- Per-chapter sections in chapter order; omit absent chapters entirely.
- Bullets should be event-level ("killed the manticore at Umbrage Hill"), not mentions-level.
- **Cite the source section per bullet** — prefix each bullet with the POV section number in parentheses, e.g. `(06.03)`. Chapters are POV-structured (`## NN.MM <POV> <date>`), so this makes every bullet traceable to who narrated it and when. Verified user-accepted format (ch06 run).
- **Registry spellings can drift from chapter prose** (e.g. registry has `Meril`, ch7 prose says "Merill"). When a near-match fails to hit, try one-letter variants before concluding the entity is absent; don't silently drop an entity over a typo.

## Related
- `campaign/obelisk-module-scanning` covers module-text scanning in this same Phandalin workspace; use that for obelisk.md encounter inventories, this one for registry→chapter digests.
- `references/phandalin-chapters-1-16.md` — verified paths, per-chapter match counts, confirmed false-positive aliases, and a chapter arc quick-reference for the Phandalin campaign (chapters 1–16).
- `references/phandalin-chapter-01.md` — per-chapter extraction notes for ch1: match results, alias-only drops, registry gaps, and spelling-variant traps.
- `references/phandalin-chapters-17-32.md` — chapter arc quick-reference, recurring-entity continuity notes, and new entities introduced across chapters 17–32.
- `references/phandalin-chapter-37.md` — completed-run notes for ch37: match results, alias hits (Xanthopoulos, Bryn), spelling drift (Corbyn), absorbed-entity flags.
- `references/phandalin-chapter-45.md` — ch45 run notes: alternate heading format (`## POV — Title`), single-chapter grep-instead-of-pipeline workflow, entities created without registry entries.
- `references/phandalin-chapters-33-47.md` — back-half notes: registry gaps (Vorga, Drubbak, Aretha, Gnomengarde location, "K."), spelling variants (Sylvine→Syleen), absorbed entities that the MERGE step must unify (Falcon split across files; Meril/Meril's Staff split; "Carver's Gang.md" non-registry filename).
- `references/phandalin-chapter-43.md` — ch43 run notes: 24 confirmed hits, alias-audit outcomes (incl. "Cleric of Lathander" false positive on the Anchorites `cleric` alias), registry tail-block (`distinct:`/`rejected_aliases:`) parsing note.
