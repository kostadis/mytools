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
   - `<campaign>/summaries/<date>/narration/session_doc_scene_06_*.md` (Stage 3 per-scene output)
   - A directory of per-scene files (critique all of them).
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

### Phase 2: Load voice context for the narrator

For the narrator's first-name lowercase (e.g. `Unla Key` → `unla`):

- `<campaign>/voice/<key>_voice.md` or `<campaign>/voice/<key>.md` — the **authoritative voice spec**.
- `<campaign>/examples/<key>.md` or `<campaign>/examples/<key>_examples.md` — verbatim prose passages for this character.
- `<campaign>/docs/party.md` — backstory / relationships / class.

If a file does not exist, omit it from the critique inputs. Note in the report which inputs were available.

### Phase 3: Apply the critic lens

Read the narration sentence by sentence. **Flag** a sentence when it falls into one of these categories:

1. **Generic fantasy prose** — could appear in any narrator's section. Stock metaphors ("the silence stretched", "his hand fell to his sword", "a chill ran down her spine") with nothing this character would specifically notice or say.
2. **Voice spec conflict** — directly contradicts the spec (uses a verbal tic the spec forbids, an emotional register the character does not have, vocabulary the spec marks as out-of-character).
3. **Convergence with house style** — the sentence sounds like the *narrator persona* of the previous section. (Useful when critiquing a directory: read scenes pairwise and flag rhythm/vocabulary repetitions.)
4. **Tell-not-show emotional commentary** — sentences that name the feeling instead of rendering it ("She felt afraid", "He was angry"). Per-character examples usually show how this writer actually renders feeling; flag when the narration falls back to naming.
5. **Cliché / on-the-nose simile** — workshopped fantasy similes (`like a coiled spring`, `like a tomb`) where the per-character examples show a more specific image vocabulary.

**Do NOT flag:**

- Verbatim dialogue (lines inside `"..."` quotation marks that came from the source extraction — these are load-bearing and must not be rewritten).
- Action beats that simply describe what happened, even if plain. Plain ≠ generic.
- Prose that already matches the per-character examples — even if it would look generic on its own, matching the writer's established voice is the *goal*.
- Sentences merely because they are short or long. Rhythm variation is intentional.

Aim for **2–8 flags per scene**. If you find more, you are probably being too strict — narrow to the worst offenders. If you find zero, say so explicitly with a one-line verdict; do not invent issues to fill the report.

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

- **Never modify the narration file.** The report is a separate artifact.
- **Never auto-apply rewrites.** Suggestions are exactly that — suggestions for the user to consider.
- **Quote verbatim.** When flagging a sentence, paste it exactly from the narration. The user will search for it; an approximate quote wastes their time.
- **Suggested rewrites must be grounded.** Pull rhythm and vocabulary from the voice spec and per-character examples. If the spec is missing, mark the suggestion `[grounded in examples only]` or `[no spec available — best guess]`.
- **No commentary on the critique itself.** Don't write "this scene is generally well-narrated but..." in the verdict's first sentence. State the strongest specific issue and stop.
- **No invented examples.** If the per-character examples are absent, don't fabricate the "right" voice — say what's missing and degrade gracefully.

## Output

Report each file written and the flag count. Surface the strongest recurring issue across scenes (e.g. "three scenes flagged Unla for stock simile usage") so the user knows where to focus their re-narration budget.

Remind the user:
- The report is review-only — they decide which flags to act on.
- For flagged sentences they want to fix, the cheapest path is a manual edit; for systemic voice problems across many scenes, re-running `session_doc.py --scene <N>` with an updated voice file is often more efficient than per-sentence edits.
