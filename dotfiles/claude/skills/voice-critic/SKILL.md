---
name: voice-critic
description: Critique a session_doc.py narration for generic prose, voice drift, doc-level budget breaches, or conflicts with the character's voice spec and the campaign's genre rulebook. Use after generating per-scene narration or an assembled fable doc, before assembly or promotion. Invoke as /voice-critic <narration-file-or-dir>.
tools: Read, Glob, Grep, Bash, Write, Artifact, WebFetch
---

# Voice Critic

Read a generated narration alongside **the same inputs the narrator model was given** — the campaign's genre rulebook, `base.md`'s HARD BANS, the character's voice spec, the per-character examples — and produce a report of sentences that read as generic, drift from the spec, or breach a rule the rulebook states. The report is a **review artifact** — never apply a rewrite the GM has not approved, and never overwrite the narration you reviewed: approved fixes go into a separate derived revision (Phase 9).

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
| **approved revision** | a `/dialogue-edit` `applied/<revision>/scene.md` (or an earlier voice-critic revision, Phase 9) | the original scene's frontmatter / the revision's source record | `<session>/voice_critic/<run>/`, with the selected revision paths recorded; the frozen dialogue-edit records are left intact |

`/fable-narration` emits the assembled shape and names this skill as its verification step; it has no frontmatter, no scene numbers and no `narration/` directory, so the per-scene report path cannot be used for it. Assembled is also the shape `voice_lint` assumes.

**The budget ledger (Phase 6) is mandatory in assembled mode** and computed across the whole document. In per-scene mode over a directory it goes in the summary report; a single-scene critique cannot evaluate a doc-level budget and must say so rather than reporting the budgets as met.

## Required information

Detect or ask for:

1. **Narration file(s)** — single file, glob, or directory. **Critique the latest approved revision of each scene, never an unapproved candidate** — see *Which text to critique* below. With no approved revision, prefer `session_doc_scene_NN_*.scrubbed.md` over the raw `session_doc_scene_NN_*.md` for each scene — the scrubbed files are the canonical pre-assembly source. Fall back to the raw `.md` only when no scrubbed variant exists for that scene. This mirrors `collect_scene_files` in `assemble.py`.
2. **Campaign directory** — root of the campaign workspace (derive from the narration path, or ask).
3. **Genre rulebook** — resolved in Phase 3. Not optional; its absence is a finding.
4. **Voice spec directory** — usually `<campaign>/voice/`. Filenames vary by campaign and are **not** limited to `<narrator>_voice.md`; resolve them with the full rule in Phase 2, which mirrors what Pass 5 actually does.
5. **Per-character examples directory** (optional) — usually `<campaign>/examples/`. Routing is per-character for files whose stem matches a narrator's first name and **global for everything else** — see Phase 2, and note it is a *different* rule from the voice-spec one.
6. **Party doc** (optional) — `<campaign>/docs/party.md` for character relationships and class info.

If invoked with a directory or glob, iterate every scene file. If a referenced voice spec is missing, fall back to the per-character examples; if both are missing, **skip only the voice-drift judgment for that narrator** — Phase 5 category 2 (voice spec conflict) needs a voice to measure against, and fabricating one is worse than saying so. Every other check still runs on that narrator's prose: the rulebook, the HARD BANS, the em-dash budget, Scan A2 provenance, Scan C orphan quotes, the budget ledger and the hatch review do not depend on a voice spec. The report says, in the resolution table and the verdict, that voice drift was **not judged** for that narrator and why.

### Which text to critique — `/dialogue-edit` runs first

`/dialogue-edit` sits directly before this skill and writes its approved wording to a **separate revision** (`<session>/dialogue_edit/<scene-run>/applied/<revision>/scene.md`), leaving the raw and scrubbed scenes untouched. A directory scan of the narration folder therefore picks up the pre-edit text and critiques the wrong version. Before collecting any files:

- **Read `<session>/dialogue_edit.sources.yaml`** if it exists, with the application records it points at, their promotion status and hashes. A revision is approved only when its `application.json` exists (the helper writes it last) and its `scene.md` still matches the recorded result hash. **Never critique `candidate.md`** — it holds every proposal, approved or not.
- **The latest approved revision wins over the directory scan**, and an approved revision the GM names explicitly wins over both. "Latest" comes from the session index and the application records, never from modification time; when two approved revisions of one scene conflict, ask the GM rather than picking one. A voice-critic revision from an earlier run (Phase 9) counts as the latest approved text for its scene when it was derived from that same approved base.
- For a promoted revision, verify the current narration file against the promotion record rather than assuming it.
- Keep the original scene identity and source mapping even though the revision file is called `scene.md`: narrator, scene number and run record come from the original scene the manifest names.
- **Say which file was critiqued**, per scene, in the report and in your reply — the revision path, or the scrubbed/raw scene when no approved revision exists. Reports for a revision go under `<session>/voice_critic/<run>/`; never write into the frozen dialogue-edit run.

GM-approved dialogue-edit rewrites are **protected edited speech**, not verbatim transcript: they get the same don't-rewrite protection as any quote (Phase 1), and they are not "corrected" back to the extraction.

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

When collecting per-scene files from a directory, deduplicate by scene number: for each scene, use its latest approved revision if one exists (see *Which text to critique*), else the `.scrubbed.md` variant if it exists, otherwise the raw `.md`.

**Separate prose from non-prose before any counting.** Every scan and every budget below is over *narration prose only*. Strip, and never flag inside:

- `"…"` verbatim dialogue — VTT-captured speech, load-bearing, must stay exactly as extracted (or exactly as `/dialogue-edit` approved it).
- `*…*` italic spans — direct thought and truncated VTT lines.
- `<!-- … -->` HTML comments — including the table-speech hatch, which Phase 7 handles separately.

## Phase 2: Resolve the voice context

**Resolve the voice spec exactly the way Pass 5 resolves it — which since feature 009 means reading a declaration, not computing a match.** The rule lives in `session_doc/voice.py` and `session_doc/examples.py`. **Read them at the start of every run.** They have changed once already and the change inverted this phase; a critic working from a remembered rule checks a fork of the pipeline rather than the pipeline.

### The current rule: declared, not matched

The roster names each character's files. Find it from `paths.party` in `<campaign>/config/session_doc.yaml` — conventionally `config/party.yaml`:

```yaml
characters:
- name: Brewbarry
  voice: voice/brewbarry_new_pipeline.md
  examples: examples/brewbarry.md
shared_examples: []          # optional; the only route to a global block
```

- **Voice:** `load_declared_voices` reads the declared path; `get_voice_note` then matches the narrator name **exactly**, case- and whitespace-insensitively. No first name, no prefix, no similarity. A narrator missing from the roster has no spec, and `sd_narrate` refuses to start rather than rendering without one (#300).
- **Examples:** `load_declared_examples` is the same shape. **A file that nothing declares is unused, not shared.** The only global block is `shared_examples:`, and it exists because a human wrote it down.
- **Orphans:** a file in `voice/` or `examples/` that no roster entry names reaches no prompt. Report it — that is what a rename produces.

### Why the old rule is gone, and why that matters to *you*

The previous rule was three steps: exact name, else first name, else the unique key beginning with the first name plus `_` or `-`. It was deleted as a similarity-based identity assertion — the thing `provenance/identity.py` forbids everywhere else in the codebase — after a character renamed `Grygum` → `Gyrgum` resolved to nothing and every render since went out with no register rules for that narrator (#175, #247). The examples fall-through went with it: a file matching no character used to join a GLOBAL block passed to **every** narrator, which is how one character's style reference silently steered all of them (#301, largest observed 51,073 characters).

**Two consequences for this skill.** First, `[no spec available]` is now almost always a lookup bug on your side, because the render would have refused to start. Second, this section is a description of someone else's code and will go stale again — so **when the source and this file disagree, the source wins and you fix this file.** That has already happened once: the text you are reading replaced a three-rule table that was still being followed months after the pipeline stopped using it.

Also load `<campaign>/docs/party.md` — backstory, relationships, class. It is prose, not the roster, and carries no `voice:` declarations; do not mistake it for `party.yaml`. Note that its roster block can be silently *partial*: the pipeline warns only when no character roster parses at all, so a missing PC section reaches the prompt unannounced (campaigns#144).

If a file does not exist, omit it from the critique inputs. Record what resolved and what did not in the report's resolution table — a miss must never be silent, because a miss is what makes every downstream suggestion ungrounded.

## Phase 3: Load the effective rulebook

**This is the phase that makes the critique a check on the pipeline rather than on a fork of it.** Two documents reach the narrator and state rules; read both, and report what you read with sizes so a reader can tell whether the check was grounded.

### 3a. The genre rulebook — from the run record first, config second

The rulebook is a **file**, addressed by `paths.genre_file` in `<campaign>/config/session_doc.yaml`, conventionally `<campaign>/voice/_genre.md` (CampaignGenerator #276). It is not a string in the config, and it is not the profile knob. If you find a `narrate.genre` key, it is a retired paste that the config loader strips and **the model never saw it** — do not read it as the rulebook, and say it is there.

Resolve in this order:

1. **The per-scene run record**, `<narration-dir>/<scene-stem>.knobs.json`. This is what that render actually used, and it beats config, which may have changed since. Two shapes exist:
   - **Post-#276:** `narration_genre_file`, `narration_genre_sha`, `narration_genre_lines`. Read the named file and compare its current digest to `narration_genre_sha`. **A mismatch means the rulebook was edited after this scene rendered** — say so, because it changes what the findings mean, and check whether sibling scenes in the same directory carry different digests from each other.
   - **Pre-#276:** `narration_genre` holding the rulebook's *text*. Note its length and newline count. **Zero newlines in a multi-thousand-character value means this render received the rulebook as a single-line `GENRE:` label** rather than a delimited block — it was delivered, but not in a form the model could follow. Measured consequence: on Phandalin, "first-person present tense, always" reached the model this way and 3 of 62 rendered scenes are in the required tense. When you see this, register findings about tense and register as *probably delivery, not authorship*, and say so in the verdict: the flattened rulebook is the **probable cause** of the generic and register-wrong prose it would have governed. Use that wording only when the evidence shows the flattening (the length and zero-newline measurement above); without it, a pre-#276 record is delivery uncertainty, not a cause.
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
- `note` — **a check that did not run.** Every one starts `[skipped]` or `[config]`. Surface it in the ledger as *not checked*. It is not a pass, and reporting it as one is the exact defect this delegation fixes: those rules used to be hardcoded to out-of-the-abyss' four narrators, so three other campaigns got a clean bill from a check that never ran.

**Read the skip's reason, do not assume it.** A `[skipped]` note names one of five causes, and they are not interchangeable: no rulebook was asked for, the file is not there, it has no `yaml voice_lint` block, the block declares no `bookkeeping` section, or that section did not parse. Only the third and fourth mean *this campaign has no filing register*. The others mean the rulebook did not arrive, which is a finding about the run, not about the campaign — report it as one.

**Exit codes.** `1` means a hard ERROR fired. `2` means the `--genre-file` path could not be read: the invocation is wrong, so fix the path and run again rather than reporting the critique. `0` with `[skipped]` notes is still an incomplete pass, not a clean one.

`voice_lint` has no equivalent for two scans, so run them yourself, with the *rulebook-derived* rule from Phase 3c:

**Scan A — em-dashes**, against what the rulebook actually says (see 3c). Report the total count and the flagged subset separately; they are usually not the same number. For each flagged one, give a suggested replacement (comma, colon, or period depending on clause relationship).

**Scan A2 — trailing em-dash PROVENANCE, at the end of a verbatim quote.** This is a different question from Scan A and it is the one the "do NOT flag verbatim dialogue" rule below will hide from you, so run it deliberately.

A quote ending `—"` is not decoration: it **asserts that the speaker was interrupted**. That assertion can be false, and when it is false the narrator did not invent it — an upstream layer did. Phandalin ch48 is the measured case. `session_doc.yaml`'s `scene_extractions_dir` pointed at `scene_extractions_smoothed/`, and the smoothing pass had rewritten the verbatim layer wholesale:

| | raw `scene_extractions/` | smoothed (what the narrator read) |
|---|---|---|
| `*(truncated)*` markers | 57 | 1 |
| quote endings `—"` | **0** | **59**, across all 8 scenes |

Most of that is genuine repair — it merges artificially split VTT cues into whole sentences, which is why zero `(truncated)` markers reach the narration. But it renders **every** residual trail-off as an interruption. 41 reached the narration; 40 were legitimate interruptions (`"Or my—"`, `"It's just an—"`, `"Disguise self as—"`) and one was a speaker trailing off with nobody speaking over her.

Why the reading pass cannot catch this: every one of the 41 sits inside `"…"`, so the Phase 5 rule correctly skips them all. The critique reports the scene clean and the false assertion ships.

Run it as a diff, not a judgment:

```bash
for d in scene_extractions scene_extractions_smoothed; do \
  echo "$d: $(grep -rhc '—"$' $d/0*.md | paste -sd+ | bc)"; done
```

**A nonzero delta is the finding.** Then adjudicate only the deltas, against the tape — a trailing em-dash is *correct* when someone speaks over them and *wrong* when they trail off. Both transcripts having a full stop, plus no overlapping speaker in the next cues, means trail-off. Prefer the raw extraction's punctuation, which is the pre-smoothing capture.

Two riders, both learned the hard way on that run:

- **Position makes a trail-off load-bearing.** A campaign may carry a standing "repair only load-bearing truncations" ruling, which normally leaves table trail-offs alone — correctly, they are an accurate record of how people talk. But a truncation that is the **scene's or the document's final line** is load-bearing by position: the chapter ends mid-sentence. That was the one wrong dash of the 41.
- **Removing the dash can strand the attribution verb.** `"…yourself—" Soma starts.` parses only while the dash marks her as cut off. Swap to a period and `starts` dangles. Check the attribution clause in the same edit, and flag that second change separately — it alters narrator prose, not punctuation.

**Scan B — register-wrong vocabulary**, using the vocabulary the rulebook and the voice specs establish for this campaign. The suggested rewrite should use the narrator's sensory or experiential vocabulary instead.

**Scan C — orphan quote runs (unattributed dialogue).** A run of three or more consecutive quote-only paragraphs with no attribution and no action beat between them. This is the *narration* failing, not the dialogue: the quotes are verbatim and correct, but the reader cannot tell who is speaking, and past two speakers strict alternation stops carrying the load. Phandalin ch2 scene 04 is the measured case — twelve such runs, one of them nine lines long, where the GM's report was simply that the dialogue was "incomprehensible."

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

**A hit is a candidate, not yet a finding.** Two shapes are legitimate and must be cleared rather than flagged:

- **A tagged two-hander.** Two speakers, an attributed opening line, then strict alternation. `"Tea? Just tea?" / "Just tea." / "You want me to boil water and give it to you?"` is unambiguous and tags would clutter it.
- **A deliberate chorus** — overlapping table voices the narrator is rendering *as* a wash, where not knowing who said what is the effect.

Everything else is a real finding, and the fix is cheap and non-destructive: **the attribution already exists upstream.** `scene_extractions_smoothed/NN_*.md` labels every quote with its speaker, including the `re-attributed from **GM** upstream` corrections. Anchor the quotes with speaker tags; **never touch a word inside them.** An action beat may be added only when the extraction or the transcript records that action — cite the line in the finding's evidence. Where neither records one, anchor with attribution alone (`Soma says.`); an invented action is invented fiction, however small. Where the smoothed layer says `UNKNOWN` or `unconfirmed`, leave that line untagged and say so in the report — an invented attribution is worse than an orphan quote.

Two things this scan will surface that are *not* its own business: table-speak inside a quote (`"With a four, you probably believe him."`) belongs to `/scrub`, and a wrong speaker label belongs to `/session-summary-consistency`. Report them, hand them off, do not fix them here.

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
8. **Unattributed dialogue** — anything Scan C missed, and the sub-threshold cases it cannot see: a two-line exchange where the second speaker is genuinely ambiguous, or a run that alternates between *three* speakers so alternation no longer identifies anyone. Flag the run, not each line, and name the speakers the smoothed extraction assigns.

**Fable's recurring profile.** These four are the model-default failure modes under the current default narrator, enumerated in `/fable-narration`, and they are first-class categories rather than opus-era anecdote: **em-dash overuse** (as a connective, per 3c), **bookkeeping-noun repetition** past the per-section cap, **cross-narrator register bleed**, and the **portable tics** — a construction that would fit any of the four narrators equally well is, for that reason, wrong for all of them. Check these explicitly even when the scans return zero.

**Do NOT flag:**

- Verbatim dialogue inside `"…"` — load-bearing, must not be rewritten. **One exception, and it is not a style flag:** a quote *ending* `—"` asserts an interruption, and that assertion is inherited from the extraction layer rather than authored by the narrator. It is checked by provenance diff in Scan A2, not by reading.
- Prose inside a `<!-- table-speech reclassified: … -->` hatch — Phase 7 handles it.
- Action beats that simply describe what happened, even if plain. Plain ≠ generic.
- Prose that already matches the per-character examples — even if it would look generic on its own, matching the writer's established voice is the *goal*. The same goes for prose that echoes a *global* example: it is obeying instructions.
- Sentences merely because they are short or long. Rhythm variation is intentional.

**Locked-dialogue anachronisms are notes, not flags — and they carry three dispositions.** A real-world reference inside a verbatim quote ("He's dead, Jim", "Scooby-Doo style") is player speech the critique must not rewrite, but it is also exactly the residue class that compounds into future renders, so surface every one as a GM scope call with the three standard dispositions: **keep** (a licensed player joke — check whether the narration already launders it, e.g. "I do not know Jim. Dead is dead."), **replace in-world** (an authorial rewrite of player speech — say so), or **annotate** with the campaign's sage's-marginal-note convention — an italic `*Marginal note in a later hand: "<term>" — <in-world explanation>. — <sage persona>*` paragraph placed after the beat, signed by the campaign's established scholar (Phandalin: **Kostadinious the Sage**). The full device rules — persona, canon logging (`provenance: on_the_fly`), tape-divergence recording, one-note-per-doc restraint — live in the scrub skill's anachronism section; do not restate them here, read them there. Precedent: Jimble the Unmoved, Phandalin ch3 scene 07, GM-approved 2026-08-18. An existing marginal note in a scene is apparatus, not narration — never flag its register against the narrator's voice.

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

**For every BREACH row, say where the instances sit** — per scene, per narrator — because the remedy is decided by distribution and cost, not by the fact of a breach:

- **Clustered** in one or a few scenes → spot-fix those instances (ranked, with a target count — see Hard rules), or re-narrate just those scenes (`sd_narrate --scene <N>`).
- **Spread throughout** the document, so that no set of scene-level edits gets it under the cap → a whole-document re-render is the recommendation. That is a paid run: recommend it only in this case, and only the GM's explicit yes starts it. This skill never starts it.

A breach is never a re-render signal on its own.

## Phase 7: Write the report

Report path per the input shape (see **Input shapes**). Structure:

```markdown
# Voice Critique — {narrator}, scene {NN}: {scene_name}

**Critiqued file:** {path actually read — the approved dialogue-edit / voice-critic revision, or the scrubbed/raw scene when none exists}
**Input shape:** {per-scene | assembled | approved revision}

## Inputs resolved

| Input | Resolved to | How |
|---|---|---|
| Genre rulebook | {path @ digest, or **UNSET — no genre reached Pass 5**, or **MISSING**} | {run record / config; lines, chars} |
| Rulebook vs run record | {match, or **edited since this render**, or **pre-#276: flattened, N chars / 0 newlines**} | {sha comparison} |
| HARD BANS | {base.md path} | {chars} |
| Voice spec | {filename, or **MISSING — voice drift not judged for this narrator**} | {the roster declaration it came from, or the roster searched on a miss} |
| Per-char examples | {filename(s), or none} | {the roster `examples:` declaration, or n/a} |
| Shared examples | {filenames from `shared_examples:`, or none} | reached every narrator |
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

{1–2 sentences: the strongest specific issue, the remedy its distribution supports (spot
edits, or re-narrating the scenes the breaches cluster in; a whole-document re-render only
when they are spread throughout, and only on the GM's yes), and — when Phase 3 found
unset/missing/flattened — that the findings are explained by a rulebook that did not reach
the model (flattened: its probable cause). Name any narrator whose voice drift was not judged.}
```

**The reclassified-table-speech section is not optional.** `sd_narrate` writes `<!-- table-speech reclassified: … -->` into per-scene files when it judges a span to be out-of-fiction table talk rather than in-character speech, and `assemble.py` strips the comment at assembly — **so the per-scene files this skill reads are exactly where it survives, and this is the last chance to review it.** Each one is the model making a scope call about what is in-fiction, which is a human's decision by this repo's doctrine. List every occurrence for the GM to accept or reject; never flag the prose inside one as a style problem.

## Phase 8: Publish the review page

**Publish by default, once the reports are written.** The `.md` reports stay the record; the page is the surface the GM actually rules on. A multi-scene critique is a triage exercise — a dozen findings at three severities across eight scenes, each needing its own decision — and that does not survive terminal scrollback. **If the GM has asked for chat only, honour it:** present the same findings in chat, one grouped pass, and record the rulings they give in the same decision envelope. Build the page after Phase 7, never instead of it.

Use the shared builder every other Claude review skill uses — read `~/.claude/skills/_shared/review-artifact/CONTRACT.md` first and follow it. Prepare every selected scene together and put the whole session on **one page**; do not run a scene-at-a-time approval cycle.

**The review files live in the session directory, not scratch:** `<session>/voice_critic_review/review_items.json`, `review.html`, `decisions.json`, plus the frozen sidecar `review_map.json` (below). A follow-up round after a discuss pass suffixes the items, map and decisions files with its round (`review_items_r2.json`, `review_map_r2.json`, `decisions_r2.json`) and republishes the **same** `review.html` path so the URL survives — per the contract's *File names* rule.

```bash
python3 ~/.claude/skills/_shared/review-artifact/build_review.py \
    --in  <session>/voice_critic_review/review_items.json \
    --out <session>/voice_critic_review/review.html
```

Publish `review.html` with the `Artifact` tool and **`capabilities: {"artifact": {}}`**, a stable favicon, a noun-phrase `title` and a `reviewId` naming the session and round (`vc:<session>:r1`). Then **stop** — the save comes back as an `artifact-changed` notification or the GM's word, never a poll. Read it back with the `Artifact` tool (CONTRACT step 5), then:

```bash
python3 ~/.claude/skills/_shared/review-artifact/read_decisions.py \
    --html <saved-artifact.html> \
    --items <session>/voice_critic_review/review_items.json \
    --out   <session>/voice_critic_review/decisions.json
```

### What each card carries

Every card shows **the passage, the rule broken, the proposed fix and the evidence**:

| field | carries |
|---|---|
| `id` | stable finding id that round-trips into Phase 9 — `s04-f03`, `doc-b02` for a ledger breach, `s03-h01` for a hatch |
| `t` | the decision as a sentence: severity (**breach** / **plausible** / **scope call**), scene and line, and the rule broken — *"Breach · s04 L37 — connective em-dash; the rulebook says never as a connective"* |
| `y` | **approve = act on the finding**: the exact `old → new` span, any dependent attribution or punctuation change shown separately, and the file it lands in (the Phase 9 derived revision — never the reviewed narration) |
| `n` | **reject = keep as is**: the passage stays exactly as written, and the rejection is recorded |
| `ev` | the passage **verbatim** in a `<blockquote>`, the rule's source as `file:line` (rulebook, `base.md`, voice spec, example), the `voice_lint` line if it fired, and your recommendation |

**Discuss** = defer or talk: the item stays pending and comes back to chat in one grouped pass with its note. **Unmarked** stays unresolved — never read it as approval or rejection. **Never pre-fill a verdict**: the page starts blank, and a recommendation goes in `y` or `ev`, not in state.

- **Convergence between two narrators is one card** with both quotes in its `ev` — the noun-swap is the evidence, and it is invisible when the halves sit in separate cards.
- **A budget breach is one card**, not N: `ev` lists where the instances sit and the ranked keep/change recommendation with its target count; `y` states the remedy the distribution supports (Phase 6). When that remedy is a whole-document re-render, `y` says it is a paid run and that approving the card is the GM's yes to it — the run itself is handed off, not started here.
- **A locked-dialogue anachronism** is a scope call: `t` says so, `y` is the disposition you recommend (keep / replace in-world / annotate), `n` keeps the quote as spoken, and the other dispositions go in `ev` for a discuss.
- **A reclassified-table-speech hatch** is a scope call too: `y` accepts the reclassification (nothing changes), `n` records that the span is in-fiction and refers restoring it to re-narration — a voice fix cannot restore dropped speech.
- A finding whose identity or source is unresolved gets a discuss-shaped card or a referral, never an executable speculative `old → new`.

Quoted narration is HTML in these fields: escape `<`, `>` and `&` in every span before it goes into the items file.

**Freeze the sidecar before publishing.** Write `review_map.json` beside the items: `reviewId`, and for each card id the target path, the target's SHA-256, the exact `old` and `new` spans (with a start offset where `old` is not unique), and which items concern narration versus an upstream referral. The page returns only ids; this map is what makes an approval executable in Phase 9 and what detects a target that changed after the GM ruled.

### What the page cannot carry, the lede and the report do

The resolution table and the budget ledger are the skill's thesis — a rulebook that did not arrive explains every register finding below it, and a skipped `voice_lint` check is not a pass — so they come **before** the cards. Put a compact version in the page's `lede` (rulebook state and digest, voice specs resolved or not, `voice_lint` errors / warns / skipped checks, every `BREACH` and every `not checked` row by name) and link the full `.md` report in the `footer`. **Never let a skipped check read like a passing one**: write *not checked* and the reason, never `ok`. The per-scene prose grid (a scene that under-narrates shows up as a short share and nowhere else), the scope-call list and the hatch list live in the `.md` summary.

**Zero findings** still gets its report. The builder refuses an empty `items`, so do not invent a dummy card: say in the reply that there is nothing to rule on, and point at the report.

### Keep the review surface honest as the work proceeds

After the GM rules and Phase 9 applies, **update the `.md` report** — mark resolved, rejected and deferred findings, correct any number that moved, and record any claim of yours that turned out to be wrong. Do not republish over a saved page to show resolved state: the saved page and `decisions.json` are the audit record of what the GM was asked and what they answered. A new round of questions is a new round's files.

## Phase 9: Apply approved fixes to a derived revision

**Approve means act on the finding; nothing else authorizes a write.** `decisions.json` (or the chat rulings recorded in the same envelope) is the only authority — the page existing, being opened, or `localStorage` never is. An approval of the stated `old → new` needs no second confirmation.

**The reviewed narration is never overwritten.** Not the raw `.md`, not the `.scrubbed.md`, not a dialogue-edit revision. Approved fixes go into a **separate derived revision**, the same model `/dialogue-edit` uses:

```
<session>/voice_critic/<run>/applied/<revision>/
    <scene file name>        # one per changed scene, built from the exact file critiqued
    approved.diff
    application.json         # written last; without it the revision is incomplete, not approved
```

1. **Validate before writing.** The decisions' `reviewId` matches `review_map.json`; every id is known; each target's current SHA-256 matches the frozen one; each `old` span is found exactly once (or at its recorded offset). A changed target or a changed proposal needs a fresh review, never a guessed merge.
2. **Apply deterministically** — exact literal replacement of the frozen `old` with the frozen `new`, no model rewrite — onto a copy of the critiqued file. Show the complete diff first.
3. **Write `application.json` last.** Record: `reviewId`; the decisions file path and its `savedAt`; per scene, the source path and which copy it was (raw, scrubbed, dialogue-edit revision), its SHA-256 and the result's; per applied item, the id, finding category, `old`, `new` and line; the rejected, discussed and unmarked ids; and, where the source was one half of a raw/scrubbed pair, whether each approved `old` span also occurs in the other copy — so whoever promotes the revision knows what to mirror. That list of every span changed is what the old replay file carried; it now lives with the revision it describes.
4. **Every later revision is rebuilt from the same critiqued base plus the complete approved subset**, under a new revision name. Keep earlier approvals in the new decisions file.

**`/scrub` and `sd_narrate` make the revision stale.** They regenerate the scrubbed or raw scene the revision was derived from, and nothing replays voice fixes onto the new text. When the base's hash no longer matches `application.json`, the revision is stale: say so, and re-critique the new text — do not silently replay the old spans onto it.

**Then verify, as a second pass.** Read each changed paragraph and its joins. Re-run `voice_lint` and every scan whose budget you claimed to move, and report before/after counts. Re-scan for collisions *you* introduced: a rewrite that borrows a phrase already used elsewhere in the document creates the exact convergence the pass exists to remove (Phandalin ch50: a replacement reading `I set it beside the rest` landed two scenes from an existing `I set it on the shelf`, both the same narrator). A new defect is a new proposal for a new round, not a repair under an earlier approval.

Finish with the revision path and state plainly that the reviewed narration is intact and the revision has not been promoted or assembled — promotion is the GM's separate action.

## Hard rules

- **Never modify the reviewed narration — during the critique or after it.** The report is a separate artifact, and approved fixes go into a separate derived revision with its own record (Phase 9), never into the raw `.md`, the `.scrubbed.md` or a dialogue-edit revision. **Warn the GM, in the reply and in the revision record, that `/scrub` and `sd_narrate` regenerate the scene the revision was derived from** and nothing replays voice fixes onto the new text: the revision goes stale, and the new text needs a fresh critique.
- **Applying fixes is a second pass with its own verification** — Phase 9's re-lint, before/after counts, and collision re-scan are not optional.
- **Never apply a rewrite the GM has not approved.** A suggestion is a suggestion until its card comes back `approve`; `reject` keeps the text as is, and `discuss` or unmarked keeps it pending.
- **Never retype a rule into this file.** Regexes come from `voice_lint`, bans come from `base.md`, register rules and budgets come from the campaign's rulebook. If a check needs a pattern this skill does not have, add it to `voice_lint` — do not paste it here. A second copy diverges at the next tic.
- **A check that did not run is never a pass.** `voice_lint` notes, an unresolved rulebook, an unresolved spec: each drops its category and says so. "No findings" and "not checked" are different report lines.
- **Quote verbatim.** Paste the flagged sentence exactly from the narration. The user will search for it; an approximate quote wastes their time.
- **Suggested rewrites must be grounded.** Pull rhythm and vocabulary from the voice spec and examples. If the spec is missing, mark the suggestion `[grounded in examples only]` or `[no spec available — best guess]`. **Earn that tag by resolving through the roster declarations first (Phase 2)** — since `sd_narrate` refuses to start without a declared spec, a report tagged `[no spec available]` is far more likely to be a lookup bug on your side than a campaign with no voice files.
- **The examples file settles register disputes the spec cannot.** A spec describes a character in the abstract; the examples show the sentences. When a flag turns on *how* a narrator would phrase something — syntax, grammar, fluency — quote the examples, not the spec. Phandalin ch50: an aphorism in Brewbarry's mouth was defensible against his spec and indefensible against `examples/brewbarry.md`, which has him saying *"Order is bullies. They bully barbarians."*
- **A doc-level cap breach is not N defects, so say which instances to keep.** A finding that reports "8 instances of this frame" and stops hands the GM eight rewrites, most of which would make the prose worse. Rank them, name the one or two that earn their place and why, and state the target count. A GM who approves the finding is approving your recommendation — if it does not contain one, they will delete all eight. Say where the instances sit, and let that distribution and the cost pick the remedy (Phase 6): spot fixes or a scene re-narration where they cluster, a whole-document re-render only where they are spread throughout and only on the GM's yes.
- **Verify an ordering claim against the whole source sequence before asserting a reorder.** Comparing two line ranges in the extraction is not enough: material *between* them may also have moved, and the narration may be in perfect order. Read the full ordered list of source beats and map narration beats onto it. Phandalin ch50 shipped a confirmed "eleven lines moved out of order" finding that was wrong — the block was in its correct position, and only the tense and an invented `Earlier, while we…` frame were real. Tense, framing and ordering are three separate claims; check them separately and drop the ones that do not hold.
- **Never critique a spec or a rule you could not read.** If it resolves, the category is live and you are expected to use it; if it does not, say so in the resolution table and drop the category rather than inferring what it probably said.
- **No commentary on the critique itself.** Don't open the verdict with "this scene is generally well-narrated but…". State the strongest specific issue and stop.
- **No invented examples.** If the per-character examples are absent, don't fabricate the "right" voice — say what's missing and degrade gracefully.

## Output

Report each file written, the flag count, and the ledger verdict summary. Surface the strongest recurring issue across scenes (e.g. "three scenes flagged Unla for stock simile usage") so the user knows where to focus their re-narration budget.

**Lead with a rulebook problem when there is one.** If Phase 3 found the rulebook unset, missing, or flattened, that is the headline and every register finding below it is downstream of it — the fix is the migration and then re-rendering what it affected (a paid run, on the GM's yes), not a round of sentence edits.

Remind the user:

- They decide which findings to act on, on the page (or in chat if they asked for chat only); approved fixes land in a separate derived revision, and the reviewed narration stays as it is.
- For systemic voice problems concentrated in a few scenes, re-running `sd_narrate --scene <N>` with an updated voice file or rulebook is often more efficient than per-sentence edits.
- A doc-wide cap breach is decided by where the breaches sit and what the fix costs: fix or re-narrate the scenes they cluster in; re-render the whole document only when they are spread throughout, and only on their yes — it is a paid run.
