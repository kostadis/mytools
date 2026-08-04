# session-summary.md generation spec

You are producing a structured session summary **from a chapter of D&D campaign
prose**. The chapter is the ONLY source. There is no transcript, no notes, no
other document. If something is not in the chapter, it does not exist.

## Hard constraints — these are the point of the exercise

An earlier unconstrained pass at this task invented dialogue, backfilled names
from the published module, and silently changed character roles. Its output is
unusable. Every rule below exists because that pass broke it.

1. **Never write a quotation mark around words that are not character speech
   copied verbatim from the chapter.** Before you write `"..."`, find that exact
   string in the chapter and copy it character-for-character. If you cannot find
   it, you may not quote it.
2. **Never convert indirect speech into direct speech.** If the chapter says
   *she questioned whether he was truly a cleric*, write that as narration. Do
   NOT write `"Are you truly a cleric?"`. This is the single most common failure.
3. **Never stitch two quotes into one.** If the chapter has "ate people" in one
   place and "Trees do not eat people" in another, they are two quotes, not one
   contiguous utterance. Quote them separately or not at all.
4. **Never invent specifics.** No counts the chapter does not state (`8 orcs`),
   no dates, no place names, no game-mechanical terms (spell names, DCs, item
   names) unless the chapter names them. In particular: do NOT supply names from
   your own knowledge of the published module. If the chapter does not say
   "Menzoberranzan", you do not write "Menzoberranzan".
5. **Never change attribution.** Preserve every character's role, pronouns, and
   name spelling exactly as the chapter has them. If the chapter calls someone
   "one of the wererat miners" and uses *his*, do not promote them to "the
   leader" or switch to *her*.
6. **Never normalize a name's spelling, and never fix a typo.** Copy each name
   exactly as the chapter writes it. If the chapter spells a character two
   different ways, or misspells a word inside a quote, that is a defect the
   human needs to see and fix at the source — reproduce what is there. Silently
   correcting it hides the problem. The verifier is built to surface these; do
   not do its job for it.
7. **Compress, never expand.** Your output MUST be shorter than the chapter.
   Aim for 40-65% of the chapter's word count. A summary longer than its source
   is proof that material was invented. This is checked automatically.
8. If the chapter is thin, produce a thin summary. Fewer scenes and shorter
   bullets are correct. Padding is failure.
9. **`## NPCs` is for characters who DO something in this chapter** — not every
   capitalized name that appears. A name merely mentioned in passing (a deity
   invoked, a distant ruler referenced) does not get an entry. One pilot run
   ballooned to 150% of its source by writing a paragraph for every proper noun
   in the text; that is the failure this rule prevents.

Scare-quoting a term the chapter itself uses in quotes is fine. Quoting a
distinctive phrase from the chapter's narration is fine, as long as the string
is verbatim.

## Required output format

Exactly this structure. `## Scenes` and `## NPCs` are mandatory — a downstream
gate (`campaignlib.lineage._summary_is_structured`) tests for both by regex and
rejects the file without them.

```markdown
# <the chapter's H1, copied exactly>

## Summary

<2-5 short paragraphs of plain narration covering what happened, in order.>

## Scenes

### <Scene title>
#### <one sentence stating what this scene is>
- <A factual bullet. One event per bullet.>
- <Another bullet.>

### <Next scene title>
#### <one sentence>
- <bullets>

## NPCs

### <NPC name exactly as spelled in the chapter>
<A prose paragraph on who they are and what they did in this chapter, drawn
only from the chapter.>
```

Scene titles are yours to write — the chapter does not carry them. Name each
scene for what happens in it. Split the chapter into as many scenes as it
naturally has (typically 3-8). **Keep the scenes in the order the chapter
presents them**; a downstream event spine derives narrative ordering from this
sequence.

**Do NOT emit a `## Memorable Moments` section.** That section is where the
earlier pass concentrated its invented pull-quotes. It is not wanted.
