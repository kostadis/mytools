# Batch chapters — running one review stage across several chapters

Not a skill: there is no `SKILL.md`. It holds the **orchestration** used when a
stage skill (`/enhance-summary`, `/staged-consistency`, `/remove-recap`, or any
other skill with a review page) runs on N chapters at once. **The method
belongs to the stage skill.** This file covers only what repeats around it:
fan-out, one page per chapter, read-back, apply and manifest.

The review page itself is defined in `../review-page/CONTRACT.md` (the builder,
`savedAt`, unmarked cards, never pre-fill). Read that first; this file does not
restate it.

This design comes from a six-chapter run (2026-09-27). Enhancement, Stage 1
and remove-recap each ran as six agents and six pages. Before this, each stage
had its own hand-written read, apply and manifest scripts. The inventory and
cohort sections were added on the next batch (2026-09-28). Those five chapters
had had no pipeline stage at all. One had no recording. Two had Descript
exports that were edited cuts, about half the length of the recording.

The third batch (2026-10-04) ran nine chapters through every stage from
speaker attribution to remove-recap, with about 350 GM rulings. It added the
known-name substitution check, the stage-to-stage re-introduction checks,
and the read-back rules for approvals that are not decisions.

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
   - whether to **replace** existing `session-summary.md` files that an older
     pipeline produced. Enhancement overwrites them, and every
     `scene_extractions*/` and `narration/` built from them goes stale. Name
     those directories in the question.

   **"Through stage X unless already done" means a per-chapter stage list.**
   A chapter that an older pass already took through the later stages gets
   only the stages it lacks. Record each chapter's list in `batch.json` and
   say so in the scope answer, so the GM can correct the reading.

   **Prep is chosen once, with dates in view.** For consistency stages,
   match session prep to chapters by the date in the prep filename and show
   each file's commit date beside it. A prep file committed weeks after its
   session may be a reconstruction, not prep. Reuse the approved set at every
   consistency stage.

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
  pole. Hand off each chapter's speaker page as its job finishes, and never wait
  for the whole queue before handing over the first page.

## The loop, per stage

```
0. batch.json          one cohort's chapters, their Stage 0 sources, the target file; blocked chapters listed apart
1. deterministic run   the stage's CLI, one process per chapter (check_consistency, enhance_summary, …)
2. agent per chapter   adjudicate from a brief → findings + items + page. No handoff, no campaign edits.
3. validate            batch.py validate — counts, card↔item ids, builds review_<stage>.html
4. hand off            give the GM each local review_<stage>.html path
5. STOP                wait for the GM to return saved decisions JSON
6. read back           place each export beside its page → batch.py read
7. re-ask              missing exports, unmarked cards and discuss notes → chat
8. apply               batch.py apply --rulings chat_rulings.json   (all-or-nothing)
9. manifest            batch.py manifest → paste the Rulings section into the stage's manifest
10. verify + commit    the stage's own checks (quote verifier, …); one commit per stage, one campaign
```

## Step 2 — the agent brief

Chapter agents keep the tape reading out of the orchestrator context. The orchestrator keeps the rulings. Write the brief **once per stage**, as a file with `<CH>`,
`<N>`, `<PREV>`, `<NEXT>` and `<STAGE0>` placeholders, and spawn all the agents
in one message. Each brief must say:

- **Campaign dir, branch, target file**, and what has already been reviewed
  upstream. Give the exact prior `findings_*/decisions_*/manifest_*` files.
- **The tape settles everything:** `transcript.cleaned.speakers.vtt`, citing
  cue numbers and timestamps. The neighbouring chapters' summaries are
  continuity evidence, **not** canon.
- **Grep every prior rulings log for the subject before carding it.** A finding
  that would reverse a ruling becomes a CONFLICT card that quotes the ruling.
- **The standing GM rulings from this cycle**, stated literally (for example,
  "the creatures in the chapter 20 fight are X, not Y"). Agents cannot see your chat.
- **Canon chain from the campaign instruction files for every name; never invent a spelling.** The
  registry holds names only.
- **Schema** (below), the review-items title/eyebrow/`reviewId`, and the builder
  path: `tmp/<CH>_<stage>_write.py`, so a card can be regenerated without
  re-running the agent.
- **Do NOT hand off the review page. Do NOT edit any campaign file.**
- **Return:** a one-line-per-card table, the counts, your doubts.

The briefs that worked are archived beside this file as `briefs/stage0.md`,
`briefs/enhance.md`, `briefs/stage1.md` and `briefs/recap.md`. Copy one and put the
campaign-specific facts in the agent prompt: players, attendance, standing
rulings, prep paths. A fact an agent cannot see is a fact it will contradict.

**Keep the cycle's standing rulings in one file** (`$TMP/RULINGS_<batch>.md`)
and point every agent at it. Append each ruling the moment the GM makes it.
Rulings pile up fast across stages: a name settled in the spell pass, an
attendance fact from speaker review, a Stage 0 reversal. When they are retyped
into each prompt, some get dropped. A ruling that **reverses** an earlier one
(for example, an enhancement card that undoes a Stage 0 edit) must also fix the
earlier stage's file, and the rulings file must say so.

**Use one fresh general-purpose agent per chapter with a self-contained brief.**
Keep the brief self-contained (paths, the rulings file, the archived brief to
follow, the output schema, "write only these files"), and put the
chapter-specific facts in the spawn prompt: attendance, the prior rulings that
touch this chapter, the previous and next session dirs. On the third batch,
eight general-purpose agents per stage ran in parallel with no loss of quality.

**Spawn each chapter's agent the moment its deterministic run finishes.**
Watch the run logs for their exit lines and do not wait for the slowest
chapter. The check for one chapter and the adjudication of another overlap.

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

  `was` is the raw cue exactly. Three agents given a brief without this schema
  wrote three shapes (`tape`; `card` plus `tape`; `card` plus
  `kind: tape` plus `tape_cues`). When a cue already has a record entry,
  **amend** its `now:`. Run the new `now` through the glossary first, so the
  cue's existing fixes survive.

### Cards must say exactly what they write, and the apply must write exactly that

Every item below reached a GM approval on the 2026-09-28 batch:

- **The card's display label is not the substitution.** A card showed
  `<garble> → saving (throw)`. Applying the label would have written "(throw)"
  onto the tape. Carry the exact `old → new` for the cue, from the agent's
  `was`/`now`, and have the apply use only that.
- **The cues a card lists are the cues it writes.** A card built its cue list
  by pattern match and showed two cues, where the agent meant only one.
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

- Prefer `../review-page/serve_review.py` when the Codex VM is reachable over
  Tailscale. Its **Save to VM** button validates and atomically writes the JSON
  to the configured `--out` path. If the page is opened directly, **Save
  output** downloads a JSON export; put it in the same review directory as the
  page, using the page's requested output name: `decisions_<stage>.json`, or
  `decisions.json` for a plain-name front-end review. A pasted **Copy output**
  payload is equivalent after it is saved to that path. `batch.py read`
  validates each export against the exact
  `review_items` file that built its page, so a stale export is rejected.
- With a directly opened page there is no save notification; wait for the GM
  to return the export or say that it is ready. With the server, a successful
  **Save to VM** response confirms the configured file was written. Then read
  every chapter's decision file.
- `batch.py read` prints, per chapter, one of: saved with a tally, UNMARKED ids,
  DISCUSS notes, **NOT EXPORTED**, **UNSAVED**, or **READ FAILED**. A missing
  export usually means the GM marked the page but did not press Save or Copy.
  Ask for the export. Do not treat it as zero approvals. A JSON file without
  `savedAt` is also not a ruling, and a stale or malformed export fails the
  read. Re-run `batch.py read` after each replacement. A page whose only cards
  write nothing (a boundary marker) can be ruled in chat instead of asking a
  third time.
- **Some approvals are not decisions.** Take these back to chat as well:
  - **An approved card that needs replacement text but has none.** A card
    whose `y` reads "write the right form in the note" was approved without a
    note. Treat it as Discuss and ask for the exact text.
  - **An approved card whose own evidence argued for rejecting it.** A
    conflict card said "the evidence favours rejecting". The GM approved it in
    a run of approvals, then reversed it when asked once with the evidence.
    Confirm these one at a time and say why you are asking.
- **Discuss notes need the canon chain too.** Notes are typed at speed and
  carry name misspellings: an NPC's surname with one letter changed, and a
  PC's name with two letters transposed. Show the canonical spelling
  letter by letter in the follow-up, and write the canonical form.
- **"Just drop one in" is not licence to pick a name.** When a note asks you to
  supply a name ("I was searching for another X's name"), offer the canon
  candidates that fit, with their registry notes, and let the GM choose.
- **One reading per note, or ask.** A note like "I meant X" can mean edit the
  document, edit the tape, or both. Offer each reading as an option that names
  the files it writes.
- Take everything left open to chat, grouped: unmarked cards, discuss notes (one
  at a time, per the campaign instruction files), and whole unsaved pages if the GM would rather rule
  in chat. Record each answer in `chat_rulings.json` **with the GM's own words**
  in `said`. A discuss note that resolves to new wording carries that wording
  as `edits`. That wording is a second question, not your interpretation.
- `batch.py apply` refuses while anything is unresolved and writes **nothing,
  in any chapter**, until every chapter resolves and every count matches. Run
  `--dry-run` first. `--propagate-stage0` also applies an identical edit to the
  chapter's Stage 0 source wherever the same text occurs, and reports each hit.
  Use it when the Stage 0 source must stay in agreement, as at Stage 1.

## When a stage has only a handful of rulings

Per the campaign review threshold (about a dozen), a stage whose cards total fewer
than that across **all** chapters is ruled in chat, not on pages. Build the
items files anyway, since they are the record. Ask one question per card with
the exact before and after text, and put every answer in the rulings file.
`batch.py apply` accepts a chapter whose page was never handed off, as long
as the chat rulings cover every card. The manifest records "ruled in chat".
The 2026-09-28 remove-recap stage (8 cards across 3 chapters) ran this way.

## Each stage can bring back what an earlier stage removed

`enhance_summary` renders from the reviewed Stage 0 source and the tape, and
it can still re-introduce wording that Stage 0 removed. On the third batch it
brought back a struck "contact poison", a quote word the GM had cut, and a
"feat" the GM had ruled to be a spell. So:

- **The enhancement brief must list every approved Stage 0 card's subject.**
  The agent then checks each one in the new summary. A re-introduction is a
  card that quotes the Stage 0 ruling.
- **Later-stage cards that fix the Stage 0 source are hand-applied.**
  `batch.py apply --propagate-stage0` copies an edit to the Stage 0 source only
  where the *same* text occurs. A card that needs a different edit there (the
  summary was already right but the gm-assist was not) carries a
  `stage0_edits` list. Apply those by hand with exact counts and name them in
  the manifest.
- **An approval covers the target file only.** When a card's `y` says "the same
  wording also sits in the Stage 0 source", approving it does not authorise
  editing that file. Ask, or leave it and say so.
- **Ruling conflicts between stages are expected.** A later stage that finds
  two earlier GM rulings in conflict, or a GM aside contradicting a ruling,
  makes a card quoting both. Remove-recap is where these surface most: the GM
  reads an older summary aloud and corrects it on the fly ("no, that was a
  typo, it was X"). Collect those asides as questions for after the pages, and
  put the live-play cue beside each one. On the third batch, one such aside
  overturned an earlier ruling and two did not.

## Cross-chapter checks catch what per-chapter checks cannot

Each agent sees one chapter, plus its neighbours only as prose. Names drift
between chapters in ways no single chapter shows. One chapter's tape used an
NPC's canonical name; two chapters later the tape used a different word for
the same NPC (same friend, same role), and that chapter's spell pass ruled it a
new real name. Only the earlier chapter's
enhancement review, reading its own tape, surfaced the collision. So:

- Give every enhancement and Stage 1 agent the neighbouring chapters' **tapes**
  as well as their summaries, and ask it to grep them for every NPC the
  chapter names.
- Before a spell-pass card says a name is new, grep the whole batch's tapes
  and the previous batch's summaries for other names used in the same role
  (same friend, same place, same title).

### Known-name substitution: the check the spell pass cannot make

An LLM-based transcriber can write a **correct canon name for the wrong
person**: one NPC's name where another was spoken, or a PC's name where the
speaker named an NPC. On the third batch this happened in five of eight
chapters: one name stood in for another 5 to 15 times in a session. The tape
was internally consistent, and every downstream document inherited the error.
`/vtt-spell-pass` cannot see it, because it only surfaces unknown tokens.

When a second, independent transcript shares the recording's timeline (a Zoom
per-participant VTT does, to within about a second):

1. Normalise both through the glossary.
2. For every registry name or alias in the target tape, collect the registry
   names the other transcript has within ±4 s.
3. Flag a name whose window never contains it but does contain a *different*
   registry name. Flag names that never agree (agree = 0, misses ≥ 2) first.
   Expect false positives from generic words that are also aliases ("Hold
   on", a capitalised common noun). Read each flagged cue before carding it.
4. Card each confirmed one as a **cue-scoped** tape entry, one cue per card,
   with both readings side by side. Never make it a glossary row: both names
   are canon.

Tell the Stage 0 agents to expect the same wrong names in the gmassist
export, which was generated from the same text, and to card each occurrence.
On the third batch, Stage 0 and enhancement found every place the wrong names
had reached.

## Re-asks carry context, or they get dismissed

A chat re-ask of an unmarked card or a note-less Discuss card must bring:

- the surrounding cues (±4), **each with its speaker label**;
- the second transcription's reading of the same span;
- the module or bible line when the card rests on one.

On the second batch, the GM dismissed a whole round of bare "X → Y?" questions: *"I don't have context."* Asked again with context, every one was answered at once. One was answered differently from the card's guess: the name the card proposed to correct was ruled "Correct." as heard.

## Speaker attribution when the chapters differ

- **Zoom per-participant VTT** (each person on their own connection) is the strongest second source. Convert its cues to a turns JSON (speaker = Zoom name) and pass it as `diarize_label.py --md`.
  - **Map Zoom display names to players explicitly**, and fail on any label not in the map. Display names drift between sessions: a player may join under a PC's name or a full name. Take each mapping from `players.yaml` or from an earlier GM-approved run record, and never infer one.
  - **Set `num_speakers` per chapter** from the people present. Absences show up as Zoom names missing from a session; confirm them with the GM once, in the inventory question set.
  - **When pyannote spends two bins on the GM, two players merge.** Name the merged player's cues from their own Zoom feed (`--md-label {"<player>":"<player>"}`). The tool's agreement figure then looks bad, because it excludes multi-bin speakers. Report **by-name agreement on the final file** instead: each cue's label against the Zoom participant with the most overlap. On the third batch, the tool reported 76.5% and by-name agreement was 97.7%.
  - **Context-judged cue review scales.** Nine chapters had about 1,800 disagreeing cues. Agents judged about 420 of them at ≥ 70% confidence and sent 13 to the GM. Have the judging agent return both the lean and the confidence inside each `ask_gm` entry, so the page can show "approve = the lean" without having to look it up.
  - **Relabels after the speaker file is written:** later stages surface mislabelled cues. Patch the label in `transcript.speakers.vtt` (text and timing untouched), add the cue to `approved_cue_labels.json`, append the ruling and the new sha256 to the run record, then rebuild `transcript.cleaned.speakers.vtt`.
- **No second recording:** `/speaker-attribution-text` run by an agent that **never sees the diarization** is a usable cross-check. Weigh it as an inference, and say so on the page.
- **When the acoustic clustering fails:**
  - The signs are one cluster above 55%, and three players scattered across clusters with no qualifying mapping.
  - Offer a re-run with one extra bin first. On the second batch it changed nothing.
  - If that fails too, the GM may make the text inference primary. Render it in best-guess mode: every label marked inferred, and the GM's cue rulings recorded as `gm_confirmed`.
- **Tiny extra clusters (under 0.5%) can be someone in the GM's room.** Read their lines before mapping them to the GM. A line like "<someone not at the table> is saying…" right after one is the tell. Label such a voice `Room (not at table)` only after the GM confirms.
- **Relabelling an already-approved attribution** (a new second source arrives later): a card must say plainly that it revises the earlier approval. Leave prior cue rulings untouched. Fix the file header when it no longer holds, for example a "single acoustic source" line.

## Tool gaps found on the second batch

- `sibling_context.py` does not strip a Descript `.md` export's unescaped `[hh:mm:ss]` stamps, so every candidate scores low against it. Search a cleaned copy by hand until that's fixed.
- `lint_glossary.py --verify-output` flags ordinary words that collide with a row's multi-word wrong-form. Example: "Lay down your weapons" against a row whose wrong-form is "a lay". Read each hit before calling it an error.

## Tool gaps found on the third batch

- **`batch/batch_scan.py` passes neither `--registry` nor the session-start
  trim**, and needs a `manifest.json` some campaigns lack. A small wrapper
  that runs the same Phase 0/1/2.5 steps with `--registry` and
  `--skip-before` works. Pin `PYTHONHASHSEED=0` in the wrapper too.
- **Sibling lookups over a whole transcript are slow.** About 100 candidates
  against a 1,100-cue sibling did not finish in two minutes. When the two
  transcripts share a timeline, search only the sibling cues within ±90 s of
  the candidate's own cue. That runs in seconds and gives better matches.
- **`find_unknowns.py` surfaces sentence-initial ordinary words** ("All",
  "Do", "We're") and tokens already in the state's ignored list. Agents
  should suppress both without a card.
- **Raw GMAssistant tapes can have a cue whose end precedes its start.**
  `diarize_label.py` refuses it. Repair the timing in a derived scratch copy
  only, and carry the repaired timing into the speaker file with a NOTE.
  `sd_corrections` keeps the original timing in the cleaned tape, so the
  labelled cleaned tape must accept that one mismatch by name.
- **Raw GMAssistant tapes can drop spoken numbers** ("at p.m.", "at around .").
  This is a source limitation, not spell-pass damage. Check the raw cue
  before blaming a glossary row.
- **Cue edits must match the whole cue, not its first line.** GMAssistant cues
  run to several text lines. A matcher that reads only the first line misses
  later occurrences silently, so assert that every listed cue matched.
- **`batch.py validate` builds no page when a chapter has zero items.** That
  is expected. List the chapter as "nothing to rule" when handing over links.
- **`registry alias` rewraps long note lines** across the YAML. Parse the
  before and after files and confirm that only the intended entity changed
  before you commit.
- **`add_to_glossary.py` searches one section, and a canonical can have two
  rows.** Moving a form between rows must find the row that *holds* the form,
  not the first row with that canonical. A script that edits the glossary
  should refuse to write until every move resolves.

## Tape corrections found along the way

An agent will find tape errors, such as one creature name misheard as another. These are not edits to
the target file. With GM approval:

- Add them to `transcript_corrections.yaml`, then run `sd_corrections apply --dir`
  and `sd_corrections check --dir`.
- The raw tape has **no cue ids**: number cues by 1-based ordinal.
- If a cue already has a record, **amend its `now:` line**. Do not add a second
  entry.
- Patch `transcript.cleaned.speakers.vtt` by cue id, keeping the speaker label.
  The speaker labels are not regenerated from the record.
- **A tape card may also edit the summary's quote of the same cue.** Give it
  `edits` on the target as well as its `tape` list. `batch.py apply` writes the
  target edits, and the tape entry stays a hand step. Verify both landed.
- **Settle glossary output to a fixed point after cue edits.** A card that
  writes a name the glossary rewrites again (a player's real name mapped to
  "GM") changes on the next pass. Re-apply the glossary until nothing changes,
  record the settled text, and tell the GM when a card's literal wording was
  normalised this way.
- **A standing row can fire on a literal phrase.** A row mapping a mishearing
  that is also an ordinary phrase (a haircut description mapped to an NPC's
  name) rewrites every literal use. When the GM drops the form from the row,
  existing records still carry the old substitution. Grep every chapter's
  record for entries whose `was` holds the dropped form, and put each one to
  the GM. Some are real nicknames for the NPC.

## Environment traps

- **Worktree guard.** In an isolated session, compound bash (loops, variables,
  git plus anything else) is refused. Write the script to `/tmp/`
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
- **Review pages are local files.** Give the GM the exact path for every page
  and the expected decision filename. Plan on an explicit returned export;
  opening a page or changing its mtime is never a ruling.
- **Background stdout is buffered.** A Python loop run in the background
  prints nothing until it exits. Check progress by the files it writes, or run
  it with `python3 -u`.
- **`pkill -f <script>` can kill your own shell** when the shell's command line
  contains the script name. Kill by PID.

## `batch.py`

```
batch.py validate --config batch.json --stage <s> [--target stage0|FILE]
batch.py read     --config batch.json --stage <s> [--review-dir D --plain-names]
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

**What it does not do:** detection, adjudication, review handoff, or anything
stage-specific in the manifest (renumbering, upstream gaps, and so on). Those
stay with the stage skill and with you.
