# remove-recap, Phases 1–2: one chapter per fork

Placeholders:
- `<CAMPAIGN>`: the absolute campaign directory
- `<CH>`: the session directory name
- `<N>`: the chapter number
- `<PREV>`: the previous session directory
- `<STAGE0>`: this chapter's Stage 0 source file
- `<TMP>`: the job's tmp directory
- `<PRIOR>`: a previous remove_recap_manifest.md from this campaign, used as the format model (optional)

Read `~/.claude/skills/remove-recap/SKILL.md` first. This run happens **before** scene_extract, so detection is done by hand.

## Inputs

- **Campaign directory:** `<CAMPAIGN>`
- **Format model:** `<PRIOR>`
- **Target:** `summaries/<CH>/session-summary.md`. It has been enhanced and has passed Stage 0 and Stage 1 review with the GM.
  Surfaces 2 and 3 are the same file.
- **Stage 0 source:** `<STAGE0>` is not narration input. Still, report whether it carries the same recap.
- **Tape:** `transcript.cleaned.speakers.vtt`. Cite cue numbers and timestamps.
- **Session-start trim:** `notes/session_start_trims.json`, if the campaign keeps one. Chatter before the trim was never reviewed.
- **Previous chapter:** `<PREV>/session-summary.md`. The recap's content should already be there.

## Phase 1: detect

Read the opening cues up to the first line of live play, and apply the skill's marker grep. Report:
- who is talking
- where the recap starts and ends, as cue numbers and timestamps
- where live play begins
- which scene or scenes in session-summary.md carry the recap, and which Summary paragraphs or sentences

Also check whether a recap sits **inside** the first live scene. Two patterns to look for: a "GM recap:" bullet in a later scene,
or a first scene titled "Recap and …" that mixes recap with live play.

## Phase 2: rescue

Run:

```
python ~/.claude/skills/remove-recap/recap_unique.py --recap <scratch copy of the recap scene section> --against summaries/<PREV>
```

Then read the recap span on the tape and look for three kinds of content:
- GM asides that reveal or correct canon
- bookkeeping for this chapter: level-ups, rests, rulings, attendance, and who is running whose PC
- beats missing from the previous chapter's session-summary.md, which are upstream gaps

Quote each one verbatim, with its cue number.

## Build the review

1. Write a builder at `<TMP>/<CH>_recap_write.py`.
2. The builder writes `staged_review/findings_recap.json`. Each entry has:
   - an id of the form `rr-NN`
   - a kind: `boundary`, `scene_cut`, `prose_trim`, `rescue` or `upstream_gap`
   - a disposition: `card` or `note`
   - edits `[{old,new,count}]` on session-summary.md, count-checked
3. The builder writes `staged_review/review_items_recap.json`, with:
   - title: "Chapter <N> Recap"
   - eyebrow: "<campaign> · ch<N> · remove-recap — session-summary.md"
   - reviewId: "recap:<CH>"
   - footer: the detection evidence and any notes
4. Check the counts and build `staged_review/review_recap.html`. `batch.py validate` does both.

## Cards

Make one card per decision:
- **Cut or trim the recap scene, or leave it.** Give the exact scene heading, and the bullets removed or kept.
- **Trim the Summary prose.** Quote the exact sentences removed, and show how the paragraph reads afterwards.
- **Each rescue item.** Say where it goes: which scene or section of THIS chapter's summary, with the exact wording.
  An aside that reveals canon may belong in a grounding doc instead. In that case, propose "note for the GM" and make no edit.
- **Each upstream gap.** Make it a note against the previous chapter, with no edit here.

Rules for every card:
- Offer "leave it / keep verbatim" as the reject option.
- If there is no recap at all, make one card: "Mark #N as the start of play, cut nothing".
- Put no literal "\n" in card text, and HTML-escape the evidence.
- Do NOT publish. Do NOT edit any campaign file.

## Return

- a table with one line per card: id, kind, issue
- a detection summary: the recap span, the live-play start, and the markers that fired
- which scenes would renumber if a scene is cut. Before extraction, the cost is only the Scenes list.
- your doubts
