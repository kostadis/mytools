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
had its own hand-written read, apply and manifest scripts. The inventory and
cohort sections were added on the next batch (2026-09-28). Those five chapters
had had no pipeline stage at all. One had no recording. Two had Descript
exports that were edited cuts, about half the length of the recording.

## Before the first stage: inventory, gaps, cohorts

**Do not assume the chapters are alike, or that the pipeline has started.**
Chapters recorded months apart arrive with different inputs, and the stage you
were asked for may not be the next one due.

0. **Take the inventory from a fresh branch off `origin/main`, never from the
   branch you happen to be on.** Other sessions land work in parallel. An
   inventory from a stale worktree branch once reported a chapter as having
   no recording and no attribution, when its attribution had already been
   merged by another session. Also run `git log --all --oneline -- <chapter
   dir>` for work still in flight on unmerged branches.
   **Media are not in worktrees.** Audio files (`.m4a`, `.mp3`) are untracked,
   so they exist only in the **main checkout** (and any `recordings/` folder
   there). Look for them there, by absolute path, before calling a recording
   missing.
1. **Inventory every chapter.** List what each session directory holds. For
   each stage, record whether it has run: `.speakers.vtt`,
   `transcript_corrections.yaml`, `staged_review/*_stage0*`, `session-summary.md`,
   `*_stage1*`, `remove_recap_manifest.md`. The batch starts at the earliest
   stage **any** chapter is missing, per
   `~/src/CampaignGenerator/docs/design/SkillPipelineOrder.md`. It never starts
   at the stage you were asked for if an earlier one is missing.
2. **Check each chapter's inputs against its own recording.** This is cheap,
   and every item below has been hit:
   - **Recording present?** Look in the session directory and the campaign's
     recordings folder. Match by the `GMT<date>` stamp, not by the chapter
     number in a filename. Filenames carry stale pre-renumber chapter numbers.
   - **Which tool made each transcript?** The filename does not say. Ask the GM
     once per campaign and record the answer. On one campaign every
     `transcript.vtt` the GM called "the Zoom VTT" was a Descript VTT export,
     and the labelled `.md` beside it was a second Descript export of the same
     session. Two exports from one tool are **one** text source. The only
     independent evidence on *who spoke* is a clustering from another tool
     (pyannote on the recording) set against Descript's voice profiles. Do not
     report a "Zoom plus Descript" cross-check that does not exist.
   - **Does each transcript run the full session?** Compare the last timestamp
     with the recording's length and the Zoom VTT. A Descript export that stops
     at 50 minutes of a 96-minute session is an **edited cut**. Its timings do
     not align with the raw audio, so cross-checking against it needs
     `/speaker-attribution`'s *raw audio, edited transcript* path, not the
     plain join. A transcript much **longer** than usual may span two
     sessions.
   - **Duplicates.** Two exports that differ only in their title line are one
     source, not two. Use `diff` or `sha256sum`.
   - **Speaker labels.** Count them against the roster. Voice-profile names that
     are PCs (`zalthir`), misspelled profiles (`kostaids`), and unlabelled Zoom
     cues (one shared microphone) each change the attribution path.
   - **Stage 0 source.** Record each chapter's filename. A chapter with none has
     nothing for `enhance_summary` to render from.
3. **Split the batch into cohorts by path, and set the odd ones out aside.**
   One batch runs one path. A chapter that needs a different attribution route
   (text-only, single source, or edited-cut projection) or is missing an input
   goes into `batch.json` under `"blocked": [{"dir": …, "reason": …}]`. It is
   not forced through a path it does not fit. `batch.py` ignores `blocked`, so
   the manifest and commit message must name those chapters.
4. **Show the GM the gaps first, then ask.** Give a table with one row per
   chapter, what it has and what it lacks, plus what each gap costs. Then
   collect every run-wide decision in **one** question set:
   - scope: which stages
   - model
   - what happens to each blocked chapter
   - each chapter's single-source acceptance (acceptance does not carry over
     from an earlier batch)

   Questions asked without the gaps in view get dismissed, and they should be.

## Which stages the loop covers

- **Stages whose output is edits to a document** use the whole loop below,
  including `batch.py validate/apply/manifest`. These are Stage 0, enhancement
  review, Stage 1 and remove-recap.
- **Transcript front-end stages** use steps 0–7: one page per chapter,
  `batch.py read --review-dir speaker_review --plain-names`, and the re-ask
  pass. Their apply belongs to their own skill. These are
  `/speaker-attribution` and `/vtt-spell-pass`. Attribution writes a new
  `.speakers.vtt` and run record. The spell pass writes
  `transcript_corrections.yaml` and regenerates `.cleaned.vtt`. Neither is a
  text substitution in a summary, so `batch.py apply` must not be used for
  them.
- **Diarization is a queue, not a fan-out.** Only one host has the environment,
  and it takes one job at a time. Start the queue first, because it is the long
  pole. Publish each chapter's speaker page as its job finishes, and never wait
  for the whole queue before handing over the first page.

## The loop, per stage

```
0. batch.json          one cohort's chapters, their Stage 0 sources, the target file; blocked chapters listed apart
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

The briefs that worked are archived beside this file as `briefs/stage0.md`,
`briefs/stage1.md` and `briefs/recap.md`. Copy one and put the
campaign-specific facts in the fork prompt: players, attendance, standing
rulings, prep paths. A fact a fork cannot see is a fact it will contradict.

**Keep the cycle's standing rulings in one file** (`$TMP/RULINGS_<batch>.md`)
and point every fork at it. Append each ruling the moment the GM makes it.
Rulings pile up fast across stages: a name settled in the spell pass, an
attendance fact from speaker review, a Stage 0 reversal. When they are retyped
into each prompt, some get dropped. A ruling that **reverses** an earlier one
(for example, an enhancement card that undoes a Stage 0 edit) must also fix the
earlier stage's file, and the rulings file must say so.

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
- **Tape cards have one schema:**

  ```json
  {"disposition": "tape", "tape": [{"cue": N, "was": "...", "now": "..."}]}
  ```

  `was` is the raw cue exactly. Three forks given a brief without this schema
  wrote three shapes (`tape`; `card` plus `tape`; `card` plus
  `kind: tape` plus `tape_cues`). When a cue already has a record entry,
  **amend** its `now:`. Run the new `now` through the glossary first, so the
  cue's existing fixes survive.

### Cards must say exactly what they write, and the apply must write exactly that

Every item below reached a GM approval on the 2026-09-28 batch:

- **The card's display label is not the substitution.** A card showed
  `<garble> → saving (throw)`. Applying the label would have written "(throw)"
  onto the tape. Carry the exact `old → new` for the cue, from the fork's
  `was`/`now`, and have the apply use only that.
- **The cues a card lists are the cues it writes.** A card built its cue list
  by pattern match and showed two cues, where the fork meant only one.
  The GM approved both, so both were written. Build the list from the
  finding, not from a regex.
- **A glossary row's wrong-form is the name alone.** `For <Name> →
  <Name>` would have deleted "For" from every future transcript. Strip
  function words before a row reaches a card.
- **"In none of the canon sources" is a claim to check, never a template
  string.** The page builder printed it on every new-name card. Two names it
  called new were registry NPCs spelled one letter differently. Stage 0 caught one, and
  a fuzzy registry check caught the other. Before a card says "not in canon",
  the orchestrator runs a fuzzy match against the registry and the bible
  chapter for that session. When a later stage overturns an earlier ruling's
  evidence, **re-ask with the new evidence**. Do not defend the ruling, and
  do not silently flip it.

## Steps 6–8 — reading back without rubber-stamping

- `Artifact` `action: read`, `url`, `path: "index.html"` saves to
  `<scratchpad>/artifact-files/<uuid>/index.html`. **That `<uuid>` is not the
  id in the page URL**, and it can change between reads. Record the saved path
  the read result names under `artifacts.<stage>` in `batch.json`. `batch.py
  read` accepts a path ending in `.html` directly. Keep the URL under
  `urls.<stage>` for re-reads.
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

## When a stage has only a handful of rulings

Per the CLAUDE.md threshold (about a dozen), a stage whose cards total fewer
than that across **all** chapters is ruled in chat, not on pages. Build the
items files anyway, since they are the record. Ask one question per card with
the exact before and after text, and put every answer in the rulings file.
`batch.py apply` accepts a chapter whose page was never published, as long
as the chat rulings cover every card. The manifest records "ruled in chat".
The 2026-09-28 remove-recap stage (8 cards across 3 chapters) ran this way.

## Cross-chapter checks catch what per-chapter checks cannot

Each fork sees one chapter, plus its neighbours only as prose. Names drift
between chapters in ways no single chapter shows. One chapter's tape used an
NPC's canonical name; two chapters later the tape used a different word for
the same NPC (same friend, same role), and that chapter's spell pass ruled it a
new real name. Only the earlier chapter's
enhancement review, reading its own tape, surfaced the collision. So:

- Give every enhancement and Stage 1 fork the neighbouring chapters' **tapes**
  as well as their summaries, and ask it to grep them for every NPC the
  chapter names.
- Before a spell-pass card says a name is new, grep the whole batch's tapes
  and the previous batch's summaries for other names used in the same role
  (same friend, same place, same title).

## Re-asks carry context, or they get dismissed

A chat re-ask of an unmarked card or a note-less Discuss card must bring:

- the surrounding cues (±4), **each with its speaker label**;
- the second transcription's reading of the same span;
- the module or bible line when the card rests on one.

On the second batch, the GM dismissed a whole round of bare "X → Y?" questions: *"I don't have context."* Asked again with context, every one was answered at once. One was answered differently from the card's guess: the name the card proposed to correct was ruled "Correct." as heard.

## Speaker attribution when the chapters differ

- **Zoom per-participant VTT** (each person on their own connection) is the strongest second source. Convert its cues to a turns JSON (speaker = Zoom name) and pass it as `diarize_label.py --md`.
- **No second recording:** `/speaker-attribution-text` run by a fork that **never sees the diarization** is a usable cross-check. Weigh it as an inference, and say so on the page.
- **When the acoustic clustering fails:**
  - The signs are one cluster above 55%, and three players scattered across clusters with no qualifying mapping.
  - Offer a re-run with one extra bin first. On the second batch it changed nothing.
  - If that fails too, the GM may make the text inference primary. Render it in best-guess mode: every label marked inferred, and the GM's cue rulings recorded as `gm_confirmed`.
- **Tiny extra clusters (under 0.5%) can be someone in the GM's room.** Read their lines before mapping them to the GM. A line like "<someone not at the table> is saying…" right after one is the tell. Label such a voice `Room (not at table)` only after the GM confirms.
- **Relabelling an already-approved attribution** (a new second source arrives later): a card must say plainly that it revises the earlier approval. Leave prior cue rulings untouched. Fix the file header when it no longer holds, for example a "single acoustic source" line.

## Tool gaps found on the second batch

- `sibling_context.py` does not strip a Descript `.md` export's unescaped `[hh:mm:ss]` stamps, so every candidate scores low against it. Search a cleaned copy by hand until that's fixed.
- `lint_glossary.py --verify-output` flags ordinary words that collide with a row's multi-word wrong-form. Example: "Lay down your weapons" against a row whose wrong-form is "a lay". Read each hit before calling it an error.

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
- **`add_to_glossary.py --section` knows only `pcs|npcs|items|factions|locations|table`.**
  Any other key creates a brand-new section at the end of the glossary: a
  `races` key split two existing rows in two. Check the
  canonical's existing row first, and `git diff` the glossary after every
  batch of rows.
- **One commit per stage, one campaign per commit.** Check `git diff --cached`
  for audio files after any broad `git add`.

## `batch.py`

```
batch.py validate --config batch.json --stage <s> [--target stage0|FILE]
batch.py read     --config batch.json --stage <s> --artifact-dir <scratchpad>/artifact-files [--review-dir D --plain-names]
batch.py apply    --config batch.json --stage <s> [--target stage0|FILE] [--rulings chat_rulings.json] [--propagate-stage0] [--dry-run]
batch.py manifest --config batch.json --stage <s> [--rulings chat_rulings.json] [--out-name FILE]
```

`--target stage0` sends edits to each chapter's Stage 0 source, which is what
Stage 0 edits. `validate` simulates the edits in file order, autos first, the
same way `apply` runs them. Checking each edit against the unedited file gives
false mismatches once an auto has renamed something a card anchors on.
Approved **tape** cards are listed for hand-application to
`transcript_corrections.yaml`. `apply` never writes the record.

`--stage` is the file-name stem (`stage0`, `enhance`, `stage1`, `recap`). File names are
`staged_review/{findings,review_items,decisions}_<stage>.json` and
`review_<stage>.html`. `batch.json` and `chat_rulings.json` formats are in the
script's docstring. The script was verified against a real two-chapter
remove-recap run. It reproduced the committed result byte for byte. It refused to
apply without the chat rulings, and refused a second apply.

**What it does not do:** detection, adjudication, publishing, or anything
stage-specific in the manifest (renumbering, upstream gaps, and so on). Those
stay with the stage skill and with you.
