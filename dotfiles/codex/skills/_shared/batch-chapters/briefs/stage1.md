# Stage 1 adjudication brief — one chapter per agent

Placeholders: <CAMPAIGN> (absolute campaign dir), <BRANCH>, <CH> (session dir name), <N> (chapter number),
<PREV>/<NEXT> (neighbouring session dirs), <STAGE0> (this chapter's Stage 0 source file), <TMP> (job tmp dir).

## Inputs

- **Campaign dir:** <CAMPAIGN> (branch <BRANCH>).
- **Checked document:** summaries/<CH>/session-summary.md. It is the enhance_summary output, and the GM has ALREADY reviewed it.
  The review record is:
  - staged_review/decisions_enhance.json
  - staged_review/findings_enhance.json
  - staged_review/manifest_enhance.json (applied cards, discuss rulings, follow-ups)
- **Report to adjudicate:** summaries/<CH>/consistency_report_stage1_summary.md.
  Its context: party.md, the glossary, known additions, the prep files, <STAGE0> and the auto-loaded registry.
- **Count the findings yourself.** Read the report body, try several delimiters, and record which one matched.
  The banner count is unreliable.

## Evidence and prior rulings

The tape settles everything. Use transcript.cleaned.speakers.vtt and cite cue numbers and timestamps.
For any card about which PC cast a spell or used an ability, check every candidate's character sheet (the campaign's
`docs/party/` or equivalent) and state on the card which sheets list it. One sheet settles it; several make it a genuine
two-candidate question that the card must show both sides of.
The neighbouring chapters' session-summary.md files (<PREV>, <NEXT>) are continuity evidence, not canon.

Before carding anything, grep every prior rulings log for its subject:

- consistency_stage0_*.sources.yaml
- staged_review/decisions_stage0.json and findings_stage0.json
- decisions_enhance.json, findings_enhance.json and manifest_enhance.json
- spell_review/
- speaker_review/

If a finding would reverse a prior ruling, make it a CONFLICT card that quotes the ruling. Never present it as a fresh question.

## False-positive filters (per /consistency-check step 5)

- **The bible chapter is downstream prose.** So is any other narrative rendering. A finding that rests only on it, or only on
  the published module (the table may have diverged), is a false positive unless the tape agrees.
- **Anything the GM already ruled on is a false positive.** Cite the ruling.
- **Hedges the tape supports stay hedged.** Never harden a hedge into a fact.

## Names and standing rulings

Resolve every name through the canon chain in the campaign instruction files, and never invent a spelling. The registry holds names only.

Standing GM rulings from this cycle (state each one literally, because agents cannot see the chat):
- <ruling 1>
- <ruling 2>

## Dispositions

Use the stage's usual schema, with ids s1-NN and report_no.

- **card:** needs a GM ruling. Its edits are [{old,new,count}] on session-summary.md, count-checked.
- **auto:** purely mechanical and already canon, e.g. a glossary spelling. List it in the footer, with its edits.
- **false_positive:** a one-line reason that cites the tape or the ruling.

Every card has four fields, and the reject option always keeps the text verbatim:

- **t** — the decision, as a sentence.
- **y** — what approving writes and where. Say whether <STAGE0> carries the same text.
- **n** — what rejecting keeps.
- **ev** — verbatim tape cues with timestamps, HTML-escaped.

## Build

Write a builder at <TMP>/<CH>_s1_write.py that writes:

- **staged_review/findings_stage1.json**
- **staged_review/review_items_stage1.json**, with:
  - title "Chapter <N> Stage 1"
  - eyebrow "<campaign> · ch<N> · stage 1 consistency — session-summary.md"
  - reviewId "stage1:<CH>"
  - a footer listing every auto and every false positive

Then check the edit counts and build the page (batch.py validate does both, or run build_review.py directly).

- No literal "\n" in card text.
- Do NOT hand off the review page. Do NOT edit any campaign file.

## Return

- a one-line-per-card table (id, severity, issue)
- the counts (report findings / cards / auto / false positives) and the delimiter you counted
- your doubts
