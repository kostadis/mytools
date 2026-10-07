---
name: campaign-chronology
description: "Build campaign entity scans and event timelines from docs."
---

# Campaign Chronology Builder

Builds ordered, dated artifacts from a campaign's narrative chapters. Three common jobs, all sharing the same extract-then-merge shape:

1. **Per-entity scan** — one file per campaign entity, each listing `## Chapter N:` sections in order as the entity reappears.
2. **Event timeline** — one crucial event per line, chronologically ordered, with day-change markers.
3. **Date inference** — where chapters have no explicit dates, detect day-passes and accumulate a running date from a known anchor, then inject it into the timeline and narrative.

## Source layout (assumed)
- Chapters: `docs/chapters/chapter_NN_slug.md` (NN zero-padded).
- "Crucial" filter: `docs/tracking*.txt` (tracking.txt, tracking-<module>.txt). Read ALL of them — they define what counts as crucial (quest starts/completions, NPC first contacts/alliances/betrayals/deaths, major plot beats & reveals, location clears, key arrivals/departures, major character decisions). Skip filler/flavor.
- Entity registry (if present): `docs/entity_registry.yaml` — names for the per-entity scan.

## Date-format convention (CRITICAL)
In-text stamps look like `DD-MM-Tarsakh 1495`. **The MIDDLE number is the MONTH; "Tarsakh" is the Forgotten Realms month name (year label is the trailing 1495).** So `07-03-Tarsakh 1495` = day 7, month 3 (Tarsakh), year 1495 DR. Spell it **Tarsakh** (NOT "Taraskh" — user corrected this dyslexia). Normalize the space variant `DD-MM Tarsakh 1495` to hyphen form.

## Extraction: ONE subagent PER CHAPTER
Dispatch one leaf subagent per chapter. **Do NOT batch 3 chapters into one agent** — the user explicitly overrode that approach (prefers 1 subagent per chapter). Respect max 3 concurrent (orchestrate in waves of 3). Each agent writes a shard (e.g. `parts/chNN/events.json` or `parts/chNN/<Entity>.md`). Give the agent:
- exact chapter path,
- the crucial-event filter (point it at the tracking files),
- the date-format rule,
- exact output schema + path,
- a "verify with `python json.load`" instruction.

After each wave: **verify every shard file exists and loads** (`json.load`). Large chapters (ch47, ~72KB) sometimes get cut off before the agent writes the file — re-dispatch if a file is missing/empty. (See Pitfalls.)

## Merge (do this in execute_code, not by hand)
- Recompute `sort_date` from `date_label` at merge time; **never trust the subagent's derived sort_date** (wave-3 agents wrote `1495-01-DD`, treating Tarsakh as month 01). Parse `DD-MM-Tarsakh 1495` → canonical `1495-MM-DD`.
- Sort: dated events by (month, day); undated keep `null` and sort to document order (usually after all dated, by chapter number).
- Insert `## DAY CHANGE — <date>` markers wherever the date advances. For undated chapters, group under `[undated]` blocks ordered by chapter.
- Show the month in day-change labels (don't drop it — "Day 1" repeats ambiguously across months).

## Date inference (no explicit dates)
- Anchor at the LAST explicit in-world date. Assume each subsequent chapter BEGINS continuous with the previous (0 gap) unless the text states an explicit gap.
- Per-chapter day-pass detection rubric (give to subagents; see `references/daypass-rubric.md`): long rest / overnight = 1 day; short rest = 0; "the next day"/"next morning"/"following day" = 1; "two days later" = 2; "a few days" = 3 (estimate); "several days"/"several days of travel" = 3–4 (estimate, flag confidence). Continuous same-day action = 0.
- Accumulate with a 30-day-month assumption (in-world month lengths unspecified — state as caveat, not canon). Flag all `estimated` values in an evidence file.
- Output a `daypass/chNN/intervals.json` per chapter, then build a chapter→date-range map.

## Non-destructive injection into source / narrative
Use HTML comment anchors — invisible when rendered, fully reversible:
- Narrative day boundaries: `<!-- INFERRED DATE: DD-MM-Tarsakh 1495 -->` on its own line BEFORE the line where the day turns.
- Entity-scan `## Chapter N:` headers: a trailing `<!-- DATE: <range> -->` line.
Insert **bottom-up** (reverse line order) so earlier indices stay valid. When two markers land in the SAME source paragraph, order them by accumulated date, not by detection order. Verify marker substrings are verbatim in the chapter before inserting; if not, use a forgiving token search (e.g. "Early the next morning") and fall back gracefully.

## Global spelling / consistency fixes
When the user corrects a spelling in source docs (e.g. Taraskh→Tarsakh), fix it EVERYWHERE in one pass: the original source document, parsed `docs/chapters/*.md`, derived `entity-scan/*.md`, and timeline outputs (`*.md` + `*.json` shards). Recursive walk + `str.replace`, then assert zero remaining.

## Pitfalls
- **Subagent write lost on truncation** — always `json.load` every shard after a wave; re-dispatch missing ones. ch47 was cut off twice in one session.
- **Wrong sort_date from agents** — recompute from `date_label`; the string is authoritative, the agent's arithmetic is not.
- **Batching chapters** — 1 subagent per chapter, per user mandate; NOT 1-per-3.
- **Dropping the month in labels** — day-change markers must include the month or they are ambiguous.
- **Month-length assumption** — 30-day months is a placeholder; state it as a caveat, not a canon fact.
- **Verbatim-marker miss** — some subagent `marker` quotes aren't exact substrings; locate via forgiving token search before inserting anchors.

## References
- `references/date-format.md` — full date convention + Tarsakh spelling + example anchors.
- `references/daypass-rubric.md` — exact subagent prompt rubric for day-pass detection.
- `scripts/merge_timeline.py` — reusable merge: recompute sort_date, sort, day-change markers, undated handling.
- `scripts/inject_dates.py` — fold a chapter→date map into entity-scan `## Chapter N:` headers as `<!-- DATE: -->` anchors.
