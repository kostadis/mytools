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
including config resolution, prep selection, context, VTT adjudication, triage,
and the sources-and-rulings manifest. Run that full procedure at every stage.
When the two skills differ on method, `consistency-check` wins; this skill
overrides only the sequencing and stage-level manifest granularity described
below.

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
ls "$SESSION"/gm-assist-update.md 2>/dev/null
ls "$SESSION"/gm-assist.md 2>/dev/null
ls "$SESSION"/session-summary.md 2>/dev/null
ls "$SESSION"/scene_extractions_new/0*.md 2>/dev/null
ls "$SESSION"/narration/enhanced_sections.md 2>/dev/null
ls "$SESSION"/narration/*.md 2>/dev/null
```

Exclude `.prev`, `.reviewed`, and `.scaffold` scene files. Also inventory
transcripts and prior `*.sources.yaml` manifests. Prefer the cleanest VTT for
wording and a speaker-labelled transcript for attribution. Compare its distinct
speakers with `docs/party.md`; a missing player often means another player ran
that PC and attribution needs extra scrutiny. Prior manifests are hypotheses and
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
prep set. Use the same prep set for every stage.

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
standard context file that exists: `docs/party.md`,
`docs/entity_registry.yaml`, `notes/vtt_transcription_corrections.md`, and
`notes/vtt_known_additions.md`. Reuse the identical resolved list at each stage.

### 3. Stage 0: gm-assist

If `gm-assist-update.md` exists, ask whether to check that instead of
`gm-assist.md`. The common convention is that `gm-assist.md` is preserved and
`gm-assist-update.md` is the corrected first-pass artifact.

Run the `consistency-check` procedure against the chosen file with the selected
prep and standard context.

After the report:
- Present a severity-ranked table.
- Ask whether to apply fixes before moving to stage 1.
- Apply approved edits.
- Grep touched files for residual bad forms.

### 4. Stage 1: session-summary

Run the `consistency-check` procedure against `session-summary.md`. Pass the
selected Stage 0 source (`gm-assist-update.md` or `gm-assist.md`) as additional
context: the enhanced summary was built from that recap plus the VTT, so its
differences are the material under test.

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

Before adjudicating any model finding, use `grep -nF` with a distinctive excerpt
to confirm its quoted target text occurs in `session-summary.md`. A miss usually
means the checker quoted the near-paraphrase source recap while naming the
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

The call shape depends on the review mode chosen in step 1:

- **Interactive review:** run the `consistency-check` procedure for each
  `scene_extractions_new/0*.md` file in scene order. After each scene, ask
  whether to continue or revisit before advancing.
- **Batch review:** enumerate every selected `scene_extractions_new/0*.md`
  path explicitly in scene order and pass the complete ordered path list to
  one CampaignGenerator `check_consistency` invocation. This is a grouped
  document audit: common context is transmitted once, and the CLI requires an
  explicit result section for every scene plus a cross-scene section. Do not
  emulate grouped mode by running one command per scene and concatenating the
  reports locally.

In both modes, exclude `.prev`, `.reviewed`, and `.scaffold` files. Never
represent an empty scene selection as "all".

Before either call shape, run the same deterministic verifier against the scene
directory, with the exact generation VTT and `--report-only`:

```bash
python3 -m session_doc.sd_verify_quotes \
  --vtt <generation-vtt> \
  --scene-extractions "$SESSION"/scene_extractions_new \
  --out "$SESSION"/quote_report_stage2.md \
  --report-only
```

Read both the quote verdicts and `## Refused`. R1 means the summary and verbatim
copies disagree and the transcript settles neither; R3 means a purportedly
verbatim span contains an editorial insertion. Quote verification complements,
but never replaces, manual VTT adjudication of wording and speaker attribution.

For grouped batch review, follow the ordinary `consistency-check` context and
backend rules, but invoke the CLI once with every scene path before the flags:

```bash
python3 <campaign-generator-repo>/session_doc/check_consistency.py \
  <scene-01.md> <scene-02.md> ... \
  --config <campaign>/config/config.yaml \
  --backend codex-cli \
  --context <file1> <file2> ... \
  --output <session-dir>/consistency_report_stage2_scenes.md
```

Grouped mode is selected by passing more than one document; it is not a flag.
Spell out the de-duplicated scene paths in order rather than relying on a shell
glob. The input order keys the output sections and the manifest.

The grouped command is fail-closed. If it reports a setup, login, model,
timeout, empty-result, context, or grouped-protocol failure:

- stop Stage 2;
- do not build or update the Stage 2 review page or sources manifest;
- do not silently retry per scene, split the selection, or switch providers;
- preserve any older report as historical output, not evidence that this run
  succeeded.

The grouped engine requires every scene-level finding to include exact target
text that occurs in the scene assigned to that section. It also derives compact
per-scene review anchors from exact wrong-form matches in supplied correction
glossaries. Those anchors prevent long-batch recall loss but remain advisory:
apply glossary exceptions and `DO NOT CORRECT` rulings, and never turn a match
into an automatic edit. A missing or cross-attributed excerpt is a protocol
failure; do not reconstruct or relocate the model's finding by hand to make the
run appear valid.

After a successful grouped run, write the Stage 2 sources manifest with the
complete ordered `documents_checked` list plus the CLI telemetry (`model_calls`,
`shared_context_chars`, `target_chars`, and `repeated_context_chars_avoided`).
Adjudicate the grouped report against transcript and campaign evidence before
building review cards; the model report remains advisory.

Read the grouped report body yourself. Reconcile per-scene finding counts from
each `## DNN` section with the command summary, and review the cross-document
section as new findings rather than a recap. Do not use a single-document
heading count for grouped output.

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
grep -n "<bad pattern>" "$SESSION"/gm-assist.md "$SESSION"/gm-assist-update.md \
  "$SESSION"/session-summary.md "$SESSION"/narration/enhanced_sections.md \
  "$SESSION"/scene_extractions_new/0*.md 2>/dev/null
```

Ignore `.prev` and `.scaffold` matches. If a bad pattern remains in an unchecked
or untouched file, surface it and ask whether to apply the corresponding fix.

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
- propagation sweep result and merged carry-forward items
- recommended next action

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
3. Create `<session-dir>/staged_consistency_stage_<N>_review.json` using the
   shared input schema. Every Critical, Moderate, or Minor judgement call gets
   one item; reuse the table number as a stable id such as `s1-03`.
4. Render the page:

   ```bash
   REVIEW_PAGE="${CODEX_HOME:-$HOME/.codex}/skills/_shared/review-page"
   python "$REVIEW_PAGE/build_review.py" \
     --in <session-dir>/staged_consistency_stage_<N>_review.json \
     --out <session-dir>/staged_consistency_stage_<N>_review.html
   ```

5. Give the user the HTML path and stop. Resume only when they paste the
   exported JSON or point to the downloaded file.
6. Validate every returned id and verdict, apply the approved fixes, group all
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
