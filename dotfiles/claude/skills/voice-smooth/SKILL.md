---
name: voice-smooth
description: Render the verbatim scene-extraction quotes into readable, in-voice prose — a derived scene_extractions_smoothed/ layer that sits between /session-summary-consistency and session_doc. Uses each character's voice file as the guardrail. Fixes garble, run-ons, and disfluencies for readability WITHOUT changing what was said; never touches the verbatim (the VTT stays the raw record). Invoke as /voice-smooth [session-dir].
tools: Read, Bash, Write, Edit, Glob, AskUserQuestion
---

# Voice-Smooth — voice-aware readability rendering of quotes

Turn the raw, transcriber-corrected verbatim quotes into **readable prose that still sounds like the character who said it**, written to a *derived* `scene_extractions_smoothed/` layer for `session_doc` to consume. This is a **rendering** step, not an error-fix and not narration.

## Where this sits (and the one inviolable rule)

```
VTT  (raw verbatim — IMMUTABLE, forever the record + the voice-file raw material)
  → scene_extractions/           (verbatim; transcriber errors fixed by /session-summary-consistency)
  → [THIS SKILL] voice-smooth    (readable, in-voice; guarded by the voice/ specs)
      → scene_extractions_smoothed/   (DERIVED — `## Voiced moments`, what session_doc reads)
  → session_doc narration
  → /voice-critic (checks the finished narration against the voice spec)
```

**Inviolable rule: the verbatim is never mutated.** This skill only ever *writes* `scene_extractions_smoothed/`. It does **not** edit the VTT or `scene_extractions/`. Because the raw quotes live permanently in the VTT, the smoothed layer is a safe derived rendering — not a rewrite of a record.

## The optimization target flips here — this is the point of the layer

Every upstream layer optimizes for **precision**: what was actually said, by whom, in what order. That is correct for a record, and the VTT and `scene_extractions/` remain that record forever.

**This layer optimizes for narration instead.** It is the last stop before `session_doc`, it writes only a derived copy, and nothing downstream of it is a record of anything. So the question at every quote is not *"is this exactly what the tape captured?"* — upstream already answered that and its answer is preserved. The question is **"will this read well, in this character's voice, when the narrator reproduces it literally?"**

That flip licenses edits an upstream pass would refuse:

- **Recovering the word a garble is hiding.** `"I app and slash"` is not what anyone said; it is what two ASR passes made of *"I hack and slash"*. Upstream's job is to record that the tape says `app`. This layer's job is to hand the narrator a line that works.
- **Completing a cue the recorder cut**, when the meaning is recoverable (`"Who are you talking."` → `"Who are you talking to?"`, `"I rehearsed it for, like, 15."` → `"…for like 15 minutes."`).
- **Reassembling one sentence spread across four broken cues.**
- **Splitting stage direction out of NPC speech** (step 2 rule 5 — the single biggest win).
- **Dropping a disfluency that belongs to the *player*, not the character**, when the voice file says otherwise. Stéphane says "you know" constantly; Brewbarry's spec says *short, declarative, does not hedge*. The voice file is authoritative, so the tic is noise here even though it is faithfully on the tape.

**The guardrail is approval, not abstention.** Because these edits change words, *the human approves each one* — see step 2.5. Do not apply them on your own judgment, and do not skip them out of caution either. Bring the candidate, the evidence from **every** transcript, and the options; let the GM rule.

**Still off-limits, approved or not:** facts, names, numbers, mechanics, attribution, and meaning. Fixing how a line *reads* is this layer's job. Changing what it *says* never is.

## What this is — and is NOT

- **IS:** readability + voice, rendered for the narrator. Collapse run-ons, drop filler-as-noise, repair unreadable fragments, punctuate, recover garbles — *while preserving each character's register, tics, and vocabulary* per their voice file.
- **IS NOT — silent error correction.** Every garble repair is a GM ruling made here, one at a time, with the tape evidence on the table (step 2.5). What it is *not* is a unilateral fix, and it is *not* a substitute for `/session-summary-consistency`, which still owns the glossary and the upstream record.
- **IS NOT — narration.** Turning quotes into flowing scene prose is `session_doc`'s job. This produces cleaner *quotes*, not narration.
- **IS NOT — critique.** Checking finished narration for voice drift is `/voice-critic`'s job.

## Precondition — run `/session-summary-consistency` first

Smooth *corrected* quotes, not garbled ones. If the verbatim still contains obvious transcription errors, run `/session-summary-consistency` first — otherwise you will fluently render a mistake, and a fluent mistake is much harder to catch than a garbled one.

That pass is where **proper nouns** get settled, because it rules against the glossary and the entity registry and writes the ruling back to both. Never decide a name here: a name is an identity decision, it recurs across every future session, and this layer has no way to record it. `Hulkrist`→`Alkrist` is upstream's call, always.

**What it does not catch is common-word garble** — `app`/`hack`, `confront-free`/`conflict-free`, `bloom`/`show`. Those aren't in any glossary, they don't trip a registry check, and they survive every upstream pass. They surface here, when you read the line and it doesn't parse. **Rule on them here, one at a time, with the GM** (step 2.5) rather than deferring them upstream to a pass that structurally cannot see them. Record what you ruled so `/session-summary-consistency` can promote anything that turns out to recur.

## Inputs

- **session-dir** — `summaries/YYYYMMDD/`. Default: CWD (if CWD is the campaign root, ask which session).
- **scene dir** — `<session-dir>/scene_extractions_new/` **or** `<session-dir>/scene_extractions/` (suffix varies). Detect it; call it `<scene-dir>`.
- **voice files** — from `<campaign-root>/voice/`. Filenames are **not** limited to `<char>_voice.md`; resolve them with the three-rule lookup in step 1, which mirrors what the pipeline does. Plus `voice/_genre.md` (overall tone). **Authoritative** for how each character speaks.
- **player→character map** — from the glossary `## Player names → characters` section (only needed if any labels still carry real names — they shouldn't after /session-summary-consistency).

## Workflow

### 1. Locate + load the guardrails
- Detect `<scene-dir>`; if missing, stop.
- Read `voice/_genre.md` for overall tone.
- **Resolve voice files the way the pipeline resolves them.** The rule lives in CampaignGenerator `session_doc/voice.py` (`load_voice_files` + `_resolve_voice_key`, CampaignGenerator#247). Do not use a narrower one: `voice/*_voice.md` matches **zero** files in Phandalin, whose specs are `brewbarry_new_pipeline.md`, `soma_new_pipeline.md`, `valphine_new_pipeline.md` and `vukradin_new_pipeline.md` — so all four PCs of the campaign smoothing is standard on would get no spec, and this skill's own "voice files are authoritative" rule could not be honoured.

  **Build the key set.** Glob `voice/*.md`. **Skip every file whose name begins with `_`** — `_genre.md` and friends are shared campaign material, not a per-character spec. For each remaining file the key is the lowercased stem with a trailing `_voice` removed: `Brewbarry_voice.md` → `brewbarry`, `vukradin_new_pipeline.md` → `vukradin_new_pipeline`.

  **Resolve each speaker against that key set, stopping at the first hit:**

  | | Rule | Example |
  |---|---|---|
  | a | exact full lowercased name | `Unla Key` → `unla key` |
  | b | first name only | `Unla Key` → `unla` |
  | c | the **unique** key beginning with the first name followed by `_` or `-` | `Vukradin` → `vukradin_new_pipeline` |

  **Refuse on ambiguity.** If rule (c) matches two or more keys, that speaker has no resolvable spec: do not guess which file the pipeline would use. Report it as ambiguous, list the candidates, and treat the spec as missing.

  Campaigns whose files happen to be named `daz.md`, `grygum.md` (out-of-the-abyss) hit rules (a)/(b), which is how the narrower rule went unnoticed.

- **Read a character's voice file before smoothing a single one of their lines** (voice files are authoritative — global campaign rule). If a speaker's spec does not resolve, say so before smoothing their lines rather than rendering them from nothing.
- Speakers with no voice file:
  - **GM** (narration / OOC / rules) → render as clean, plain GM prose; do not invent a voice.
  - **GM as <NPC>** → draw the NPC's characterization from its dossier (`docs/npcs/`) **or the session prep docs** (`notes/session_prep/`, `notes/sessions/`) if either gives you one, else a neutral, readable rendering. Never flatten a distinctive NPC into GM-neutral when a source gives you a voice — this run rendered Kalan (precise, professorial), Bookwyrm (compliment-as-warning, maternal-turned-glacial), Grygum (warm-as-method reassurance), and Daral (effusive) from prep/dossier characterization, not from PC voice files.

### 1.5. Survey the whole scene set before smoothing any of it

Three defects are invisible one-scene-at-a-time and change **what you render**, not just how. Find all three before writing a single file.

#### Duplication across scenes — check every pair

Extractors routinely emit the same quotes into two or three neighbouring scenes. Smooth them all and `session_doc` narrates the same beat two or three times.

```bash
cd <scene-dir>
for f in 0*.md; do grep '^> "' "$f" | sed 's/^> //' | sort -u > /tmp/q_$f.txt; done
for a in /tmp/q_0*.txt; do for b in /tmp/q_0*.txt; do [ "$a" \< "$b" ] || continue
  n=$(comm -12 "$a" "$b" | wc -l); [ "$n" -gt 3 ] && echo "$n  $(basename $a)  <->  $(basename $b)"; done; done
```

One or two shared lines is noise — `"Yes."`, `"Yeah."`, `"Exactly."`. Real duplication is loud: Phandalin ch48 scored **67 of scene 01's 98 quote lines** repeated verbatim in scene 02, with a shared tail across three scenes.

**De-duplication is a SCOPE decision — what belongs where — and scope belongs to the human.** Never draw the boundaries yourself. Present the overlap with counts, propose cut points, and get them approved.

**Then rescue before you cut.** Diff the losing copy against the keeper and *read every line unique to it*. In ch48 exactly one line — Brewbarry's `"I hack and slash."` — lived only in the half scene 01 was losing, while its setup line lived only in scene 02. Cutting blind would have destroyed the joke.

```bash
comm -23 /tmp/q_<losing>.txt /tmp/q_<keeper>.txt   # lines about to be lost — read them all
```

Leave a **scene boundary note** in each affected smoothed file saying what moved where and why, and strike through (don't delete) the now-relocated bullets in the copied `## Scene summary` so the gm-assist original stays auditable.

#### Extractor splices

A quote fused mid-string with the next speaker's header — `> "…a typical medieval bank**GM** — *introducing the banker*`. Structurally broken markdown that no consistency pass catches.

```bash
grep -rn '[a-z0-9…"]\*\*\[\?\(GM\|<PC names>\)' <scene-dir>/0*.md
```

Repair in the smoothed layer (the split is unambiguous), and **report that `scene_extractions/` still carries it**. Phandalin ch48 had four, in scenes 01, 02, 04 and 08 — one of which had survived a full `/staged-consistency` run.

#### Player knowledge wearing a character's name

**The highest-consequence defect this layer can catch, and it is not a transcription error at all.** A VTT labels by *speaker*, so when a player says something out of character — recalling another campaign, reasoning from GM-side knowledge, metagaming aloud — it lands in the transcript under their **character's** name. The narrator then reproduces it as an in-fiction thought, and the character now knows something they cannot possibly know.

Phandalin ch48 had two:

- Soma's *"Were they Cambions?"* and Valphine's *"they're Cambions"* — the **players** met the cambion/House Margaster connection in a different adventure. No character in the campaign knows it.
- Vukradin's *"I have a feeling I know who the gnome is"* — the **player** knows who KP is. Vukradin does not.

You cannot detect these from the tape, because the tape looks identical either way. Detect them by **reading for knowledge the character has no route to** — a fact nobody on-page told them, a conclusion that arrives too fast, a proper noun from outside the campaign. When one is even plausible, **ask the GM**; they are the only one who knows what was established at the table.

When the GM confirms one:

1. Keep the line (it was said) but **relabel it OOC and annotate it** — state plainly that it is the player's knowledge, name what the character does *not* know, and write **"Do not narrate X as suspecting/asserting this."**
2. **Record it durably.** Annotations live in a derived file that the next `scene_extract` run deletes. The boundary must outlive it — a hand-authored dossier at `docs/<Subject>.md` with a *what the party actually knows* table, plus a pointer from the campaign's `CLAUDE.md` so it loads every session. Phandalin keeps `docs/KP.md` and `docs/Margaster.md` this way.

### 2. Smooth each quote (per scene, from the source's `## Verbatim moments`)
For every quote block:
1. Identify the **speaker** and load their voice spec.
2. Produce a **smoothed** version that is:
   - **Readable** — complete sentences, filler-as-noise removed, false starts collapsed, garbled fragments repaired *only where meaning is unambiguous* (else keep the fragment or mark `[unclear]`).
   - **In-voice** — keeps the character's register, characteristic vocabulary, sentence rhythm, and signature tics. Thorin's clipped bluntness and Zalthir's hedging verbosity are **voice, not error** — preserve them. Do **not** homogenize everyone into the same neutral prose.
   - **Faithful** — same meaning, same content, **same names, numbers, mechanics, and attribution**. Add nothing; drop no substance. If you can't smooth a line without changing what it means, leave it closer to verbatim.
3. **OOC / table chatter** (jokes, rules talk, real-world tangents): smooth *lightly* for readability only — do **not** force it into in-character voice, and keep any OOC marker. When in doubt, leave OOC lines near-verbatim.

   **Exception — pure tooling/logistics noise gets cut, not smoothed.** Not all OOC content is table talk. A distinct sub-class carries zero narratable content and doesn't belong in `## Voiced moments` even lightly smoothed: VTT/roll20 tool-fighting ("Where's the init thing?... run script... screw it"), map-token placement ("put this here — Bloodstained"), and off-mic real-world asides to someone in the room ("get out of there... sorry"). None of it is banter *about the game* — it's the players operating the software, or talking to someone who isn't at the table. Phandalin ch3 (2025-05-28 session): the GM ruled the init-tracker fight in scene 01 should be **deleted** from the smoothed layer, not merely smoothed — and that standard was then applied to every other instance of the same class found while smoothing the rest of the session (the map-token line, Soma's off-mic aside), not just the one line the GM actually reviewed. Generalizing a ruling beyond its original scope is itself a judgment call — flag it explicitly for confirmation rather than assuming the GM's intent covers every future instance silently.

   **Cut it; don't fake-render it.** Deleting is different from marking `[inaudible]` (that tag is for lost *meaningful* content) — this is content that was captured cleanly but isn't part of the scene. Leave an italic note at the top of the affected sub-section recording what was cut and why, so the omission stays auditable rather than silent: `*Cut from this layer: a beat of VTT map-token placement (...) — table/tooling logistics, not narratable content. See voice_smooth.sources.yaml.*` Record each cut in the manifest's `calibration_decisions` (or equivalent) so a later reader can see the ruling was made once and applied consistently, not re-litigated per line.
4. **Mixed-attribution blocks.** The extraction often tucks a reply from another speaker *inside* a quote block (a GM or NPC line under a PC's label). Render each line in the correct voice and **tag the interloper inline** (`[GM]`, `[Kalan]`, `[Bookwyrm]`, `[Dawnbringer]`), but do **not** re-attribute the block's label — that is an upstream fix; flag it, don't silently move it.
5. **Split stage direction out of NPC speech — this is the single biggest win this skill delivers to narration.** A GM speaks narration and NPC dialogue in one unbroken breath, and the extractor captures the whole breath inside one pair of quotation marks. The result is a "quote" that is not a quote:

   > "He looks at you, he looks… Mr. Vukradin, I want to thank you. Mr. Brewbarry, I wish you to know that you have this… the Counting House's full financial support…"

   Left alone, this is **poison for `session_doc`**. The narrator's voice files lock quoted spans as immutable in-fiction speech, so it must reproduce the whole span verbatim — including `He looks at you`, third-person narration about the speaker, addressed to a player in the second person. The narrator then either emits an NPC narrating himself in third person, or silently violates the quote-lock to fix it. Both are defects, and neither is fixable downstream, because by then the narration constraint has already fired.

   So split it here, where the layer is explicitly derived and a human reviews it:

   > *He looks at you.* "Mr. Vukradin, I want to thank you. Mr. Brewbarry, I wish you to know that you have the Counting House's full financial support…"

   **Rules for the split:**
   - **Italics outside the quotation marks for stage direction; quotation marks only around what the NPC actually says.** The narrator's quote-lock then protects the speech and leaves the direction free to be re-rendered in the POV character's voice — which is exactly what you want it to do.
   - **Do not re-attribute and do not change the speaker label.** The block stays `**GM** — *as the banker*`. This is a rendering fix, not an attribution fix.
   - **Convert second person to third inside the direction only when the direction is unambiguously about the NPC** (`He looks at you` stays as-is; the "you" is the party and survives fine). Never rewrite the speech to match.
   - **Speech tags embedded in the quote get lifted the same way**: `"turns to Vukradin and says, Mr. Vukradin, there appears to be a notice of credit"` → *He turns to Vukradin.* `"Mr. Vukradin, there appears to be a notice of credit."` Same for `"He goes, oh, what are you making again?"`.
   - **When you cannot tell where direction ends and speech begins, leave it fused and flag it.** A wrong split invents a beat; a fused line is merely ugly.

   Expect several of these per scene — Phandalin ch48 scene 01 alone had four. Report the count at review; it is the clearest signal of how much this pass bought the narrator.
6. **A sentence split across two speakers is an attribution defect — surface it, never fix it silently.** ASR sometimes cuts one person's sentence in half and hands the tail to whoever spoke next. Phandalin ch48 scene 03: Zoom rendered the GM's *"No, no, not from me."* as GM `"No, no, not from."` + Vukradin `"for me."`, leaving Vukradin with a standalone line that means nothing.

   Attribution is on the never-change list, so **do not rejoin it on your own judgment** — but do not leave it silently broken either. Bring it as a ruling with all three options (rejoin / repair the words only and flag the split upstream / leave it), and if the GM approves the rejoin, record it in an HTML comment in the smoothed file noting that the verbatim layer still carries the split.
7. **An unrecoverable garble gets annotated, not deleted and not guessed.** When neither transcript resolves a line and context gives you nothing, say so in the editorial note — name what each pass heard and add **"Do not narrate it as meaningful."** Phandalin ch48 kept two on that basis (`"Caribbean stew."`, `"It's not so firmly, no."`).

   Deleting loses something that was genuinely said; inventing a plausible replacement is worse, because a fluent fabrication is far harder to catch downstream than an obvious garble. The annotation is the honest third option.

   **Your confident reading of an unrecovered line is worth less than you think it is.** Phandalin ch4 produced three such readings, each obvious enough to feel safe; when the GM later cleared them for repair and they were finally checked against the second transcript, **one of the three was wrong** — `"Why'd that cost us the gold?"` was not the question it looked like, it was the statement *"And that cost us a gold."* A third strike rate on lines that felt certain is the calibration to carry into every one of these.

   Related: **not every odd line is a garble.** Deliberate table jokes (`"Oral B. Vance"`, `"SystemD of Neverwinter"`), OOC riffs in modern register (`"charge thousands of dollars"`), and throwaway placeholder names in an illustrative example (`"married to Pengro, you know, whatever"`) are all correct as captured. Offer keep-verbatim and say why you think it is deliberate.

### 2.5. Rule the garbles with the GM

Any repair that changes a *word* rather than punctuation, filler, or sentence boundaries is a GM ruling. Collect them per scene and show a running checklist so the GM can see how many are left.

**Default to one at a time.** Do not apply a garble because the answer seems obvious.

**But strict 1x1 does not survive volume, and pretending otherwise is its own failure.** Phandalin ch48 produced **74 rulings across 8 scenes** — scene 05 alone had 18. Seventy-four separate questions exhausts the GM long before scene 08, and an exhausted GM rubber-stamps. Once a scene exceeds roughly six candidates, offer the split explicitly and let the GM choose it:

- **Batch** the ones a second transcript settles outright — where you are not reconstructing anything, it simply heard the word Zoom dropped. **List every item in the batch in full, with its before → after, in the question itself.** A batch the GM cannot read is a silent decision wearing a checkbox.
- **1x1** everything else: transcripts disagreeing, nothing corroborating, or a word you are inferring from context.

A third tier appears once the run is long: candidates that are *mechanical applications of a ruling the GM already made this session* (a proper noun settled two scenes ago, recurring in a new one). Those can join the batch — but say so, and name the earlier ruling you are applying.

**Never batch:** anything that establishes canon, any name not already settled, and anything where your recommendation is a guess. Those stay 1x1 no matter how long the queue is.

#### Reporting at volume — the interactive review artifact

Batch-vs-1x1 is about how many decisions to bundle into one *question*; it doesn't solve the problem of 74 rulings across 8 scenes exhausting the GM's attention regardless of bundling. For a full-session run, publish an interactive **Approve / Reject / Discuss** HTML artifact instead of (or as well as) walking the queue in chat. Demonstrated end-to-end on Phandalin ch3 (2025-05-28): a full 10-scene pass reviewed in two rounds, each round-tripped by download.

Build it with the `Artifact` tool (`artifact-design` skill for treatment — this is a utilitarian tool, not editorial; `artifact-capabilities` skill for the `downloads` contract):

- Declare `capabilities: {"downloads": true}`.
- One card per candidate, grouped by scene (or by decision class for calibration pairs — step 4). Each card carries exactly what a 1x1 chat question would: every transcript's reading named, corroboration found, the voice-file/framing rationale, the full-sentence before→after preview, and a keep-verbatim option.
- Each card gets a segmented **Approve / Reject / Discuss** control. **Discuss** reveals a `<textarea>` for the GM's own words — never force a bare reject when they want to explain or counter-propose.
- A sticky tally dock (counts per verdict + how many remain undecided) so a long queue stays legible instead of becoming a wall to skim.
- A "Download decisions" button: `claude.use("downloads")`, then `downloads.save({filename, data})`; if the namespace resolves `null`, reveal a fallback `<textarea>` pre-filled with the same content so the GM can copy-paste manually instead.
- Export a single Markdown decision record, one section per candidate, verdict + any discuss-text — structured so you can parse it back mechanically.

**The round trip:** the GM downloads the record, then either pastes it into chat or names the saved path (on WSL2, a Windows-side save lands at `/mnt/c/Users/<user>/Downloads/...`, directly readable). Read it back and apply per verdict: **Approve** → apply the garble fix or calibration ruling exactly as a chat "yes" would; **Reject** → skip, don't re-litigate; **Discuss** → resolve using the GM's own text in conversation before acting — never auto-apply a Discuss item on your own reading of their note.

This does not relax the confirmation requirement — every garble ruling still needs an explicit GM verdict, per-item. It changes the delivery mechanism at volume, not the checkpoint itself. Below the batch threshold (a handful of candidates in one scene), a chat question is still simpler; reach for the artifact once the queue is long enough that serial chat would exhaust the reviewer.

**Reading the record back is where a review artifact quietly turns into rubber-stamping.** Two verdict states are not decisions, and treating either as one destroys the checkpoint the artifact exists to provide:

- **UNDECIDED is not a verdict.** A card that comes back with no mark was not ruled on — the GM scrolled past it, or ran out of attention, which is exactly the failure a long queue produces. **Re-ask those cards.** Do not apply your own recommendation because it was the recommendation, and do not silently drop them. Phandalin ch4 returned 3 undecided out of 38; re-asked as a single grouped question, they were ruled in one line. Say how many were undecided when you report.
- **A DISCUSS note is an instruction to talk, not a pre-approval.** The note is usually three or four words written at speed — `"Back to phandalin"`, `"Table chatter drop"`, `"We will do the thing where we make it part of the workd"`. Some are unambiguous; some carry two readings that produce different files. State your interpretation and confirm it before applying, and when the note points at an edit that would **invent canon** — rewriting a real-world reference into an in-world one, naming a place, settling a quest title — bring the *specific proposed wording* back as its own question. The GM ruling "rewrite it in-world" has not told you what the in-world words are.

For each candidate, bring:

- **Every transcript's reading, named.** They disagree, and the disagreement is the evidence. Zoom heard `app and slash`; the re-transcription heard `act and slash`. Two passes garbling one phrase two different ways is the signature of a real utterance neither caught — and it is far stronger evidence than either pass alone. When both agree, say so; that is a reason to leave it.
- **Corroboration from elsewhere in the tape.** The GM said "all about this hack and the slash" twenty minutes earlier. Grep for the phrase before asking.
- **What the voice file or the scene's own framing implies.** The GM called it "the soft bathrobe"; a pitch about *softness* fits, a pitch about *roughness* does not.
- **Options as full-sentence previews**, so the GM reads the line as it will land, not a diff of one token.
- **A "keep it verbatim" option, every time.** Sometimes the garble is the joke ("Oral B. Vance"), and sometimes the GM remembers what was actually said.

Know which transcript to trust for what — it differs per campaign **and per session**, and is worth recording in the manifest. Phandalin ch48: the Zoom export was better on **proper nouns**, the re-transcription better on **sentence completion** (it recovered "15 *minutes*" and "Who are you talking *to?*" where Zoom cut both). Phandalin ch4: Zoom was better at *both*, and settled most of the run. Record what you actually observed this session rather than carrying the previous session's split forward as fact.

**When the transcripts disagree and nothing corroborates either, say so plainly and let the GM decide.** Do not pick the more fluent reading because it is more fluent.

#### First prove the second transcript is a second *reading*

Before any of the evidence work below, confirm the file you are about to treat as corroboration is not the same text under a different name. **A session directory routinely holds four or five transcripts that are byte-identical.** Phandalin ch4: `*.extract_input.vtt`, `*.final.vtt`, `*.rebuilt.retranscribed.vtt` and `*.rebuilt.retranscribed.cleaned.vtt` were all the same retranscription. Three "confirmations" came back before the pattern was obvious, and each one was the same pass agreeing with itself.

This failure is silent and it inverts your confidence exactly backwards: identical readings look like the *strongest* possible corroboration when they are in fact no evidence at all.

```bash
# one distinctive phrase, every candidate transcript — group the identical ones
for f in <session-dir>/*.vtt <session-dir>/*Recording*.md; do
  echo "-- $f"; grep -i -m1 "<a distinctive phrase from the middle of the session>" "$f"
done
```

Files that print the same string are one reading. What survives is your evidence base — often a single genuine second pass. In Phandalin that is **Zoom's own text export** (`GMT<date>_Recording.md` and its `.speakers.vtt` siblings), which is produced by a different engine than the vocabulary-biased retranscription and is the only true independent reading in the directory.

Also look for a **pre-built diff** before grepping anything by hand: `*.retranscribed.cleaned.proper_nouns.md` is a ready-made Zoom-vs-retranscription comparison over every flagged proper-noun span. For a name candidate it answers the question instantly, and it caught a third reading of one ch4 line that neither raw file gave.

#### Grep the anchor, not the garble

The obvious search fails on every single candidate, and it fails *silently* — you get zero hits and conclude the other transcript doesn't cover the scene. It does. **You are grepping for a word that, by definition, the other pass did not produce.**

Search instead for a **clean phrase adjacent to it** — a distinctive line one or two cues away that both passes almost certainly got right — then read the region around the hit:

```bash
grep -n -B6 -A6 -i "<clean anchor phrase>" <other-transcript>.vtt | grep -vE '\-\->|^[0-9]+[-:]$'
```

Every hard recovery in Phandalin ch48 came this way: anchoring on `"civic notice"` produced *"Okay, what's on the notice?"* for Zoom's meaningless `"In order to sake."`; `"disappear anyone"` produced *"I love having Brewbarry"* for `"I love having blueberries."`; `"recently unalived"` produced *"Not that long."* and *"He pauses."* for `"Not bad, Lol."` and `"We can pauses."`

Before concluding a transcript lacks coverage, **prove it with an anchor**, not with a failed search for the garbled token.

**Run the anchor grep on every fragment before calling any of them unrecoverable — one anchor per fragment, never one per group.** Phandalin ch4 bundled four scene-03 fragments onto a single "neither pass resolves these" card and kept all four. Two were recoverable from the first anchor tried: `"Friggin?"` was **"Free him?"** and `"let's try to freeze it"` was **"let's try to free him"**, both sitting two cues from the clean phrase `"free the slaves"`. A third, `"11 insight on Do."`, was not a garble at all — it was a missing sentence boundary (*"Got 11 insight on. Do I think he's a surface ogre?"*). Only the fourth survived scrutiny. A bundle card is where unrecoverable fragments go to avoid being checked; if you are grouping them, that is the signal you have not anchored them individually.

#### A garbled number is still a number

`numbers` and `mechanics` are on the never-change list, which makes it easy to skim past a dice value that ASR turned into a *word*. Phandalin ch48: Vukradin's persuasion roll reads `"Event persuasion. Does that help?"` in Zoom — the re-transcription has `"27 persuasion."` It reads as prose and is in fact the roll that decides whether an NPC hands over a plot-critical name.

When a line mentions a check, a roll, or a quantity and the value is absent or reads oddly, treat it as a **high-priority** candidate and go to the tape. Leaving it garbled is not the safe option: the narrator will either invent a number or drop the mechanic.

#### Write new wrong-forms back to the glossary

A proper-noun garble ruled here is one the upstream pass will meet again next session. When the GM settles one, offer to add it to `notes/vtt_transcription_corrections.md` as part of the same ruling — Phandalin ch48 added `Utgartian`, `Rieber`, `Vubert`, `Rueberg`, `CORN`, `Corin`, `Don Juan`.

Checking the glossary also audits it. That pass found the `Don-Jon Raskin` row pointing at an **unhyphenated** canonical form, contradicting `entity_registry.yaml` — a live bug that had been quietly producing inconsistent output. **The registry is the authority; the glossary is a lookup table that can drift from it.** When they disagree, say so and let the GM pick which one is wrong.

**Writing the rows is not appending a table.** Two rules govern that file, and both are easy to break:

- **One canonical, one row.** A dated section may only hold a row whose canonical appears nowhere else in the file; `add_to_glossary.py --section` searches within a single section, so a new dated row for an existing canonical silently creates a duplicate and makes every future append worse. Merge new variants into the **existing** row and put the provenance in the dated section as prose. Check first — many "new" variants are already there (7 of 28 in Phandalin ch4).
- **Never put a pipe table in a prose section of that file.** `lint_glossary.parse_rows` treats *any* table as live rules. A two-column provenance table headed `| Canonical | Added this pass |` is parsed with the columns **backwards**: Phandalin ch4 briefly registered `Brewbarry → Brubit`, a rule `apply_replacements` would have used to rewrite a PC's name out of a transcript. Use a bulleted list instead.

Then run the linter — the file's own standing rule, and the thing that caught the table bug when reading would not have:

```bash
python3 ~/src/mytools/dotfiles/claude/skills/vtt-spell-pass/lint_glossary.py \
  --glossary notes/vtt_transcription_corrections.md
```

Expect `0 errors`. Compare the warning list against a run from *before* your edit and account for every new one; `split_section` means the one-canonical-one-row rule was broken, and a new `chained` warning naming something you just added is the table bug above.

Finally, **flag the variants that are ordinary names.** Matching is word-boundary but case-insensitive, so `Rooker`, `Hubbard`, `Thelma`, `Norquist` will rewrite a real person of that name if one ever appears at the table. Say so in the section you write, rather than letting a future pass discover it.

### 3. Write the derived layer
Write `<session-dir>/scene_extractions_smoothed/NN_slug.md`, mirroring the verbatim file's structure (frontmatter, `## Scene summary`, a moments section, and the same speaker labels) so it is a drop-in for `session_doc` — **with one deliberate exception, below.** Mark it as derived:
- frontmatter `source: voice-smoothed` and `from: ../scene_extractions/NN_slug.md`
- **rename the moments heading to `## Voiced moments`.** Do NOT copy `## Verbatim moments` across. The heading is a *claim*, and CampaignGenerator's `session_doc/io.py` binds it to one: `## Verbatim moments` says *these are the tape's words*, which this skill has just stopped being true. `## Voiced moments` says *tidied for reading; not exact* — which is what a smoothed file is (CampaignGenerator#250 R5).

  This is not cosmetic. The heading is what drops the file out of the **contract axis**: rules R1 and R3 police exactness inside a span marked verbatim, and firing them on prose that openly declares it was edited produces refusals for edits this layer exists to make. (It does not change the verdict counts — `unverified` still means untraceable to any transcript line, which is a fabrication or a splice either way, and remains a defect here too.)

  Phandalin's `scene_extractions_smoothed/` currently carries `## Verbatim moments` on every file, which is the state CampaignGenerator#304 detects and warns about.
- copy the `## Scene summary` across, but **scrub player real names as you copy** (e.g. `Kostadis → GM`, via the glossary `## Player names → characters` map) — these summaries routinely leak the GM's real name, and copying it forward propagates the leak. **Flag** (don't rewrite) any transcription garble you notice in the summary (its origin is gm-assist / the scene-extract step). Leave the summary's wording and facts otherwise unchanged.
- replace each verbatim quote's text with its smoothed rendering under the same speaker label

Do **not** modify anything under `<scene-dir>/`.

### 4. Human review — REQUIRED before it feeds session_doc
Smoothing changes words, so the human is the checkpoint (LLM drafts → human reviews → then it feeds `session_doc`).

**Calibrate on one scene first.** On a first run for a session (or a new campaign), smooth a single representative scene, present *its* pairs, and get the voice fidelity and the grammar-fix aggressiveness approved **before** rendering the rest. It catches over/under-smoothing early and keeps the review tractable. (Calibration question that came up this run: how aggressively to repair grammar the *player* actually spoke — clear-meaning fixes like "we got a nail Bookwyrm" → "we've got to nail Bookwyrm" are fair game; ambiguous ones stay near-verbatim; suspected *transcription* errors get flagged upstream, never smoothed away.)

**Present the calibration scene as verbatim → smoothed pairs, grouped by decision class** — filler removal, grammar repair, stage-direction split, truncation handling — not as an undifferentiated list. The GM is approving *policies* here, not lines; one representative pair per class, plus every pair where you are least confident, is what makes that possible. Flag explicitly any rendering that risks changing meaning, flattens the character's voice, or repairs an ambiguous fragment.

Ask: *"Approve these, edit specific ones, or want a different smoothing pass on any character?"*

**Once calibration is locked, do not dump pairs for the remaining scenes.** A full session is many hundreds of quote lines and a wall of pairs gets skimmed, which is worse than no review. The real review of the rest happens through the garble rulings in step 2.5 — those are the changes that can actually go wrong. For each remaining scene, report what you rendered, the count of stage-direction splits and truncations handled, and then go to its rulings.

If the calibration pairs themselves run long (many representative pairs, several decision classes), the same **interactive review artifact** described under step 2.5 applies here too — one card per pair, grouped by decision class, Approve/Reject/Discuss, download-and-read-back. Use plain chat for a single calibration scene's handful of pairs; reach for the artifact only if that set grows past what a reviewer can hold in view at once.

Apply all edits to the `scene_extractions_smoothed/` files only.

### 5. Verify the layer

Cheap, and each check has caught a real defect:

```bash
cd <session-dir>/scene_extractions_smoothed
grep -l "## Verbatim moments" 0*.md | wc -l          # MUST be 0 — see step 3
grep -l "## Voiced moments"   0*.md | wc -l          # MUST equal the scene count
grep -l "^source: voice-smoothed" 0*.md | wc -l      # MUST equal the scene count
grep -c 'truncated' 0*.md | grep -v ':0'             # leftover markers (summary copies are OK)
grep -c '[a-z0-9…"]\*\*\[\?\(GM\|<PCs>\)' 0*.md | grep -v ':0'   # splices you re-introduced
```

Also confirm the player-name policy actually landed the way the GM ruled it — scan the summary sections and the quote lines **separately**, since the ruling usually differs between them.

#### Audit the deltas — every changed word must trace to an approved card

The checks above catch structural defects. They do not catch the one this layer is most likely to commit: **while writing hundreds of lines of prose you will repair a garble nobody approved**, because it is sitting right there and the fix is obvious. That is precisely the unilateral edit the whole ruling process exists to prevent, and it is invisible in a finished file — it reads as clean prose.

Diff the smoothed quotes against the source and read every word-level change:

```bash
for n in 01 02 03 04 05; do
  diff <(grep '^> ' <scene-dir>/${n}*.md) \
       <(grep '^> ' <session-dir>/scene_extractions_smoothed/${n}*.md)
done
```

Punctuation, capitalisation, filler and false-start changes are covered by the calibration approval. **Every substantive word change must map to a card the GM approved.** Anything that does not, revert to verbatim and add it to `carry_forward` — it is a candidate for next time, not yours to fix now.

Phandalin ch4 caught three this way (`"Why'd that cost us the gold?"`, `"those interested ones"`, `"transport you poorly"`), all in one scene, all made in good faith while writing. They were reverted and reported as unruled. **When the GM later said to fix them, going back to the tape showed one of the three confident guesses was wrong** — the line was a statement, not the question it had been "corrected" into. That is the whole argument for this check: a plausible repair is not a correct one, and the only thing separating them is evidence the GM has seen.

### 6. Write the manifest — REQUIRED

Rulings made in conversation and applied as scattered annotations are unreconstructable a week later. Write `<session-dir>/voice_smooth.sources.yaml` recording:

- scene count, quote-line count, and **the garble-ruling count broken down by scene**
- the resolved voice specs, and any NPC characterization source used
- **which transcripts were consulted and what each is good at** — this is per-campaign knowledge that makes the next run faster. Record which files turned out to be **the same text**, by name; that is the single most time-saving line in the manifest for whoever runs this next.
- the **verdict counts** from the review round trip, including how many came back undecided and were re-asked — so a later reader can see the checkpoint held
- the calibration decisions the GM approved (filler aggressiveness, grammar repair, stage-direction split, truncation handling)
- every **scope** ruling — de-duplication boundaries, player-name policy, knowledge boundaries — with what moved where
- garbles **kept deliberately**, and why, so a later reader doesn't re-flag them
- glossary rows written back, and any registry/glossary conflict found
- upstream defects found but not fixed, and `carry_forward` for anything left open

Validate it parses (`python3 -c "import yaml; yaml.safe_load(open(...))"`). Watch the indentation trap: keys that follow a list at the same indent level get swallowed into the sequence.

### 7. Hand-off
Note that `session_doc` should now read from `scene_extractions_smoothed/` (the verbatim `scene_extractions/` and the VTT remain the record).

Say explicitly that **re-running the extractor would discard this pass**, and name what is now true only in the smoothed layer — de-duplication, splice repairs, knowledge-boundary annotations. That is the difference between the GM knowing the smoothed layer is authoritative for narration and losing a day's rulings to a routine regeneration.

## Conventions

- **Verbatim is immutable.** Never write to the VTT or `scene_extractions/`. This skill's only output is `scene_extractions_smoothed/`.
- **Never carry a claim you cannot keep.** The output heads its moments section `## Voiced moments`, never `## Verbatim moments` — see step 3.
- **Voice files are authoritative** — read them first, preserve the voice, never homogenize. When a player corrects a characterization, the voice file wins; update it there, not here.
- **Preserve, don't rewrite.** Readability + voice only. Names, numbers, mechanics, attribution, and *meaning* are off-limits.
- **Don't over-smooth.** Deliberate style is voice; only transcription noise and genuine unreadability get cleaned. A character who rambles on purpose should still ramble.
- **Deciding a name is upstream; spelling a settled one is here.** Establishing *who someone is* is an identity decision belonging to `/session-summary-consistency` and the registry — never make one in this layer. But applying a form the registry has **already** settled is spelling, not identity: `Utgartian` → `Uthgardtian`, `Colin` → `Cullen`, `a house like Astra` → `House Margaster`. Check the registry first, say which authority you are applying, and offer the glossary write-back.
- **Common-word garble is ruled here.** `app`/`hack`, `confront-free`/`conflict-free`, `bloom`/`show` are in no glossary and trip no registry check, so they survive every upstream pass and surface only when a human reads the line. Rule them here with the GM (step 2.5) and record what was ruled.
- **Scope belongs to the human.** What belongs in which scene, and who knows what, are precision decisions — never settle a de-duplication boundary or a player-vs-character knowledge question yourself (step 1.5).
- **Knowledge boundaries need a home outside this layer.** An annotation in a derived file dies at the next `scene_extract`. Push it to a hand-authored `docs/` dossier with a `CLAUDE.md` pointer.
- **No card, no change — in THIS layer.** A word you repair without an approved ruling is a unilateral edit no matter how obvious it looked, and obvious is not a track record (one in three of ch4's "certain" readings was wrong). If you notice it while writing, revert it and put it in `carry_forward`. Audit for these before you report done (step 5).

  **The rule governs the smoothed layer, which is a record. It does not govern downstream narration, and it never governs *reporting*.** Phandalin ch4 got this backwards: asked to find logic breaks in the finished narration, the pass spotted `"let's try to freeze it"` sitting one line after `"All right, let's free the slaves!"`, declined to touch it by citing this rule, and wrote the refusal into the audit comment as considered judgment — dressing a wrong call up as a careful one. The GM had asked for exactly that class of defect. A rule that stops you editing a transcript must never stop you saying *"this sentence contradicts the one before it."* When in doubt, surface it; silence is the one option that is always wrong.
- **An unmarked card is not a decision, and a three-word note is not a specification.** Re-ask what came back undecided; confirm what a terse DISCUSS note meant before applying it; bring exact wording back when the ruling would invent canon.
- **Two files with different names are not two readings.** Prove independence before treating one transcript as corroboration for another — identical passes agreeing with themselves is the most convincing worthless evidence you will meet here.
- **Human reviews before session_doc.** This is a first-draft render, not a final artifact.

## Why this design

Smoothing is *rendering* — exactly what LLMs are good at ("taking verified structure and making it feel alive"). It is safe here because: the raw record is preserved (VTT + verbatim extractions untouched), it writes only a derived copy, each line is guarded by an authoritative voice file, and a human reviews the render before it feeds the next stage. That is the house pattern — *LLM extracts → human imposes structure → LLM renders inside it* — applied to the quote layer.
