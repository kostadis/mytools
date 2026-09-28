# Stage 0 adjudication brief — one chapter per fork

Placeholders:
- `<CAMPAIGN>` (absolute campaign dir) and `<BRANCH>`
- `<CH>` (session dir name) and `<N>` (chapter number)
- `<PREV>`/`<NEXT>` (neighbouring session dirs)
- `<STAGE0>`: this chapter's Stage 0 source file, the gm-assist export `enhance_summary` renders from
- `<TAPE>`: the speaker-labelled cleaned tape, usually `transcript.cleaned.speakers.vtt`
- `<TMP>` (job tmp dir)

## Inputs

- **Campaign dir:** <CAMPAIGN> (branch <BRANCH>).
- **Checked document:** `summaries/<CH>/<STAGE0>`. Nothing has been enhanced yet. A fix made here carries into the enhanced summary.
- **Report to adjudicate:** `summaries/<CH>/consistency_report_stage0_gmassist.md`.
- **Count the findings yourself.** Read the body, try several delimiters, and record which one matched. The banner count is unreliable.
- **Prior rulings already made on this chapter** (the transcript front end):
  - `speaker_review/` (the mapping, attendance, cue labels)
  - `spell_review/` (`decisions.json`, `chat_rulings.json`)
  - `transcript_corrections.yaml`

  Grep them before carding anything. A finding that would reverse a ruling is a CONFLICT card that quotes the ruling.

## Evidence

- **The tape settles everything.** Use `<TAPE>` and cite cue numbers and timestamps.
- **The report's "authoritative" sources are not authoritative.** A bible chapter and a module excerpt are downstream prose or the published plan. The table often diverged from both.
- **The neighbouring chapters' summaries** (<PREV>, <NEXT>) are continuity evidence, not canon.
- **Run the inline quote sweep** before judging quotes:

  ```
  python3 ~/.claude/skills/staged-consistency/verify_quotes.py --doc summaries/<CH>/<STAGE0> --vtt summaries/<CH>/<TAPE>
  ```

  Card any real miss it finds that the report did not.
- **Attribution is a speaker-label question.** Use the labels in `<TAPE>`. Never settle "who said it" from a summary.
- **Check who *can* do it: read the character sheets.** For any card about which PC cast a spell or used an ability, look it up in
  every candidate's sheet (the campaign's `docs/party/` or equivalent) and put the result on the card: "on the wizard's sheet (a
  cantrip) and on the monk's (a subclass feature)". If only one sheet has it, that settles it. If several do, the card presents a real
  two-candidate question, never a one-sided one. Speaker labels are fallible at turn boundaries; the sheet is not.

## False-positive filters (per /consistency-check step 5)

- **A finding that rests only on the bible or the module** is a false positive unless the tape agrees.
- **Anything already ruled** (see above) is a false positive. Cite the ruling.
- **Hedges the tape supports stay hedged.** Never harden a hedge into a fact.
- **Table rulings outrank the rulebook.** Module vocabulary versus the table's own words is not an error.

## Names

- Resolve every name through the canon chain in the campaign CLAUDE.md, and never invent a spelling.
- A settled glossary or registry spelling fix is an `auto`. List it in the footer.
- A conflict between canon sources is a card that shows every source. You do not rule on it.

## Dispositions

Use ids `s0-NN` for cards and `a-NN` for autos, plus `report_no`.

- **card:** needs a GM ruling. Its edits are `[{old,new,count}]` on `<STAGE0>`, count-checked.
- **tape card:** a garble in the tape itself, found while checking. Give the cue number and the exact `was`/`now` text. Approving writes a `transcript_corrections.yaml` entry (or amends the existing one for that cue) and regenerates the cleaned tapes.
- **auto:** settled and mechanical. Give its edits.
- **false_positive:** give a one-line reason that cites the tape or the ruling.

Every card has four fields:

- **t:** the decision, as a sentence.
- **y:** what approving writes, and in which file.
- **n:** what rejecting keeps. Always offer a keep-verbatim option.
- **ev:** verbatim cues with timestamps, HTML-escaped.

## Build

Write a builder at `<TMP>/<CH>_s0_write.py`. It writes:

- `staged_review/findings_stage0.json`
- `staged_review/review_items_stage0.json`, with:
  - title "Chapter <N> Stage 0"
  - eyebrow "<campaign> · ch<N> · stage 0 — <STAGE0>"
  - reviewId "stage0:<CH>"
  - a footer listing every auto and every false positive, plus the prior rulings you relied on

Then run `batch.py validate`, or check the counts and build `review_stage0.html` with `build_review.py`.

- No literal `\n` in card text.
- Do NOT publish. Do NOT edit any campaign file.

## Return

- a one-line-per-card table: id, severity, issue
- counts: report findings / cards / tape cards / autos / false positives, and the delimiter you counted
- your doubts
