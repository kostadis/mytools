---
name: voice-critic
description: Critique a session_doc.py narration for generic prose, voice drift, doc-level budget breaches, or conflicts with the character's voice spec and the campaign's genre rulebook. Use after generating per-scene narration or an assembled fable doc, before assembly or promotion. Invoke as /voice-critic <narration-file-or-dir>.
tools: Read, Glob, Grep, Bash, Write
---

# Voice Critic

Read a generated narration alongside **the same inputs the narrator model was given** — the campaign's genre rulebook, `base.md`'s HARD BANS, the character's voice spec, the per-character examples — and produce a report of sentences that read as generic, drift from the spec, or breach a rule the rulebook states. The report is a **review artifact** — never auto-apply rewrites, never overwrite the narration file.

## What this is for

`sd_narrate` Pass 5 produces first-person narration, one section per scene. Its system prompt is assembled from `config/agents/session_doc/narrate/`: `base.md` (including HARD BANS, stated as *moves* rather than wordings), the campaign's genre rulebook delivered as a delimited `GENRE & REGISTER` block and repeated as a tail reminder, scene scoping plus the anti-restatement length directive, `prose_mode`, the per-character examples, the resolved voice spec, and the previous-narrator contrast. This skill is the human-in-the-loop critique pass over what comes out.

**The reason this skill keeps drifting is worth stating once.** The narration rules are written down in several places, and only some of them reach the model. A critic that carries its own hand-typed copy of the rules is not checking the pipeline — it is checking a fork of the pipeline's intent, and it drifts in both directions: flagging what the prompt no longer says, and missing rules that live only in the rulebook. So the standing instruction is: **read the rules from where the model read them, and delegate the mechanical layer to the checker the repo already ships.** Do not retype a regex or a word list into this file.

The skill is structurally similar to `consistency-check` — same post-hoc, artifact-based, "agent flags / human decides" pattern.

## Input shapes

Declare which one you are in, in the report. They differ in where the narrator name comes from and where the report goes.

| Shape | Input | Narrator from | Report path |
|---|---|---|---|
| **per-scene** | `session_doc_scene_NN_*.{scrubbed.,}md`, or a directory of them | YAML frontmatter | `<narration-dir>/voice_critique_scene_<NN>_<narrator-slug>.md`, plus `voice_critique_summary.md` for a directory |
| **assembled** | one doc split on `## <Char> — <Scene>` — `session-summary-doc.md`, `session-summary-fable-doc.md` | the `##` heading | `<doc-stem>.voice_critique.md`, sections keyed by heading |

`/fable-narration` emits the assembled shape and names this skill as its verification step; it has no frontmatter, no scene numbers and no `narration/` directory, so the per-scene report path cannot be used for it. Assembled is also the shape `voice_lint` assumes.

**The budget ledger (Phase 6) is mandatory in assembled mode** and computed across the whole document. In per-scene mode over a directory it goes in the summary report; a single-scene critique cannot evaluate a doc-level budget and must say so rather than reporting the budgets as met.

## Required information

Detect or ask for:

1. **Narration file(s)** — single file, glob, or directory. For per-scene input, prefer `session_doc_scene_NN_*.scrubbed.md` over the raw `session_doc_scene_NN_*.md` for each scene — the scrubbed files are the canonical pre-assembly source. Fall back to the raw `.md` only when no scrubbed variant exists for that scene. This mirrors `collect_scene_files` in `assemble.py`.
2. **Campaign directory** — root of the campaign workspace (derive from the narration path, or ask).
3. **Genre rulebook** — resolved in Phase 3. Not optional; its absence is a finding.
4. **Voice spec directory** — usually `<campaign>/voice/`. Filenames vary by campaign and are **not** limited to `<narrator>_voice.md`; resolve them with the full rule in Phase 2, which mirrors what Pass 5 actually does.
5. **Per-character examples directory** (optional) — usually `<campaign>/examples/`. Routing is per-character for files whose stem matches a narrator's first name and **global for everything else** — see Phase 2, and note it is a *different* rule from the voice-spec one.
6. **Party doc** (optional) — `<campaign>/docs/party.md` for character relationships and class info.

If invoked with a directory or glob, iterate every scene file. If a referenced voice spec is missing, fall back to the per-character examples; if both are missing, skip that scene with a one-line note rather than fabricating a critique.

## Phase 1: Parse the narration

Per-scene narration files written with `--per-scene-output` start with YAML frontmatter:

```yaml
---
scene: 06
slug: <slug>
narrator: <name>
scene_name: <human-readable scene name>
session: <session id>
---
```

Pull `narrator` and `scene_name` from it. In assembled input there is no frontmatter: treat each `## <Name> — <Scene>` block as a separate critique target and take the narrator from the heading.

When collecting per-scene files from a directory, deduplicate by scene number: for each scene, use the `.scrubbed.md` variant if it exists, otherwise the raw `.md`.

**Separate prose from non-prose before any counting.** Every scan and every budget below is over *narration prose only*. Strip, and never flag inside:

- `"…"` verbatim dialogue — VTT-captured speech, load-bearing, must stay exactly as extracted.
- `*…*` italic spans — direct thought and truncated VTT lines.
- `<!-- … -->` HTML comments — including the table-speech hatch, which Phase 7 handles separately.

## Phase 2: Resolve the voice context

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

If a file does not exist, omit it from the critique inputs. Record what resolved and what did not in the report's resolution table — a miss must never be silent, because a miss is what makes every downstream suggestion ungrounded.

## Phase 3: Load the effective rulebook

**This is the phase that makes the critique a check on the pipeline rather than on a fork of it.** Two documents reach the narrator and state rules; read both, and report what you read with sizes so a reader can tell whether the check was grounded.

### 3a. The genre rulebook — from the run record first, config second

The rulebook is a **file**, addressed by `paths.genre_file` in `<campaign>/config/session_doc.yaml`, conventionally `<campaign>/voice/_genre.md` (CampaignGenerator #276). It is not a string in the config, and it is not the profile knob. If you find a `narrate.genre` key, it is a retired paste that the config loader strips and **the model never saw it** — do not read it as the rulebook, and say it is there.

Resolve in this order:

1. **The per-scene run record**, `<narration-dir>/<scene-stem>.knobs.json`. This is what that render actually used, and it beats config, which may have changed since. Two shapes exist:
   - **Post-#276:** `narration_genre_file`, `narration_genre_sha`, `narration_genre_lines`. Read the named file and compare its current digest to `narration_genre_sha`. **A mismatch means the rulebook was edited after this scene rendered** — say so, because it changes what the findings mean, and check whether sibling scenes in the same directory carry different digests from each other.
   - **Pre-#276:** `narration_genre` holding the rulebook's *text*. Note its length and newline count. **Zero newlines in a multi-thousand-character value means this render received the rulebook as a single-line `GENRE:` label** rather than a delimited block — it was delivered, but not in a form the model could follow. Measured consequence: on Phandalin, "first-person present tense, always" reached the model this way and 3 of 62 rendered scenes are in the required tense. When you see this, register findings about tense and register as *probably delivery, not authorship*, and say so in the verdict.
2. **`paths.genre_file` in `<campaign>/config/session_doc.yaml`**, resolved relative to the campaign directory. Use this when there is no run record, and always report it alongside the run record so a divergence between "what this render used" and "what the next render will use" is visible.

**Three states, and two of them are findings:**

| State | What it means | What to do |
|---|---|---|
| resolved | `paths.genre_file` set, file present | read it; budgets and rules come from here |
| **unset** | no `paths.genre_file` | **Pass 5 received no genre directive at all.** Check whether `<campaign>/voice/_genre.md` exists: if it does, this campaign has a rulebook and is not pointing at it — an unrun migration, `python -m server.migrate_narrate_genre --campaign-dir <DIR>`. Report it as the report's first line. |
| **missing** | path set, file absent | same consequence — no genre directive, no register rules, no banned-tic list, no caps. There is no YAML fallback behind it. |

In the unset and missing states, **do not fall back to reading `voice/_genre.md` as if the model had seen it.** Read it if it exists, clearly labelled as *the rulebook the model did not receive*, and use it only to explain the findings — every register finding in such a report is expected, and the fix is the migration, not a rewrite.

### 3b. `base.md` — the HARD BANS

Read `config/agents/session_doc/narrate/base.md` from the CampaignGenerator checkout (`~/src/CampaignGenerator` unless the campaign says otherwise). Its HARD BANS section is the campaign-independent half of the rules, and it is explicit that the bans are **moves, not wordings**: behavioral taxonomy in any shell, and recap framing. Take the ban list from the file at read time; do not summarise it here, because a summary is the copy this phase exists to remove.

### 3c. Derive the checks from what you read — never from this file

The rulebook is prose written for a human, so read it and extract, for this campaign:

- **What it says about em-dashes.** This matters and is the standing example of the fork. Phandalin's rulebook says the em-dash is for *interrupted speech or interrupted thought* and **never as a connective** — so the check is "flag connective em-dashes", not "flag every em-dash". A previous version of this skill flagged all of them, which on a scene that correctly used 17 interruption dashes would have produced 17 findings the rulebook permits. Out-of-the-abyss' rulebook states only the permission and not the prohibition, so there the honest report is that the rule does not distinguish, and connective use is a *note*, not a flag.
- **Register-wrong vocabulary.** Which words this campaign's narrators would not reach for. Analytical, architectural, mathematical and bureaucratic defaults are the usual family. Take the specifics from the rulebook and the voice specs; where the rulebook names banned constructions verbatim ("the shape of X", "the cusp of something", "what could only be described as X"), those are exact.
- **Doc-level budgets** — see Phase 6.
- **Per-narrator registers** — bookkeeping verbs, stock phrases, what each POV is and is not licensed to do.
- **Content protections** that read as style but are not, e.g. out-of-the-abyss' "never sanitize the escapee names" and "do not invent sky". A paraphrase of `Leemoogoogoon` as "the Sea Mother's rival" is a rulebook breach, not a style preference.

If the rulebook says nothing about a category, **the category is not checked** — report it as not-applicable in the ledger rather than falling back to a default. A rule this skill invents is a rule the model was never given.

## Phase 4: Run the mechanical layer

**Delegate, do not retype.** The repo ships `voice_lint` as a console script for exactly this. Run it and fold its output into the flag list verbatim:

```bash
voice_lint <narration-files> --genre-file <resolved genre_file from Phase 3>
```

It checks the doc-level banned constructions (`the shape of`, the `with the X of a man who` portrait, and the behavioral-taxonomy move after it rotates into `the way X do … when …`) and the campaign's bookkeeping/filing rules, which it reads from a fenced `yaml voice_lint` block inside the rulebook.

Its output has three streams and they mean different things:

- `ERROR` — a hard breach. Include as a flag.
- `warn` — at or approaching a cap. Include as a flag.
- `note` — **a check that did not run.** Most often `[skipped] bookkeeping/filing checks — this campaign's rulebook declares no voice_lint bookkeeping block`. Surface it in the ledger as *not checked*. It is not a pass, and reporting it as one is the exact defect this delegation fixes: those rules used to be hardcoded to out-of-the-abyss' four narrators, so three other campaigns got a clean bill from a check that never ran.

`voice_lint` has no equivalent for two scans, so run them yourself, with the *rulebook-derived* rule from Phase 3c:

**Scan A — em-dashes**, against what the rulebook actually says (see 3c). Report the total count and the flagged subset separately; they are usually not the same number. For each flagged one, give a suggested replacement (comma, colon, or period depending on clause relationship).

**Scan B — register-wrong vocabulary**, using the vocabulary the rulebook and the voice specs establish for this campaign. The suggested rewrite should use the narrator's sensory or experiential vocabulary instead.

**The scans are a floor, not a ceiling.** In the #245 Opus-vs-Fable benchmark every mechanical scan returned **zero** tic hits across all 12 scenes, while reading the same prose found three confirmed instances of the banned behavioral-taxonomy move. A clean scan is not evidence of clean prose. The reading pass below is what actually catches this family; the scans only buy you the cheap hits — and under fable they buy less, because fable flags at roughly half opus's rate (≈1.1 vs ≈2.4 per 1000 words on matched corpora; the numbers are owned by `Issue245Followups_handoff.md`, not re-derived here).

## Phase 5: Read the narration

Then read the prose sentence by sentence. **Flag** a sentence when it falls into one of these categories:

1. **Generic fantasy prose** — could appear in any narrator's section. Stock metaphors ("the silence stretched", "his hand fell to his sword", "a chill ran down her spine") with nothing this character would specifically notice or say.
2. **Voice spec conflict** — directly contradicts the spec (a verbal tic the spec forbids, an emotional register the character does not have, vocabulary the spec marks as out-of-character). Live only when the spec resolved.
3. **Rulebook conflict** — breaches something the genre document states: a banned construction, a protected name sanitized, a register rule broken, tense or POV wrong. Live only when the rulebook resolved.
4. **Convergence with another narrator** — the sentence sounds like the *narrator persona* of another section. Read sections pairwise and flag rhythm and vocabulary repetitions.
5. **Tell-not-show emotional commentary** — naming the feeling instead of rendering it ("She felt afraid"). Per-character examples usually show how this writer renders feeling; flag when the narration falls back to naming.
6. **Cliché / on-the-nose simile** — workshopped fantasy similes (`like a coiled spring`, `like a tomb`) where the examples show a more specific image vocabulary.
7. **Register-wrong vocabulary** — anything scan B missed. Judgment, not a word list.

**Fable's recurring profile.** These four are the model-default failure modes under the current default narrator, enumerated in `/fable-narration`, and they are first-class categories rather than opus-era anecdote: **em-dash overuse** (as a connective, per 3c), **bookkeeping-noun repetition** past the per-section cap, **cross-narrator register bleed**, and the **portable tics** — a construction that would fit any of the four narrators equally well is, for that reason, wrong for all of them. Check these explicitly even when the scans return zero.

**Do NOT flag:**

- Verbatim dialogue inside `"…"` — load-bearing, must not be rewritten.
- Prose inside a `<!-- table-speech reclassified: … -->` hatch — Phase 7 handles it.
- Action beats that simply describe what happened, even if plain. Plain ≠ generic.
- Prose that already matches the per-character examples — even if it would look generic on its own, matching the writer's established voice is the *goal*. The same goes for prose that echoes a *global* example: it is obeying instructions.
- Sentences merely because they are short or long. Rhythm variation is intentional.

Flag every genuine issue, and no more. **There is no minimum.** Zero flags on a scene is a legitimate and valuable result, especially under fable; a floor invites invention, and an invented flag costs more than a missed one because the GM has to verify it.

## Phase 6: Build the budget ledger

The fable-era rules are **doc-level budgets**, not per-sentence prohibitions: *more than one "the shape of X" across the entire doc means the pass failed*; *more than two of four sections containing "filed" is the convergence bug*; *at most one bookkeeping metaphor per section*; *1–2 load-bearing narration em-dashes in the whole doc*. A per-scene critique can evaluate none of them, and a flag count is not a budget check — a document can breach every cap without any single sentence reading badly. **That is the entire point of a cap**, so a breach is a finding in its own right.

Every budget comes from Phase 3's rulebook or from `voice_lint`'s output. Do not carry a default here.

```markdown
## Budget ledger

Scope: {whole document | scenes NN–NN | single scene — doc-level budgets NOT evaluable}
Budgets from: {genre_file path} @ {digest}

| Budget | Observed | Budget | Verdict |
|---|---|---|---|
| "the shape of" | 0 | ≤1 doc-wide | ok |
| portable portrait ("with the X of a man who") | 0 | ≤1 doc-wide | ok |
| behavioral taxonomy | 1 | 0 | **BREACH** |
| "I file/filed" — sections containing | 3 of 4 | ≤2 | **BREACH** |
| "I file/filed" — Grygum, per section | 2 | ≤1 | **BREACH** |
| connective em-dashes | 8 | rulebook: never | **BREACH** |
| bookkeeping caps | — | — | *not checked — rulebook declares none* |
```

Three verdict values only: `ok`, `**BREACH**`, and `*not checked*` with the reason. Never write `ok` for a row nothing evaluated.

## Phase 7: Write the report

Report path per the input shape (see **Input shapes**). Structure:

```markdown
# Voice Critique — {narrator}, scene {NN}: {scene_name}

**Narration:** {path}
**Input shape:** {per-scene | assembled}

## Inputs resolved

| Input | Resolved to | How |
|---|---|---|
| Genre rulebook | {path @ digest, or **UNSET — no genre reached Pass 5**, or **MISSING**} | {run record / config; lines, chars} |
| Rulebook vs run record | {match, or **edited since this render**, or **pre-#276: flattened, N chars / 0 newlines**} | {sha comparison} |
| HARD BANS | {base.md path} | {chars} |
| Voice spec | {filename, or **MISSING**, or **AMBIGUOUS: a, b**} | {rule a / b / c, or the key set searched on a miss} |
| Per-char examples | {filename(s), or none} | {matched `<first>_…`, or n/a} |
| Global examples | {filenames, or none} | reached every narrator |
| Party doc | {path, or none} | {roster N/M PCs} |
| voice_lint | {ran / not available} | {N errors, N warns, N skipped checks} |

## Budget ledger

{Phase 6}

## Flags

### [1] {category}

> {sentence verbatim from the narration — quote exactly}

**Why:** {one sentence on what makes this off-voice, naming the rule and where it is stated}
**Suggested rewrite:** {one alternative in this character's voice, drawn from spec/examples patterns}

## Reclassified table speech

{One entry per `<!-- table-speech reclassified: … -->` hatch found, with the before/after
quoted. Empty section with "none" when there are none — its absence should not be ambiguous.}

## Verdict

{1–2 sentences: the strongest specific issue, whether the scene is worth re-narrating or
spot-editing, and — when Phase 3 found unset/missing/flattened — that the findings are
explained by a rulebook that did not reach the model.}
```

**The reclassified-table-speech section is not optional.** `sd_narrate` writes `<!-- table-speech reclassified: … -->` into per-scene files when it judges a span to be out-of-fiction table talk rather than in-character speech, and `assemble.py` strips the comment at assembly — **so the per-scene files this skill reads are exactly where it survives, and this is the last chance to review it.** Each one is the model making a scope call about what is in-fiction, which is a human's decision by this repo's doctrine. List every occurrence for the GM to accept or reject; never flag the prose inside one as a style problem.

## Hard rules

- **Never modify the narration file during the critique pass.** The report is a separate artifact. When the user subsequently applies fixes, they belong in the `.scrubbed.md` file (not the raw `.md`) so `assemble.py` picks them up.
- **Never auto-apply rewrites.** Suggestions are exactly that.
- **Never retype a rule into this file.** Regexes come from `voice_lint`, bans come from `base.md`, register rules and budgets come from the campaign's rulebook. If a check needs a pattern this skill does not have, add it to `voice_lint` — do not paste it here. A second copy diverges at the next tic.
- **A check that did not run is never a pass.** `voice_lint` notes, an unresolved rulebook, an unresolved spec: each drops its category and says so. "No findings" and "not checked" are different report lines.
- **Quote verbatim.** Paste the flagged sentence exactly from the narration. The user will search for it; an approximate quote wastes their time.
- **Suggested rewrites must be grounded.** Pull rhythm and vocabulary from the voice spec and examples. If the spec is missing, mark the suggestion `[grounded in examples only]` or `[no spec available — best guess]`. **Earn that tag by running Phase 2's full three-rule resolution first** — a whole report tagged `[no spec available]` is far more likely to be a lookup bug than a campaign with no voice files.
- **Never critique a spec or a rule you could not read.** If it resolves, the category is live and you are expected to use it; if it does not, say so in the resolution table and drop the category rather than inferring what it probably said.
- **No commentary on the critique itself.** Don't open the verdict with "this scene is generally well-narrated but…". State the strongest specific issue and stop.
- **No invented examples.** If the per-character examples are absent, don't fabricate the "right" voice — say what's missing and degrade gracefully.

## Output

Report each file written, the flag count, and the ledger verdict summary. Surface the strongest recurring issue across scenes (e.g. "three scenes flagged Unla for stock simile usage") so the user knows where to focus their re-narration budget.

**Lead with a rulebook problem when there is one.** If Phase 3 found the rulebook unset, missing, or flattened, that is the headline and every register finding below it is downstream of it — the fix is the migration or the re-render, not a round of sentence edits.

Remind the user:

- The report is review-only — they decide which flags to act on.
- For flagged sentences they want to fix, the cheapest path is a manual edit; for systemic voice problems across many scenes, re-running `sd_narrate --scene <N>` with an updated voice file or rulebook is often more efficient than per-sentence edits.
- Budget breaches usually cannot be spot-edited into compliance — a doc-wide cap breach is a re-render signal.
