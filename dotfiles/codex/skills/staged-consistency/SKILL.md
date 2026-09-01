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
- Use `update_plan` to show stage progress.
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

## When to Use

Use this skill when preparing a session document for players, when narration does
not match the session prep or transcript, or when the user explicitly asks for
`staged consistency`.

For a quick check of one file, use `consistency-check` directly.

## Workflow

### 0. Choose Review Mode

Before locating files, ask whether to review each stage in a batch page or
interactively in chat. Ask every run and do not remember a default. Batch mode
keeps the severity table in chat but moves the rulings to one standalone page
per stage. The rest of the stage order and apply workflow stays unchanged.

### 1. Locate the Session

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

### 2. Choose Session Prep

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

### 3. Inventory Stage Artifacts

Check which files exist:

```bash
SESSION=<session-dir>
ls "$SESSION"/gm-assist-update.md 2>/dev/null
ls "$SESSION"/gm-assist.md 2>/dev/null
ls "$SESSION"/session-summary.md 2>/dev/null
ls "$SESSION"/scene_extractions_new/0*.md 2>/dev/null
ls "$SESSION"/narration/enhanced_sections.md 2>/dev/null
ls "$SESSION"/narration/*.md 2>/dev/null
```

Exclude `.prev` and `.scaffold` files from scene extraction checks.

Tell the user which stages were found and what will be checked. Do not generate
missing artifacts; this skill only reviews existing pipeline outputs.

### 4. Stage 0: gm-assist

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

### 5. Stage 1: session-summary

Run the `consistency-check` procedure against `session-summary.md`.

Pay special attention to:
- contradictions between summary prose and scene bullets
- pronoun drift on player characters
- NPC affiliation inventions
- combat attribution errors
- details added by the enhancement pass that do not appear in the source recap

Apply only approved fixes before moving to stage 2.

### 6. Stage 2: Scene Extractions

The call shape depends on the review mode chosen in step 0:

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

In both modes, exclude `.prev` and `.scaffold` files. Never represent an empty
scene selection as "all".

For grouped batch review, follow the ordinary `consistency-check` context and
backend rules, but invoke the CLI once with every scene path before the flags:

```bash
python3 /home/kroussos/src/CampaignGenerator/session_doc/check_consistency.py \
  <scene-01.md> <scene-02.md> ... \
  --config <campaign>/config/config.yaml \
  --backend codex-cli \
  --context <file1> <file2> ... \
  --output <session-dir>/consistency_report_stage2_scenes.md
```

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

This is the load-bearing stage because scene extractions contain quote blocks
that narration may reuse literally. A fix made only in `session-summary.md` can
be undone later if the scene extraction still carries the bad quote or wrong
attribution.

When correcting quote-level transcription drift:
- Preserve speaker attribution and table tone.
- Add a brief editorial note when the quote differs from raw ASR but matches
  prep or transcript evidence.
- Do not strip table jokes or table vocabulary that the group actually uses.

### 7. Stage 3: Narration

If final narration exists, check it last.

Narration findings usually indicate upstream fixes or a narration rerun rather
than direct prose edits. Direct edits are acceptable only when the user asks and
the fix is narrow.

### 8. Report Format at Each Stage

Always present findings as a severity-ranked table before asking about fixes.

Severity rubric:
- `Critical`: contradicts established canon or would confuse players if shipped.
- `Moderate`: correct event, wrong framing, wrong attribution, or voice conflict.
- `Minor`: proper noun, pronoun, one-word transcription, local inconsistency.
- `Trivial`: style, defensible flavor, or already-deferred table vocabulary.

If a stage has no issues, say so and continue.

### 9. Fix Propagation

After all approved fixes, sweep for residual bad patterns across every stage
artifact:

```bash
grep -n "<bad pattern>" "$SESSION"/gm-assist.md "$SESSION"/gm-assist-update.md \
  "$SESSION"/session-summary.md "$SESSION"/narration/enhanced_sections.md \
  "$SESSION"/scene_extractions_new/0*.md 2>/dev/null
```

Ignore `.prev` and `.scaffold` matches. If a bad pattern remains in an unchecked
or untouched file, surface it and ask whether to apply the corresponding fix.

### 10. Final Summary

End with:
- stages run and issue counts
- fixes applied per stage
- findings rejected, deferred, or unresolved
- whether prep was available
- propagation sweep result
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
   invocation defined in step 6, then consolidate its per-scene and cross-scene
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
