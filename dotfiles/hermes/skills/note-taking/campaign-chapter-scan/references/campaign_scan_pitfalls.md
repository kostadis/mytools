# Campaign Chapter Scan — Pitfalls & Reference

## Date format (THE big gotcha)
Chapter section headers carry inline dates, e.g.:
  `## 02.01 vukradin 01-01-taraskh 1495`
Format is **DAY-MONTH-Taraskh 1495**:
- First number = DAY
- Second number = MONTH (01–10 observed; "Taraskh" is month 01 of the FR calendar, but the number is what matters)
- "Taraskh" is the YEAR LABEL (campaign year 1495), NOT a month name to look up.

Agents almost always misread `01-02-Taraskh` as "day 1, month 02, ...oh Taraskh=month 1 → 1495-01-02", producing wrong sort_dates.
**Fix:** at merge time recompute sort_date from date_label:
  `DD-MM-Taraskh 1495` → `1495-MM-DD` (month = the MIDDLE number).

Verified across all 47 Phandalin chapters: only "Taraskh"/"Tarksh" appear as the year token; day/month numbers span 01–10. Format is fully consistent.

## Entity registry structure
`docs/entity_registry.yaml` (Phandalin, ~577 entities, 2463 lines):
```
version: 1
campaign: Phandalin
entities:
- name: Adabra Gwynn
  type: npc
  aliases:
  - Adabra
  - Adabra Adabra Gwynn
  note: ...
```
PyYAML may be unavailable — a hand-rolled parser (loop on `- name:` + collect `aliases:`) works.

## False-positive aliases to skip (generic words that collide)
- `cleric` (Anchorites of Talos alias)
- `courtyard` (Falcon's Hunting Lodge alias)
- `woman` (generic — do not map to Jenna/Kaella)
- `Townmaster` (Harbin Wester alias — but keep if context clearly identifies Harbin)
- bare `bard`, `Bard` (Vukradin alias — generic)

## Spelling-variant normalization seen in-text → registry
- Gnercli / Gnercli → Gnerkli
- Fiddlestib → Fibblestib
- Facktore → Facktoré
- Miral → Miraal
- Sylvine → Syleen Wintermoon
- Tarksh → Taraskh
- Elmer → Elmar Barthen
- "Stonehill Tavern" → Stonehill Inn (reference, not an appearance)

## Merge ordering rules
1. Sort chapter dirs by integer chapter number (chNN → int(NN)), NOT directory-listing order (lexical order puts ch10 before ch02 and can interleave a shared batch dir).
2. Within an entity file, order per-chapter sections by chapter number.
3. For timeline, sort events by recomputed sort_date; insert a `--- DAY CHANGE: <date_label> ---` marker before the first event of each new date_label.
4. Dedup identical section bodies (sig = first 80 chars) to avoid the chapter re-appearing twice when two sources cover it (e.g. a `parts/b` block + a `parts/chNN` block for the same chapter).

## Concurrency
delegate_task caps at 3 concurrent children. Orchestrate waves of 3; wait for the batch-complete message; dispatch next wave. For 47 chapters that is 16 waves. Do not over-batch — user explicitly rejected "1 agent per 3 chapters."
