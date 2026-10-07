---
name: obelisk-module-scanning
description: "Scan and structure data from the PaBTSO (Phandelver and Below: The Shattered Obelisk) module text in this campaign workspace — grouping monsters/NPCs/locations by type+tribe+location, excluding named entities per the glossary, and writing _scan_N.md artifacts. Use when the user says 'scan lines X-Y of obelisk.md', 'group all unnamed/generic monsters', 'build the encounter inventory', or otherwise processes docs/background/obelisk.md."
---

# Obelisk Module Scanning (PaBTSO campaign pipeline)

Extract and structure data from the Phandelver and Below: The Shattered Obelisk module text that lives in this campaign workspace.

## When to use
- "Scan lines X-Y of obelisk.md"
- "Group all unnamed/generic monsters by type+tribe+location"
- "Build the encounter inventory / write _scan_N.md"
- Any task that turns `docs/background/obelisk.md` into grouped, structured artifacts.

## Workspace layout
- `docs/background/obelisk.md` — full module text, **6,078 lines**. Single source of truth; if a discrepancy surfaces, the module text wins.
- `docs/background/name_glossary.md` — canonical list of NAMED NPCs/creatures/factions/locations (Core NPCs, townsfolk, kidnapped, other named creatures, factions, deities, locations, items). **Exclude these from any "unnamed/generic" scan.** Also carries campaign rulings (e.g., Greska→Grista, Pip Stonehill→Tuck, Daran is a drow, Reidoth is a woman) — honor them so you don't re-introduce renamed entities.
- `docs/background/obelisk-inventory.md` — companion inventory; consult for cross-checks.
- `docs/background/_scan_A.md`, `_scan_B.md`, `_scan_C.md` — per-range grouped scan outputs. New scans take the next free letter.

## Workflow
1. **Read `name_glossary.md` first.** It is the exclusion list. Note the "Rulings & verified attributions" section — those decisions are load-bearing.
2. **Read the requested line range** of `obelisk.md` (use offset/limit). Confirm the chapter header at the start of the range.
3. **Enumerate creature types with `search_files`** — see Pitfalls for the alternation bug. Use single-word patterns, fired many at a time in parallel batches, with `output_mode=content` and a `limit` to bound volume.
4. **For each type**, capture: type · tribe/faction · location (area code) · count (**preserve die notation** like `1d4`, `1d6`, `1d6/hour`) · verbatim module descriptor · named-leader flag.
5. **Group by type + tribe + location.** Same creature type in two different areas = two groups (e.g., encephalon cluster in Talhundereth T21 vs Briny Maze B12).
6. **Exclude named individuals** into a separate "Excluded (named)" section so the pipeline can trust the boundary. A named leader (e.g., Vundru the grell psychic) is flagged, not grouped; its unnamed minions stay in the type group.
7. **Write** to `docs/background/_scan_<next letter>.md`: scope line (chapter + line range), grouped entries, an Excluded section, and a one-line summary. End with a count of distinct groups.

## Pitfalls
- **`search_files` regex alternation (`a|b|c`) is UNRELIABLE in this workspace — it returns 0 matches even when the words clearly exist.** Workaround: search ONE word per call and fire many such calls in a single parallel batch. Verified this session: `oculorb|beholder|spectator`, `grimlock|cloaker`, `flumph|gnawble|encephalon`, `mezzoloth|nycaloth|arcanaloth`, `aberrant zealot|flesh meld|humanoid mutate`, `gray ooze|duergar`, `svirfneblin|quaggoth|roper`, `gibbering|black pudding|mimic` ALL returned 0, while every single-word search of the same terms returned hits. Frame this as a workaround, not a blanket "search_files is broken" claim — single-word search works fine.
- **Area codes are scoped per map, not globally unique.** `W` = Wave Echo Cave (ch4) AND the Endless Void / Wailing Battlefield nodules (ch8, see "W1: Prison Pyramid" at line ~5720). Always cite chapter + map context, not just the letter.
- **Same monster recurs across chapters.** When scanning a later range, ignore earlier-chapter occurrences of the same type. Example: feral ashenwights appear in ch5 Zorzula's Rest (lines 2622/2753/3797) AND ch8 Briny Maze (5073/5084) — only the in-range ones count for a ch6–8 scan.
- **Preserve exact counts.** Don't normalize `1d4 grells` to "some grells" or sum die rolls.
- **Named-vs-unnamed is the whole point.** Cross-check every hit against `name_glossary.md`. When a type has a named exemplar (grell psychic **Vundru**, grell host **Feedkeeper Naruv**, gray slaad **Chalaag**, flumph **Wise Borblish**, nycaloth **Nellik**), exclude that individual and keep the unnamed rest.
- **`search_files` alternation bug is workspace-wide.** The regex `a|b|c` pattern returns 0 matches in this workspace's `search_files` — but single-word search works fine. This is the same pitfall documented in `campaign-entity-summaries`; the workaround (one-word-per-call, fired in parallel batches) applies here too.

## References
- `references/module-structure.md` — chapter map (verified + inferred boundaries), area-code legend (with the `W` collision), and the compiled monster-type → named-exclusion list from the ch6–8 scan. Reuse it as a starting index for the next scan.
