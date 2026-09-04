---
name: chapter-enhance
description: >
  Build a rich "enhanced summary" from a campaign CHAPTER's prose, in the full
  GMAssistant session-summary schema (Summary / Scenes / Locations / NPCs /
  Items / Memorable Moments / Spells). Unlike chapter-summarise, this pass
  EXPANDS the chapter into a wider schema rather than compressing it, so every
  claim is machine-traced back to the source: quoted fragments must appear
  verbatim, proper nouns must exist in the chapter, and facts from later
  sessions are treated as leaks. Source typos are surfaced as a fix-at-source
  queue, never silently corrected. Batch runs hold all GM questions to the end
  and present them in one artifact. Invoke as
  /chapter-enhance [campaign-dir] [chapter-numbers].
tools: Read, Bash, Write, Edit, Glob, Grep, AskUserQuestion, Artifact
---

# chapter-enhance

Turn a chapter of campaign prose into a full `session-summary.md` in the schema
the GM's newest sessions use, so that a backfilled chapter has the same shape as
a transcript-derived one.

## How this differs from `chapter-summarise` — read before choosing

| | `chapter-summarise` | `chapter-enhance` (this) |
|---|---|---|
| Output length | 40–65% of chapter (compress) | Typically 150–250% (expand into a wider schema) |
| Sections | Summary, Scenes, NPCs | + Locations, Items, Memorable Moments, Spells |
| Engine | one Haiku subagent per chapter | single pass, no subagents |
| Risk model | padding = invention | expansion is expected, so **every claim is traced** |

They are not interchangeable. `chapter-summarise` uses length as its invention
detector. This skill cannot — it is *supposed* to be longer than its source —
so it replaces that signal with `verify_enhanced.py`, which traces quotes and
proper nouns back to the chapter. **Never run this skill without the verifier.**

## When NOT to run

If the chapter has a real session workspace with a VTT behind it, prefer that
workspace's transcript-derived `session-summary.md`. A generated summary sits
downstream of the chapter and can only lose or invent relative to it.

**Verify that claim, do not assume it from a directory name.** Session dirs are
named `YYYYMMDD-chapter-NN` and the NN is frequently wrong by one — it records
the session ordinal, not the bible chapter. Chapter 7's events are not in
`summaries/20250805-chapter-07/`; that session opens *after* the chapter's final
battle and actually covers chapter 8.

```bash
# The check that settles it: do the chapter's distinctive NPCs appear?
grep -ric 'name1\|name2\|name3' summaries/<dir>/*.vtt summaries/<dir>/gm-assist.md
```

Zero hits on names the chapter uses repeatedly means that directory is a
different session. Say so in the output's provenance line.

## Procedure

### 1. Establish sources

- Chapter prose: `docs/chapters/chapter_NN_*.md` — **the only content source.**
- Style reference: the campaign's newest `summaries/<date>/session-summary.md`.
- `docs/chapter_provenance.md` — tells you which generation model wrote the
  chapter and whether its scene order tracks narrative order (models B and
  later do not always).
- Prior attempts, for comparison only, never as a source of fact:
  `summaries/attempts/{haiku,dgx-deep-seek,hand-edited}/`.
  **`hand-edited/` is GM prose. Never write there and never quote it as canon.**

### 2. Date line

Take the in-world date from the chapter's own POV headers
(`## NN.SS <POV> <DD-MM-Month YYYY>`). A chapter spanning two dates gets a
range: `Date: 03-02 to 07-02 of Taraskh 1495`. Sanity-check it against the
neighbouring chapters' headers. Do not copy a date from a prior attempt —
they disagree with each other.

### 3. Canonical spellings

Check `docs/entity_registry.yaml` for every named NPC. Record mismatches
between chapter and registry as **questions**, do not act on them: an alias or
merge is an identity decision and needs the GM. Watch for name collisions
across eras — two different people can share a first name.

### 4. Write the summary

Follow `enhance_spec.md` in this directory. Hard rules, in priority order:

1. **Quote nothing you have not found verbatim in the chapter.** No converting
   indirect speech to direct. No stitching two utterances into one.
2. **Introduce no proper noun the chapter does not contain.** If the chapter
   describes someone only as "the only human, who looks like a bandit", leave
   them unnamed even when you can identify them from another document. Naming
   them is an attribution decision — surface it as a question.
3. **No forward leaks.** A fact established in a *later* session is not
   available to this chapter, even when you just read it. This is the failure
   that survives casual review, because the leaked fact is *true*.
4. **Never silently fix a typo or normalise a spelling** — including spell
   names. Reproduce it and queue it. A normalisation here becomes a divergence
   between the summary and the bible that nobody can see.
5. Sections with nothing real in them stay thin. Two Items is a fine Items
   section; padding it is invention.

### 5. Provenance footer

Never stamp `*Exported from GMAssistant on ...*` on a file that was not. State
the real source, whether a recording exists, and the date:

```
*Enhanced summary derived from `docs/chapters/<file>`, the GM's hand-written
recap. No recording of this chapter's events exists in `summaries/` — <the
evidence> — so the chapter prose is the sole source. Generated <date>.*
```

### 6. Verify — this is the gate, not your self-report

```bash
python3 ~/.claude/skills/chapter-enhance/verify_enhanced.py \
    --chapter docs/chapters/chapter_NN_*.md \
    --summary <output path>
```

Fix every FAIL and re-run until clean. In the pilot run this caught a real
forward leak — a "only two people knew the party's travel plans" deduction
imported from the *next* session's gm-assist — that had read as obviously
correct.

## Batch runs

When given several chapters:

1. Do **all** chapters end to end first. Do not stop to ask after each one.
2. Accumulate a question queue as you go: registry mismatches, unnamed-but-
   identifiable characters, date ambiguities, source typos, chapter/attempt
   contradictions.
3. Review the finished set together — cross-chapter contradictions only become
   visible here.
4. Present **one** artifact at the end containing every question, grouped by
   kind and not by chapter, each with the evidence and a recommendation.

Typos found in the chapter are reported, never fixed in place, unless the GM
asks. When they do ask, fix them in `docs/NeverwinterExpansionismandtheNorth.md`
**and** in the `docs/chapters/` splits in the same pass — the splits are derived
from the bible and a re-split will otherwise silently reintroduce or revert the
change. Verify with an exact-occurrence count on both before and after.

## Output location

`summaries/chapter_summaries/<NNN>-<chapter-slug>/session-summary.md`

Inside the `summaries/` mempalace wing, so the files are mined and searchable,
but outside `summaries/attempts/`, which is a model-comparison corpus rather
than a set of real artifacts. **Never write into `summaries/attempts/` at all**,
and least of all `hand-edited/` — its README explains that model output landing
there gets scored as a human's writing.

Generate into a scratch location first if the GM has open rulings; a ruling on a
name or a place changes text *inside* the summaries, and they should not land in
their final home carrying spellings that are about to be retired.
