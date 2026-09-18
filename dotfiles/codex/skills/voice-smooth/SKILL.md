---
name: voice-smooth
description: Render corrected scene-extraction quote blocks into readable, in-voice prose in a derived scene_extractions_smoothed/ layer. Use for /voice-smooth [session-dir] or voice-aware smoothing after session-summary-consistency; never use it to rewrite the verbatim VTT or scene extractions.
metadata:
  short-description: Smooth scene quotes in character voice
---

# Voice Smooth

Render transcriber-corrected quotes into readable prose that still sounds like
the character who said it. The output is a derived
`scene_extractions_smoothed/` layer for `session_doc`, not a corrected transcript
and not narration.

This is the Codex port of the Claude skill. Do not edit
`~/src/mytools/dotfiles/claude/skills/voice-smooth/` when changing this skill.

## Pipeline and Hard Invariant

```text
VTT
  -> scene_extractions_new/ or scene_extractions/  (verbatim record)
  -> voice-smooth
  -> scene_extractions_smoothed/                   (derived, ## Voiced moments)
  -> session_doc narration
```

Never mutate the VTT, `scene_extractions_new/`, or `scene_extractions/`. Those
remain the verbatim record. The primary outputs are
`scene_extractions_smoothed/` and `voice_smooth.sources.yaml`; an optional
review queue may also be written beside them.

Glossary changes, durable knowledge-boundary records, or campaign-instruction
pointers are ancillary edits. Make them only after the user explicitly approves
their exact destination and content.

## Codex Compatibility

- Ask the GM questions in chat. Do not refer to Claude `AskUserQuestion`.
- Codex does not have Claude's Artifact review callback. Use chat for a small
  queue. For a large queue, write a normal Markdown or JSON review file in the
  session directory, then read the GM's decisions back from chat or a named
  decision file.
- Use `apply_patch` for manual file edits. Preserve unrelated user changes.
- A generated smoothed layer is a draft until calibration and every required
  scope or garble ruling is resolved. Do not hand it to `session_doc` early.
- Do not invoke a paid or remote backend unless the user has approved that
  backend and scope.

## Optimization Target

Upstream layers optimize for precision: what was said, by whom, and in what
order. This derived layer optimizes for how verified material will read when a
narrator reproduces it.

Allowed after review:

- collapse false starts and reassemble sentences broken across cues
- remove filler that belongs to the player rather than the character
- complete a recorder-truncated cue when every reading makes the completion
  unambiguous
- recover a common-word ASR garble after a GM ruling
- split stage direction out of NPC speech

Never change facts, names, numbers, mechanics, attribution, or meaning on
smoothing judgment. Any correction to those fields needs evidence and an
explicit GM ruling; identity and scene scope are human decisions.

## Precondition

Run `session-summary-consistency` first. Proper-noun identity belongs there
because it is checked against the glossary and entity registry and must remain
stable across sessions.

Common-word garbles can survive that pass because no glossary can recognize
them. Surface those here, compare every independent transcript, and obtain a
GM ruling before changing a word. A proper noun whose canonical form is already
settled may be spelled consistently here, but cite the authority and include it
in the review; never use smoothing to decide who or what the name denotes.

## Inputs

- `session-dir`: a session directory under `summaries/`. Use CWD only if it is
  already a session directory. If invoked from a campaign root without a path,
  identify likely sessions but ask the user before choosing when more than one
  plausible extraction set exists.
- `scene-dir`: detect `scene_extractions_new/` or `scene_extractions/`. Refuse
  if neither exists. If both exist and campaign convention or freshness does
  not identify the active source, ask before choosing.
- `config/party.yaml`: authoritative declarations of PC voice files.
- `voice/_genre.md`: overall tone, when present.
- Player-to-character mapping: the
  `## Player names -> characters` section of the transcription glossary, when
  labels or scene summaries still contain real names.
- All transcript candidates in the session directory, plus any pre-built
  comparison report such as `*.retranscribed.cleaned.proper_nouns.md`.

## Workflow

### 1. Resolve Voice Guardrails Exactly

Collect every speaker label across the complete scene set before rendering.
Resolve PC voices from each character's `voice:` declaration in
`config/party.yaml`. Do not infer mappings by globbing `voice/*.md`, first-name
matching, or prefix/fuzzy matching.

Use CampaignGenerator's own resolver when available:

```bash
python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, '<campaign-generator-repo>')
from campaignlib.party_config import load_party_config, resolve_party_config
from session_doc.voice import (
    load_declared_voices,
    unknown_narrators,
    voice_declaration_problems,
)
cfg = resolve_party_config(
    load_party_config(Path('config/party.yaml')),
    Path('.'),
)
speakers = [<every exact speaker label>]
print('resolved:', sorted(load_declared_voices(cfg)))
for line in unknown_narrators(cfg, speakers) + voice_declaration_problems(cfg, speakers):
    print(' ', line)
"
```

`resolve_party_config` is required; the voice helpers take a resolved
configuration. Exact matching is case- and whitespace-insensitive across the
full character name. A titled name such as `Sister Maela Dawnforge` must not be
reduced to `Sister`.

Expected `unknown_narrators` findings for NPCs and `GM` are not PC failures.
Before smoothing a PC, stop if their declaration is absent or its declared file
is missing. Read every resolved PC voice file and `voice/_genre.md` before
editing that speaker's lines.

For speakers without a PC voice declaration:

- `GM` narration, OOC, and rules talk: clean plain prose; invent no voice.
- `GM as <NPC>`: use characterization from an NPC dossier or session-prep
  document. If none exists, use a neutral readable rendering. Record the source
  used in the manifest.

`load_voice_files(voice_dir)` is an orphan census, not a speaker resolver. Do
not use it to map speakers to voices.

### 2. Survey the Whole Scene Set Before Writing

Three defects change what belongs in the derived layer and are easy to miss
one scene at a time.

#### Cross-scene duplication

Compare quoted lines across every pair of scenes. One or two shared responses
such as “Yes” may be noise; a large shared block is a boundary defect.

```bash
review_tmp=$(mktemp -d)
for f in <scene-dir>/0*.md; do
  rg '^> "' "$f" | sort -u > "$review_tmp/$(basename "$f").quotes"
done
for a in "$review_tmp"/*.quotes; do
  for b in "$review_tmp"/*.quotes; do
    [ "$a" \< "$b" ] || continue
    n=$(comm -12 "$a" "$b" | wc -l)
    [ "$n" -gt 3 ] && echo "$n  $(basename "$a")  <->  $(basename "$b")"
  done
done
```

De-duplication is a scope decision. Present overlap counts and proposed cut
points, then obtain approval. Before cutting, read every quote unique to the
losing copy. In affected smoothed files, record the approved move in a scene
boundary note and strike through relocated scene-summary bullets rather than
silently deleting them from the copied summary.

#### Extractor splices and split speakers

Search for a speaker header fused inside a quote and for sentence fragments
split across consecutive speakers. Repair an unambiguous Markdown splice only
in the smoothed layer and report that the source still carries it.

A sentence whose tail was assigned to a different speaker is an attribution
defect. Bring the GM the options to rejoin it, repair only the words while
flagging attribution upstream, or leave it. If rejoining is approved, add an
HTML comment in the derived file noting that the verbatim layer retains the
split.

#### Player knowledge under a character label

Read for facts the character has no established route to know: an unexplained
proper noun, knowledge from another campaign, or a conclusion that arrives from
player-side context. The tape cannot adjudicate player-versus-character
knowledge; ask the GM.

When confirmed, keep the line but mark it OOC and annotate what the character
does not know and what `session_doc` must not narrate. Because derived
annotations disappear on re-extraction, propose a durable knowledge record in
`docs/` and a pointer from the campaign's persistent Codex instruction or index
file, usually `AGENTS.md`. Obtain separate approval before those durable edits.

### 3. Render Each Quote

Work from the source's `## Verbatim moments` section.

For each block:

1. Identify the speaker and loaded voice source.
2. Make the text readable: punctuate, collapse false starts, remove
   filler-as-noise, and reassemble broken cues.
3. Preserve the speaker's register, vocabulary, rhythm, and intentional tics.
   A character who rambles or hedges by design must continue to do so.
4. Preserve meaning and substance. If a repair is ambiguous, leave it near
   verbatim and flag it.
5. Keep OOC jokes, rules talk, and real-world tangents lightly smoothed and
   explicitly OOC.

Pure tooling or logistics noise is different from table banter: VTT controls,
initiative-widget trouble, token placement, and off-mic household asides carry
no narratable content. Propose cutting those spans from the derived layer.
Apply a ruling to similar spans only if the GM confirms that broader scope.
Leave an italic audit note in the affected smoothed section and record every cut
in the manifest.

For a mixed-attribution block, render each embedded line in its actual voice and
tag the interloper inline, such as `[GM]` or `[Kalan]`. Do not silently move the
outer speaker label.

#### Split stage direction out of NPC speech

A GM may narrate an NPC's action and then voice the NPC inside one extracted
quotation. Split only when the boundary is clear:

```markdown
*He looks at the party.* “I want to thank you for coming.”
```

Stage direction is italicized outside quotation marks; only spoken words remain
quoted. Keep the original `GM as <NPC>` label. Lift embedded speech tags in the
same way. If direction and speech cannot be separated without inventing a beat,
leave them fused and flag the line.

#### Unrecoverable garble

Do not delete or guess. Add an editorial note naming what each independent pass
heard and state `Do not narrate this as meaningful.` Deliberate jokes and odd
but intentional table language remain valid; always offer a keep-verbatim
option.

### 4. Rule Every Substantive Word Change

Punctuation, capitalization, filler removal, and false-start handling may be
covered by the approved calibration policy. Any other word change requires an
explicit item-level GM verdict.

For each candidate provide:

- a stable ID, scene, quote index, speaker, and voice source
- every independent transcript's reading, named
- nearby corroboration and the voice or scene evidence
- full-sentence before-and-after previews
- approve, keep/revert verbatim, and discuss options

Never batch a canon decision, unsettled name, transcript disagreement, or
contextual guess. When a scene has more than roughly six candidates, offer to
batch only changes independently settled by another transcript or mechanical
applications of a ruling already made in this session. List every batched item
in full.

For a long run, write `voice_smooth_review_queue.md` or JSON with one item per
candidate, grouped by scene. A decision record must distinguish:

- `approve`: apply the exact proposed rendering
- `revert`: restore the source text in the derived file
- `discuss`: pause and confirm the GM's interpretation or exact wording
- unmarked: undecided; re-ask rather than applying or silently dropping it

A short discuss note is not a specification. If implementing it would invent
canon, propose exact wording and obtain another confirmation.

#### Establish transcript independence

Different filenames are not necessarily different readings. Group byte-identical
files with `sha256sum`, then confirm independence with a distinctive clean phrase
from the middle of the session. Record duplicate groups in the manifest.

Search other transcripts by a clean phrase adjacent to a garble, not by the
garbled token itself:

```bash
rg -n -B 6 -A 6 -i '<clean anchor phrase>' <other-transcript>
```

Use one anchor per fragment before calling anything unrecoverable. When
transcripts disagree and no other evidence resolves them, state that plainly
and let the GM decide. Never prefer a reading merely because it is fluent.

A missing or word-like dice value, check result, or quantity is high priority:
go to every independent transcript. Do not invent or discard a number.

#### Proper-noun write-back

Establishing a name belongs upstream. If the registry already settles the
canonical form, cite it and ask whether to add the observed wrong form to
`notes/vtt_transcription_corrections.md`.

If approved:

- keep one row per canonical form; merge variants into the existing row
- put provenance in prose or bullets, never a new pipe table in a prose section
- compare registry and glossary; the registry is authoritative unless the GM
  rules otherwise
- flag ordinary-name variants that a case-insensitive replacement could
  overmatch
- run the installed `vtt-spell-pass/lint_glossary.py` before and after; require
  zero errors and account for every new warning

### 5. Write the Derived Layer

Create `<session-dir>/scene_extractions_smoothed/NN_slug.md` as a structural
copy of each source scene, with these deliberate changes:

- preserve frontmatter but set `source: voice-smoothed` and
  `from: ../<scene-dir-name>/NN_slug.md`
- copy `## Scene summary`, scrubbing player real names through the approved
  player-to-character map; do not otherwise rewrite or fact-correct it
- rename `## Verbatim moments` to `## Voiced moments`
- preserve moment order and outer speaker labels
- replace quote text only with reviewed smoothed renderings
- include approved boundary, splice, OOC, and knowledge annotations

`## Voiced moments` is a contract claim: these words were tidied for reading and
are not exact tape language. Never label smoothed output `## Verbatim moments`.

Flag summary garbles upstream instead of rewriting them. Do not modify anything
under `<scene-dir>/`.

### 6. Calibrate and Review

On the first run for a session, smooth one representative scene and present
verbatim-to-smoothed pairs grouped by decision class:

- filler removal
- grammar repair
- stage-direction splitting
- truncation handling

Show one representative pair per class plus every low-confidence pair. Ask the
GM to approve, edit specific items, or request a different pass for a speaker.
Do not render the rest until calibration is approved.

If `voice_smooth.sources.yaml` already records an approved calibration for the
same session and source set, verify it and resume rather than re-asking.

After calibration, draft the remaining scenes. Report per scene the quote count,
stage-direction splits, truncations, tooling cuts, and garble rulings. Do not
dump hundreds of routine pairs into chat; route risky word changes through the
decision queue.

The layer is ready only when calibration is approved, every scope decision is
approved, every substantive word change has a verdict, every `discuss` item is
resolved, and no item remains undecided.

### 7. Verify

Run structural checks across the complete output set:

```bash
rg -l '## Verbatim moments' <session-dir>/scene_extractions_smoothed/0*.md
rg -l '## Voiced moments' <session-dir>/scene_extractions_smoothed/0*.md
rg -l '^source: voice-smoothed$' <session-dir>/scene_extractions_smoothed/0*.md
rg -n 'truncated' <session-dir>/scene_extractions_smoothed/0*.md
```

Required invariants:

- zero smoothed files claim `## Verbatim moments`
- every source scene has exactly one matching smoothed file
- every smoothed file has `## Voiced moments` and
  `source: voice-smoothed`
- every `from:` target exists
- no new fused speaker header or orphaned quote block was introduced
- summary and quote sections separately satisfy the approved player-name policy

Audit quote deltas between each source and derived file. Punctuation,
capitalization, filler, and false-start changes must fit the calibration ruling.
Every substantive word change must map to an approved queue item. Revert any
unmapped word change and add it to `carry_forward`.

### 8. Write and Validate the Manifest

Write `<session-dir>/voice_smooth.sources.yaml` with:

- source and output directories; scene and quote counts
- resolved PC voice declarations and NPC characterization sources
- transcript files consulted, independent reading groups, and duplicate files
- calibration policy and approval
- verdict counts, including undecided items re-asked
- garble-ruling counts by scene
- every scope ruling: duplicate boundaries, tooling cuts, player-name policy,
  attribution repairs, and knowledge boundaries
- deliberately kept garbles and their rationale
- glossary rows written and registry/glossary conflicts
- upstream defects, unresolved findings, and `carry_forward`
- structural and delta-audit results

Validate it with `yaml.safe_load` and inspect the parsed top-level keys. Do not
mark the run ready if any required decision or verification remains open.

### 9. Hand-Off

State that `session_doc` should now read
`scene_extractions_smoothed/` while the VTT and verbatim extraction remain the
record.

Warn that re-running scene extraction will discard the smoothed layer's
de-duplication, splice repairs, OOC cuts, and knowledge annotations. Name those
session-specific derived changes in the hand-off so they are not lost casually.

## Compact Decision Rules

- Verbatim sources are immutable.
- Voice specs are declared in `party.yaml` and matched by exact full name.
- Voice files are authoritative; intentional style is not noise.
- Scope and knowledge boundaries belong to the GM.
- Proper-noun identity belongs upstream; settled spelling may be applied here
  with authority and approval.
- Common-word garbles are ruled here against independent transcript evidence.
- No approved item, no substantive word change.
- Unmarked and discuss items are not approvals.
- The output says `## Voiced moments`, never `## Verbatim moments`.
- Human review gates `session_doc`.
