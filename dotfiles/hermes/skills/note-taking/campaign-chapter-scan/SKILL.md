---
name: campaign-chapter-scan
description: One subagent per chapter to build dossiers or a timeline.
---

# Campaign Chapter Scan

Recurring task class for this user: turn the chapter docs in a campaign workspace into consolidated artifacts. Two flavors seen so far:
1. **Entity dossiers** — one file per campaign entity, each with a per-chapter section of key events (chronological).
2. **Event timeline** — a single dated timeline of crucial events, with day-change markers where the date advances.

## Core orchestration pattern (CRITICAL — user-mandated)

The user **explicitly corrected** "1 agent per 3 chapters" → **"1 sub-agent per chapter, then orchestrate the sub-agents."** Do NOT batch multiple chapters into one agent.

- `delegate_task` is capped at **3 concurrent children**. Orchestrate in **waves of 3**: dispatch 3, wait for the batch-complete message, dispatch the next 3. YOU are the orchestrator between waves.
- For N chapters that is ceil(N/3) waves (47 chapters → 16 waves). This is normal; do not try to "optimize" by over-batching — the user rejected that.
- Each chapter agent writes to its OWN isolated directory (e.g. `parts/chNN/`) so there is zero cross-agent file contention and ordering is guaranteed by directory name.
- Merge is a single deterministic step YOU run (execute_code) AFTER all waves finish. Never let the chapter agents merge.

## Workflow — Entity dossiers

1. Read `docs/entity_registry.yaml` (~577 entities: name/type/aliases). Canonical entity list.
2. Per-chapter agent:
   - Reads chapter NN.
   - Matches registry entities by name+alias (case-insensitive, word-boundary aware).
   - Skips generic/false-positive aliases (`cleric`, `courtyard`, `woman`, `Townmaster`, bare `bard`). Normalizes in-text spelling variants (`Gnercli`→Gnerkli, `Miral`→Miraal, `Sylvine`→Syleen Wintermoon).
   - Writes ONE file per appearing entity: `<Registry Name>.md` with `# <Name>` + `## Chapter N: <title>` + narrative-order bullets.
3. Merge: concatenate `parts/chNN/<Entity>.md` in chapter order into `<Entity>.md` at output root.

## Workflow — Event timeline

1. Per-chapter agent reads the chapter PLUS all `docs/tracking*.txt` files (these are the "crucial events" filter / quest & beat taxonomy).
2. Extracts crucial events (quest starts/completions, NPC first contacts/alliances/betrayals/deaths, major reveals, location clears, key departures, major decisions). Skip filler.
3. Writes `parts/chNN/events.json` — JSON array of `{chapter, date_label, sort_date, event}`.
4. Merge: sort by real date, insert `--- DAY CHANGE: <date> ---` markers where the date advances, write `TIMELINE.md`.

## Pitfalls (READ references/campaign_scan_pitfalls.md)

- **Date format gotcha**: headers look like `01-02-Taraskh 1495`. Format is `DAY-MONTH-Taraskh 1495` — the **middle number IS the month** (01–10 seen); "Taraskh" is the year label. Agents routinely misread this and set `sort_date` to month 01. Always recompute `sort_date` from `date_label` at merge time. Two rendering traps: (a) the stamp also appears SPACED (`01-03 Taraskh 1495` with no hyphen — e.g. ch13); a hyphen-only regex silently drops it into undated, so accept both with `(\d{1,2})-(\d{1,2})\s*-?\s*([A-Za-z]+)\s*(\d{4})`; (b) render the day-change marker VERBATIM (`01-01-Taraskh 1495`) — do NOT remap the middle number onto Forgotten Realms month names (Hammer/Alturiak/Ches); the source never uses them, so that's editorial, not sourced.
- **Merge ordering**: sort by actual chapter number, not dispatch/write order. Directory-listing order is wrong (a ch17–32 block once landed ahead of ch01).
- **Concurrency**: 3 max. Never dispatch more than 3 at once.
- **Stale batch dirs**: if an earlier run wrote shared dirs (`parts/a`, `parts/b`), discard them; use per-chapter dirs only.

## Support files
- `references/campaign_scan_pitfalls.md` — date format, registry structure, false-positive alias list, merge-ordering notes.
- `scripts/merge_entity_files.py` — merge parts/chNN/* into per-entity root files, chapter-ordered.
- `scripts/merge_timeline.py` — merge events.json into a dated TIMELINE.md with day-change markers and correct sort_date.
