---
name: voice-smooth
description: Render the verbatim scene-extraction quotes into readable, in-voice prose — a derived scene_extractions_smoothed/ layer that sits between /session-summary-consistency and session_doc. Uses each character's voice file as the guardrail. Fixes garble, run-ons, and disfluencies for readability WITHOUT changing what was said; never touches the verbatim (the VTT stays the raw record). Invoke as /voice-smooth [session-dir].
tools: Read, Bash, Write, Edit, Glob, AskUserQuestion, Artifact, WebFetch
---

# Voice-Smooth — voice-aware readability rendering of quotes

Turn the raw, transcriber-corrected verbatim quotes into **readable prose that still sounds like the character who said it**, written to a *derived* `scene_extractions_smoothed/` layer for `session_doc` to consume. This is a **rendering** step, not an error-fix and not narration.

## Where this sits (and the one inviolable rule)

```
VTT  (raw verbatim — IMMUTABLE, forever the record + the voice-file raw material)
  → scene_extractions/           (verbatim; transcriber errors fixed by /session-summary-consistency)
  → [THIS SKILL] voice-smooth    (readable, in-voice; guarded by voice/<char>_voice.md)
      → scene_extractions_smoothed/   (DERIVED — what session_doc reads)
  → session_doc narration
  → /voice-critic (checks the finished narration against the voice spec)
```

**Inviolable rule: the verbatim is never mutated.** This skill only ever *writes* `scene_extractions_smoothed/`. It does **not** edit the VTT or `scene_extractions/`. Because the raw quotes live permanently in the VTT, the smoothed layer is a safe derived rendering — not a rewrite of a record.

## What this is — and is NOT

- **IS:** readability + voice. Collapse run-ons, drop filler ("you know / like / I mean" *as noise*), repair genuinely unreadable fragments, punctuate — *while preserving each character's register, tics, and vocabulary* per their voice file.
- **IS NOT — error correction.** Fixing what the *transcriber* got wrong (`snake`→sneak, `Hulkrist`→Alkrist) is `/session-summary-consistency`'s job and must be done **first** (see Precondition).
- **IS NOT — narration.** Turning quotes into flowing scene prose is `session_doc`'s job. This produces cleaner *quotes*, not narration.
- **IS NOT — critique.** Checking finished narration for voice drift is `/voice-critic`'s job.

## Precondition — run `/session-summary-consistency` first

Smooth *corrected* quotes, not garbled ones. If the verbatim still contains obvious transcription errors (mis-heard names, garbled phrases), run `/session-summary-consistency` first — otherwise you will fluently render a mistake. If you spot residual transcription errors while smoothing, **stop and flag them** for that skill; do not silently "fix" them here (that decision belongs upstream, against the glossary).

## Inputs

- **session-dir** — `summaries/YYYYMMDD/`. Default: CWD (if CWD is the campaign root, ask which session).
- **scene dir** — `<session-dir>/scene_extractions_new/` **or** `<session-dir>/scene_extractions/` (suffix varies). Detect it; call it `<scene-dir>`.
- **voice files** — `<campaign-root>/voice/<char>_voice.md`, plus `voice/_genre.md` (overall tone). **Authoritative** for how each character speaks.
- **player→character map** — from the glossary `## Player names → characters` section (only needed if any labels still carry real names — they shouldn't after /session-summary-consistency).

## Workflow

### 0. Choose the review mode
Before anything else, one `AskUserQuestion`:

> **Review the smoothed pairs in an artifact, or here in the shell?**
> - **Artifact** — one page of the flagged renderings, mark them at your own pace, save once.
> - **Shell** — pairs grouped by scene in the conversation, the way this skill has always worked.

Ask this every run; do not remember a default. **The one-scene calibration in
step 4 happens in the shell either way** — it is a conversation about how hard
to smooth, not a list of rulings, and it has to settle before there is
anything worth batching. Artifact mode replaces only the *post-calibration*
review. See **Artifact mode** below.

### 1. Locate + load the guardrails
- Detect `<scene-dir>`; if missing, stop.
- `ls voice/` and read **every** `voice/*_voice.md` + `voice/_genre.md`. Build a `speaker → voice-spec` map. **Read a character's voice file before smoothing a single one of their lines** (voice files are authoritative — global campaign rule).
- Speakers with no voice file:
  - **GM** (narration / OOC / rules) → render as clean, plain GM prose; do not invent a voice.
  - **GM as <NPC>** → draw the NPC's characterization from its dossier (`docs/npcs/`) **or the session prep docs** (`notes/session_prep/`, `notes/sessions/`) if either gives you one, else a neutral, readable rendering. Never flatten a distinctive NPC into GM-neutral when a source gives you a voice — this run rendered Kalan (precise, professorial), Bookwyrm (compliment-as-warning, maternal-turned-glacial), Grygum (warm-as-method reassurance), and Daral (effusive) from prep/dossier characterization, not from PC voice files.

### 2. Smooth each quote (per scene, under `## Verbatim moments`)
For every quote block:
1. Identify the **speaker** and load their voice spec.
2. Produce a **smoothed** version that is:
   - **Readable** — complete sentences, filler-as-noise removed, false starts collapsed, garbled fragments repaired *only where meaning is unambiguous* (else keep the fragment or mark `[unclear]`).
   - **In-voice** — keeps the character's register, characteristic vocabulary, sentence rhythm, and signature tics. Thorin's clipped bluntness and Zalthir's hedging verbosity are **voice, not error** — preserve them. Do **not** homogenize everyone into the same neutral prose.
   - **Faithful** — same meaning, same content, **same names, numbers, mechanics, and attribution**. Add nothing; drop no substance. If you can't smooth a line without changing what it means, leave it closer to verbatim.
3. **OOC / table chatter** (jokes, rules talk, real-world tangents): smooth *lightly* for readability only — do **not** force it into in-character voice, and keep any OOC marker. When in doubt, leave OOC lines near-verbatim.
4. **Mixed-attribution blocks.** The extraction often tucks a reply from another speaker *inside* a quote block (a GM or NPC line under a PC's label). Render each line in the correct voice and **tag the interloper inline** (`[GM]`, `[Kalan]`, `[Bookwyrm]`, `[Dawnbringer]`), but do **not** re-attribute the block's label — that is an upstream fix; flag it, don't silently move it.

### 3. Write the derived layer
Write `<session-dir>/scene_extractions_smoothed/NN_slug.md`, **mirroring the verbatim file's structure** (frontmatter, `## Scene summary`, the moments section, and the same speaker labels) so it is a drop-in for `session_doc`. Mark it as derived:
- frontmatter `source: voice-smoothed` and `from: ../scene_extractions/NN_slug.md`
- copy the `## Scene summary` across, but **scrub player real names as you copy** (e.g. `Kostadis → GM`, via the glossary `## Player names → characters` map) — these summaries routinely leak the GM's real name, and copying it forward propagates the leak. **Flag** (don't rewrite) any transcription garble you notice in the summary (its origin is gm-assist / the scene-extract step). Leave the summary's wording and facts otherwise unchanged.
- replace each verbatim quote's text with its smoothed rendering under the same speaker label

Do **not** modify anything under `<scene-dir>/`.

### 4. Human review — REQUIRED before it feeds session_doc
Smoothing changes words, so the human is the checkpoint (LLM drafts → human reviews → then it feeds `session_doc`).

**Calibrate on one scene first.** On a first run for a session (or a new campaign), smooth a single representative scene, present *its* pairs, and get the voice fidelity and the grammar-fix aggressiveness approved **before** rendering the rest. It catches over/under-smoothing early and keeps the review tractable. (Calibration question that came up this run: how aggressively to repair grammar the *player* actually spoke — clear-meaning fixes like "we got a nail Bookwyrm" → "we've got to nail Bookwyrm" are fair game; ambiguous ones stay near-verbatim; suspected *transcription* errors get flagged upstream, never smoothed away.)

After writing the draft layer, present **verbatim → smoothed pairs**, grouped by scene, and explicitly flag any rendering that:
- risks changing meaning, or
- risks flattening / over-correcting the character's voice, or
- required repairing an ambiguous fragment.

Ask: *"Approve these, edit specific ones, or want a different smoothing pass on any character?"* Apply edits to the `scene_extractions_smoothed/` files only.

### 5. Hand-off
Note that `session_doc` should now read from `scene_extractions_smoothed/` (the verbatim `scene_extractions/` and the VTT remain the record).

## Artifact mode (batch review)

Replaces the second half of step 4 — the full-run pair review. Steps 1–3, the
calibration gate, and step 5 are unchanged. Full contract:
`~/.claude/skills/_shared/review-artifact/CONTRACT.md`.

**Calibrate in the shell first.** Do not build an artifact until the GM has
approved the smoothing register on one representative scene. A page built at
the wrong aggressiveness is a page of wrong answers.

### What is auto-applied, footer only

Renderings that trip **none** of step 4's three flags — they do not risk
changing meaning, do not risk flattening the character's voice, and did not
require repairing an ambiguous fragment. These are already written to
`scene_extractions_smoothed/`; list the count per scene in the `footer`.

### What becomes a card

The flagged ones, and only those. One card per verbatim → smoothed pair.

```json
{ "id":  "s04-q07",
  "t":   "Brewbarry, scene 04 — ambiguous fragment repaired",
  "y":   "Keep the smoothed rendering in <code>scene_extractions_smoothed/04_*.md</code>.",
  "n":   "Revert this quote to the verbatim text. Nothing else in the file changes.",
  "ev":  "Verbatim: <em>“we got a nail Bookwyrm”</em><br>Smoothed: <em>“we've got to nail Bookwyrm”</em><br>Flag: <b>repaired an ambiguous fragment</b> · voice file <code>voice/brewbarry_voice.md</code>" }
```

**Both texts go in `ev`, verbatim first.** The GM is judging a rewrite; a card
that shows only the result is unreviewable. Say which of the three flags
fired, and name the voice file that governed the rendering.

Id as `s<NN>-q<NN>` (scene, quote index) so the apply step can find the line.
Keep cards grouped by scene, in scene order.

### Publish, then stop

Hand over the link and **stop**.

**Two ways the save reaches you, and one that is forbidden.**

- **The notification.** Publishing arms a live subscription on this session. When
  the GM saves, an `artifact-changed` task-notification naming this artifact
  arrives on its own — **that is the save signal.** Act on it: `WebFetch` the URL
  and read the decisions without waiting to be told. It can lag (the subscription
  arms in the background), and it only lives as long as the session that
  published.
- **The GM's word.** If the session was restarted, or the notification never
  comes, the GM simply says they are done. Same action.
- **Never poll.** Not on a timer, not "just checking" — the two routes above
  cover every case, and a poll loop burns a turn per check for nothing.

A notification means *the page was republished*, nothing more. It is not the GM
speaking and it is not approval of anything: the decisions come from the state
block, and `read_decisions.py` still refuses a page whose `savedAt` is null.

Then `WebFetch` the URL and run `read_decisions.py`.

### Verdict mapping

| verdict | action |
|---|---|
| **approve** | Nothing to do — the rendering is already in the smoothed layer |
| **reject** | Revert that one quote to its verbatim text in `scene_extractions_smoothed/` only |
| **discuss** + note | Apply the GM's wording; if the note asks for a different pass on a character, re-smooth **all** of that character's quotes and bring the new pairs back |
| **discuss**, no note | Back to the shell, grouped with the other discussed pairs |
| **unmarked** | Undecided — the smoothed rendering stands, but say which ones were never looked at before step 5 hands off |

**Never touch `<scene-dir>/` or the VTT.** Reverting means rewriting the
derived file to match the verbatim, not editing the record.

**Transcription errors still escalate.** If the GM's note says a quote is
wrong in the *source*, that is a `/session-summary-consistency` item — flag
it, do not smooth it away.

## Conventions

- **Verbatim is immutable.** Never write to the VTT or `scene_extractions/`. This skill's only output is `scene_extractions_smoothed/`.
- **Voice files are authoritative** — read them first, preserve the voice, never homogenize. When a player corrects a characterization, the voice file wins; update it there, not here.
- **Preserve, don't rewrite.** Readability + voice only. Names, numbers, mechanics, attribution, and *meaning* are off-limits.
- **Don't over-smooth.** Deliberate style is voice; only transcription noise and genuine unreadability get cleaned. A character who rambles on purpose should still ramble.
- **Errors are upstream.** Residual transcription mistakes → flag for `/session-summary-consistency`; do not fix them here.
- **Human reviews before session_doc.** This is a first-draft render, not a final artifact.

## Why this design

Smoothing is *rendering* — exactly what LLMs are good at ("taking verified structure and making it feel alive"). It is safe here because: the raw record is preserved (VTT + verbatim extractions untouched), it writes only a derived copy, each line is guarded by an authoritative voice file, and a human reviews the render before it feeds the next stage. That is the house pattern — *LLM extracts → human imposes structure → LLM renders inside it* — applied to the quote layer.
