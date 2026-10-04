# Enhancement review brief — one chapter per fork

Placeholders:
- `<CAMPAIGN>` and `<BRANCH>`
- `<CH>` (session dir name) and `<N>` (chapter number)
- `<PREV>` and `<NEXT>` (neighbouring session dirs)
- `<STAGE0>`: the reviewed Stage 0 source the enhancement rendered from
- `<TAPE>`: usually `transcript.cleaned.speakers.vtt`
- `<TMP>`: the job tmp dir

## Inputs

- **Campaign and target:** `<CAMPAIGN>` (branch `<BRANCH>`). The file under review is `summaries/<CH>/session-summary.md`, the `enhance_summary` output rendered from `<TAPE>` and `<STAGE0>`.
- **Prior rulings.** Read these before carding anything:
  - `consistency_stage0_gmassist.sources.yaml` (resolution, carry_forward)
  - `staged_review/*_stage0.json`
  - `spell_review/`
  - `speaker_review/`

  A finding that reverses a Stage 0 ruling is a CONFLICT card. It quotes the ruling and says that approving the old reading means editing the Stage 0 source too. Never present it as a fresh question.
- **Quote leads:**
  - `quote_report_stage1.md` (from `sd_verify_quotes`)
  - the inline sweep: `python3 ~/.claude/skills/staged-consistency/verify_quotes.py --doc <CH>/session-summary.md --vtt <CH>/<TAPE>`

  Each flag is a lead to check on the tape. Cue splits, ellipsis joins and stutter smoothing are benign.
- **Continuity:** use `<PREV>` and `<NEXT>`: their `session-summary.md` where present, else their Stage 0 source. Check the hand-offs:
  - where the session opens and ends
  - who is present
  - items
  - NPC names and fates

  Neighbours are evidence, not canon. The tape wins.
- **Names:** use the canon chain from the campaign CLAUDE.md for every name, and never invent a spelling.

## Failure modes to check

- **Re-introduced Stage 0 removals.** For every approved Stage 0 card, check that its subject did not come back in the new
  summary: a struck word, a corrected referent, a quote trimmed by ruling. A re-introduction is a card that quotes the ruling.
- **Wrong-referent names.** The transcriber can write one canon name for another. Check every NPC the summary names against
  the tape and the second transcript at that beat.
- invented dice or damage values (grep the tape for the literal number)
- attribution drifting toward the most prominent character. For any spell or ability, check every candidate's character sheet
  (`docs/party/` or equivalent) and say on the card which sheets list it. Only one listing settles it; several make it a
  two-candidate question.
- events duplicated or lost
- "(truncated)" markers left in quotes
- DM asides relocated
- pronoun drift
- Summary and Scenes contradicting each other
- real player names used as characters

## Dispositions

- **card:** needs a GM ruling. Edits are `[{old,new,count}]` on `session-summary.md`, count-checked in file order.
- **benign:** checked and fine. Give a one-line reason that cites the tape.
- **note:** worth knowing, no edit.

Every card has four fields: `t` (the decision), `y` (what approving writes, and where), `n` (what rejecting keeps; always keep-verbatim), `ev` (verbatim tape cues with timestamps, HTML-escaped).

## Build

Write a builder at `<TMP>/<CH>_enh_write.py`. It writes:
- `staged_review/findings_enhance.json`
- `staged_review/review_items_enhance.json`, with:
  - title "Chapter <N> Enhancement"
  - reviewId "enhance:<CH>"
  - a footer listing every benign flag and every note

Then build `staged_review/review_enhance.html`, either by running `batch.py validate --stage enhance` or with `build_review.py`.

Do NOT publish, and do NOT edit any campaign file.

## Return

- a table with one line per card: id, severity, issue
- counts: cards, benign, notes
- the outcome of each quote flag
- your doubts
