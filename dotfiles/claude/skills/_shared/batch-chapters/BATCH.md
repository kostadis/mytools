# Batch chapters — running one review stage across several chapters

Not a skill: there is no `SKILL.md`. It holds the **orchestration** used when a
stage skill (`/enhance-summary`, `/staged-consistency`, `/remove-recap`, or any
other skill with a review page) runs on N chapters at once. **The method
belongs to the stage skill.** This file covers only what repeats around it:
fan-out, one page per chapter, read-back, apply and manifest.

The review page itself is defined in `../review-artifact/CONTRACT.md` (the builder,
`savedAt`, unmarked cards, never pre-fill). Read that first; this file does not
restate it.

This design comes from a six-chapter run (2026-09-27). Enhancement, Stage 1
and remove-recap each ran as six forks and six pages. Before this, each stage
had its own hand-written read, apply and manifest scripts.

## The loop, per stage

```
0. batch.json          name the chapters, their Stage 0 sources, the target file
1. deterministic run   the stage's CLI, one process per chapter (check_consistency, enhance_summary, …)
2. fork per chapter    adjudicate from a brief → findings + items + page. No publish, no campaign edits.
3. validate            batch.py validate — counts, card↔item ids, builds review_<stage>.html
4. publish             one Artifact per chapter; record each uuid in batch.json under artifacts.<stage>
5. STOP                hand over the links; wait for the GM to say "done"
6. read back           Artifact read (path: index.html) per page → batch.py read
7. re-ask              unsaved pages, unmarked cards, discuss notes → chat (AskUserQuestion)
8. apply               batch.py apply --rulings chat_rulings.json   (all-or-nothing)
9. manifest            batch.py manifest → paste the Rulings section into the stage's manifest
10. verify + commit    the stage's own checks (quote verifier, …); one commit per stage, one campaign
```

## Step 2 — the fork brief

Forks (`subagent_type: "fork"`) keep the tape reading out of your context. You
keep the rulings. Write the brief **once per stage**, as a file with `<CH>`,
`<N>`, `<PREV>`, `<NEXT>` and `<STAGE0>` placeholders, and spawn all the forks
in one message. Each brief must say:

- **Campaign dir, branch, target file**, and what has already been reviewed
  upstream. Give the exact prior `findings_*/decisions_*/manifest_*` files.
- **The tape settles everything:** `transcript.cleaned.speakers.vtt`, citing
  cue numbers and timestamps. The neighbouring chapters' summaries are
  continuity evidence, **not** canon.
- **Grep every prior rulings log for the subject before carding it.** A finding
  that would reverse a ruling becomes a CONFLICT card that quotes the ruling.
- **The standing GM rulings from this cycle**, stated literally (for example,
  "the creatures in the chapter 20 fight are X, not Y"). Forks cannot see your chat.
- **Canon chain from CLAUDE.md for every name; never invent a spelling.** The
  registry holds names only.
- **Schema** (below), the review-items title/eyebrow/`reviewId`, and the builder
  path: `tmp/<CH>_<stage>_write.py`, so a card can be regenerated without
  re-running the fork.
- **Do NOT publish. Do NOT edit any campaign file.**
- **Return:** a one-line-per-card table, the counts, your doubts.

The briefs that worked are archived beside this file as
`briefs/stage1.md` and `briefs/recap.md`. Copy one and change the
campaign-specific lines.

## The findings schema — what makes the apply mechanical

`staged_review/findings_<stage>.json`, a list or `{"findings": [...]}`:

```json
{"id": "s1-04", "disposition": "card | auto | false_positive | note",
 "edits": [{"old": "exact text", "new": "replacement", "count": 1}], "...": "stage-specific fields"}
```

- `card` needs a GM ruling and gets an item on the page with the same `id`.
- `auto` is mechanical and already canon, such as a glossary spelling. It is
  applied without asking and listed in the page footer.
- `false_positive` and `note` never touch the file. A note can record an
  upstream gap, for example.
- **`count` is the exact number of occurrences of `old`.** The apply refuses on
  any mismatch. That is how a stale finding, a double apply or an ambiguous
  anchor is caught instead of silently mis-editing the file.
- Card text (`t`, `y`, `n`) holds no literal `\n`. `ev` is HTML-escaped. `y`
  says what approving writes **and where**, including whether the Stage 0
  source carries the same text. `n` is always a keep-verbatim option.

## Steps 6–8 — reading back without rubber-stamping

- `Artifact` `action: read`, `url`, `path: "index.html"` saves to
  `<scratchpad>/artifact-files/<uuid>/index.html`. Pass the parent directory as
  `--artifact-dir`.
- **Watches run out at 10 per session.** After that, publish results stop
  confirming a watch, so do not wait for a save notification. Rely on the GM
  saying "done", then read every page.
- `batch.py read` prints, per chapter, one of: saved with a tally, UNMARKED ids,
  DISCUSS notes, or **UNSAVED**. An unsaved page means the GM marked it but did
  not press Save. Ask them to save. Do not treat it as zero approvals.
- Take everything left open to chat, grouped: unmarked cards, discuss notes (one
  at a time, per CLAUDE.md), and whole unsaved pages if the GM would rather rule
  in chat. Record each answer in `chat_rulings.json` **with the GM's own words**
  in `said`. A discuss note that resolves to new wording carries that wording
  as `edits`. That wording is a second question, not your interpretation.
- `batch.py apply` refuses while anything is unresolved and writes **nothing,
  in any chapter**, until every chapter resolves and every count matches. Run
  `--dry-run` first. `--propagate-stage0` also applies an identical edit to the
  chapter's Stage 0 source wherever the same text occurs, and reports each hit.
  Use it when the Stage 0 source must stay in agreement, as at Stage 1.

## Tape corrections found along the way

A fork will find tape errors, such as one creature name misheard as another. These are not edits to
the target file. With GM approval:

- Add them to `transcript_corrections.yaml`, then run `sd_corrections apply --dir`
  and `sd_corrections check --dir`.
- The raw tape has **no cue ids**: number cues by 1-based ordinal.
- If a cue already has a record, **amend its `now:` line**. Do not add a second
  entry.
- Patch `transcript.cleaned.speakers.vtt` by cue id, keeping the speaker label.
  The speaker labels are not regenerated from the record.

## Environment traps

- **Worktree guard.** In an isolated session, compound bash (loops, variables,
  git plus anything else) is refused. Write the script to `$CLAUDE_JOB_DIR/tmp/`
  and run it by literal path. A heredoc that creates the script is compound
  too, so write it with the Write tool.
- **Stage 0 filenames vary per chapter.** Some are GMAssistant exports
  (`session_<date>_session_<date>.md`), some are `summary.md`. Put each chapter's
  name in `batch.json`. Never glob for it.
- **Model choice.** Every model-bearing CLI takes the model the user named for
  this run. Pass it explicitly each time; never rely on the fallback.
- **One commit per stage, one campaign per commit.** Check `git diff --cached`
  for audio files after any broad `git add`.

## `batch.py`

```
batch.py validate --config batch.json --stage <s>
batch.py read     --config batch.json --stage <s> --artifact-dir <scratchpad>/artifact-files
batch.py apply    --config batch.json --stage <s> [--rulings chat_rulings.json] [--propagate-stage0] [--dry-run]
batch.py manifest --config batch.json --stage <s> [--rulings chat_rulings.json] [--out-name FILE]
```

`--stage` is the file-name stem (`enhance`, `stage1`, `recap`). File names are
`staged_review/{findings,review_items,decisions}_<stage>.json` and
`review_<stage>.html`. `batch.json` and `chat_rulings.json` formats are in the
script's docstring. The script was verified against a real two-chapter
remove-recap run. It reproduced the committed result byte for byte. It refused to
apply without the chat rulings, and refused a second apply.

**What it does not do:** detection, adjudication, publishing, or anything
stage-specific in the manifest (renumbering, upstream gaps, and so on). Those
stay with the stage skill and with you.
