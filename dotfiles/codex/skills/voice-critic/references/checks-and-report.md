# Coverage and report contract

## Separate the layers

Count narrative prose separately from quoted dialogue, frontmatter, headings,
HTML comments, and scholarly marginal apparatus. Recognize straight and curly
quotes, multiline speech, and attribution outside quotes; a naïve quote regex
is not a reliable parser. Italic inner thought remains relevant to voice/tense
judgment, but exclude it from counts when the actual rule/checker's budget scope
excludes it. State the measurement boundary and denominator for prose share.
Never present estimates as exact counts or incompatible checker/manual counts as
one measure. Explicitly report any parsing limitation.

Treat dialogue as protected, including GM-approved dialogue-edit rewrites, which
are protected edited speech rather than verbatim transcript. Honor recorded tape
divergences. Do not “correct” them back to the extraction. Existing sage notes are
apparatus, not the narrator's register.

## Required reading checks

- Generic prose, clichés, and emotional commentary: show why the sentence loses
  this particular narrator's perspective. Plain action, short sentences, and
  direct feeling are not defects by themselves. Examples may deliberately license
  the very construction that would otherwise look generic.
- Voice and register conflicts: cite a resolved voice/rulebook and relevant
  example. Preserve comprehensible ESL diction and formal reach. For syntax or
  fluency disputes, examples are stronger evidence than abstract personality notes.
- Cross-narrator convergence and portable tics: compare full passages and show
  both quotes. Check repeated bookkeeping vocabulary and stock frames only against
  applicable caps/registers. A character explicitly licensed to think in prices
  must not be criticized merely for doing so.
- Em-dashes: count and classify interruption versus connective uses under the
  effective rule. Total occurrences and prohibited subset are separate numbers.
  No universal limit is implied by this skill.
- Interruption provenance: trace dialogue ending in an em-dash through selected
  narration, reviewed extraction, predecessor, and tape where available. A count
  delta is a candidate, not proof of a false interruption. Establish overlapping
  speech versus trail-off from sequence/timing; missing evidence stays unresolved.
  Final-line truncations matter especially. Changing a dash may also require a
  separately visible attribution change such as “starts.”
- Orphan quote runs: look for three or more quote-only paragraphs and for shorter
  exchanges with unclear speakers. Clear two-speaker alternation and deliberate
  choruses are legitimate. Use source stage directions and identity declarations
  for tags; an UNKNOWN label cannot support an invented speaker. Tagging is a prose
  proposal, not permission to rewrite dialogue. An action beat may be added only
  when the extraction or transcript records that action (cite it in evidence);
  otherwise anchor the quote with attribution alone. Never invent an action.
- Sequence claims: map the complete source beat order to narration before asserting
  reordering. Separate chronology, tense, and invented framing. Do not infer a
  missing or displaced event from two isolated excerpts.

Scans surface candidates; the full reading establishes findings. There is no
minimum finding count. Missing events, source errors, identity disputes, and table
mechanics get evidence-backed referrals to coverage/consistency/scrub workflows.
Do not perform those repairs under a style flag.

## Dialogue scope calls and hatches

Apply existing campaign rulings before surfacing anachronisms; do not re-ask settled
ren-faire or imported-vocabulary decisions. Unresolved references in protected
speech belong in a separate GM scope-call section: keep, replace in-world, or
annotate. Replacement is an authorial divergence, not transcription correction.
For annotation, consult the campaign's established sage convention and scrub
instructions if available; never invent a new scholar, canon, or gloss without an
exact reviewed proposal and provenance record.

List every `<!-- table-speech reclassified: … -->` hatch by source file/line and
quote its contents for scope review. Do not style-flag its contents or fabricate
missing hatches. On assembled input, where assembly may strip them, inspect
available selected source scenes; otherwise say hatch review unavailable rather
than “none.” Record actual absence separately from inability to inspect.

## Budget ledger

For assembled input, aggregate over the entire selected document. For a directory,
aggregate once over the effective scenes in the summary. For a subset/single scene,
state that full-document caps cannot be certified. Resolve mixed rulebook versions
per render; do not merge contradictory thresholds into a made-up global cap.

Every ledger row records rule source/digest, scope, observed count, permitted count,
and `ok`, `BREACH`, or `not checked` with a reason. No default numerical budgets
live here. Undeclared rules are not checked; unavailable tools/files are not passed.
Preserve lint ERROR/warn/note distinctions and the actual reason a check skipped.
Only report a measured budget as met.

A cap breach is one finding with linked instances. Report where the instances
sit, per scene and narrator. Rank which occurrences earn their place, recommend
which to keep/change, and state the target count. Do not invite deletion of every
occurrence. Decide the remedy by distribution and cost: where breaches cluster in
a few scenes, spot-fix or re-narrate those scenes (`sd_narrate --scene <N>`);
recommend re-rendering the whole document only when they are spread throughout,
and only the GM's explicit yes starts that paid run. A breach alone is never a
whole-document re-render signal.

## Markdown report

Include these sections in both per-scene and aggregate records as applicable:

1. Identity: selected file/revision, hash, input shape, scene/narrator, review ID.
2. Inputs resolved: run/source records; genre path, digest, sizes and delivery
   status; current versus rendered rules; generator bans/brief; declared voices,
   per-character/shared examples; roster/party coverage; policy and approvals;
   lint command/result and unavailable checks.
3. Budget ledger: explicit scope, measurement method, counts and verdicts.
4. Findings: stable ID, severity/category, exact quote and line, cited evidence,
   reason, exact suggested replacement, uncertainty and any dependent edit.
5. Per-scene grid: narration prose count, total-text denominator/share, narrator.
   A small prose share is diagnostic, not an invented minimum requirement.
6. Locked-dialogue scope calls: standing rulings applied and unresolved calls.
7. Reclassified table speech: all hatches, none found, or unavailable with reason.
8. Verdict and carry-forward: strongest supported problem, missing-input impact,
   suggested next action, and separate unresolved upstream issues.

Retain tool output, source/reference hashes, exact proposal mapping and returned
decisions beside the report. Review records must distinguish open, rejected,
deferred, resolved, and not-run states. A resolved style review does not certify
unperformed consistency, coverage, or upstream fidelity checks.

## Commands

Run from the session directory, substituting the reviewed extraction layers the
run records name for the two directory names below.

Mechanical layer (exit 1 = hard ERROR fired; exit 2 = unreadable
`--genre-file`, fix the invocation before claiming coverage):

```bash
voice_lint <narration-files> --genre-file <resolved genre_file>
```

Interruption-provenance count (raw versus smoothed `—"` quote endings). A delta
is a candidate; adjudicate each one against the tape, preferring the raw
extraction's punctuation as the pre-smoothing capture:

```bash
for d in scene_extractions scene_extractions_smoothed; do \
  echo "$d: $(grep -rhc '—"$' $d/0*.md | paste -sd+ | bc)"; done
```

Orphan-quote candidates (three or more consecutive quote-only lines). It sees
only single-line, straight-quoted paragraphs, so read for curly quotes and
multiline speech too:

```bash
python3 - "$@" <<'EOF'
import sys
for f in sys.argv[1:]:
    lines=open(f).read().split('\n'); run=[]; start=0
    def flush(end):
        if len(run)>=3: print(f"{f}:{start+1}-{end}  ({len(run)} orphan quote lines)")
    for i,l in enumerate(lines):
        t=l.strip()
        if t.startswith('"') and t.endswith('"'):
            if not run: start=i
            run.append(t)
        elif t=='': continue
        else: flush(i); run=[]
    flush(len(lines))
EOF
```

Name, but never run, the rulebook migration for an unset `paths.genre_file`
when `voice/_genre.md` exists, and make it the report's first line:
`python -m server.migrate_narrate_genre --campaign-dir <DIR>`.

## Measured cases

The long narratives live in the Claude copy of this skill; here each is one line.

- Phandalin ch48: smoothing turned 0 raw `—"` endings into 59; of 41 that reached
  narration, 40 were real interruptions and 1 was the scene's final-line trail-off.
- Phandalin ch50: a rewrite (`I set it beside the rest`) collided with `I set it
  on the shelf` two scenes away; Brewbarry's examples ("Order is bullies. They
  bully barbarians.") settled a register dispute his spec could not; a confirmed
  "eleven lines moved out of order" was wrong, only tense and an invented
  `Earlier, while we…` frame were real.
- Phandalin ch2 scene 04: twelve orphan quote runs, one nine lines long; the GM
  called the dialogue "incomprehensible."
- #245 benchmark: every scan found zero tics across 12 scenes while reading found
  three behavioral-taxonomy instances; fable flags at about half opus's rate.
- #276: the rulebook became a file (`paths.genre_file`); pre-#276 records embed it
  as text, and on Phandalin "first-person present tense, always" arrived flattened
  to one line and only 3 of 62 scenes used that tense.
- #300: `sd_narrate` refuses to start without a declared voice spec, so a
  `[no spec]` result is usually a lookup bug; #175/#247: the retired first-name
  rule lost a renamed character's spec (`Grygum` → `Gyrgum`).
- #301: undeclared example files once joined a global block sent to every
  narrator (largest 51,073 characters); only `shared_examples:` is global now.
- Sage note: Phandalin's format is `*Marginal note in a later hand: "<term>" —
  <in-world explanation>. — Kostadinious the Sage*`; precedent Jimble the Unmoved,
  ch3 scene 07, GM-approved 2026-08-18.
- Em-dash rule: Phandalin forbids the connective dash, so flagging every dash
  would have raised 17 false findings on one scene of interruptions;
  out-of-the-abyss states only the permission, so connective use is a note there.
