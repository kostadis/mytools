# Inferring dates for undated chapters (the day-pass pass)

Extends the timeline scan. Early chapters (here ch1–19) carry explicit
`DD-MM-Taraskh 1495` section stamps; later chapters (ch20–47) drop them
entirely, yet time still moves ("after a long rest", "the following day",
"several days of travel"). This pass reconstructs a *running inferred date*
for every undated event so both the timeline and the narrative carry dates.

## Anchor
Find the last explicit `DD-MM-Taraskh 1495` in the chapter set (e.g. ch19
`09-03-Taraskh 1495`). Convert to an ordinal:
`ordinal = (month - 1) * DAYS + day`. Use **DAYS = 30** as the month length —
the in-world calendar's month lengths are unspecified in the source, so FLAG
this assumption in the deliverable. `Taraskh` is the year label, not a month.

## Per-chapter detection (one subagent each, waves of 3)
For each undated chapter a leaf agent reads the chapter and emits
`daypass/chNN/intervals.json`:

```json
{
  "chapter": 20,
  "assumed_start_continuous": true,
  "intervals": [
    {"idx": 1, "marker": "<verbatim quote of the day-pass text>",
     "section": "<header>", "days_elapsed": 1,
     "confidence": "explicit|inferred|estimated", "note": "<why>"}
  ],
  "total_days_estimated": 1
}
```

Rubric for `days_elapsed`:
- long rest / overnight = 1; short rest = 0.
- "the next day" / "next morning" / "following day" = 1.
- "two days later" = 2; "a few days" = 3 (estimated);
  "several days" / "several days of travel" = 3–4 (estimated);
  use a stated travel-day number when the text gives one.
- continuous same-day action = 0.
- `assumed_start_continuous: true` — each chapter begins where the prior
  left off (0 gap) unless the text states an explicit gap.

Agent prompt must instruct: read the WHOLE chapter (chunk files >1k lines),
walk section by section, record each transition where ≥1 day elapses, verify
the JSON with `python json.load`. Empty `intervals: []` if the chapter is one
continuous day.

## Accumulation (merge step, execute_code)
```python
ordinal = (3 - 1) * 30 + 9   # 09-03 anchor
run = ordinal
chap_start = {}
for ch in range(20, 48):
    chap_start[ch] = to_dm(run)
    run += daytotal[ch]       # total_days_estimated from intervals.json

def to_dm(o):
    m = o // 30 + 1
    d = o % 30
    if d == 0:
        m -= 1; d = 30
    return f"{d:02d}-{m:02d}-Taraskh 1495"
```
Every undated event in chapter `ch` gets `date_resolved = chap_start[ch]`.

## Injecting dates into the NARRATIVE (user-preferred: non-destructive)
The user chose HTML comment anchors over visible stamps or sidecar-only, so
the source stays pristine and reversible:
`<!-- INFERRED DATE: DD-MM-Taraskh 1495 -->` on its own line, immediately
before the line where the day turns. For each `+>0` interval, compute the
post-increment date and insert the anchor at the marker's line.

### Pitfalls (all hit in-session)
- **Skip `days_elapsed <= 0` intervals.** Agents record same-day transitions
  (+0, e.g. POV changes) — those are NOT day boundaries; inserting anchors for
  them is wrong.
- **Markers are not always verbatim.** The agent's `marker` string may be a
  paraphrase absent from the source (observed: ch21 "they agreed to remain at
  Falcon's Lodge for two nights…" was not in the text; ch33/ch38 needed
  fallback tokens like "The long rest, at least, was simple." / "We were moving
  through the forest toward the Circle of Thunder"). Locate the real line with a
  forgiving token search (lowercased substring of a distinctive phrase); fall
  back to the nearest section/date header if needed. Always verify
  `marker in line` before inserting; if not found, search a fallback token and
  record the skip.
- **Multiple day-passes can resolve to the SAME source line.** If two
  intervals' markers both match one paragraph line (ch28: both "After taking a
  long rest" and "several days of travel" sat in the same line), naive
  line-index insertion emits them in the wrong order. Fix: collect
  `(line_index, inferred_date)` pairs, sort by inferred_date ascending, and
  insert bottom-up so the EARLIEST date sits closest to the text with later
  dates stacked above it.
- **Insert bottom-up per file** (highest line index first) so earlier
  insertions don't shift later line indices.
- **30-day-month is an assumption** — state it in the deliverable. If the user
  later wants real FR months, that's an editorial remap (and the verbatim-render
  rule from the parent skill still applies to explicit stamps).
- **Re-verify every written file.** A subagent whose summary is truncated
  mid-task may have written nothing (seen with ch47 twice) — check the file
  exists before trusting it; re-dispatch missing chapters.

## Deliverables
- `dates_inferred.md` — chapter→date-range table + per-chapter day-pass
  evidence (marker, days, confidence, note). This is the reviewable provenance
  list the user wants before trusting the dates.
- `timeline_dated.md` / `.json` — the merged timeline with `date_resolved` on
  every event.
- Injected `<!-- INFERRED DATE -->` anchors in the chapter files
  (non-destructive; removable with `grep -v 'INFERRED DATE'`).
