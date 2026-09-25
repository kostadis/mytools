---
name: dialogue-edit
description: Review and improve dialogue in EXISTING campaign narration against its reviewed extraction and declared voices, so players recognize their own speech — with a per-scene GM ruling on every proposed wording change and exact, deterministic application to a separate revision. Reads the whole scene, proposes the smallest supported change, never applies "obvious cleanup" unreviewed. Runs after narration and any /scrub pass, before the final /voice-critic gate. The original narration, every extraction layer and the VTT are read-only. For upstream smoothing of the extraction use /voice-smooth. Invoke as /dialogue-edit [session-dir-or-scene].
tools: Read, Bash, Glob, Grep, Write, Edit, Artifact, WebFetch, AskUserQuestion
---

# Dialogue Edit

> **Ported from the Codex copy, which is canonical** (`dotfiles/codex/skills/dialogue-edit`).
> Change it there first, then port. `scripts/` and `references/editorial-guide.md`
> are kept byte-identical.

Help the players recognize their own speech in readable narration. Use the
surrounding scene to understand a line, then propose the smallest supported
change. The reading pass does the editorial work; the GM decides; the helper
applies exactly what was approved.

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

Continue generating narration through the existing UI. Invoke this skill on the
resulting session or scene. It does not change the UI, its configuration, its
generation prompt, or its model.

**Which prompt is in play?** This skill uses contextual editing guidance from
experimental approach B, strengthened by its review findings. The accepted
narration-v1 prompt is the separate upstream generation brief now shared by CG's
single-scene and bundled UI/CLI narration. This skill does **not** install it,
select it, or regenerate drafts. On older CG installations, check
`config/agents/session_doc/narrate/writing_brief.md` and the generation log
rather than inferring the active prompt from historical v1 drafts.

Ordinary use is this conversation reading and proposing edits. Do not launch
another model runner, re-narrate, or regenerate a whole scene merely because the
original experiment did so.

**After no-mech, before the final voice-critic pass.** `no-mech` edits the
smoothed extraction *before* narration; this skill needs the finished narrative
context. Complete any intended scrub pass first and explicitly select its
reviewed result as the draft. Regenerating narration or scrubbed output later
invalidates these edits — do not silently replay them onto the new text.

Hand `voice-critic` the exact approved revision plus the original scene
identity, run-record location, and reference provenance from the manifest. A
directory scan that picks the old raw/scrubbed scene would critique the wrong
version. The critic's prose checks complement this skill's dialogue review; they
do not certify the edited speech as verbatim. An earlier critique is useful
diagnostic input, but repeat affected checks after later approved edits. Run the
final consistency gate against the actual selected revision before promotion.

## Boundaries

- Read but **never** change the VTT, any extraction layer (smoothed included),
  voice/example files, campaign policy, or the original narration.
- Put review artifacts and new revisions under
  `<session>/dialogue_edit/<scene-run>/`, outside the narration files selected
  for assembly. The helper enforces the output location and refuses existing
  runs, stale inputs, and ambiguous replacements.
- **Every proposed wording change needs a GM ruling.** No "obvious cleanup" is
  applied before review. Ambiguous cadence, filler, or attribution is a separate
  question, never smuggled into a larger approved edit.
- A changed proposal is a new proposal. Approval is not permission to rewrite
  the replacement or fix nearby text.
- Missing events, transcription errors, identity disputes, broad prose edits and
  mechanics removal belong to their existing workflows. Record the finding and
  its source evidence; do not silently do those jobs here.
- No automatic assembly, source repair, publication, or extra backend call. A
  requested remote run needs authorization for that scope and backend; reuse
  existing authorization rather than asking again.

## 1. Inventory and read the campaign's rulings

Accept a session directory or an exact scene path. Use explicit user selection;
if several sessions or scenes remain plausible, ask with `AskUserQuestion`. Do
not turn an empty selection into the entire session. Report the chosen files and
any missing inputs.

Resolve each scene's **exact reviewed extraction**, narrator, and voices from
its plan/provenance and declared configuration. Read:

- the complete existing narration and its corresponding complete extraction —
  descriptive account, dialogue, and disambiguating notes;
- `config/party.yaml` and `config/players.yaml` for declared character
  identities, voices, examples, and supporting speakers;
- the declared voice/example files actually relevant to the scene;
- the applicable genre/register file (including a declared `paths.genre_file`)
  and `notes/scrub_register_policy.md` if present;
- any earlier dialogue-edit manifests and applicable scoped GM rulings.

Do not guess a source from filename similarity, pick the freshest extraction, or
guess a voice from first-name prefixes. A declared-but-missing voice is a
blocker for that scene. Missing optional policy is reported as absent, not
invented. An NPC/GM label need not have a PC voice file. A GM may also voice a
PC — read stage directions and identity declarations.

Use existing review records and clear instructions without re-asking settled
questions. If the narration/source mapping or its review status is unresolved,
get that scene's input ruling before editing it. Missing narration means this
skill is **NOT RUN** — it is not an instruction to call the narrator.

Ask whether the GM wants **chat** or an **artifact** review for this run, unless
they have already chosen. Chat rules one scene at a time. Artifact mode puts
every prepared scene of the session on **one page**; each scene is still frozen,
split out and applied separately afterwards.

## 2. Read the full scene; propose exact changes

Read [editorial-guide.md](references/editorial-guide.md) before your first
scene. It contains the tested editing latitude and the concrete failure cases
that should change your decisions.

Read every selected scene in full. A scanner can mark possible repetition; zero
hits cannot establish that a scene needs no work.

For each proposal, present:

- exact original and replacement text, with the surrounding exchange;
- speaker, target file/location, and the particular readability gain;
- exact source/voice evidence, and what remains uncertain;
- any required adjacent attribution/punctuation change, visibly identified.

Preserve the narrator's inner and descriptive prose. Do not normalize fluent or
ESL diction, improve a joke, add a response, silently turn a question into an
assertion, or merge separate speakers' agreement. If you cannot support a
completion from the source, leave it and ask.

Save proposals **before** asking for rulings. Follow
[review-and-apply.md](references/review-and-apply.md) to freeze exact spans,
evidence, and content identities with `scripts/review_edits.py prepare`. The
helper writes the original copy, the full candidate, a diff, a readable review,
the shared-artifact queue, and the frozen review record. A candidate contains
all proposals and remains **unapproved**. Unresolved or out-of-scope proposals
are marked and cannot be applied even if mistakenly approved.

If nothing needs changing, record **read: complete; proposals: none** and
continue in the selected scope. Do not manufacture an approval question.

## 3. The GM rules — one scene at a time

In chat, show the exact proposals with evidence and wait for explicit rulings.
Save those actual rulings in a decision file bound to the frozen review ID.
Never manufacture an approval to satisfy the helper.

In artifact mode, prepare every selected scene, collect their frozen runs onto
one session page (`review_edits.py session-page`), build it with the shared
builder and publish it with `capabilities: {"artifact": {}}`, then **stop** — the save
comes back as a notification or the GM's word, and is never polled for. Read it
back with the `Artifact` tool (CONTRACT step 5) and `read_decisions.py`, then `split-decisions` gives one
decision file per scene for `apply`. Full sequence in
[review-and-apply.md](references/review-and-apply.md); contract in
`~/.claude/skills/_shared/review-artifact/CONTRACT.md`.

- **approve** — apply only the stated, supported replacement.
- **reject** — retain the original wording and record the rejection.
- **discuss** — return the proposal and note to chat.
- **unmarked** — unresolved. Never inferred approval or rejection.

There is no session-wide catch-all approval. Discuss uncertain radio-play
phrasing, or any other distinct editorial decision, separately. Keep unresolved
items pending until the GM rules or explicitly defers them. An explicit deferral
allows moving on while preserving the original text and carrying the item
forward.

## 4. Apply, then read the result and its joins

Run the helper's application **dry-run first**, inspect the complete approved
diff, then use `--write` with the same frozen review and the same actual
decisions. An approval already given for these exact edits covers both steps.

Application uses the recorded replacement text, not another model rewrite. It
checks the original, source, references, proposal identity, and exact spans, and
rejects conflicting or stale application before changing the scene. It writes a
fresh derived revision and never overwrites the original.

Read the result, then compare the previous scene's closing lines and the next
scene's opening lines. Look for orphaned replies, lost setups, repeated seam
sentences, or a narrator's boundary echo now presented as spoken dialogue.

A newly noticed defect is a **new proposal**. Do not repair it under an earlier
ruling, including in neighbouring scenes. Partial application is explicitly
labelled; it does not make unresolved findings disappear.

## 5. Record the run and stop at its boundary

Maintain `<session>/dialogue_edit.sources.yaml` as the session index, preserving
prior runs. Record:

- ordered selected scenes and exact draft/source/reference paths;
- frozen review ID and artifact paths (hashes live in each review record);
- per-scene reading, review, and application status, including not-run reasons;
- actual GM decisions, revision paths, remaining issues, and seam findings;
- scoped campaign rulings and open/resolved carry-forward items;
- whatever runtime/model details are actually observable.

The helper writes an application record with the returned decisions and the
result hash. Reference it from the session index. If all proposals were rejected
or deferred, retain the decision file and record that no revision was written.
Validate the index by parsing it as YAML.

Record unknown execution details as unknown. Do not fabricate a submitted prompt
pair. If a separate runner is explicitly requested, preserve its actual inputs,
reported model/effort, and failure status without silent provider changes.

Session rulings belong in this manifest. Promoting a ruling into shared campaign
policy is an ancillary edit: get approval for the destination and the exact
wording unless already authorized. Reuse standing rulings within their scope; do
not turn one scene's choice into a universal rule.

Finish with scenes reviewed/not run, changes applied, rejected/deferred/open
items, revision paths, and seam results. State that the original narration is
intact and the new revision has not been assembled or published. Let the GM
choose any downstream promotion as a separate action.
