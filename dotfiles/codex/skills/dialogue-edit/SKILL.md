---
name: dialogue-edit
description: Review and improve dialogue in existing campaign narration against its reviewed extraction and declared voices, with per-scene GM rulings and exact application to a separate revision. Use for /dialogue-edit, $dialogue-edit, or requests to make narrated player speech more readable without losing cadence or inner voice. For upstream extraction smoothing use voice-smooth.
metadata:
  short-description: GM-reviewed dialogue editing after narration
---

# Dialogue Edit

Help the players recognize their own speech in readable narration. Use the
surrounding scene to understand a line, then propose the smallest supported
change. The reading pass does the editorial work; the GM decides; the helper
applies exactly what was approved.

This is a **Codex skill** maintained beside no-mech and staged-consistency.
It does not modify the Claude skill collection.

## Where this sits — keep narrating in the UI

```text
voice-smooth → no-mech → existing UI narration → GM review
                                                   ↓
                                           scrub, if needed
                                                   ↓
                                             dialogue-edit
                                      read → propose → GM rules
                                                   ↓
                                        separate edited revision
                                                   ↓
                                       voice-critic → final review
                                                   ↓
                                  explicit promotion / assembly
```

Continue generating narration through the existing UI. Invoke this skill on
the resulting session or scene. It does not change the UI, its configuration,
its generation prompt, or its model.

**Which new prompt is used?** The skill uses the contextual editing guidance
from experimental approach B, strengthened by its review findings. The
accepted narration-v1 prompt is the separate upstream generation brief now
shared by CG's single-scene and bundled UI/CLI narration. This skill does
**not** install it, select it, or regenerate drafts. On older CG installations,
check `config/agents/session_doc/narrate/writing_brief.md` and the generation
log rather than inferring the active prompt from historical v1 drafts.

Ordinary use is this conversation reading and proposing edits. Do not launch
another model runner, re-narrate, or generate a whole scene afresh merely
because the original experiment did so.

**After no-mech, before the final voice-critic pass.** no-mech edits the
smoothed extraction before narration; this skill needs the finished narrative
context. Complete any intended scrub pass first and explicitly select its
reviewed result as the draft. Regenerating narration or scrubbed output later
can invalidate these edits; do not silently replay them onto the new text.

Hand voice-critic the exact approved revision plus the original scene identity,
run-record location, and reference provenance from the manifest. A directory
scan that selects the old raw/scrubbed scene would critique the wrong version.
The critic's prose checks complement this skill's dialogue review; they do not
certify the edited speech as verbatim. An earlier critique is useful diagnostic
input, but repeat affected checks after later approved edits. Run the final
consistency gate against the actual selected revision before promotion.

## Boundaries

- Read but never change VTT, any extraction layer (including smoothed),
  voice/example files, campaign policy, or the original narration.
- Put review artifacts and new revisions under
  `<session>/dialogue_edit/<scene-run>/`, outside the narration files
  selected for assembly. The helper enforces the output location and refuses
  existing runs, stale inputs, and ambiguous replacements.
- Every proposed wording change needs a GM ruling. No "obvious cleanup" is
  applied before review. Ambiguous cadence, filler, or attribution is a
  separate question, never smuggled into a larger approved edit.
- A changed proposal is a new proposal. Do not reinterpret approval as
  permission to rewrite the replacement or fix nearby text.
- Missing events, transcription errors, identity disputes, broad prose edits,
  or mechanics-removal work belong to their existing workflows. Record the
  finding and source evidence; do not silently perform those jobs here.
- No automatic assembly, source repair, publication, or additional backend
  call. A requested remote run needs authorization for that scope/backend;
  reuse existing authorization rather than asking again.

## 1. Inventory and read the campaign's rulings

Accept a session directory or exact scene path. Use explicit user selection;
if several sessions/scenes remain plausible, ask. Do not turn an empty
selection into the entire session. Report the chosen files and missing inputs.

Resolve each scene's **exact reviewed extraction**, narrator, and voices from
its plan/provenance and declared configuration. Read:

- the complete existing narration and its corresponding complete extraction,
  including descriptive account, dialogue, and disambiguating notes;
- `config/party.yaml` and `config/players.yaml` for declared
  character identities, voices, examples, and supporting speakers;
- the declared voice/example files actually relevant to the scene;
- the applicable genre/register file (including a declared
  `paths.genre_file`) and `notes/scrub_register_policy.md` if present;
- any earlier dialogue-edit manifests and applicable scoped GM rulings.

Do not guess a source from filename similarity, pick the freshest extraction,
or guess a voice from first-name prefixes. A declared missing voice is a
blocker for that scene. Missing optional policy is reported as absent, not
invented. An NPC/GM label need not have a PC voice file. A GM may also voice a
PC: read stage directions and identity declarations.

Use existing review records and clear instructions without re-asking settled
questions. If the narration/source mapping or its review status is unresolved,
get that scene's input ruling before editing it. Missing narration means this
skill is **NOT RUN**, not an instruction to call the narrator.

Ask whether the GM wants **chat** or a **standalone review page** for this run,
unless they already chose. Both modes retain one scene's checkpoint at a time.

## 2. Read the full scene; propose exact changes

Read [editorial-guide.md](references/editorial-guide.md) before your first
scene. It contains the tested editing latitude and concrete failure cases
that should change your decisions.

Read every selected scene in full. A scanner can mark possible repetition;
zero hits cannot establish that a scene needs no work.

For each proposal, present:

- exact original and replacement text, with the surrounding exchange;
- speaker, target file/location, and the particular readability gain;
- exact source/voice evidence and what remains uncertain;
- any required adjacent attribution/punctuation change, visibly identified.

Preserve the narrator's inner and descriptive prose. Do not normalize fluent
or ESL diction, improve a joke, add a response, silently change a question into
an assertion, or merge separate speakers' agreement. If you cannot support a
completion from the source, leave it and ask.

Save proposals before asking for rulings. Follow
[review-and-apply.md](references/review-and-apply.md) to freeze exact spans,
evidence and content identities using `scripts/review_edits.py prepare`.
The helper writes the original copy, full candidate, diff, readable review,
shared-page queue, and frozen review record. A candidate includes all proposals
and remains **unapproved**. Unresolved/out-of-scope proposals are marked and
cannot be applied even if mistakenly approved.

If nothing needs changing, record **read: complete; proposals: none** and
continue in the selected scope. No manufactured approval question is needed.

## 3. The GM rules — one scene at a time

In chat, show the exact proposals with evidence and wait for explicit rulings.
Save those actual rulings in a decision file bound to the frozen review ID.
Never manufacture an approval to satisfy the helper.

For page mode, read the sibling
[shared review contract](../_shared/review-page/CONTRACT.md), then build the
page from the prepared queue using the existing shared builder. Escape all
transcript text (the helper does this). Give the GM the page path and wait for
pasted output or the downloaded decision file; there is no save callback.

- **approve**: apply only the stated, supported replacement.
- **reject**: retain original wording and record rejection.
- **discuss**: return the proposal and note to chat.
- **unmarked**: unresolved, never inferred approval or rejection.

There is no session-wide catch-all approval. Discuss uncertain radio-play
phrasing or another distinct editorial decision separately. Keep unresolved
items pending until the GM rules or explicitly defers them. An explicit deferral
allows moving on while preserving original text and carrying the item forward.

## 4. Apply, then read the result and its joins

Run the helper's application **dry-run first**, inspect the complete approved
diff, then use `--write` with the same frozen review and actual decisions.
An approval already given for these exact edits covers both steps.

Application uses recorded replacement text, not another model rewrite. It
checks the original, source, references, proposal identity, and exact spans;
it rejects conflicting or stale application before changing the scene.
It writes a fresh derived revision, never overwrites the original.

Read the result, then compare the previous scene's closing lines and the next
scene's opening lines. Look for orphaned replies, lost setups, repeated seam
sentences, or a narrator's boundary echo now presented as spoken dialogue.

A newly noticed defect is a **new proposal**. Do not repair it under an earlier
ruling, including in neighboring scenes. Partial application is explicitly
labeled; it does not make unresolved findings disappear.

## 5. Record the run and stop at its boundary

Maintain `<session>/dialogue_edit.sources.yaml` as the session index,
preserving prior runs. Record:

- ordered selected scenes and exact draft/source/reference paths;
- frozen review ID and artifact paths (hashes live in each review record);
- per-scene reading, review, and application status, including not-run reasons;
- actual GM decisions, revision paths, remaining issues, and seam findings;
- scoped campaign rulings and open/resolved carry-forward items;
- what runtime/model details are actually observable.

The helper writes an application record with the returned decisions and result
hash. Reference it from the session index. If all proposals were rejected or
deferred, retain the decision file and record that no revision was written.
Validate the index by parsing it as YAML.

Record unknown execution details as unknown. The active Codex conversation
does not expose a standalone submitted prompt pair; do not fabricate one.
If a separate runner is explicitly requested, preserve its actual inputs,
reported model/effort, and failure status without silent provider changes.

Session rulings belong in this manifest. Promoting a ruling into shared campaign
policy is an ancillary edit: obtain approval for the destination and exact
wording unless already authorized. Reuse standing rulings within their scope;
do not turn one scene's choice into a universal rule.

Finish with scenes reviewed/not run, changes applied, rejected/deferred/open
items, revision paths, and seam results. State that the original narration is
intact and the new revision has not been assembled or published. Let the GM
choose any downstream promotion as a separate action.
