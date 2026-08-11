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
3. **Voice spec directory** — usually `<campaign>/voice/`. Filenames vary by campaign and are **not** limited to `<narrator>_voice.md`; resolve them with the full rule in Phase 2, which mirrors what Pass 5 actually does.
4. **Per-character examples directory** (optional) — usually `<campaign>/examples/`. Routing is per-character for files whose stem matches a narrator's first name and **global for everything else** — see Phase 2, and note it is a *different* rule from the voice-spec one.
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

**Resolve the voice spec exactly the way Pass 5 resolves it.** The pipeline's rule lives in `session_doc/voice.py` (`load_voice_files` + `_resolve_voice_key`, CampaignGenerator#247). A critic that uses a narrower rule reports "spec missing" for a file the render actually *used*, then grounds every suggestion in nothing and can never fire the spec-conflict category — the mirror image of the bug #247 fixed in the pipeline.

**Step 1 — build the key set.** Glob `<campaign>/voice/*.md`. **Skip every file whose name begins with `_`**: `_genre.md` and friends are shared campaign material, not a per-character spec. For each remaining file, the key is the lowercased stem with a trailing `_voice` removed — `Brewbarry_voice.md` → `brewbarry`, `vukradin_new_pipeline.md` → `vukradin_new_pipeline`.

**Step 2 — resolve the narrator against that key set, in this order, stopping at the first hit:**

| | Rule | Example |
|---|---|---|
| a | exact full lowercased name | narrator `Unla Key` → key `unla key` |
| b | first name only | `Unla Key` → `unla` |
| c | the **unique** key beginning with the first name followed by `_` or `-` | `Vukradin` → `vukradin_new_pipeline` |

**Step 3 — refuse on ambiguity.** If rule (c) matches two or more keys, this narrator has *no* resolvable spec: do not guess which file the render used. Report it as ambiguous, list the candidates, and treat the spec as missing for grounding purposes.

Rule (c) is the one that matters in practice, and it fires for two distinct reasons:

- **Suffixed filenames.** Phandalin's `voice/` holds `brewbarry_new_pipeline.md`, `soma_new_pipeline.md`, `valphine_new_pipeline.md` and `vukradin_new_pipeline.md` — so a critic checking only `<key>_voice.md` / `<key>.md` reports "spec missing" for **all four** narrators of the campaign the fable benchmark was run on, while Pass 5 had delivered all four specs to the prompt.
- **Multi-word names.** stormgiants stores `Unla Key` as `unla_key.md`. First-name-only lookup asks for `unla` and misses. Note this skill's previous text used `Unla Key → unla` as its *worked example* of correct behaviour — an example that fails on the very campaign it was drawn from.

Campaigns whose files happen to be named `daz.md`, `grygum.md` (out-of-the-abyss) hit rules (a)/(b) and hid this for months.

**Per-character examples use a different rule — do not reuse the voice rule for them.** From `<campaign>/examples/` (`session_doc/sd_narrate.py::_load_examples`, `session_doc/examples.py`):

- Skip `_`-prefixed files.
- A file routes to a narrator when its lowercased stem **equals** their first name, or **starts with** `<first>_` or `<first>-`.
- Several matching files for one character are **concatenated** into that character's block, in sorted order — so check for more than one.
- **Any file matching no character is GLOBAL** — it reached every narrator's prompt. Read those as house style the render was steered toward, never as evidence of *this* character's voice. A sentence that echoes a global example is doing what it was told.
- Lookup is first name, then full lowercased name.

Also load `<campaign>/docs/party.md` — backstory, relationships, class. Note that its roster block can be silently *partial*: the pipeline warns only when no character roster parses at all, so a missing PC section reaches the prompt unannounced (campaigns#144).

If a file does not exist, omit it from the critique inputs. Record what resolved and what did not in the report's resolution table (Phase 4) — a miss must never be silent, because a miss is what makes every downstream suggestion ungrounded.

### Phase 3: Apply the critic lens

**Before the sentence-by-sentence pass, run three mechanical scans and include their findings directly in the flags list:**

**The scans are a floor, not a ceiling.** In the #245 Opus-vs-Fable benchmark every mechanical scan returned **zero** tic hits across all 12 scenes, while reading the same prose found three confirmed instances of the banned behavioral-taxonomy move. A clean scan is not evidence of clean prose. The sentence-by-sentence pass below is what actually catches this family; the scans only buy you the cheap hits.

**Mechanical scan A — em-dashes.** Grep the narration for `—`. Flag every narration-level em-dash for conversion (comma, colon, or period depending on clause relationship). Do NOT flag em-dashes inside `"..."` dialogue or `*...*` italic spans — those are VTT-captured speech disfluencies or truncated lines and must stay verbatim. For each flagged em-dash, give a suggested replacement in the report.

**Mechanical scan B — register-wrong vocabulary.** Grep for words such as: `shape`, `shaped`, `filed`, `geometry`, `geometric`, `aligned`, `configured`, `structure`, `structural`, `axis`, `angle`, `vector`, `plane`, `arc`, `perimeter`, `dimensions`, `calculated`, `formula`. Flag any occurrence in *narration prose* (not inside verbatim dialogue or italic VTT quotes). These are analytical/architectural/mathematical defaults the LLM reaches for when describing arrangement or form; none of the narrators in this party think in those terms. The suggested rewrite should use the narrator's sensory or experiential vocabulary instead.

Also flag the phrase `filed (it|that) away` specifically. `filed` is already in the word list above, but the full phrase is worth calling out as its own reflex: it appeared in three scenes across **both** arms of the #245 benchmark (opus Valphine 02, opus Soma 04, fable Vukradin 03), which makes it a cross-model register default rather than one model's quirk.

**Mechanical scan C — behavioral taxonomy in a rotated shell.** Grep the narration for:

```
\b(in )?the way (he|she|they|men|women|people|\w+)\s+(do|does|say|says|said|get|gets)\b.{0,40}?(\bwhen\b|\bat (that|his|her|their) age\b)
```

The trailing alternation is load-bearing. CG#251 proposed this scan requiring a `when` clause, but the third instance it cites has no `when` in it — it generalises via "at that age" instead — so the `when`-only form catches 2 of the 3 cases the scan exists to catch. Dropping the trailing requirement altogether over-fires instead: it flags "I liked the way she said my name" (one person, specific, fine) and "He fixed it the way Brewbarry does" (a named individual, not a class). Requiring *either* a `when` clause *or* an age appeal catches 3/3 with no false positives on that set.

Flag every match in *narration prose* (not inside verbatim dialogue or italic VTT quotes). This is the `base.md` HARD BANS behavioral-taxonomy family wearing a shell that the older "with the [Adj] [Noun] of someone who…" pattern does not match. The banned move is explaining an observed behaviour by generalising it to a class of people, and it survives renaming — so treat a match as a prompt to check the *move*, and check for unmatched variants by reading too.

The three instances this scan was built from — all found by reading, after every existing scan returned zero:

- "He said *aha*, in the way men say it when they have understood nothing." (opus, scene 02)
- "…everyone looked at me the way they do when they want someone else to decide." (opus, scene 05)
- "The third one said it plain, the way they say things at that age…" (opus, scene 05)

The suggested rewrite names what the POV character actually saw — the hands, the pause, the word they chose — and stops there.

Then read the narration sentence by sentence. **Flag** a sentence when it falls into one of these categories:

1. **Generic fantasy prose** — could appear in any narrator's section. Stock metaphors ("the silence stretched", "his hand fell to his sword", "a chill ran down her spine") with nothing this character would specifically notice or say.
2. **Voice spec conflict** — directly contradicts the spec (uses a verbal tic the spec forbids, an emotional register the character does not have, vocabulary the spec marks as out-of-character).
3. **Convergence with house style** — the sentence sounds like the *narrator persona* of the previous section. (Useful when critiquing a directory: read scenes pairwise and flag rhythm/vocabulary repetitions.)
4. **Tell-not-show emotional commentary** — sentences that name the feeling instead of rendering it ("She felt afraid", "He was angry"). Per-character examples usually show how this writer actually renders feeling; flag when the narration falls back to naming.
5. **Cliché / on-the-nose simile** — workshopped fantasy similes (`like a coiled spring`, `like a tomb`) where the per-character examples show a more specific image vocabulary.
6. **Register-wrong vocabulary** — catches anything the mechanical scan missed: analytical, bureaucratic, or clinical words that no one in this party would reach for. Use judgment; the scan list is a starting point, not an exhaustive inventory.

**Do NOT flag:**

- Verbatim dialogue (lines inside `"..."` quotation marks that came from the source extraction — these are load-bearing and must not be rewritten).
- Action beats that simply describe what happened, even if plain. Plain ≠ generic.
- Prose that already matches the per-character examples — even if it would look generic on its own, matching the writer's established voice is the *goal*.
- Sentences merely because they are short or long. Rhythm variation is intentional.

Flag every genuine issue. Do not drop real problems to keep the list short.

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

## Inputs resolved

| Input | Resolved to | How |
|---|---|---|
| Voice spec | {filename, or **MISSING**, or **AMBIGUOUS: a, b**} | {rule a / b / c, or the key set searched on a miss} |
| Per-char examples | {filename(s), or none} | {matched `<first>_…`, or n/a} |
| Global examples | {filenames, or none} | reached every narrator |
| Party doc | {path, or none} | {roster N/M PCs} |

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
- **Suggested rewrites must be grounded.** Pull rhythm and vocabulary from the voice spec and per-character examples. If the spec is missing, mark the suggestion `[grounded in examples only]` or `[no spec available — best guess]`. **Earn that tag by running Phase 2's full three-rule resolution first** — a whole report tagged `[no spec available]` is far more likely to be a lookup bug than a campaign with no voice files, so check the key set before believing it.
- **Never critique a spec you could not read.** If a spec resolves, the spec-conflict category is live and you are expected to use it; if it does not, say so in the resolution table and drop that category rather than inferring what the spec probably said.
- **No commentary on the critique itself.** Don't write "this scene is generally well-narrated but..." in the verdict's first sentence. State the strongest specific issue and stop.
- **No invented examples.** If the per-character examples are absent, don't fabricate the "right" voice — say what's missing and degrade gracefully.

## Output

Report each file written and the flag count. Surface the strongest recurring issue across scenes (e.g. "three scenes flagged Unla for stock simile usage") so the user knows where to focus their re-narration budget.

Remind the user:
- The report is review-only — they decide which flags to act on.
- For flagged sentences they want to fix, the cheapest path is a manual edit; for systemic voice problems across many scenes, re-running `session_doc.py --scene <N>` with an updated voice file is often more efficient than per-sentence edits.
