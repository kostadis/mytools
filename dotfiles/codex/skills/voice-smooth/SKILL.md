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
`scene_extractions_smoothed/` and `voice_smooth.sources.yaml`. Review-page
files for a long queue live in a per-run scratch directory, not in the session
directory (step 4).

Glossary changes, durable knowledge-boundary records, or campaign-instruction
pointers are ancillary edits. Make them only after the user explicitly approves
their exact destination and content. Show the exact glossary row or knowledge
text and get an explicit yes for that text; a garble ruling fixes one quote,
while a glossary row changes every future transcript.

## Codex Compatibility

- Ask the GM questions in chat. Do not refer to Claude `AskUserQuestion`.
- Codex does not have Claude's Artifact review callback. Use chat for a small
  queue. For a long queue, build the shared review page
  (`../_shared/review-page/CONTRACT.md`) and read the GM's exported decisions
  back with `read_decisions.py --items`; there is no save callback (step 4).
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
- complete a recorder-truncated cue when the meaning is recoverable (`"Who are
  you talking."` -> `"Who are you talking to?"`); if the meaning is not
  recoverable, leave the fragment or mark it `[unclear]`
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
Read every resolved PC voice file and `voice/_genre.md` before editing that
speaker's lines.

A PC in scope whose declaration is absent (no `voice:` entry) or whose declared
file is missing is a stop, not a flag. Before smoothing any of that
character's lines, tell the GM which of the two failures the pre-flight
reported and ask whether to:

- proceed plainly for that character this session (clean, readable, no invented
  voice; record the ruling in the manifest)
- write a voice file first (then declare it in `party.yaml` and re-run the
  pre-flight)
- skip that character's lines in this pass

Do not choose for the GM, and do not treat silence as "proceed plainly".

For speakers without a PC voice declaration:

- `GM` narration, OOC, and rules talk: clean plain prose; invent no voice.
- `GM as <NPC>`: use characterization from the NPC's dossier (`docs/npcs/`) or
  the session prep documents (`notes/session_prep/`, `notes/sessions/`). If
  none exists, use a neutral readable rendering. Never flatten a distinctive
  NPC into GM-neutral prose when a source gives it a voice. Record the source
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
file, usually `AGENTS.md`. When the campaign is also run from Claude, the same
pointer goes in its `CLAUDE.md` too, so both harnesses load the same knowledge.
Confirming the boundary is not approval to write it: show the exact file paths
and the exact text (dossier content and every pointer line), and write only
after an explicit yes for that text.

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
- approve, reject (keep the verbatim text), and discuss options

Never batch a canon decision, unsettled name, transcript disagreement, or
contextual guess. When a scene has more than roughly six candidates, offer to
batch only changes independently settled by another transcript or mechanical
applications of a ruling already made in this session. List every batched item
in full.

#### Long queue: the shared review page

Below the batch threshold, ask in chat. For a long run (a full session with
dozens of rulings), build the shared review page instead of walking the queue
in chat. Read `../_shared/review-page/CONTRACT.md` relative to this skill
directory first. Put every review file in a per-run scratch directory, not in
the session directory:

```bash
REVIEW_PAGE="${CODEX_HOME:-$HOME/.codex}/skills/_shared/review-page"
review_dir=$(mktemp -d)
python "$REVIEW_PAGE/build_review.py" \
  --in "$review_dir/review_items_<round>.json" \
  --out "$review_dir/review_<round>.html"
```

Create `review_dir` once per run, record its path, and reuse it for every
round; a fresh `mktemp -d` in a later shell loses the earlier rounds.

- One card per garble candidate, id `s<NN>-g<NN>` (scene, candidate index) so
  the apply step can find the line, grouped by scene in scene order.
  Calibration pairs (step 6) use `cal-<NN>`, grouped by decision class.
- Each card carries exactly what a chat question would. `ev` holds every
  transcript's reading, named; the corroboration found; the voice-file
  rationale, naming the voice file; and the full-sentence verbatim -> smoothed
  preview, verbatim first. A card that shows only the result is unreviewable.
  Escape transcript text (`<`, `>`, `&`) before it goes into those HTML fields.
- `y` applies the proposed rendering to the derived file; `n` keeps the
  verbatim text there.
- Never pre-fill a verdict. Put a recommendation in `y` or `ev`, not in `state`.
- Each round gets its own items file, page, decisions file, and `reviewId`
  (`voice-smooth:<session>:<round>`), per the contract's multi-page rule, so
  every round's card text survives as the record of what the GM was asked.

Give the GM the page path and stop. Copy output and Save output stay disabled
until something is marked. Only an export the GM pastes into chat or saves
authorizes follow-up work; the page existing, being opened, or changing mtime
is never approval. Save a pasted export to `$review_dir/decisions_<round>.json`
and validate it against the items file it came from:

```bash
python "$REVIEW_PAGE/read_decisions.py" \
  --in "$review_dir/decisions_<round>.json" \
  --items "$review_dir/review_items_<round>.json"
```

Apply nothing from a read that did not exit 0. Before treating a second export
as new rulings, check its `savedAt` is newer than the one already processed.

Apply per verdict, whether it came from the page or from chat:

- `approve`: apply the exact proposed rendering
- `reject`: keep the source text in the derived file; do not re-litigate
- `discuss`: state your interpretation of the note and confirm it with the GM
  before applying anything
- unmarked: undecided; re-ask rather than applying your recommendation or
  silently dropping it. Say how many came back unmarked.

A short discuss note is not a specification. If implementing it would invent
canon, propose exact wording and obtain another confirmation.

Applying a ruling rewrites only the derived `scene_extractions_smoothed/` file,
never `<scene-dir>/` or the VTT. The page itself never edits files.

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

The write-back is its own ruling, never part of the garble ruling. A garble
ruling fixes one quote; a glossary row changes every future transcript. Show the
exact row you would write (canonical, full variant list after the merge, and
the section) and write it only after an explicit yes for that row.

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
Do not render the rest until calibration is approved. Use chat for a handful of
pairs; if the calibration set grows past what the GM can hold in view, put it on
the review page as `cal-<NN>` cards grouped by decision class (step 4).

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
- the GM's ruling for any PC without a resolved voice spec
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
- No approved item, no substantive word change. The no-card rule governs the
  smoothed layer; it never governs reporting. (Phandalin ch4 saw `"let's try to
  freeze it"` one line after `"All right, let's free the slaves!"`
  and cited this rule to
  stay silent; say "this contradicts the line before it" and let the GM rule.)
- Unmarked and discuss items are not approvals.
- Glossary rows, knowledge records, and instruction pointers each need an
  explicit yes to their exact text, separate from any garble ruling.
- A PC in scope without a resolved voice spec stops that character's smoothing
  until the GM chooses: proceed plainly, write a voice file first, or skip.
- A campaign used from both harnesses keeps its knowledge pointer in both
  `AGENTS.md` and `CLAUDE.md`.
- The output says `## Voiced moments`, never `## Verbatim moments`.
- Human review gates `session_doc`.
