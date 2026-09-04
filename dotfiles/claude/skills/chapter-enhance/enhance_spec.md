# Enhanced session-summary generation spec

You are expanding **one chapter of D&D campaign prose** into the full
GMAssistant session-summary schema. The chapter is the ONLY content source.
If something is not in the chapter, it does not exist.

Because this pass is allowed to be *longer* than its source, length is useless
as an invention detector. Every rule below is what replaces it.

## Hard constraints

1. **Quotation marks are a claim of verbatim.** Before writing `"..."`, find
   that exact string in the chapter and copy it character-for-character. Keep
   the chapter's punctuation and its typos. If you cannot find it, do not
   quote it.
2. **Never convert indirect speech into direct speech.** If the chapter says
   *she asked who they were*, write that as narration — never `"Who are you?"`.
3. **Never stitch two utterances into one quote.** Two lines said at different
   moments are two quotes. Joining them with `...` fabricates a sentence. The
   one exception is an exchange rendered as `"A" / "B"` with both speakers
   named, where each half is independently verbatim.
4. **Introduce no proper noun absent from the chapter.** No module canon, no
   names recalled from other documents, no place names, no counts, no dates the
   chapter does not state. If the chapter leaves a character unnamed, they stay
   unnamed.
5. **No forward leaks.** Facts from later chapters or later sessions are not
   available here. This is the hardest rule to self-check, because a leaked
   fact is usually *true* — which is exactly why it survives review. When a
   detail feels well-established, ask where you read it.
6. **Never normalise a spelling or fix a typo — spell names included.** If the
   chapter writes `Fairy Fire`, `Lathandar`, `Faerzess` or `Valpine`, reproduce
   it and queue it for the GM. Silent correction hides the defect *and* puts
   the summary out of sync with the bible.
7. **Preserve attribution exactly.** Roles, pronouns, and who said what. If the
   chapter's POV narrator is unreliable or sarcastic, report what they say
   without adopting their judgement as fact.
8. **Thin is correct when the chapter is thin.** A two-entry Items section, or
   no Items section at all, beats a padded one.
9. **`## NPCs` is for characters who DO something.** A deity invoked in passing
   or a ruler mentioned once does not get an entry.

## Required structure

```markdown
# <the chapter's H1, copied exactly>

Date: <in-world date or range from the chapter's POV headers>

## Summary
<Flowing prose paragraphs covering the chapter in narrative order. This is the
longest section. Weave verbatim quotes in naturally.>

## Scenes
### <Scene title>
#### <One sentence saying what this scene is>
- <Beat, in order. Quotes verbatim.>

## Locations
### <Place named in the chapter>
<What it is and what happened there. Omit the section if the chapter names no places.>

## NPCs
### <Name exactly as the chapter spells it>
<Who they are, what they did, how they speak.>

## Items
### <Object that matters>
<What it is and why it matters. Omit the section if there are none.>

## Memorable Moments
> "<verbatim quote>"
> — <Speaker>

*<Italic line giving the context that makes it land>*

**<Or a bold statement of a non-verbal moment.>**

*<Its italic context line.>*

## Spells
### <Spell name AS THE CHAPTER SPELLS IT>
<Who cast it and what it did. Omit the section if no spells are named.>

---

*<Honest provenance line — see SKILL.md step 5.>*
```

`## Scenes` and `## NPCs` are mandatory; a downstream gate
(`campaignlib.lineage._summary_is_structured`) regex-tests for both and rejects
a file without them.

## Self-check before running the verifier

- Every `"` pair: located in the chapter?
- Every capitalised name: present in the chapter?
- Every number: stated in the chapter?
- Anything you know that the chapter does not say — is it in the file?
