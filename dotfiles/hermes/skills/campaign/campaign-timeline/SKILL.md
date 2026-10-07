---
name: campaign-timeline
description: Build dated campaign timelines; infer undated dates.
---

# campaign-timeline

Build or repair a dated campaign event timeline across a campaign's chapter files,
including date *inference* for chapters that carry no in-world dates, and folding
those dates into the per-entity scan files. Also covers systematic date-layer
corrections (e.g. a misspelled month name) and producing a reproducibility doc.

## When to use

- "Build a timeline of the campaign" / "merge the chapter events into one timeline"
- "These chapters have no dates — figure out when they happen"
- "Add dates to the entity scan" / "fold the dates into the per-entity files"
- "Verify the dates are correct against the calendar"
- Fixing a systematic error (e.g. a misspelled month name) across the whole date layer.

## Core concepts

**Explicit vs inferred dates.** Split chapters into those the source stamps with
real dates and those it doesn't. The last explicit stamp is the *anchor*; all
subsequent dates are *inferred* by counting days forward.

**Date format convention (CRITICAL — see references/forgotten-realms-calendar.md).**
In-world dates here look like `DD-MM-Tarsakh 1495`. Decode carefully:
- `DD` = day of month (01–30)
- `MM` = **MONTH** — the *middle* number is the month, not the day
- `Tarsakh 1495` = month name + year (DR)

A date `09-03-Tarsakh 1495` means "9th day of the month Tarsakh, year 1495" — NOT
"March 9th." Misreading the middle field as the day is the single most common
parsing bug. Always confirm the convention by scanning the source before trusting it.

**30-day months.** Forgotten Realms calendar uses 30-day months, so accumulation
rolls `30-03` → `01-04` and `29-03 + 5d = 04-04`. This matches canon.

**Day-pass detection.** A "day pass" is any in-text cue that the in-world clock
advances between events: a long rest, "the following day", stated travel days,
"several days of travel", a numbered journey day, an overnight. Each detected
boundary increments the running date.

## Workflow

1. **Locate the authoritative source.** Usually a single parsed doc
   (`~/src/campaigns/<campaign>/docs/NeverwinterExpansionismandtheNorth.md`) and/or
   its split chapters (`docs/chapters/chapter_NN_*.md`). The single doc is the
   source of truth for real dates.
2. **Extract explicit stamps.** Regex every `(\d{1,2})-(\d{1,2})-(\w+) 1495` and
   attach each to the nearest preceding `## N.M` section header. Group by chapter N
   → span [earliest, latest]. Chapters with one stamp = single date. A prologue
   with no stamps = `undated`.
3. **Confirm the explicit/inferred boundary.** Verify *zero* date stamps appear
   after the last explicit one (e.g. grep the source tail). This validates that
   everything downstream is inference, not missing data.
4. **Day-pass detection for undated chapters.** One sub-agent per undated chapter;
   each writes `daypass/chNN/intervals.json` recording, per day-pass: the verbatim
   marker quote, days elapsed, and a confidence (explicit / inferred / estimated).
   Dispatch in waves of 3 (max concurrency).
5. **Accumulate.** Start from the last explicit anchor. Walk chapters in order;
   each inherits the previous chapter's end date; each chapter's internal
   day-passes increment it. Build `chapter_dates.json` = `{ "N": ["start","end"] }`
   for all chapters.
6. **Fold into artifacts (NON-DESTRUCTIVE).** Append `<!-- DATE: ... -->` comment
   lines to each `## Chapter N:` header in the entity-scan files
   (`~/phandalin-entity-scan/*.md`); inject `<!-- INFERRED DATE: ... -->` anchors
   at day boundaries in the narrative chapters. HTML comments are invisible when
   rendered and reversible with `grep -v`/`sed`.
7. **Produce a VERIFICATION.md** (see below). Always — the user expects a
   reproducibility document for non-trivial derived datasets.

## Pitfalls

- **Fix the SOURCE, not just the derivatives.** When correcting a systematic error
  (e.g. misspelled month "Taraskh"→"Tarsakh"), propagate it to the authoritative
  source document AND every derived layer (parsed chapters, entity scan, timeline
  outputs) in one pass. Fixing only the derived files leaves the source corrupt and
  the error will re-surface on any re-parse.
- **"Several days" is an estimate.** When the text gives no number, pick a default
  (3) and flag it `estimated` in the intervals file and in the verification doc so
  a reviewer can adjust it without re-deriving everything.
- **Year-less stamps.** A source header may write `07-02-Tarsakh` without the
  `1495` year (cosmetic inconsistency). When re-deriving spans, use a year-OPTIONAL
  regex or you'll get false "mismatches." Record and optionally normalize the source.
- **Don't commit derived artifacts** without review — keep them uncommitted working
  files so the user can adjust or revert.
- **Middle = month.** Re-stated because it bites everyone once.

## Verification recipe (give this to a reviewer)

```bash
# A. Last explicit stamp in source is at section 19.10 / line ~3473; nothing after:
grep -n "Tarsakh 1495" ~/src/campaigns/<c>/docs/<source>.md | tail -5

# B. Re-derive ch01-19 spans from source, diff against chapter_dates.json — must match.
# C. Every emitted date matches DD-MM-Tarsakh 1495 with 01<=DD<=30, 01<=MM<=12, rollover ok.
# D. Spot-check: ch02=01-01→01-02, ch16=07-03, ch19=09-03, ch47=29-03 (example campaign).
# E. Read day-pass quotes in dates_inferred.md for any chapter in doubt.
```

## Standard artifact layout

```
~/phandalin-timeline/
  chapter_dates.json      # master map {N: [start, end]} — read this first
  dates_inferred.md       # human-readable evidence: per-chapter span + marker quotes
  timeline_dated.md/.json # full event timeline with resolved dates
  timeline.md/.json       # undated timeline (provenance)
  parts/chNN/events.json  # 47 raw per-chapter event extractions
  daypass/chNN/intervals.json  # 28 day-pass detections (undated chapters)
~/phandalin-entity-scan/*.md   # 268 entity files, each ## Chapter N: has <!-- DATE --> annotation
```

## Complements

- `campaign-entity-summaries` — the per-entity chronological *content* (what
  happened to each entity). This skill adds the *dates* layer on top and the
  merged timeline. Use both together.
- `corpus-digest` (note-taking) — for synthesizing sources; different deliverable.
