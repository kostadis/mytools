---
name: campaign-timeline-scan
description: Build a chronological campaign timeline from chapter prose.
---

# Campaign Timeline Scan (chapters → one chronological crucial-event timeline)

Build a single campaign timeline: one event per crucial beat, in play order, with in-world dates and explicit **day-change markers**, merged across all chapters. Distinct from `campaign-entity-summaries` (which produces one file *per entity*); this produces one file for the *whole campaign arc*, crucial-only, chronological.

## Inputs
- `docs/chapters/chapter_NN_<slug>.md` — chapter files. Frontmatter `chapter:` + `title:`. Early chapters (roughly 1–32) carry section headers like `## 02.01 vukradin 01-01-Taraskh 1495`; **later chapters (≈33+) drop the date stamps entirely.**
- `docs/tracking*.txt` — the **crucial-event filter**. There are FOUR: `tracking.txt` (main Phandalin quests/NPC beats/locations/major-plot-beats), plus `tracking-devine-contention.txt`, `tracking-sleeping-dragons-wake.txt`, `tracking-storm-lords-wrath.txt` (other campaign arcs). Read ALL of them so agents know what counts as "crucial" (quest starts/completions, NPC first contacts / alliances / betrayals / deaths, major plot beats & reveals, location clears, key departures/arrivals, major character decisions). Skip filler/flavor.

## Date format — CRITICAL
Chapter headers read `DD-MM-Taraskh 1495`. **The middle number is the MONTH** (01–10 seen); `Taraskh` is a year label, NOT the month. So `01-02-Taraskh 1495` = day 1, month 2 (Ches). Agents will naively treat `Taraskh` as month 01 and produce wrong `sort_date` — do NOT trust per-agent `sort_date`. **Recompute `sort_date` from `date_label` at merge time**: parse `DD-MM-Taraskh 1495` → `1495-MM-DD` (month = middle number). Example: `07-02-Taraskh 1495` → `1495-02-07`.
- Some chapters have NO date stamps at all (ch33–47). Set `date_label: null`, `sort_date: null` — these are ordered by chapter number only (they sit after the dated chapters in the merge).
- A chapter may carry several dates; when the date changes between sections, that is a **day change** — record each event with its own correct `date_label`.

## Workflow (user-preferred orchestration)
The user explicitly corrected a 3-subagent-per-range fan-out to **one subagent per chapter**, parent as orchestrator:
- **Delegation concurrency is capped at 3** for this user → dispatch in waves of 3; next wave as each returns.
- Each chapter subagent reads the chapter + all four `tracking*.txt`, extracts crucial events, and writes **structured JSON** to `parts/chNN/events.json` (the dir name encodes chapter order, so merge ordering is trivial). Element schema:
  `{"chapter": N, "date_label": "01-01-Taraskh 1495" (or null), "sort_date": "1495-01-01" (or null, best-effort), "event": "one-line past-tense crucial event"}`
  One element per crucial event, in document/section order. Verify with `python json.load` before returning.
- **Re-run discipline:** a single-subagent run whose summary gets truncated mid-task can finish having written NOTHING (observed: ch47 agent's final message was cut and no file existed — `FileNotFoundError` on merge). After a wave completes, **verify the JSON file exists** (`ls parts/chNN/events.json`) before trusting it; re-dispatch any missing chapter.
- **Final merge** (`execute_code`): load every `parts/chNN/events.json`, recompute `sort_date` from `date_label` via the DD-MM rule, then sort all events by `(sort_date or sentinel, chapter, document order)`. Emit ONE `TIMELINE.md` where you insert a day-change marker whenever `sort_date` (or null-bucket) changes from the prior event. Then discard `parts/`.

## Pitfalls
- **Don't trust agent `sort_date`** — recompute from `date_label` (middle number = month). Verified: wave-3 agents mapped `Taraskh`→month 01, giving `1495-01-DD` which is wrong for any chapter whose middle number ≠ 01.
- **Null-date chapters are normal, not errors** — ch33+ omit stamps; carry `null` and let chapter order place them after dated events.
- **Filename drift is real** — the parent's supplied chapter filename can be wrong (e.g. a filename said "gnome/king" but chapter 17 is actually `blood_money_clean_gold_and_fine_wine.md`). Agents should glob the real file and proceed, noting the swap in their report; don't fail on a bad path.
- **tracking*.txt are a FILTER, not a source** — they tell agents what category of event is crucial; events still come from the chapter prose. Don't invent events that only appear in tracking files.
- **Exclude the same generic-noise as entity scans**: `cleric`/`woman`/`courtyard` alias false-positives, filler banter, individual low-stakes combat. The crucial filter already steers agents away, but audit borderline calls.
- **Day-change markers belong at the MERGE step**, not per-chapter — a single chapter is usually one day, so the marker only has meaning once events are interleaved chronologically.
- **Render date markers VERBATIM — do NOT remap to the Forgotten Realms calendar.** The in-world text only ever writes `Taraskh 1495`; it never uses month names like Hammer/Alturiak/Ches. Displaying a marker as `Day 1, Hammer 1495` (middle number mapped onto the FR calendar) is unsupported editorial invention. Render the raw stamp: `01-01-Taraskh 1495`. Observed in-session: an early merge produced ambiguous `Day 1, Taraskh 1495` (dropping the month) and a later one produced `Day 1, Hammer 1495` (wrong remap) — both corrected to verbatim display.
- **Date-stamp spacing varies.** Headers appear as `DD-MM-Taraskh 1495` (hyphen) AND `DD-MM Taraskh 1495` (space, no hyphen — e.g. ch13 `01-03 Taraskh 1495`). A regex keyed only on the hyphen form silently drops the spaced variant into the undated bucket. Use `(\d{1,2})-(\d{1,2})\s*-?\s*([A-Za-z]+)\s*(\d{4})` to accept both forms when parsing and normalizing to `DD-MM-Taraskh 1495`.

## Inferring dates for undated chapters (the "day-pass" pass)

Early chapters carry explicit `DD-MM-Taraskh 1495` stamps; later ones (here ch20–47) drop them but time still moves (long rests, "the following day", "several days of travel"). Reconstruct a *running inferred date* so the timeline AND the narrative both carry dates. Full method, agent-prompt schema, accumulation math, and injection pitfalls are in `references/inferred_dates.md` (read it before running this pass). Essentials:

- **Anchor** on the last explicit stamp (e.g. ch19 `09-03-Taraskh 1495`); accumulate with a **30-day-month assumption** (in-world month lengths unspecified in source — FLAG this in the deliverable).
- **One subagent per undated chapter** (waves of 3) emits `daypass/chNN/intervals.json`: each `+>0` interval = a day boundary, with a verbatim `marker`, `days_elapsed`, and `confidence` (explicit/inferred/estimated). `total_days_estimated` feeds the accumulator.
- **Merge** computes `chap_start[ch]` by walking the running ordinal; every undated event gets that chapter's inferred date.
- **Inject into the narrative as non-destructive HTML comment anchors** (`<!-- INFERRED DATE: DD-MM-Taraskh 1495 -->` on its own line at the boundary). The user explicitly chose this over visible stamps or sidecar-only, because source prose stays pristine, reversible, and invisible when rendered. Skip `+0` (same-day) intervals; watch for markers that aren't verbatim in the source (use a forgiving token search + fallback line); when two day-passes resolve to the same source line, sort by inferred date and insert bottom-up so the earliest date sits closest to the text.
- Deliver `dates_inferred.md` (reviewable evidence: marker + confidence per boundary) + `timeline_dated.md/.json` alongside the injected anchors.

## Output conventions
- One merged `TIMELINE.md` at the scan root (e.g. `~/phandalin-timeline/TIMELINE.md`).
- Events grouped/separated by day-change markers; within a day, ordered by chapter then section.
- Each line: `- <event>` (past tense, one line). Optionally prefix the chapter: `- [Ch.N] <event>`.
- Undated (null) events appear after all dated ones, in chapter order, under a `### Undated (chapter order)` marker.

## Related
- `campaign-entity-summaries` — sibling skill: per-entity chapter digests (one file per entity). Use that when the ask is "what happened to X across chapters"; use this one when the ask is "give me the campaign timeline." Both share the one-subagent-per-chapter / waves-of-3 / `parts/chNN` orchestration pattern.
- `references/phandalin-timeline-notes.md` — date-format proof, the four tracking files and what each covers, null-date chapter range, and the verified merge/recalculate approach.
