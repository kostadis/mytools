# Original audio beside a review decision

The GM preferred this presentation in the Hillsfar chapter 38 Stage 0 review
(2026-11-17). Reuse it when a ruling depends on uncertain spoken wording,
speaker attribution, or a recording boundary and the matching audio is available.
Ordinary canon or prose edits do not need a clip.

Keep the standard shared review page. On the relevant card, show:

- the exact proposed edit and its file/cue scope;
- an inline player for a short **original-recording** excerpt;
- the original transcript reading and, when available, an independently
  transcribed reading, with their sources named;
- enough surrounding dialogue to judge the exchange, plus cue numbers and
  recording-relative times;
- a recommended interpretation, explicit uncertainty, and a keep-verbatim choice.

Choose clip boundaries around the exchange rather than clipping only the disputed
word. Roughly eight seconds on either side worked in this review; widen or shorten
that context to fit the dialogue. Confirm the source recording and timeline first.
Reuse existing clips and ASR evidence where suitable. Follow the owning audio
workflow and existing host/data permissions when extraction or fresh ASR is needed;
this presentation preference grants no additional transfers or service changes.

Two ASRs agreeing on an awkward phrase is not proof of a lexical repair. Keep
raw and glossary-normalized readings distinguishable. If the audio remains
uncertain, offer a neutral paraphrase of the derived prose or retain the wording.
A tape correction is a separate, explicit file action through its correction
record; a prose-paraphrase approval does not authorize it. Decision-model scores
are displayed predictions, never saved GM rulings.

## Attach a clip without rebuilding the page UI

`attach_audio.py` accepts an already extracted WAV. It adds a responsive native
player to the card's `ev` and stores source/clip SHA-256 hashes and times in
`audio_evidence`. It checks the clip duration against the supplied time range.
It does not extract, transcribe, edit a transcript, or approve anything.

```bash
KIT=~/.codex/skills/_shared/review-artifact
python "$KIT/attach_audio.py" \
  --items review_items.json --id s0-06 \
  --clip audio/disputed-line.wav --source /absolute/path/recording.m4a \
  --start 120.0 --end 144.0 --out review_items.audio.json
python "$KIT/build_review.py" --save local \
  --in review_items.audio.json --out review.html
```

The output must be a new file. For several cards, feed the last output into the
next attachment, then freeze the final items file before handoff. Build, serve,
and read decisions against **that same final file**. Use the usual Tailscale
`serve_review.py` and **Save to VM** transport; verify the live page includes the
player and save marker. Preserve the run's chosen review threshold.

Embedding the WAV keeps the page self-contained; the server still exposes only
one capability URL, without a recording directory or extra asset routes. Retain
the small clip and its provenance, not a full recording on every card. Avoid
duplicating embedded audio across unnecessary intermediate specs. Keep the exact
questions, saved decisions, and audio hashes together in the stage record.

If new evidence changes a proposal already handed off, preserve its earlier
wording/rulings and use a new review ID and decision file for the revised question.
Loading or playing the audio is not a ruling. Never pre-fill choices; Discuss
and unmarked items keep the ordinary review semantics.
