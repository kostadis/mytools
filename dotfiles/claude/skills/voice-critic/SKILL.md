---
name: voice-critic
description: Critique a session_doc.py narration for generic prose, voice drift, or conflicts with the character's voice spec. Use after generating per-scene narration to flag sentences worth rewriting before assembly. Invoke as /voice-critic <narration-file-or-dir>.
tools: Read, Glob, Grep, Bash, Write
---

# Voice Critic

Read a generated narration alongside its character's voice spec and per-character examples, and produce a report of sentences that read as generic, drift from the spec, or echo a different narrator. The report is a **review artifact** — never auto-apply rewrites, never overwrite the narration file.

## What This Is For

`session_doc.py` Pass 5 produces first-person narration per scene. Even with Phase 1 (per-character examples), Phase 2 (hoisted voice spec), and Phase 3 (previous-narrator contrast), individual sentences sometimes still read as generic fantasy prose or break the character's voice. This skill is the human-in-the-loop critique pass: it surfaces those sentences so the user can decide whether to keep, edit, or re-run the scene.

The skill is structurally similar to `consistency-check` — same post-hoc, artifact-based, "agent flags / human decides" pattern.

## Required Information

Detect or ask for:

1. **Narration file(s)** — single file, glob, or directory. Common shapes:
   - `<campaign>/summaries/<date>/narration/session_doc_scene_06_*.scrubbed.md` (preferred — what `assemble.py` reads)
   - `<campaign>/summaries/<date>/narration/session_doc_scene_06_*.md` (raw, if no scrubbed variant exists)
   - A directory of per-scene files (critique all of them).
   When given a directory, prefer `session_doc_scene_NN_*.scrubbed.md` over the raw `session_doc_scene_NN_*.md` for each scene — the scrubbed files are the canonical pre-assembly source. Fall back to the raw `.md` only when no scrubbed variant exists for that scene.
2. **Campaign directory** — root of the campaign workspace (derive from the narration path, or ask).
3. **Voice spec directory** — usually `<campaign>/voice/`. Each narrator's spec lives at `<narrator>_voice.md` or `<narrator>.md` (case-insensitive, first-name match).
4. **Per-character examples directory** (optional) — usually `<campaign>/examples/`. Files named `<narrator>.md` or `<narrator>_examples.md` route per-character; everything else is global.
5. **Party doc** (optional) — `<campaign>/docs/party.md` for character relationships and class info.

If invoked with a directory or glob, iterate every scene file. If a referenced voice spec is missing, fall back to the per-character examples; if both are missing, skip that scene with a one-line note rather than fabricating a critique.

## Per-scene workflow

### Phase 1: Parse the narration file

Per-scene narration files written by `session_doc.py --per-scene-output` start with YAML frontmatter:

```yaml
---
scene: 06
slug: <slug>
narrator: <name>
scene_name: <human-readable scene name>
session: <session id>
---
```

Pull `narrator` and `scene_name` from the frontmatter. If frontmatter is absent (assembled doc rather than per-scene file), infer narrator from the `## <Name>` heading immediately preceding the prose; if multiple narrators appear in the same file, treat each `## <Name>` block as a separate critique target.

When collecting files from a directory, deduplicate by scene number: for each scene, use the `.scrubbed.md` variant if it exists, otherwise the raw `.md`. This mirrors the selection logic in `assemble.py`.

### Phase 2: Load voice context for the narrator

For the narrator's first-name lowercase (e.g. `Unla Key` → `unla`):

- `<campaign>/voice/<key>_voice.md` or `<campaign>/voice/<key>.md` — the **authoritative voice spec**.
- `<campaign>/examples/<key>.md` or `<campaign>/examples/<key>_examples.md` — verbatim prose passages for this character.
- `<campaign>/docs/party.md` — backstory / relationships / class.

If a file does not exist, omit it from the critique inputs. Note in the report which inputs were available.

### Phase 3: Apply the critic lens

**Before the sentence-by-sentence pass, run two mechanical scans and include their findings directly in the flags list:**

**Mechanical scan A — em-dashes.** Grep the narration for `—`. Flag every narration-level em-dash for conversion (comma, colon, or period depending on clause relationship). Do NOT flag em-dashes inside `"..."` dialogue or `*...*` italic spans — those are VTT-captured speech disfluencies or truncated lines and must stay verbatim. For each flagged em-dash, give a suggested replacement in the report.

**Mechanical scan B — register-wrong vocabulary.** Grep for words such as: `shape`, `shaped`, `filed`, `geometry`, `geometric`, `aligned`, `configured`, `structure`, `structural`, `axis`, `angle`, `vector`, `plane`, `arc`, `perimeter`, `dimensions`, `calculated`, `formula`. Flag any occurrence in *narration prose* (not inside verbatim dialogue or italic VTT quotes). These are analytical/architectural/mathematical defaults the LLM reaches for when describing arrangement or form; none of the narrators in this party think in those terms. The suggested rewrite should use the narrator's sensory or experiential vocabulary instead.

Two traps in scan B. Do not anchor the regex with a fixed-width prefix
(`.{55}\bfiled\b`) — it silently drops hits near the start of a line. And
`shaped` has legitimate uses (`the man who had shaped my devotion`); flag on
`the shape of X`, not on every inflection.

**Mechanical scan C — the taxonomising-appositive family.** `_genre.md`
bans "with the [Adj] [Noun] of someone who…", but **the tic rotates surface
form between renders rather than disappearing.** Observed across two renders
of the same scene: `with the grace of a man who understood…` became
`that grin he gets when…`, `had a way of saying…`, `with that quiet,
watchful look he gets`, and `that slight, fond squint he gets`. Scan for the
whole family, allowing adjectives between the determiner and the noun:

```bash
grep -nEi "\bthat\b[^.]{0,45}\b(look|thing|grin|pinch|edge|squint|air|hunger)\b[^.]{0,45}\b(he|she|they)\s+(gets?|does|do|had)\b|\bwith that\b[^.]{0,40}\b(look|expression|air|squint|hunger)\b|\b(the|with the) (look|hunger|expression|grace|air) of (a man|a woman|someone|people)\b|\bhad a way of \w+ing\b" <scene.md>
```

Even this under-matches: instances split across a sentence boundary
(`that look in his eye. The one he gets when…`) and nouns outside the list
still slip through. **Treat all three scans as a floor, not a ceiling** —
reading found 2–3 additional instances per scene that no pattern caught, in
every scene checked. Say so in the report rather than implying the scan was
exhaustive.

**Mechanical scan D — canon facts.** Before critiquing prose, check the
narration's factual claims about the party against `docs/party.md` and
`characters/<name>.md`: species, class, stature, relationships, equipment.
One render described a **goliath** (7–8 ft, Path of the Giant) as "all five
and a half feet of immediate presence", contradicting both his sheet and
another scene in the same session. A canon error outranks every stylistic
flag in the report and should be listed first. Watch for anachronism too —
`split an atom` appeared in a Faerûn tortle's narration.

Then read the narration sentence by sentence. **Flag** a sentence when it falls into one of these categories:

1. **Generic fantasy prose** — could appear in any narrator's section. Stock metaphors ("the silence stretched", "his hand fell to his sword", "a chill ran down her spine") with nothing this character would specifically notice or say.
2. **Voice spec conflict** — directly contradicts the spec (uses a verbal tic the spec forbids, an emotional register the character does not have, vocabulary the spec marks as out-of-character).
3. **Convergence with house style** — the sentence sounds like the *narrator persona* of the previous section. (Useful when critiquing a directory: read scenes pairwise and flag rhythm/vocabulary repetitions.)
4. **Tell-not-show emotional commentary** — sentences that name the feeling instead of rendering it ("She felt afraid", "He was angry"). Per-character examples usually show how this writer actually renders feeling; flag when the narration falls back to naming.
5. **Cliché / on-the-nose simile** — workshopped fantasy similes (`like a coiled spring`, `like a tomb`) where the per-character examples show a more specific image vocabulary.
6. **Register-wrong vocabulary** — catches anything the mechanical scan missed: analytical, bureaucratic, or clinical words that no one in this party would reach for. Use judgment; the scan list is a starting point, not an exhaustive inventory.

7. **GM stage direction inside quoted dialogue.** The upstream extraction
   sometimes quotes the GM's out-of-fiction narration, and the voice pass is
   *forbidden* from touching anything between quotation marks — so it passes
   through as character speech. Symptoms: a speech tag inside the quote
   (`"Toblen says: well—…"`), second-person address to a player
   (`"And you immediately remember that…"`), stage direction as dialogue
   (`"Then he looks at Valphine and notices…"`), third-person reporting
   inside a character's own quote (`"But she says there's been a small
   problem"`), and worst, the POV character referring to herself by name in
   the third person. Detect with:
   ```bash
   grep -nEi '"[^"\n]*\b(he goes|he says|she says|she wonders|so he says|and you immediately remember|he does point out|Then he looks at)\b[^"\n]*"' <scene.md>
   ```
   Use a newline-excluding character class — `"[^"]*…"` spans paragraph
   breaks in most regex engines and produces cross-paragraph false
   positives. This is an upstream defect: re-running the pipeline reproduces
   it, because the immutable-quote rule guarantees it. Say that explicitly
   rather than recommending a re-render.

**Do NOT flag:**

- Verbatim dialogue (lines inside `"..."` quotation marks that came from the source extraction — these are load-bearing and must not be rewritten).
- Action beats that simply describe what happened, even if plain. Plain ≠ generic.
- Prose that already matches the per-character examples — even if it would look generic on its own, matching the writer's established voice is the *goal*.
- Sentences merely because they are short or long. Rhythm variation is intentional.
- **A construction the character's own examples establish as theirs.**
  `ever the X` looks like a house-style tic, and is one in most narrators —
  but `examples/valphine.md` uses it natively, so its appearance in
  Valphine's section is voice, not drift. Check the examples before calling
  something convergence. Repetition within a single scene is still worth
  flagging; existence is not.

Flag every genuine issue. Do not drop real problems to keep the list short.

### Phase 3b: verify before you assert

Two failure modes cost real credibility in practice. Both are avoidable.

**Verify claims about tooling by reading the tool.** A structural flag once
asserted that `assemble.py` needed an in-body `### <Narrator>` heading to
mark POV boundaries. It does not — it builds `## {narrator} — {scene_name}`
from the *frontmatter* and never reads the body heading, so the flag was
backwards: the scenes that *had* the heading were duplicating the narrator's
name. Before flagging anything as structural or pipeline-breaking, open the
consuming code.

**Never propose a rewrite that lands inside `"..."`.** Before drafting a
suggestion, confirm the span you are rewriting is narration. One suggested
fix targeted a line of tax-code English that read badly for the character —
but the VTT confirmed the player said it verbatim, so the "fix" would have
edited real player speech. When a quoted line reads wrong for a character,
the available moves are: check the VTT for a mis-attribution, fix the
*attribution* in the narration, or report it as an upstream note. Rewriting
the quote is not one of them.

**Check the inputs against each other.** The specs and the examples can
disagree. `examples/soma.md` is half terse and half lush, while
`voice/soma_new_pipeline.md` forbids the lush half in three separate
failure-prevention rules — so narration that drifts literary is obeying half
its own inputs. When a tic appears in the example corpus itself
(`ever the X` occurs in three of four example files), it is **inherited, not
drift**; report it as an input problem with a recommendation to amend
`_genre.md`, not as a per-scene failure.

### Phase 4: Write the report

For a single-scene critique, write to:

```
<narration-dir>/voice_critique_scene_<NN>_<narrator-slug>.md
```

For a directory critique, write one report per scene, plus a top-level `voice_critique_summary.md` with counts and the strongest recurring theme across scenes.

Each per-scene report uses this structure:

```markdown
# Voice Critique — {narrator}, scene {NN}: {scene_name}

**Narration:** {path}
**Voice spec:** {path or "missing"}
**Per-char examples:** {path or "none"}

## Flags

### [1] {category — Generic prose / Voice spec conflict / etc.}

> {sentence verbatim from the narration — quote exactly}

**Why:** {one sentence on what makes this off-voice for this narrator}
**Suggested rewrite:** {one alternative, written in this character's voice — drawn from spec/examples patterns}

### [2] {category}

> {sentence}

**Why:** {...}
**Suggested rewrite:** {...}

(continue for 2–8 total flags)

## Verdict

{1–2 sentences: overall voice fidelity, the top recurring theme, and whether the scene is worth re-narrating or just spot-editing}
```

## Hard rules

- **Never modify the narration file during the critique pass.** The report is a separate artifact. When the user subsequently applies fixes, they belong in the `.scrubbed.md` file (not the raw `.md`) so that `assemble.py` picks them up.
- **Never auto-apply rewrites.** Suggestions are exactly that — suggestions for the user to consider.
- **Quote verbatim.** When flagging a sentence, paste it exactly from the narration. The user will search for it; an approximate quote wastes their time.
- **Suggested rewrites must be grounded.** Pull rhythm and vocabulary from the voice spec and per-character examples. If the spec is missing, mark the suggestion `[grounded in examples only]` or `[no spec available — best guess]`.
- **No commentary on the critique itself.** Don't write "this scene is generally well-narrated but..." in the verdict's first sentence. State the strongest specific issue and stop.
- **No invented examples.** If the per-character examples are absent, don't fabricate the "right" voice — say what's missing and degrade gracefully.

## Output

Report each file written and the flag count. Surface the strongest recurring issue across scenes (e.g. "three scenes flagged Unla for stock simile usage") so the user knows where to focus their re-narration budget.

**On a second pass over a re-rendered scene**, open the report with what
*resolved* since the last render before listing new flags, and mark any
withdrawn flag as withdrawn rather than deleting it — the record of what was
found matters. Re-rendering genuinely fixes structural problems (one
re-render eliminated a 60-line stretch with no narrator and recovered
speaker attributions I had said were unrecoverable) while simultaneously
regressing on tics, so report both directions honestly. If earlier reports
in the same session now contain superseded claims, annotate them rather than
leaving them to mislead.

Remind the user:
- The report is review-only — they decide which flags to act on.
- For flagged sentences they want to fix, the cheapest path is a manual edit; for systemic voice problems across many scenes, re-running `session_doc.py --scene <N>` with an updated voice file is often more efficient than per-sentence edits.
