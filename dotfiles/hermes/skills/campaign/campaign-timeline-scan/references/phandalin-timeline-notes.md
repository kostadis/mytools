# Phandalin Timeline Scan — notes & proof

## The date-format gotcha (verify before merge)
All dated chapter headers look like `DD-MM-Taraskh 1495`. The literal middle number is the
MONTH (01–10 observed in the corpus). `Taraskh` is the in-world year label, not the month.

Proof (grep of every section header across all 47 chapters):
- Months present in tokens: only `Taraskh` / `Tarksh` (typo), so the calendar is a single
  year (1495 DR) with month = the middle number.
- Sample tokens: `01-01`, `01-02`, `01-03`, `02-02`, `02-03`, `03-02`, `04-03`, `07-02`,
  `07-03`, `08-01`, `08-02`, `08-03`, `10-02` → therefore the second field really is the
  month index.

Recompute rule (run at merge, do NOT trust per-agent sort_date):
```
m = re.match(r'(\d{1,2})-(\d{1,2})-(?:Tarkh|Taraskh)\s*(\d{4})', date_label)
day, month, year = m.groups()
sort_date = f"{year}-{month:0>2}-{day:0>2}"   # e.g. 07-02-Taraskh 1495 -> 1495-02-07
```
Observed failure: a wave of agents read "Taraskh" as month 01 and emitted `1495-01-DD`,
which is wrong for any chapter whose middle number != 01 (e.g. ch02's `01-02` became
`1495-01-02` correctly by luck, but ch04's `01-02`/`02-02` and ch07's `03-02`/`07-02` would
be misordered). Always recalc.

## Which chapters are dated vs null
- Dated (carry inline `DD-MM-Taraskh 1495` stamps): ch01–ch32 (ch01 is undated prologue
  backstory though — null on purpose).
- Null-date (NO stamps): ch33–ch47. These are ordered by chapter number only and land
  AFTER all dated events in the merge.
- Within a dated chapter, the date usually changes only 1–2 times; treat each event with
  its own date_label so day-change markers are accurate.

## The four tracking*.txt files (the "crucial" filter)
Read ALL FOUR for every chapter — they define what category of event is crucial. They are a
FILTER for categories, not a source of events; events still come from chapter prose.
1. `tracking.txt` — main Phandalin arc: main quests, starting/follow-up quests, locations,
   NPC events, major plot beats (Cryovain, Gorthok, Gulthias tree, relic recoveries, etc.).
2. `tracking-devine-contention.txt` — Storm Lord's Wrath / Leilon siege arc (Drow warships,
   Ebondeath, Claugiyliamatar, Battle of Leilon battlefield events).
3. `tracking-sleeping-dragons-wake.txt` — Sleeping Dragon's Wake arc (Wayside Inn,
   Cult of Talos, Thunder Cliffs, House of Thalivar).
4. `tracking-storm-lords-wrath.txt` — Thunder Cliffs / Mere of Dead Men arc (Bronze Shrine,
   Claugiyliamatar's lair, Death Knight-Dreadnaught).

Crucial = quest starts/completions, NPC first contacts / alliances / betrayals / deaths,
major plot beats & reveals (dragon sightings, summonings, visions, relic recoveries),
location clears, key departures/arrivals, major character decisions. Skip filler/flavor.

## Orchestration that actually worked (47 chapters)
- One subagent per chapter; output `parts/chNN/events.json`. Dir name = chapter order, so
  merge is a directory sort — no fragile numbering.
- Concurrency capped at 3 → waves of 3. ~16 waves for 47 chapters (incl. re-runs).
- Re-run discipline: verify each JSON exists after its wave (`ls parts/chNN/events.json`).
  ch47's agent summary got truncated and wrote nothing; caught at merge via FileNotFoundError,
  re-dispatched. Always verify before merge.
- Merge in execute_code: load all events, recalc sort_date, sort by (sort_date or "9999",
  chapter, order-in-file), emit TIMELINE.md with `### DAY CHANGE — <date_label>` markers on
  sort_date boundaries; null-bucket events go under `### Undated (chapter order)`.

## Filename drift
The parent's supplied filename for ch17 was wrong ("gnome a gnome a gnome and their king" is
actually ch04). Real ch17 = `chapter_17_blood_money_clean_gold_and_fine_wine.md`. Agents
should glob `chapter_17_*.md` and proceed, noting the swap.
