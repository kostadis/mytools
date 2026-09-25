---
name: staged-consistency
description: "Run CampaignGenerator consistency checks at each session-doc pipeline boundary: gm-assist, session-summary, scene extractions, and narration. Use when the user asks for staged consistency or types /staged-consistency [session-dir]."
metadata:
  short-description: Multi-stage session-doc consistency review
---

# Staged Consistency

Run a consistency check at each LLM pipeline boundary, with a human review gate
between stages. This prevents a stale quote or summary error from being fixed in
one layer and then reintroduced by the next layer.

This is the Codex port of the Claude skill. Do not edit
`~/src/mytools/dotfiles/claude/skills/staged-consistency/` when changing this
skill.

**Where this sits:** phase 0 runs after `/vtt-spell-pass` and **before** `enhance_summary` (it checks the spec the enhancement renders from); phase 1 runs on its output, before `/remove-recap` and `/scene-extract` (together they supersede `/gmassist-precheck`); phase 2 after `/session-summary-consistency`; phase 3 on the final selected narration. Full order: `~/src/CampaignGenerator/docs/design/SkillPipelineOrder.md`.

## Codex Compatibility

- Ask user questions in chat.
- Keep the user informed as each stage starts, stops, or reaches its review gate.
- Use `apply_patch` for manual edits.
- Do not use Claude Artifact mode. Codex has no equivalent save notification.
- For batch review, use the shared standalone page at
  `~/.codex/skills/_shared/review-page/`; accept its output pasted into chat or
  from a downloaded JSON file. Do not wait for callbacks or infer a save.
- For the single-document check procedure, follow the Codex
  `consistency-check` skill. If it is not already loaded, read
  `~/.codex/skills/consistency-check/SKILL.md`.

The underlying `consistency-check` procedure uses CampaignGenerator's
`--backend codex-cli`, backed by the operator's saved ChatGPT subscription
login. Preserve any setup, login, model, timeout, or empty-result failure from
that command and stop the current stage; do not switch providers or advance on
partial output.

## Orchestration Boundary

This skill owns sequencing: which artifact is checked, in what order, and where
the human gates occur. The `consistency-check` skill owns the check method,
including config resolution, prep selection, context, VTT adjudication, the
false-positive filters and canon-judgment rule behind the severity table, and
the sources-and-rulings manifest. Run that full procedure at every stage.
When the two skills differ on method, `consistency-check` wins; this skill
overrides only the sequencing and stage-level manifest granularity described
below.

CampaignGenerator auto-loads `docs/entity_registry.yaml` as authoritative canon,
including aliases, `distinct`, and `rejected_aliases`. Reuse that automatic
context at every stage; do not pass the raw registry through `--context`.

## When to Use

Use this skill when preparing a session document for players, when narration does
not match the session prep or transcript, or when the user explicitly asks for
`staged consistency`.

For a quick check of one file, use `consistency-check` directly.

Use `gmassist-precheck` when only the gm-assist-to-summary boundary is in scope.
Use `session-doc-run` when the required pipeline artifacts do not exist yet;
return to this skill after that runner creates them.

## Workflow

### 0. Locate the Session and Inventory the Run

If the user passed a session directory, use it. Otherwise:
- Confirm the campaign root by walking upward until `docs/`, `summaries/`, and
  `config/` are present.
- List recent directories under `summaries/`.
- Ask which session directory to use.

Current campaign layout is:

```text
<campaign>/
  config/config.yaml
  docs/
  summaries/<session>/
```

Do not require a root `config.yaml`.

Inventory the stage artifacts before resolving config, selecting prep, or
spending a model call:

```bash
SESSION=<session-dir>
ls "$SESSION"/gm-assist-update.md "$SESSION"/gm-assist.md 2>/dev/null
ls "$SESSION"/session-summary.md "$SESSION"/session_summary.md 2>/dev/null
ls "$SESSION"/scene_extractions{,_new}/0*.md 2>/dev/null | grep -v ".prev\|.reviewed\|.scaffold"
ls "$SESSION"/narration/enhanced_sections.md 2>/dev/null
ls "$SESSION"/narration/*.md 2>/dev/null
ls -t "$SESSION"                                     # input mtimes
cat "$SESSION"/.cg/activity.jsonl 2>/dev/null         # stage, rc, real input/output paths
ls "$SESSION"/consistency_report_stage*.md 2>/dev/null
cat "$SESSION"/consistency_*stage*.sources.yaml 2>/dev/null   # prior rulings
ls "$SESSION"/logs/*_enhance_summary.md 2>/dev/null
```

Exclude `.prev`, `.reviewed`, and `.scaffold` scene files.

**Filenames vary.** Do not call a stage missing from one failed `ls`; read the
directory listing. A GMAssistant export is the Stage 0 source under its own name
(`session_<date>_session_<date>.md`), the summary may be `session_summary.md`,
and scenes live in `scene_extractions/` or `scene_extractions_new/`. Use the
real names everywhere below where this skill writes the usual ones.

**Check input mtimes before anything else.** They show whether stage N was
generated from corrected stage N-1 input or from the pre-review version; if the
extract ran before Stage 1 fixes landed, this run is a redo, and the opening
message says so. `.cg/activity.jsonl` names which file fed which; confirm that
mapping with the user before checking anything.

Also inventory transcripts and `zoom-summary.md`. Prefer the cleanest VTT for
wording and a speaker-labelled transcript for attribution. Compare its distinct
speakers with `docs/party.md`; a missing player often means another player ran
that PC and attribution needs extra scrutiny. How to weigh each transcript and
the zoom summary, attribution, retracted slips, and rules editions are method:
they live in `consistency-check`, not here.

**Read prior rulings before presenting any finding.** For each prior stage, the
`.sources.yaml` (`consistency_stage<N>_*` or the older
`consistency_report_stage<N>_*`) holds `resolution.gm_rulings_this_run`,
`resolution.applied`, and `resolution.open_items`. Search them for each
finding's subject. A finding with a prior ruling is not a fresh question: quote
the ruling on its row or card, say that approving reverses it, and never re-ask
it as new. If the ruling contradicts what the documents now say, present it as an
open conflict with both sides, not as a finding. Example: OOTA Ch 65 re-asked a
damage question the GM had ruled on earlier that day, and the GM reversed a
correct ruling without seeing it. If a `consistency_report_stage*.md` exists,
ask whether to re-check that stage or take it as settled; if settled, its
rulings become the propagation checklist for step 8. Prior manifests are otherwise hypotheses and
history, not proof: re-verify any ruling touched by the current findings.

Tell the user exactly which stages and transcripts were found before continuing.
Do not generate missing artifacts.

A stage that did not run did not pass. Report it as `NOT RUN` in the final
summary and add an `OPEN` carry-forward item to the latest manifest actually
produced by this run; do not fabricate a manifest for an unrun stage. Name Stage
2 explicitly when scene extractions are absent. If only Stage 0 exists, offer
these choices before doing setup work: check Stage 0 alone; check Stage 0 plus a
focused manual VTT sweep; or stop and run `session-doc-run` first.

### 1. Choose Review Mode

Ask whether to review each stage in a batch page or interactively in chat. Ask
every run and do not remember a default. Batch mode keeps the severity table in
chat but moves the rulings to one standalone page per stage. The rest of the
stage order and apply workflow stays unchanged.

### 2. Resolve Config and Choose Session Prep

Resolve config once and reuse it. Pass `<campaign>/config/config.yaml`
explicitly, or follow `consistency-check`'s absolute-path temporary-config
procedure if its relative document paths resolve incorrectly. Locate the
CampaignGenerator script or installed command instead of assuming a home path.

Before running any stage, locate prep candidates and ask the user to choose the
prep set. Delegate the character-count table, HIGH/MEDIUM/LOW subtotals, and
choice totals to the full `consistency-check` procedure. Do not recreate a
second sizing method here. Use the same approved `prep_selection`—tier, exact
files, per-file counts, and prep-only `total_chars`—for every stage.

Search the whole `notes/` tree, including:
- `notes/session_prep/`
- `notes/prep/`
- `notes/sessions/`
- `notes/sessions/handouts/`
- location, arc, NPC, and canon notes

If the user says `none`, proceed but record in the final summary that the run was
prep-less and may miss transcription errors.

For a backfilled session with no dated prep, look for a matching chapter in
`docs/chapters/`. Match by distinctive people, locations, and events, never by
chapter number alone; renumbering can make the directory, recap, campaign state,
and chapter filenames disagree. Treat chapter prose as corroboration, not tape.
Do not edit the chapter to match downstream output; record remaining divergence
as carry-forward.

Use one `--context` flag containing the complete selected prep set plus every
standard context file that is not auto-loaded: `docs/party.md`,
`notes/vtt_transcription_corrections.md`, and `notes/vtt_known_additions.md`.
Reuse the identical resolved list at each stage; the registry remains present
through CampaignGenerator's automatic canonical rendering.

### 2b. Verbatim Sweep

Before the model check on every prose document, run the deterministic sweep for
inline `"…"` quotes, which `sd_verify_quotes` does not check (it reads only
`> "…"` blockquotes):

```bash
python3 ~/.codex/skills/staged-consistency/verify_quotes.py \
  --doc "$SESSION"/<artifact>.md --vtt "$SESSION"/<transcript>.vtt
```

It prints each quoted span that is not contiguous in the transcript. Each hit is
a lead to check in the transcript, not a finding; stutter-smoothing produces
false positives. It shows whether the words were said, not who said them. Do not
replace it with `grep` over the raw VTT, which misses every quote that crosses a
cue boundary.

### 3. Stage 0: gm-assist

If `gm-assist-update.md` exists, ask whether to check that instead of
`gm-assist.md`. The common convention is that `gm-assist.md` is preserved and
`gm-assist-update.md` is the corrected first-pass artifact. A GMAssistant export
under its own filename is checked under that name. The file chosen here is the
**Stage 0 source** for the rest of the run.

Run the `consistency-check` procedure against the chosen file with the selected
prep and standard context.

Fix gm-assist before enhancing, never after. It is the spec `enhance_summary`
renders from, so a Stage 0 fix usually does not recur at Stage 1 (usually: see
the survival check in step 4). Example: on OOTA Ch 48,
Stage 0 found 12 issues, then Stage 1 found only 6 on a summary three times
longer. If the file has already been enhanced from, Stage 0 is not a first pass: say
so in the manifest, or its finding count will read as a clean result.

After the report:
- Present a severity-ranked table.
- Ask whether to apply fixes before moving to stage 1.
- Apply approved edits.
- Grep touched files for residual bad forms.

### 4. Stage 1: session-summary

Run the `consistency-check` procedure against `session-summary.md`. Pass the
Stage 0 source that was actually checked in step 3 (`gm-assist.md`,
`gm-assist-update.md`, or the GMAssistant export under its real filename) as
additional context, never `gm-assist.md` by default. The enhanced summary was
built from that recap plus the VTT, so its differences are the material under
test.

Check that every Stage 0 ruling survived the enhancement before reading the
report. The enhancement also reads the VTT, and where the tape seems to disagree
with a ruling the tape can win. On OOTA ch02 (2026-09-25) the GM ruled at Stage 0
that Thorin flattered Buppido and that Gracklstugh stays a duergar city; the
enhancement credited the flattery to Gyrgum (following diarization labels) and
rewrote Gracklstugh as "a major city of Buppido's people". The check flagged
neither, because they contradict only the Stage 0 manifest, which it never sees.
For every entry in the Stage 0 manifest's `resolution.applied` and
`gm_rulings_this_run`, grep `session-summary.md` for the subject and confirm the
ruled reading. Present a reversal as a conflict with a prior ruling (quote the
ruling; approving the old reading means editing the Stage 0 source too), never as
a fresh finding.

Run deterministic quote verification first, using the exact VTT that generated
the artifact:

```bash
python3 -m session_doc.sd_verify_quotes \
  --vtt <generation-vtt> \
  --summary "$SESSION"/session-summary.md \
  --out "$SESSION"/quote_report_stage1.md \
  --report-only
```

Exit `1` means the verifier ran and found unverified quotes or refusals; review
them. Exit `2` means it could not run; mark quote verification degraded and do
not describe the stage as fully cleared. `--report-only` is required until the
user rules, because the default mode annotates checked artifacts.

Read a 100% result narrowly. The verifier checks blockquotes, not inline quoted
prose, and establishes that words occur in the transcript, not who said them.
Review `near` as well as `unverified`, because `near` means the quote was edited.
"No quotes found" is zero coverage, not 100%: when the enhancement quotes
inline (OOTA ch02: 40 curly-quoted spans, no blockquotes), the inline sweep
(`verify_quotes.py`) is the only quote check this stage has.
Labelled blockquotes (`> **Zalthir:** “…”`, OOTA ch03: all 26 lines) were
skipped the same way until CampaignGenerator `d4e8047`; on an older install, a
nonzero `grep -c '^> '` beside "No quotes found" is that gap.

Before adjudicating any model finding, use `grep -nF` with a distinctive excerpt
to confirm its quoted target text occurs in `session-summary.md`. A miss usually
means the checker quoted the near-paraphrase Stage 0 source while naming the
summary as the location. Do not reintroduce an error that the enhancement pass
already removed.

Pay special attention to:
- contradictions between summary prose and scene bullets
- pronoun drift on player characters
- NPC affiliation inventions
- combat attribution errors
- details added by the enhancement pass that do not appear in the source recap
- invented precise dice values, duplicated or lost events, and truncated quotes
- DM asides relocated onto the wrong mechanical result

Apply only approved fixes before moving to stage 2.

### 5. Stage 2: Scene Extractions

`<scene-dir>` below is `scene_extractions_new/` or `scene_extractions/`,
whichever this session has (step 0). The call shape depends on the review mode
chosen in step 1:

- **Interactive review:** run the `consistency-check` procedure for each
  `<scene-dir>/0*.md` file in scene order. After each scene, ask whether to
  continue or revisit before advancing.
- **Batch review:** enumerate every selected `<scene-dir>/0*.md` path
  explicitly in scene order and pass the complete ordered path list to one
  CampaignGenerator `check_consistency` invocation. This is a grouped document
  audit: common context is transmitted once, and the CLI requires an explicit
  result section for every scene plus a cross-scene section. Do not emulate
  grouped mode by running one command per scene and concatenating the reports
  locally.

In both modes, exclude `.prev`, `.reviewed`, and `.scaffold` files. Enumerate
the scenes explicitly; never let a shell glob decide the list, and never
represent an empty scene selection as "all".

Before either call shape, run the same deterministic verifier against the scene
directory, with the exact generation VTT and `--report-only`:

```bash
python3 -m session_doc.sd_verify_quotes \
  --vtt <generation-vtt> \
  --scene-extractions "$SESSION"/<scene-dir> \
  --out "$SESSION"/quote_report_stage2.md \
  --report-only
```

Exit codes are as in Stage 1: `1` means review the unverified quotes or
refusals, `2` means quote verification is degraded. Read both the quote verdicts
and `## Refused`. R1 means the summary and verbatim copies disagree and the
transcript settles neither; R3 means a purportedly verbatim span contains an
editorial insertion. Quote verification complements, but never replaces, manual
VTT adjudication of wording and speaker attribution.

For grouped batch review, follow the ordinary `consistency-check` context and
backend rules, but invoke the CLI once with every scene path before the flags:

```bash
python3 <campaign-generator-repo>/session_doc/check_consistency.py \
  "$SESSION"/<scene-dir>/<scene-01>.md "$SESSION"/<scene-dir>/<scene-02>.md ... \
  --config <campaign>/config/config.yaml \
  --backend codex-cli \
  --context <file1> <file2> ... \
  --output <session-dir>/consistency_report_stage2_scenes.md
```

Grouped mode is selected by passing more than one document; it is not a flag.
The `...` is a placeholder for the remaining literal paths, not a glob. The
input order keys the output sections and the manifest. The CLI rejects duplicate
paths, so de-duplicate the list first.

Size the output ceiling before a large batch. `check_consistency.py` reads
`CG_CONSISTENCY_MAX_TOKENS` (default `32000`); set it for the run. However,
`codex exec` has no output-token flag, so `--backend codex-cli` ignores it
(CampaignGenerator #414). On this backend, output from a large batch that gets
cut off fails the grouped protocol check and stops the run. Say that the ceiling
was not enforced; do not assume it applied.

The grouped command is fail-closed. If it reports any setup, login, model,
timeout, empty-result, context, grouped-protocol, or validation failure:

- stop Stage 2;
- do not build or update the Stage 2 review page or sources manifest;
- do not quietly retry per scene, split the batch, or switch backends or
  providers. A changed call shape is a different run: do it only after telling
  the user, and record it as that;
- preserve any older report as historical output, not evidence that this run
  succeeded. A failed run leaves the previous report untouched, so check its
  timestamp.

The grouped engine requires every scene-level finding to include a single-line
**Target text** excerpt that occurs verbatim in the scene assigned to that
section, and it rejects the run when one does not. Never hand-repair a rejected
run: do not move a finding to the section where it seems to belong, trim an
excerpt until it matches, or edit the report until it parses. Re-run instead.
Cross-scene misattribution is the failure grouping introduces, and this check
is what catches it.

The engine also derives per-scene review anchors from exact wrong-form matches
in the supplied correction glossaries. These anchors are attention aids, not
rulings: apply glossary exceptions and `DO NOT CORRECT` rulings, and never turn
a match into an automatic edit.

Read and count the grouped report body yourself. Its shape is
`# Grouped Consistency Report`, then one `## D01 — <path>` section per scene in
the order passed, then `## Cross-document findings`; a clean scene is the
literal word `CLEAN`. Count `**Location**` within each `## D` section and
reconcile the per-scene totals with the command summary. Do not use a
single-document heading count for grouped output. Review the cross-document
section as new findings, not a recap. Peer scenes are not evidence for each
other: two scenes agreeing on a name does not make it right, so never pick a
winner by frequency.

After a successful grouped run, write the Stage 2 sources manifest with the
complete ordered `documents_checked` list plus the CLI telemetry (`model_calls`,
`shared_context_chars`, `target_chars`, and `repeated_context_chars_avoided`).
Adjudicate the grouped report against transcript and campaign evidence before
building review cards; the model report remains advisory.

This is the load-bearing stage because scene extractions contain quote blocks
that narration may reuse literally. A fix made only in `session-summary.md` can
be undone later if the scene extraction still carries the bad quote or wrong
attribution.

When correcting quote-level transcription drift:
- Preserve speaker attribution and table tone.
- Add a brief editorial note when the quote differs from raw ASR but matches
  prep or transcript evidence.
- Do not strip table jokes or table vocabulary that the group actually uses.

### 6. Stage 3: Narration

If final narration exists, check it last.

Narration findings usually indicate upstream fixes or a narration rerun rather
than direct prose edits. Direct edits are acceptable only when the user asks and
the fix is narrow.

### 7. Report Format at Each Stage

Always present findings as a severity-ranked table before asking about fixes.

Severity rubric:
- `Critical`: contradicts established canon or would confuse players if shipped.
- `Moderate`: correct event, wrong framing, wrong attribution, or voice conflict.
- `Minor`: proper noun, pronoun, one-word transcription, local inconsistency.
- `Trivial`: style, defensible flavor, or already-deferred table vocabulary.

Severity orders review; it does not authorize a fix. Mark canon judgments as
`GM ruling needed`, even when Critical, and never auto-apply them. Apply the
`consistency-check` false-positive filters before placing a finding in the
table.

Do not trust a `No issues found` command banner. Read the saved report and count
findings from its body; grouped Stage 2 uses its per-document sections rather
than the single-document heading convention. Continue automatically only when
the body is genuinely clean. If a stage has no issues, say so and continue.

### 8. Fix Propagation

After all approved fixes, sweep for residual bad patterns across every stage
artifact:

```bash
grep -nF "<whole bad clause>" "$SESSION"/gm-assist.md "$SESSION"/gm-assist-update.md \
  "$SESSION"/<stage-0 source, if named otherwise> \
  "$SESSION"/session-summary.md "$SESSION"/narration/enhanced_sections.md \
  "$SESSION"/scene_extractions{,_new}/0*.md 2>/dev/null | grep -v ".prev\|.reviewed\|.scaffold"
```

Use `grep -F` with a whole distinctive clause, never a short token. For example,
`Mechanis` also matches `Mechanist`, so it reports a regression that never
happened. If a bad pattern remains in an unchecked or untouched file, surface it
and ask whether to apply the corresponding fix.

**Upward propagation matters most.** The Stage 0 source is the pipeline's input:
`enhance_summary` reads it, and a ruling applied only at Stage 1 is re-injected by
the next run. When the sweep finds residue in the Stage 0 source, say that a
rerun would undo the work, then ask the user to choose: edit it in place, write a
`-update.md` alongside it, or accept the regression. If a prior run already
edited that file, it is no longer a preserved original, and editing in place is
the honest choice.

A flag written into a regenerated file does not survive. Scene extractions are
rebuilt, so a to-do or "needs a GM call" marker added there is lost on the next
run. When a ruling creates future work, ask before filing it, then write the
durable copy to `notes/issues/YYYYMMDD_slug.md` and reference it from the inline
flag.

Never edit `logs/*_enhance_summary.md`. It is the run log, and residue there is
expected; name it as out of scope.

Also survey grounding documents such as `world_state.md` and `party.md` before
deciding the direction of propagation. They may already be correct while the
generated artifact is wrong. Never bulk-replace a name, title, color, or other
ambiguous token across the campaign; enumerate and read each hit first. Put any
known but unapplied sibling or grounding-document correction in `carry_forward`.

### 9. Stage Manifests

The `consistency-check` sources-and-rulings manifest is required at every stage.
Staging changes its granularity:

- Write one manifest per stage:
  `consistency_stage0_gmassist.sources.yaml`,
  `consistency_stage1_summary.sources.yaml`,
  `consistency_stage2_scenes.sources.yaml`, and
  `consistency_stage3_narration.sources.yaml`.
- Copy the approved `prep_selection` block into every stage manifest unchanged.
  Stage-specific inputs such as the Stage 0 source recap are ordinary context
  and do not change the prep-only total.
- Stage 2 uses one manifest for the stage. Record a `scenes` list with per-scene
  counts and rulings. For grouped mode also record `grouped: true`, the ordered
  `documents_checked`, CLI telemetry, and a separate `cross_scene` list.
- Record the transcript used for quote verification and the transcript manually
  consulted for VTT adjudication. A manually read transcript is provenance, not
  a `--context` input.
- Preserve `document_class`, `speaker_map`, `vtt_adjudicated`, and a status on
  every `carry_forward` item. Carry unresolved items into later stages of the
  same run and close them there when evidence settles them.
- Validate every manifest by parsing it as YAML.

### 10. Final Summary

End with:
- stages run and issue counts taken from report bodies
- stages `NOT RUN`, with the missing artifacts stated plainly
- fixes applied per stage
- findings rejected, deferred, or unresolved
- what deterministic quote verification and manual VTT review caught
- whether prep was available
- whether `zoom-summary.md` was available, with its scorecard: which findings it
  caught and which it got wrong
- propagation sweep result and merged carry-forward items
- recommended next action

If Stage 2 did not run, say that the per-scene verbatim layer was not exercised
and that the step 2b sweep covered it only in part. Offer to write
`consistency_report_stage<N>_<artifact>.md` beside each stage's `.sources.yaml`,
matching any prior-stage reports in the session; step 0 of the next run reads
them. Record `resolution.open_items` even when empty, and put anything a stage
could not settle there rather than in prose.

Likely next actions:
- rerun `session_doc.py` from corrected upstream artifacts
- rerun narration from corrected scene extractions
- share the session doc with players
- revisit a stage with unresolved Critical or Moderate findings

## Batch Review Page

This replaces each stage's interactive adjudication only. Read the full shared
contract at `~/.codex/skills/_shared/review-page/CONTRACT.md` before building a
queue.

Use one page per stage. Do not combine all stages into one end-of-run review:
the user must rule on a stage, approved fixes must be applied, and only then may
the next stage run against the corrected input.

For every stage:

1. Run the consistency check and present the severity-ranked table in chat.
   Stage 2 is the exception to the single-document call shape: use the grouped
   invocation defined in step 5, then consolidate its per-scene and cross-scene
   findings into this stage's one table.
2. Apply only unambiguous mechanical corrections that need no ruling, and name
   their count and touched files in the review `footer`.
3. Create `<session-dir>/staged_review/review_items_stage<N>.json` using the
   shared input schema, with its own `reviewId` (e.g. `<chapter>:stage-<N>`).
   Every Critical, Moderate, or Minor judgement call gets one item; reuse the
   table number as a stable id such as `s1-03`. Per the contract's multi-page
   rule, each stage has its own items, page and decisions files, so a later
   stage never overwrites the question an earlier one asked.
4. Render the page:

   ```bash
   REVIEW_PAGE="${CODEX_HOME:-$HOME/.codex}/skills/_shared/review-page"
   python "$REVIEW_PAGE/build_review.py" \
     --in  <session-dir>/staged_review/review_items_stage<N>.json \
     --out <session-dir>/staged_review/review_stage<N>.html
   ```

5. Give the user the HTML path and stop. Resume only when they paste the
   exported JSON or point to the downloaded file.
6. Save the export as `<session-dir>/staged_review/decisions_stage<N>.json` and
   validate it: `python "$REVIEW_PAGE/read_decisions.py" --in
   <session-dir>/staged_review/decisions_stage<N>.json --items
   <session-dir>/staged_review/review_items_stage<N>.json`. It exits non-zero on
   an unsaved, stale or foreign export. Then apply the approved fixes, group all
   discussed items with their notes into one chat pass, and carry unmarked ids
   forward as unresolved. Then advance to the next stage.

Each card must state the actual consequences of both choices and cite the
affected files. Where the audit may be wrong because its grounding source is
stale, include evidence for both sides.

Verdict mapping:

| verdict | action |
|---|---|
| **approve** | Apply the card's stated fix, then run the propagation sweep across every touched artifact |
| **reject** | Leave files unchanged and log the finding as deferred |
| **discuss** + note | Follow the note; a canon ruling may require correcting a source and regenerating rather than editing generated output |
| **discuss**, no note | Return all such findings to chat as one grouped pass |
| **unmarked** | Keep unresolved; do not silently treat it as rejected or advance past unresolved Critical findings without saying so |

Never infer approval from an HTML or queue file's existence, mtime, or browser
storage. Only pasted or saved decision JSON authorizes edits.

An approval on the page authorizes the stated file edit, not an external action
such as posting a GitHub comment; obtain separate confirmation immediately
before that visible action. An accepted fix still receives the full propagation
sweep, including sibling artifacts outside the page's review scope. Review scope
and propagation scope are different: do not silently broaden the former or
truncate the latter.
