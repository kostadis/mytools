---
name: vtt-spell-pass
description: Clean up Otter/Zoom VTT transcripts for a D&D campaign — applies the known-misspellings glossary and prompts the user about unrecognised proper nouns. Invoke as /vtt-spell-pass [vtt-path].
tools: Read, Glob, Grep, Bash, Edit, Write, AskUserQuestion, TaskCreate, TaskUpdate, ToolSearch, Artifact, WebFetch
---

# VTT Spell Pass

Clean up a campaign session's VTT transcript with two complementary passes:

1. **Known-misspellings pass** — apply every wrong→right replacement already
   recorded in the campaign's corrections glossary.
2. **Unknown-proper-noun pass** — flag every Capitalised token (or run) in
   the transcript that is **not** in the campaign's known-names set
   (glossary canonicals + NPC dossiers + extras). Treat each unknown as a
   suspect new misspelling. Ask the user, one at a time, what each one
   should map to (or whether it's a real new name to add to the known set,
   or table-chatter to ignore).

The user's stated invariant: *"I know all the NPCs. If a proper name appears
in a transcript that isn't in our notes, it's a misspelling."* The skill
operationalises that: the unknown set IS the candidate-misspelling set.

**Where this sits:** after `/speaker-attribution` (or `/transcript-rebuild`), before `enhance_summary`. Run it on the **unlabelled** tape, never on a `.speakers.vtt` — the glossary's player→PC rows would rewrite the speaker labels — then re-apply the approved speaker mapping to the `.cleaned.vtt`. Full order: `~/src/CampaignGenerator/docs/design/SkillPipelineOrder.md`.

## What this skill delivers — read this before Phase 5

**The deliverable is a set of entries in `transcript_corrections.yaml`, not a
cleaned `.vtt`.**

A session's `<stem>.transcript.cleaned.vtt` is *generated* by
CampaignGenerator's `sd_corrections apply` from that cue-indexed record
(issue #250 R4); the raw `<stem>.transcript.vtt` is the archive and is never
written. So this skill never writes either file. It writes a **candidate**
transcript to scratch, and Phase 7 converts the candidate's diff into record
entries the GM reviews.

This is not bookkeeping pedantry. The arrangement that predated the record —
a spell pass writing the cleaned tape directly — put 74 unenumerated
substitutions into Phandalin ch46, three of which inserted a surname nobody
spoke. Every verbatim guarantee downstream is measured against that file. If
you write it here instead of recording the diff, `sd_corrections check`
reports the cues as unexplained and the next `apply` throws the whole pass
away.

Two consequences to keep in mind from Phase 0 onward:

- **Never write a transcript into the session directory.** Not the cleaned
  tape, not the candidate, not a filtered or deduped copy, and not a stray
  `.vtt` of any kind: `sd_corrections` finds the raw tape by globbing every
  non-`.cleaned` `*.vtt` in the directory and demands exactly one, so a
  candidate parked next to the original makes its commands fail. Every
  transcript this pass produces goes to `$SCRATCH`. The one exception is the
  review record: the Artifact-mode items, page and decisions files live in
  `<session-dir>/spell_review/` (see Artifact mode), so the question the GM
  was asked survives beside the tape. That folder holds `.json`/`.html` only —
  never a `.vtt`.
- **`apply_replacements.py --output` is required and has no default**, and it
  refuses to write a file an existing record claims. There is no `--in-place`.

## Required inputs

Detect or ask:

1. **VTT path** — from args, or default to the most recent
   `summaries/*/[Gg][Mm][Tt]*.vtt`. List candidates if ambiguous.
2. **Campaign root** — CWD if it contains `notes/vtt_transcription_corrections.md`,
   otherwise walk up.
3. **Glossary path** — `<campaign>/notes/vtt_transcription_corrections.md`.
   If missing, abort and tell the user to seed it (this skill assumes a
   glossary already exists in the documented format — see Out of the Abyss
   for the canonical example).
4. **NPC dossier dir** — `<campaign>/docs/npcs/` if present.
5. **Entity registry — the canonical known-names source.** If
   `<campaign>/docs/entity_registry.yaml` exists, pass it directly via
   `--registry` on **both** scripts (`find_unknowns.py`
   and `cluster_unknowns.py` read it natively — no flattening, no
   `registry.py project` regeneration first, always current with the last
   registry edit). A registry name or alias is, by construction
   (`registry-cleanup/SKILL.md`'s rule), an approved canonical alternate
   name — **never** a mishearing — so it is always safe to treat as known.
   If no registry exists yet but `docs/entity_inventory.md` (its older,
   generated markdown projection) does, fall back to flattening that one
   file per the bullet steps below and pass it via `--extra-known` instead.

6. **Verified-noun dictionaries** — flat, one-name-per-line files of
   confirmed proper nouns (module NPCs, creatures, spells, locations,
   deities) that should be treated as known and therefore never surfaced
   as candidate misspellings. These are *not* the glossary — they are
   pre-verified vocabulary that suppresses false positives and improves
   clustering (dictionary entries also become canonical replacement
   targets). **Auto-detect the conventional flat path
   `<campaign>/notes/proper_nouns_adventure.txt`. Surface what you found
   and ask the user to confirm or add more before running Phase 1.** Pass
   every confirmed flat file to both scripts via `--extra-known` (the flag
   accepts multiple paths).

   Format matters: `--extra-known` treats every non-`#` line as a name, so
   only feed flat one-per-line dumps. Do **not** pass a markdown file raw
   (tables, `- **Name** — description` bullets, prose) — it injects markup
   and prose fragments into the known set and can silently suppress real
   unknowns.

   **Flatten generated markdown sources first.** `notes/vtt_known_additions.md`
   (and `docs/entity_inventory.md`, only when used per #5's fallback) are
   valuable name sources but are markdown, not flat. Extract each into a
   throwaway `.txt` in your scratchpad, then pass the `.txt`:
   - pull every `**bold**` span from each `- ` bullet line;
   - split each span on ` / ` (multi-alias entries like
     `**Whistlerites / Miloites / Protanthians**` become three names);
   - unescape `\'` → `'` (e.g. `Drow\'s`);
   - dedupe case-insensitively, one name per line.

   **`vtt_known_additions.md` can hold stale entries.** It records
   "real name, not a misspelling" rulings from prior passes, but some may
   since have been reclassified — a name the glossary now treats as a
   *wrong-form*. This run, `Callan Strongbench` was listed here as canonical
   but the glossary maps it → `Kalan Strongbranch`; a stale "known" entry
   silently suppresses a real unknown. When you flatten it, flag any entry
   that also appears as a glossary wrong-form to the user — the glossary wins.
   (`vtt_known_additions.md` is also not yet fed into the registry's own
   `triage-candidates` queue — CampaignGenerator#141 — so a name confirmed
   here today does not promote itself into the registry; that's still a
   separate, manual step via `/entity-triage` or `registry add`.)

   If no dictionary exists, proceed without one — it is an enhancement, not
   a hard dependency.

7. **Retranscription context (when available)** — if `<vtt>`'s filename
   contains `.retranscribed` or `.retranscribed.cleaned` (i.e. it's an
   `audio-to-vtt` output, not a plain Otter/Zoom export), two extra
   sources exist and should be used:
   - **Zoom's original transcript**, the sibling file with those suffixes
     stripped (`<x>.transcript.retranscribed.cleaned.vtt` →
     `<x>.transcript.vtt`). `zoom_context.py` (this skill's directory)
     looks up Zoom's original cue for any context excerpt — see "Cross-
     referencing Zoom's original" under Phase 3.
   - **`<vtt-stem>.proper_nouns.md`**, if `retranscribe.py` already
     produced it — a report (from the sibling `audio-to-vtt` project)
     flagging cue groups where the campaign vocabulary is confidently
     present in the retranscription but doesn't appear in Zoom's original
     for that span. Skim it before Phase 3; it's the same underlying
     technique as `zoom_context.py` run in bulk ahead of time, and gives
     useful priors on which names this session's ASR struggled with most.
   Both are enhancements, not hard dependencies — a plain Otter/Zoom VTT
   with no `.retranscribed` sibling has neither, and the skill runs
   exactly as it always has.

8. **A second, independent transcription (when one exists)** — the same
   session transcribed by a *different* tool, with no shared timestamps and
   different segmentation (e.g. a voice-detection markdown export alongside a
   D&D-tuned WebVTT). This is NOT the `.retranscribed` pairing in #7, which is
   filename- and cue-aligned; here nothing lines up, so matching is by text.
   Use `sibling_context.py` (Phase 3). Check the session directory for one
   before starting — if two transcripts of the same date exist, you have this.

9. **The published module, via the `5etools` MCP server (when the campaign
   runs one).** The campaign's own stores — glossary, registry, dossiers —
   only know names the table has already written down correctly at least
   once. A name the party met for the *first time* this session is in none of
   them, so every fuzzy-match and cluster signal will call it new canon. The
   module knows it, and knows how it is spelled.

   `search` (the whole name, or a distinctive fragment) and `get_section` are
   the two verbs. Scope with `source_ids` when you know the module, or search
   unscoped and read which source comes back. See "Consult the module" under
   Phase 2.5 for when to reach for it.

## Workflow

### Phase -1 — choose the review mode

Before anything else, one `AskUserQuestion`:

> **Review the candidates in an artifact, or here in the shell?**
> - **Artifact** — one page, every pair that needs a ruling, mark them at your own pace, save once.
> - **Shell** — one cluster at a time, the way this skill has always worked.

Ask this every run; do not remember a default. If they choose the artifact,
Phases 0–2.5 run exactly as written and **Artifact mode** below replaces
Phase 3. Phases 4–7 are shared.

### Scratch files — one namespace per run, never a fixed path

Every intermediate below goes in a per-run scratch directory. Set it once and
use `$SCRATCH` everywhere:

```bash
SCRATCH="${CLAUDE_SCRATCH:-/tmp}/spell_pass_$(basename <session_dir>)_$$"
mkdir -p "$SCRATCH"
```

This matters because the intermediates are **read back**, not just written.
Phase 1's collapse step writes a preview, then re-scans that preview to compute
the true residual. With a fixed `/tmp/preview_current.vtt`, two runs in flight at
once — two chapters, two terminals, two agents — silently interleave: run A
writes its preview, run B overwrites it, run A scans B's chapter. Nothing
crashes and no output looks wrong; run A just reports a residual for a transcript
it never read. Same hazard for `/tmp/scan_src.txt` and the cluster JSON.

If you are processing more than one transcript, **assert before every re-scan**
that the file you are about to read is the one you just wrote — compare line
count or sha256 against your own input. A cheap check here is the difference
between a wrong answer and a caught mistake.

### Phase 0 — normalise the input (deterministic, no LLM)

Do not assume the input is a plain Otter/Zoom WebVTT. Run:

```bash
python ~/.claude/skills/vtt-spell-pass/prepare_input.py \
  --input <transcript> --scan-copy "$SCRATCH/scan_src.txt"
```

It reports three things that change the rest of the run:

- **`format`** — `webvtt`, `labelled_markdown`, `labelled_text` or `plain`.
  `find_unknowns.py` strips `Name:` / `Name (Player):` labels but NOT
  markdown-bold ones (`**dave:**`), so for `labelled_markdown` you MUST scan
  the `--scan-copy`, not the original. Apply replacements to the ORIGINAL in
  Phase 5 — the scan copy is only for candidate gathering.
- **`speakers`** — who is attributed and how often. A file reporting *no*
  speakers cannot support quote attribution at all; if the GM needs speakers
  (they usually do), that file cannot be the deliverable no matter how clean
  its text is. Say so before doing the work, not after.

  `prepare_input.py` counts `Name:` cue labels in WebVTT and plain labelled
  text as well as `**name:**` in markdown. (It used to count markdown only, and
  reported `speakers: none detected` on a WebVTT whose 1,008 cue lines *all*
  carried `Name:` prefixes — acting on that false negative would have meant
  telling the GM their transcript could not be used.) A `none detected` is
  still worth one cheap cross-check before you tell the GM anything:

  ```bash
  grep -oE '^[A-Za-z][A-Za-z ._()-]{1,30}:' <vtt> | sort | uniq -c | sort -rn
  ```

  A speaker count is also a party roster check. Four labels where the campaign
  has five players means **someone was absent**, which changes how you read
  third-person references to their character — see the absent-player failure
  mode in `/consistency-check`.
- **people in the room who are not at the table.** A partner, a child, or a
  housemate wandering through gets transcribed like anyone else, and every
  proper noun in their speech becomes a candidate the GM must dismiss by hand
  (`Ben didn't find this funny` → `Ben`). If the speaker list contains a label
  you don't recognise as a player or the GM, **ask** who it is before Phase 1
  rather than scanning their lines. Then:

  ```bash
  # keep their lines in the file, just don't mine them for names
  prepare_input.py --input <t> --exclude-speaker natasha --scan-copy "$SCRATCH/scan.txt"
  # a label-preserving copy without their lines, for reading only
  prepare_input.py --input <t> --exclude-speaker natasha --filtered-output "$SCRATCH/filtered.md"
  ```

  `--scan-copy` filtering is always safe. `--filtered-output` writes a copy
  with content deleted — a reading and scanning aid, never the deliverable —
  so it goes to `$SCRATCH` like every other derived transcript.

  **But do not feed a `--filtered-output` or `--dedup-output` file to Phase 5.**
  Both drop cues, and `sd_corrections import` pairs the two transcripts by cue
  index — it refuses a mismatched pair outright (*"the two transcripts do not
  carry the same cue indices"*), so a filtered candidate cannot be recorded at
  all. Filtered and deduped copies are for **scanning**; apply against the full
  transcript. If the GM genuinely wants a speaker's lines gone from the tape,
  that is a separate cue-level decision recorded in
  `transcript_corrections.yaml`, not a side effect of the spell pass.
- **`duplication`** — whether the body is recorded twice. This does not break
  replacement, but it **doubles every occurrence count**, so every "26x" you
  put in front of the GM is really 13. Detect it here, and pass
  `--dedup-output` to write a single-copy file. Do not eyeball this with a
  midpoint split: one split or merged utterance shifts everything after it and
  makes a 99.8%-identical duplicate look ~60% similar. The script anchors on
  the repeated first line and aligns with difflib.

### Phase 1 — gather candidates (deterministic, no LLM)

Run `find_unknowns.py`, piping into `cluster_unknowns.py`:

```bash
python ~/.claude/skills/vtt-spell-pass/find_unknowns.py \
  --vtt <vtt> \
  --glossary <campaign>/notes/vtt_transcription_corrections.md \
  --npcs-dir <campaign>/docs/npcs \
  --extra-known <campaign>/notes/proper_nouns_adventure.txt \
  --registry <campaign>/docs/entity_registry.yaml \
  --min-count 1 \
| python ~/.claude/skills/vtt-spell-pass/cluster_unknowns.py \
  --glossary <campaign>/notes/vtt_transcription_corrections.md \
  --npcs-dir <campaign>/docs/npcs \
  --extra-known <campaign>/notes/proper_nouns_adventure.txt \
  --registry <campaign>/docs/entity_registry.yaml \
  > "$SCRATCH/clusters.json"
```

`--registry <campaign>/docs/entity_registry.yaml` is the canonical
known-names source. Omit it only when the campaign has no registry; then, and
only then, required-input #5's fallback applies — flatten
`entity_inventory.md` and pass the `.txt` via `--extra-known`.

`--extra-known` accepts multiple paths — pass every dictionary the user
confirmed in required-input #6 (omit the flag if none exist), plus the
flattened inventory when #5 fell back to it.

**`--npcs-dir`, `--registry` and `--extra-known` are optional, and a path you
name must exist.** A campaign need not have `docs/npcs/` (`out-of-the-abyss`
does not): omit `--npcs-dir` from **both** commands when required-input #4
found no dossier dir. But a path that is passed and does not exist makes
either script exit 1 (`Error: --npcs-dir path does not exist: …`), because a
typo there would otherwise drop a whole source of known names without a word.
Pass the identical set of these flags to both scripts, or the two known sets
diverge.

`find_unknowns.py` emits the raw unknown-token list with counts and
contexts. `cluster_unknowns.py` then:

- **Bound clusters** — every token within edit distance ≤ 1/2/3 (length-
  scaled) OR matching phonetic key of a known canonical or wrong-form
  is grouped under that canonical. *One question per canonical replaces
  N questions per variant.*
- **Cross-unknown clusters** — remaining tokens that look like each
  other (ed ≤ 2 with first-letter match, or matching phonetic key) get
  grouped together. The user names the canonical once and all members
  get glossed.
- **Singletons** — leftovers each get a one-member cluster.

Each cluster carries a confidence (high/medium/low) and a reason
(`exact` / `substring` / `edit_distance` / `metaphone` / `phonetic` /
`cross-unknown` / `singleton`). `metaphone` = a vendored Double Metaphone
code match (models pronunciation, links variants that cross the first
letter like Elvara↔Ilvara); `phonetic` = the crude devowel fallback key,
used when Double Metaphone finds nothing or its module is unavailable.

Also run the state filter:

```bash
python ~/.claude/skills/vtt-spell-pass/state.py \
  --state <campaign>/notes/.vtt_spell_pass_state.json show
```

Drop any cluster whose only member is in `ignored_tokens` — the user
already said "not a name, ignore" in a prior run.

**Sanity check before continuing:** `find_unknowns.py`'s
`known_names_count` should be in the hundreds for a mature campaign. If
it's <50 the glossary or `docs/npcs/` isn't being read correctly —
investigate before bothering the user with hundreds of false positives.
If `--registry` was passed, also check `registry_names_count` is nonzero
(0 with a real registry file usually means the wrong path was passed, or
the YAML has no `entities:` key).

**Collapse the set first: apply the current glossary, then re-scan.**
Before surfacing anything, run `apply_replacements.py` with the *existing*
glossary to a throwaway copy, then re-run `find_unknowns.py` +
`cluster_unknowns.py` on that cleaned copy. This removes every token the
glossary already knows how to fix (e.g. `Bookworm`, `Alcrist`, `Gergam`)
and leaves the **true residual** — the tokens that actually need a decision.

```bash
python ~/.claude/skills/vtt-spell-pass/apply_replacements.py \
  --vtt <vtt> --glossary <glossary> --output "$SCRATCH/preview_current.vtt"
python ~/.claude/skills/vtt-spell-pass/find_unknowns.py \
  --vtt "$SCRATCH/preview_current.vtt" --glossary <glossary> \
  --npcs-dir <npcs> --extra-known <dicts> --registry <registry> --min-count 1 \
| python ~/.claude/skills/vtt-spell-pass/cluster_unknowns.py \
  --glossary <glossary> --npcs-dir <npcs> --extra-known <dicts> --registry <registry>
```

Many survivors are **false residuals**: multi-word capitalised runs whose
embedded name is *already correct* — `And Kalan`, `The Helmed Horror`,
`But Alkrist`, `How's Grygum`. The scanner flags them only because it can't
split the run. Don't ask about these; the name is right. Only surface a
residual when the embedded proper noun is actually wrong.

### Phase 2 — pre-classify candidates (LLM judgment, MINIMAL filtering)

Read the unknown list. Before asking the user, **only filter what is
unambiguously not a campaign name**. When in doubt, surface — the user
explicitly prefers being asked over silent dismissal.

Drop ONLY:

- **Confirmed real-world places** the user has previously talked about
  (e.g. "Greece", "Europe" in conversational context — but if a token
  doubles as a campaign location, surface it).
- **Pure stopwords** that snuck past the helper's list ("Sounds",
  "Mr" — pronouns and articles).
- **Capitalised mechanics** that are clearly D&D rules text ("Wisdom"
  in "Wisdom save", spell names like "Misty Step", "Tremor Sense").
- **Obvious garbage** — single letters, all-caps acronyms with no context.

DO NOT drop:

- **Anything that looks like a personal name**, even if you suspect it's
  a player name. (User invariant: there are very few players, the user
  knows them all by name, and if you guess wrong about whether something
  is a player vs an NPC misspelling, you will silently lose a real
  correction. Always ask.)
- **Anything that could be a place, faction, item, or deity** the user
  hasn't dossiered yet.
- **Multi-word capitalised phrases** — these are almost always real.

For everything that survives, you have your **candidate list**.

### Phase 2.5 — adjudicate against the second transcription (MANDATORY when one exists)

If Phase 0 / required-input #8 found a second transcription, check **every**
candidate against it BEFORE putting any of them to the GM:

```bash
python ~/.claude/skills/vtt-spell-pass/sibling_context.py \
  --sibling <other-transcript> --context "<excerpt from the candidate's contexts>"
```

This is not a spot-check and not an optional enrichment. It is the only
evidence available that distinguishes *a real name transcribed badly* from
*a word the ASR invented*, and fuzzy-match confidence cannot tell them apart —
a garbled token scores just as well against a known name whether or not the
underlying audio contained a name at all.

Read the result four ways:

- **Sibling spells the name correctly** → confirms the proposed canonical.
- **Sibling has ordinary words at that span** → *probably* no name here; the
  token is likely an ASR hallucination. Real examples:
  `You can just barely see the Grygum` vs `…see the game`; `Oh yeah, it's me.
  Summer, all right` vs `Oh, yeah, it's me. All right.` — neither name was
  spoken. **But run the two checks below before ruling**: this is the reading
  that has been wrong in practice, because it is also exactly what a
  *successful* vocabulary-primed recovery looks like from the other side.
- **Both transcriptions produce the same odd string** → usually genuine audio.
  Route it to "new canon", not to a correction — but see the contamination
  warning below before trusting agreement on a *name*.
- **Sibling shows a DIFFERENT plausible name** → do not rule. See below.

A low score (<0.55) is inconclusive, not negative — the sibling may not cover
that span. Say so rather than ruling.

**Two checks before calling any name invented.** Both were skipped in the
Phandalin chapter-04 pass, and skipping them produced a confident, fully
evidenced, wrong ruling.

1. **Normalise every source through the glossary first.** Run
   `apply_replacements.py` over the sibling and the pre-retranscription VTT,
   not just the file under review. A raw token comparison reports "the sibling
   does not contain this name" whenever the sibling spelled it a *different
   wrong way* — and the glossary exists precisely because names have many wrong
   spellings. Also flatten the sibling across speaker labels before testing
   containment: a mid-sentence speaker flip puts the corroborating half of a
   sentence under someone else's label, where a per-line search will not see it.

2. **Grep the previous session's transcripts for the candidate.** A name the
   table used recently is live vocabulary and is the single strongest signal
   that the audio really contained it.

Worked example — the ruling this section used to cite as a hallucination, and
which was wrong. The re-transcription read *"He's not late-stage Orsik. He's
not Orsik."*; the pre-retranscription pass read *"He's not late stage or not or
sick"*, and a raw search said Zoom had no "Orsik". All three readings of that
evidence were artifacts:

- Zoom **did** have it, spelled `Orsick` — an existing glossary wrong-form.
- Zoom's sentence was split four ways by mid-sentence speaker flips, so the
  corroborating fragment sat under a different speaker.
- `Orsik` is a real NPC, and the same player had said the name three times in
  the *previous session*.

The vocabulary priming had recovered a real name that generic ASR mangled into
"or sick" — the success case, misread as the failure case. **A
vocabulary-primed recovery and a hallucination are indistinguishable from the
transcripts alone**; what separates them is whether the name is already canon
and recently spoken.

**Establish what kind of transcriber the sibling is before weighing it.**
An acoustic ASR fails phonetically: it turns a name into a similar-sounding
non-word. An LLM-based, domain-tuned transcriber fails *semantically*: it
substitutes a plausible name it already knows — including one from a
**different campaign** — for the name actually spoken. The second failure mode
produces confident, well-formed, entirely fictitious output that looks like
strong evidence.

Confirmed instance (Phandalin chapter 04): the D&D-tuned VTT rendered
**Valphine** as **"Bramgrim"** five times. Bramgrim is a cleric in another of
the GM's campaigns; Valphine is a cleric in this one. Nothing phonetic connects
them. Reasoning from the sibling's spelling produced a proposal to rewrite a PC
name to another campaign's NPC — caught only because the GM recognised the
name. Note this also poisons the "both agree" rule: agreement with an LLM
transcriber is not independent corroboration.

So weight the sibling's evidence **by kind, not by score**:

| Sibling shows | Trust | Why |
|---|---|---|
| ordinary words / plain prose | medium | contamination swaps names for names, so this is usually a real absence — but only *after* the two checks above. Un-normalised, it is also what a correct recovery looks like (`Orsick` → "or sick") |
| a campaign-correct name | high | it is recovering real vocabulary |
| a *different* plausible name | **none** | possible cross-campaign substitution — GM rules, you do not |

When the two transcriptions disagree on *which character* was named, that is a
question for the GM with both readings shown, never a proposal.

**The auto-dismissal gate — the only candidate you may drop without asking.**
A candidate may be auto-dismissed only when **`count == 1` AND its sibling
reading is `ordinary_words`** (after the two checks above). Never on an
`inconclusive` reading (score < 0.55, or the span isn't covered), never on
`count ≥ 2`, never on a `different_name` or `campaign_correct_name` reading.
This is the same gate `batch/AGENT_BRIEF.md` sets for `auto_dismissed[]`, and
it applies in shell mode too. Every auto-dismissed candidate is **listed** —
token, count and the sibling line — in the page `footer` in Artifact mode, or
in the chat summary before Phase 3 in shell mode, so the GM can pull any of
them back. A dismissal nobody can see is a silent drop, which is the thing this
skill refuses to do.

**Why this is mandatory.** In the session this phase was written from, five
candidates (`Grygum`, `Grym`, `Gryumary`, `Gilly`, `Summer`) were proposed
from fuzzy matching, approved by the GM on that framing, applied, and only
then caught by the sibling check — every one was a hallucinated word, and one
more (`Thalne`) pointed at the wrong character. Confirmation by the GM does
not validate the evidence you gave them; it only validates their reading of
it. Get the evidence right first.

**The error runs both ways, and the second direction is worse.** That session
over-corrected — it proposed fixes for words nobody said. The Phandalin
chapter-04 pass made the opposite mistake: it presented a real, canon, recently
spoken NPC name as an invented one, with a confident three-source table behind
it. The GM caught it from memory alone. An over-correction adds a phantom the
registry audit will eventually surface; **a wrongly rejected name deletes a real
one and leaves nothing behind to notice** — no unknown token, no candidate, no
audit trail. When the two readings are close, prefer the one that keeps a name
alive and put it to the GM with both spellings shown.

**Consult the module before calling anything new canon.**

The sibling check answers *"was a name spoken here?"* It cannot answer *"is
that a real name, and is this how it is spelled?"* — for that, ask the module.

Run a `5etools` `search` for any candidate that is about to be routed to
**new canon**, and for any candidate whose surrounding line describes a thing
the module would name: a creature guarding a room, a clan, a shop, a deity, a
titled NPC, a magic item. Two lookups per session is typical; it is cheap and
it is often decisive.

Three outcomes:

- **The module has it, spelled differently** → it is a *correction*, not new
  canon. This is the case the rest of the skill cannot reach on its own.
- **The module has it, spelled exactly** → confirms the name and gives you the
  section to cite in the question.
- **The module does not have it** → genuinely new (GM invention, or a name the
  party coined). Route to `vtt_known_additions.md` as before.

Worked example (obelisk session 8). `Sarnak` appeared 5×, **both**
transcriptions agreed on the spelling every time, and the line was an NPC
introducing himself — textbook "real new name", and it was about to be logged
to `vtt_known_additions.md` as one. A `5etools` search returned *Phandelver
and Below: The Shattered Obelisk*, ch. 2, R8: *"a nothic named **Ssarnak**
guards this cave."* Double S. Independent-ASR agreement had confirmed that a
name was spoken; it said nothing at all about the spelling, because both
systems heard the same audio and neither had read the book.

That search paid a second dividend. Its results also named the magic sword
**Talon** — one letter from `Talan`, a wrong-form approved earlier in the same
run for `Thel`. The party looted Talon at the end of that session, so from the
next session on the rule is a live hazard. **Read what the module search
returns around your hit, not just the hit** — near-collisions with the row you
are about to write are exactly what you cannot see from the transcript.

### Phase 3 — ask the user, one CLUSTER at a time, ALWAYS

Per the user's stated preferences (memories: `feedback_question_style`,
`feedback_scope_discipline`, `feedback_vtt_spell_pass_confirm`), use
TaskCreate to enumerate clusters and AskUserQuestion to walk them one at
a time as multiple choice.

**Cross-referencing Zoom's original (when a `.retranscribed` sibling
exists — see Required input #7).** Before asking about a cluster, look up
Zoom's original text for one representative context excerpt:

```bash
python ~/.claude/skills/vtt-spell-pass/zoom_context.py \
  --vtt <vtt> --context "<a ~40-80 char excerpt containing the candidate>"
```

Prints `null` if there's no `.retranscribed` sibling, the pair doesn't
align (different `--max-group-seconds` than the original retranscribe.py
run — pass `--max-group-seconds` to match if known), or the excerpt isn't
found verbatim (try a shorter/exact substring from the candidate's own
`contexts` field). When it returns a hit, include Zoom's original line in
the question — it's often decisive, not just supporting color:

- It can **confirm a proposed canonical is right** even for a large,
  unusual mangle a fuzzy-match cluster would otherwise flag as
  low-confidence (obelisk session 6: "Zerabira" looked like a new
  character on its own, but Zoom's original for that exact cue was
  "...sorry, Vera is a 19" — clearly the existing PC "Veyra", not new).
- It can **overturn a high-confidence bound-cluster match**. Run this
  check even for clusters `cluster_unknowns.py` already scored high-
  confidence — a strong edit-distance/phonetic match to a known canonical
  says nothing about whether the underlying cue was intelligible speech at
  all (obelisk session 6: "Redbrand Exo" edit-distance-matched "Redbrand"
  at high confidence, got confirmed, and was only caught as wrong after
  the fact — Zoom's original for that exact cue turned out to be
  "Welcome Maxwell Press PS6 Short Short Short", equally unintelligible
  gibberish on both sides, not a real Redbrand mention either system
  missed).
- It can **rule out a mangle as a real name entirely** when Zoom's
  original is a plausible, coherent ordinary phrase at that span
  (obelisk session 6: retranscription's "...in the back of and Povit"
  vs. Zoom's cleaner "...back and forward" — "Povit" was a Whisper
  hallucination of "forward", not a name to fix).

This is a deterministic lookup (no LLM judgment), so it's cheap enough to
run for every cluster and singleton when the sibling exists — do not
skip it just because a cluster already looks high-confidence.

**Hard rule: every new wrong→right mapping requires explicit user
confirmation before being written to the glossary.** The cluster
proposal is exactly that — a *proposal*. The user always picks.

**Cluster ordering:** present in this order so the user makes the
highest-yield decisions first:

1. High-confidence bound clusters (proposed canonical, ≥2 members)
2. Medium-confidence bound clusters
3. Cross-unknown clusters (≥2 members, no canonical)
4. High-count singletons (count ≥ 3)
5. Low-count singletons (final bulk dismissal batch — acceptable to
   ask "any of these N tokens look like real names you want to address?"
   with a multi-select)

For each multi-member cluster, your AskUserQuestion shows the proposal:

```
Cluster #2  (3 members, 5 occurrences total)
Proposed canonical: "Glabbagool"
Members:
  - "And Glabbagool"   1x   "And Glabbagool, of course, is really happy to..."
  - "Does Glabbagool"  1x   "Does Glabbagool have anything that he wants to..."
  - "Globagool"        1x   "How many eyes you can have, Globagool?"

A) Confirm — all members → Glabbagool
B) Different canonical — I'll type it
C) Split — not all the same; ask me one at a time
D) All ignore (table chatter)
```

For singleton clusters (one member), use the per-token form:

```
Token: "Vulking Valve"  (3 occurrences)
Context: "...we returned to Vulking Valve and..."

A) Misspelling of <closest known suggestion>      ← if cluster has a proposed canonical
B) Misspelling — I'll type the right form
C) New canon — add to known set
D) Not a name (ignore — saved to state)
```

When `zoom_context.py` returns a hit for either template, add it as a
line under the context/members before the options, e.g.:

```
Token: "Povit"  (1 occurrence)
Context: "...what could be useful to us in the back of and Povit."
Zoom's original for this cue: "...what could be useful to us back and forward."

A) Misspelling — I'll type the right form
B) New canon — add to known set
C) Not a name (ignore — saved to state)
```

Let it inform your own recommended default (if the question format
supports one) as well as the user's decision — Zoom's original is often
the tie-breaker between "real garbled name" and "ASR noise on both sides."

**(D) "Ignore" decisions** must be persisted via `state.py` so the same
token doesn't resurface next session:

```bash
python ~/.claude/skills/vtt-spell-pass/state.py \
  --state <campaign>/notes/.vtt_spell_pass_state.json \
  ignore "Joe" "Gabe" "Christmas" ...
```

**No assumed table chatter.** If a token looks like a personal name and
you don't know whether it's a player or an NPC, ask. Mistakes here cost
real corrections. Clustering already cuts the question count — don't
compound that with silent dismissals.

#### At volume, use Artifact mode instead of serial `AskUserQuestion`

Clustering cuts question count, but a mature campaign's residual can still run
to dozens of clusters and singletons per session — enough that a serial
one-at-a-time chat walk exhausts the user before Phase 3 finishes, and an
exhausted user starts rubber-stamping (the same failure mode this skill's
Phase 2.5 exists to prevent for evidence quality — don't reintroduce it at
the delivery stage). Once the queue is longer than a handful of clusters,
offer **Artifact mode** (below): the shared review builder, one card per
`(wrong-form → canonical)` pair, grouped by canonical.

This does not relax the hard rule above — every new wrong→right mapping still
needs the user's explicit confirmation, one candidate at a time. It changes
*how* that confirmation is collected, not whether it's required. Below the
volume threshold — a short residual, or a rerun where only a few new tokens
surfaced — the chat/`AskUserQuestion` walk above is simpler.

### Phase 4 — record decisions

For each "misspelling" decision (A or B), call:

```bash
python ~/.claude/skills/vtt-spell-pass/add_to_glossary.py \
  --glossary <campaign>/notes/vtt_transcription_corrections.md \
  --section <pcs|npcs|items|factions|locations|table> \
  --wrong "<wrong-form>" \
  --right "<canonical>"
```

The script appends to the existing canonical's row if one exists, or
creates a new row, or creates a new section. You decide which section
based on what the canonical refers to (ask the user if unclear).

**Match `--section` to the canonical's *existing* row.** `add_to_glossary.py`
only looks for an existing row *inside the named section*. If the canonical
already has a row in a different section, a wrong `--section` silently
creates a **duplicate** row (this run: `Talon, Talen → Kalan` landed in
`## PCs` while the real `Kalan` row lives in `## NPCs and creatures`). Grep
the glossary for the canonical first (`grep -n '\*\*Kalan\*\*' <glossary>`)
and use whatever section its row is already in.

For "New canon" decisions: don't write to the glossary. Instead append a
line to a new file `<campaign>/notes/vtt_known_additions.md` listing
`<canonical>  — <context excerpt>  — <date>`. The user can promote that
into a real NPC dossier or world note later. This avoids polluting the
glossary with non-misspellings.

For "Ignore" decisions: take no action.

Mark the corresponding TaskUpdate as completed after each decision.

**Glossary entry vs. targeted edit — the case-insensitivity gate.**
`apply_replacements.py` matches `\bwrong\b` with `re.IGNORECASE`, so a
wrong-form that is also a common English word will over-replace anywhere it
appears lowercase. Before writing a *new* wrong-form to the glossary, grep
the VTT for lowercase occurrences of it. If any exist — or the wrong-form is
a common word (`Embrace`, `Close`, `Home`), a generic phrase (`Call and`),
or a non-name transcription fix (`Izzy` → `he's`) — **do not add it to the
glossary.** This keeps the glossary safe to auto-apply to every future
transcript. Examples this run: `Embrace → Fembris` (a blanket rule would
corrupt "corrosive embrace"), `Call and → Kalan`, `Izzy → he's`.

**The gate has a blind spot: REAL-WORLD PROPER NOUNS.** The lowercase grep and
`lint_glossary.py --corpus`'s `corpus_lower` check both fire only on wrong-forms
that appear *lowercase* — and a real-world proper noun never does. `Cisco`,
`Greg`, `Dave`, `Glenn`, `Zuck`, `Chris` are all legitimate capitalised words
that collide with campaign names, and **no automated check in this skill can
catch them.** Only grepping the corpus for the bare form will.

`Cisco → A'lai` sat in a blanket row and rewrote a real company across ~8
sessions: *"6 of the top 10 customers at Cisco are federal government"*, *"I went
to Cisco, Juniper, VMware, back to Cisco"*. `Ally → A'lai` rewrote the ordinary
D&D word inside a rules question — *"keep the daggers from hitting my ally"*.
The linter did warn on `Ally`; it could not warn on `Cisco`, and it never will.

Out-of-character pre-roll is where this bites, because that is where real-world
speech lives — jobs, tooling, sport. Expect it, and grep there first.

**NEVER promote a cue-scoped GM ruling into a glossary row.** This is how the
`Cisco` damage happened, and the glossary's own notes had recorded the decision
correctly:

> *targeted edits, all GM-confirmed: … "Cisco" → **A'lai** (GM ruling — "I don't
> trust Cisco anymore" is Gyrgum on the prisoner)*

The ruling was right **for that one line**. Someone later moved it into the
standing row, where it began firing on every genuine mention of the company. A
ruling about *a cue* and a rule about *every future transcript* are different
objects, and the record exists precisely so the first does not have to become
the second. When you find a wrong-form in a row that reads like it was meant for
one line, check the notes section for its origin before trusting it.

**This skill cannot see ordinary-word garbles at all — and that is fine, as long
as you know it.** `find_unknowns.py` surfaces unknown *capitalised* tokens, so an
ASR error that produces a correctly-spelled common word is structurally
invisible here: `"an associated feed"` (feat), `"plus 2 to decks"` (Dex), `"an
infinite diamond jack"` (damage hack). `sd_verify_quotes` cannot catch them
either — it scores them **verified**, correctly, because the recap quotes the
tape faithfully. They surface only in `/consistency-check`, which reads the
recap for *sense*. So a clean spell pass is not evidence the tape is clean, and
when a consistency check later reports a garbled quotation, the fix belongs back
here as per-cue record entries — never as glossary rows, for the reason above.

**Write these as record entries, not as edits.** A one-off fix used to be a
targeted `Edit` on the cleaned output; it is now a `transcript_corrections.yaml`
entry, which is a strictly better fit — the entry is *cue-scoped*, so it does
not need to be globally safe the way a glossary row does, and unlike an edit it
survives the next `sd_corrections apply`. Note the cue number and the exact
before/after text now (`find_unknowns.py` contexts give you the span; grep the
transcript for the cue index), and add them in Phase 7 alongside the imported
glossary entries:

```yaml
- id: cue-0224-fembris
  cue: 224
  was: 'Gary Young: The corrosive embrace of Embrace is upon us.'
  now: 'Gary Young: The corrosive embrace of Fembris is upon us.'
  recorded: <today>
  verified: true
  note: one-off; not glossaried because a blanket Embrace rule corrupts "corrosive embrace".
```

`was` must match the cue exactly, speaker prefix included — that check is what
makes a stale entry fail loudly instead of pasting an old repair over new words.

The glossary keeps its own running landmine list (a "Notes for future passes"
section flagging risky case-insensitive rows like `Char→Shar`, `Cal→Kalan`).
Re-read it and grep the VTT for those lowercase forms before every apply.

### Phase 5 — lint the glossary, then apply replacements

**Lint first.** The glossary is a standing rewrite rule applied to every
future transcript, so a bad row is not a one-off. Run:

```bash
python ~/.claude/skills/vtt-spell-pass/lint_glossary.py \
  --glossary <campaign>/notes/vtt_transcription_corrections.md \
  --corpus <vtt>
```

Exit 1 means ERRORs. Show them to the user before applying; each names the
offending row with a `<file>:<line>` location.

- `doubling` — the canonical contains the wrong-form as a word, so the rule
  fires on *already-correct* text (`Brin Bundlewine` →
  `Brin Bundlewine Bundlewine`). Note the trigger is a **correct** transcript,
  not a mangled one — the better the ASR, the more damage. `apply_replacements.py`
  now refuses these rules and prints what it skipped, so the row is inert until
  rewritten. Fix by dropping the row (a bare short name standing alone is fine)
  rather than by editing the canonical.
- `conflict` / `noop` — one wrong-form with two canonicals; or a row mapping
  a form to itself.
- `chained` (warn) — a canonical is also someone else's wrong-form, so output
  depends on rule order.
- `split_section` (warn) — same canonical with rows in two sections; the next
  `add_to_glossary.py --section` append will silently create a third.
- `common_word` / `corpus_lower` (warn) — the automated form of the
  case-insensitivity gate described in Phase 4. `common_word` consults a small
  built-in list; `--corpus` is the reliable one, flagging wrong-forms that
  genuinely occur lowercase in a real transcript. Warnings are for review, not
  automatic rejection: `Brewberry` and `Thunder Wave` both trip `corpus_lower`
  and both are correct rules.

Replacement is expected to be **idempotent** — running the pass twice must
equal running it once. Re-applying the glossary to the candidate (to a second
scratch path) should produce a byte-identical result; if it doesn't, a row is
corrupting correct text and the lint will say which. This property is what makes
Phase 7's import trustworthy — a non-idempotent row puts a corruption in the
record's `now` text, where it reads as an approved correction.

Then apply the now-updated glossary to the transcript, **to scratch**:

```bash
python ~/.claude/skills/vtt-spell-pass/apply_replacements.py \
  --vtt <vtt> \
  --glossary <campaign>/notes/vtt_transcription_corrections.md \
  --output "$SCRATCH/candidate.cleaned.vtt"
```

`--output` is required, there is no `--in-place`, and the script refuses to
write a `.cleaned.vtt` that an existing `transcript_corrections.yaml` claims
(see "What this skill delivers"). The candidate is an input to Phase 7, not the
deliverable — nothing downstream reads it.

Report the per-pair replacement count back to the user.

### Phase 5.5 — assert the output against canon (deterministic, no LLM)

Requires a CampaignGenerator checkout with `entity_registry/resolve.py`
(CampaignGenerator#477). Skip if the campaign has no registry.

```bash
python ~/.claude/skills/vtt-spell-pass/lint_glossary.py \
  --glossary <campaign>/notes/vtt_transcription_corrections.md \
  --campaign-dir <campaign> \
  --campaign-generator ~/src/CampaignGenerator \
  --verify-output <the .cleaned.vtt this run produced> \
  --quiet
```

Two checks, both ERROR, both assertions rather than review queues — there is no
card, no cluster, and nothing to decide per candidate. Either the output is
canon or it is not.

- **`canon_conflict`** reads the glossary rows. A row whose own **canonical**
  disagrees with `config/party.yaml` / the registry, or which is itself another
  row's wrong-form, is a standing rewrite rule that manufactures the error in
  every future transcript.
- **`output_not_canon`** reads what this run *produced*. Every proper noun in it
  must already resolve to itself; anything coming back `is_change: true` is a
  name written in a form the campaign's own canon chain rejects. `not_canon` is
  ignored — unknown names are this skill's normal input.

**Why the second one exists.** Out-of-the-Abyss accumulated 1,737 occurrences of
`Grygum` across 39 files, in every session with a cleaned transcript, while
`**Gyrgum**` was the canonical the whole time and `Grygum` sat in the *wrong*
column of its own row. No row-level check could see it: the glossary was
correct. It entered through a card decision and landed in the output. The
origin is still in `summaries/20260907/vtt_spell_pass_decisions.json` — the card
`gurrigam__grygum`, marked **discuss** with the note *"This is player Grygum
confirm spelling"*. The conversation that note asked for never happened.

A discuss note is an instruction to talk, not a pre-approval — and this phase is
the backstop for when that rule is broken anyway.

### Phase 6 — re-scan to confirm

Re-run `find_unknowns.py` against the candidate. Any remaining
unknowns mean either (a) a candidate slipped through pre-classification
or (b) a new word the user didn't get to. Show the user the diff and ask
whether to do another pass.

Expect **false residuals** to remain (see Phase 1) — multi-word capitalised
runs like `And Kalan`, `The Helmed Horror`, `Helmed Horror No` whose embedded
name is already correct. These are *not* a reason for another pass; only a
residual whose embedded proper noun is actually *wrong* is. Also grep the
candidate for accidental doubling from full-name wrong-forms (e.g.
`Strongbranch Strongbranch`). **Fix these in the glossary and re-run Phase 5**,
not by editing the candidate — a doubling is a bad *row*, and an edit leaves it
in place to fire again next session. `lint_glossary.py` names the fix.

### Phase 7 — hand the diff to `sd_corrections`, then regenerate

The candidate is a proposal. Turn it into record entries, get them reviewed,
and let CampaignGenerator generate the tape:

```bash
cd <session-dir>

# 1. one entry per differing cue, all verified: false
sd_corrections import --dir . \
  --raw <stem>.transcript.vtt \
  --edited "$SCRATCH/candidate.cleaned.vtt" \
  --record "$SCRATCH/proposed.yaml"

# 2. review, then merge into ./transcript_corrections.yaml (hand-merge if one
#    already exists — `import --force` discards its notes and verified flags)

# 3. generate the tape and confirm
sd_corrections apply --dir .
sd_corrections check --dir .          # expect: no findings
```

Notes that matter:

- **Pass `--raw` explicitly whenever the session has more than one non-cleaned
  `.vtt`** (any `audio-to-vtt` run leaves `<stem>.transcript.retranscribed.vtt`
  beside the original). Auto-detection demands exactly one and exits 2
  otherwise. The raw you name is the one the record is written against, and it
  determines which `.cleaned.vtt` `apply` produces.
- **Every imported entry lands `verified: false`.** Here that is a formality,
  not a backlog: Phase 3 already put each cluster to the GM. Flipping
  `verified: true` is transcribing rulings that were already made — so do it
  entry by entry against your Phase 3 answers, and **delete** rather than
  approve any cue the GM did not rule on. An import captures *whatever* differs,
  including a substitution a glossary row made in a context nobody looked at.
- **`import` writes one entry per cue, not per substitution.** Two glossary
  rows firing in one cue produce one entry whose `now` holds both fixes; that is
  correct, and the record refuses two entries on a single cue.
- Add the Phase 4 one-off entries here too, with `verified: true` — they never
  went through the glossary, so `import` does not know about them.
- **`apply` is all-or-nothing.** If any `was` no longer matches the tape,
  nothing is written and every failure is named. A stale entry means the raw
  tape changed under the record; fix `was` or drop the entry.
- Deleting an entry is how you *revert* a substitution: drop it and the next
  `apply` restores what was spoken.

Finally, record the transcript as processed so future runs against the same path
are no-ops:

```bash
python ~/.claude/skills/vtt-spell-pass/state.py \
  --state <campaign>/notes/.vtt_spell_pass_state.json \
  processed <vtt-path>
```

## Batch mode — a whole campaign's backlog (`batch/`)

For many chapters at once, the deterministic half is scripted so every agent
computes the same residual:

- `batch/batch_scan.py --campaign-dir <c> --dir <chapter> --scratch <s> [--npcs-dir <d>]`
  runs Phase 0, Phase 1 (apply then re-scan) and the sibling lookups for one
  chapter, and writes `<batch-dir>/<chapter>/scan.json`.
- An agent per chapter fills in judgments per `batch/AGENT_BRIEF.md` and writes
  `proposals.json` beside it.
- `batch/merge_proposals.py --campaign-dir <c> --wave <n>` merges a wave into one
  GM question queue, applying the two checks no single agent can make: the
  corpus-wide lowercase gate (against `<batch-dir>/corpus_all.txt`) and
  cross-chapter conflicts for the same wrong form.
- `batch/stage_c.py --campaign-dir <c> --scratch <s> --dry-run` applies the
  glossary to every manifest target in scratch, before anything is written,
  and reports chained rules, doubling artefacts the apply introduced, and any
  file a second apply still changes (not idempotent). Exit 1 means it found
  one of those. `--apply` is not implemented yet; Phase 5 still writes the
  cleaned files.

Run data (`manifest.json`, `known_flat.txt`, the per-chapter folders) stays in
the campaign under `--batch-dir`, default `<campaign>/notes/spell_pass_batch/`.
Only the orchestrator writes the glossary.

## Artifact mode (batch review)

Replaces Phase 3 only. Phases 0–2.5 and 4–7 are unchanged, and the shell path
stays exactly as documented. Full contract:
`~/.claude/skills/_shared/review-artifact/CONTRACT.md`.

**Where the review files live.** This skill keeps its review record in the
session directory, not `$SCRATCH`: `<session-dir>/spell_review/review_items.json`,
`review.html`, `decisions.json`, and the id sidecar map
`spell_review/review_map.json`. They are `.json`/`.html`, so they cannot trip
`sd_corrections`' `*.vtt` glob, and they are the only trace of the question the
GM was actually asked. Nothing else this pass writes goes under the session
directory (see "What this skill delivers").

```bash
REVIEW="<session-dir>/spell_review"; mkdir -p "$REVIEW"
python ~/.claude/skills/_shared/review-artifact/build_review.py \
    --in "$REVIEW/review_items.json" --out "$REVIEW/review.html"
```

Give the page a `reviewId` such as `vtt-spell-pass:<session>`, and never put a
verdict in `state` — a recommendation goes in the card's `y` or `ev` text.

### The consent unit is the PAIR, never the cluster

**This is not negotiable and it is why this skill produces more cards than the
others.** The batch merger, `batch/merge_proposals.py`, states it directly:

> *"Consent granularity: the unit is the (wrong_form → canonical) PAIR.
> Questions are grouped by canonical for batching, but every member carries
> its own count and sibling verdict so the GM can accept some and reject
> others. **Collapsing a group into one yes/no would approve hallucinated
> members invisibly.**"*

So one card per `(token → canonical)` pair. Group them by canonical in card
order so the GM reads a canonical's members together, but never merge them
into a single card, and never let approving one member imply another.

### What is auto-applied, footer only

- `action ∈ {leave_alone, add_to_known_set}` — no ruling needed.
- `auto_dismissed[]` under the `batch/AGENT_BRIEF.md` gate (Phase 2.5): **`count == 1` AND
  `kind == ordinary_words`**. Never on `inconclusive`, never on `count ≥ 2`.
- Glossary rows that already exist — Phase 0's known-misspellings pass.

Name the counts in the `footer` so the GM can see what ran without them, and
**list every auto-dismissed token by name** (token, count, sibling line) — a
count alone does not let the GM pull one back.

### What becomes a card

`action ∈ {propose, propose_low_confidence, escalate, escalate_blocking}`.

```json
{ "id":  "vucherton__vukradin",
  "t":   "<code>Vucherton</code> → <b>Vukradin</b> · 3 occurrences, 2 chapters",
  "y":   "Apply the correction: add the row to <code>vtt_transcription_corrections.md</code>, lint, and record the 3 substitutions to <b>Vukradin</b> in <code>transcript_corrections.yaml</code> (Phase 7).",
  "n":   "Not a garbling of Vukradin. Saved to <code>.vtt_spell_pass_state.json</code> as ignored, and never asked again.",
  "ev":  "Verbatim: <em>…a no-skimming clause that Mr. Vucherton insisted…</em> · rule <code>edit_distance,metaphone</code> · confidence <code>medium</code> · sibling: <code>agent_corrected</code>" }
```

**Approve always means apply the correction; "real name, not a misspelling"
comes back as reject.** Each card's `n` states which reject it is. When the
evidence leaves open that the token is a real name (new canon — module hit,
both transcriptions agree, a named thing in the line), write `n` as
*"Not a misspelling — add <code>Vucherton</code> to the known set
(<code>notes/vtt_known_additions.md</code>); no glossary row."* Otherwise `n`
is the ignore text above. A token with no proposed canonical still gets an
approve that corrects: `y` reads *"Misspelling — write the right form in the
note; it becomes a glossary row"*, and its `n` is the known-set text. Never
write a card whose approve keeps the token as it is.

Card ids must round-trip to the pair. Use `<token>__<canonical>`, lowercased
and non-alphanumerics collapsed to `_`, and keep a sidecar map in
`spell_review/review_map.json` from id → `{token, canonical, section, count,
reject_as}` (`reject_as` is `ignore` or `known`, matching the card's `n`) — the
page returns ids only.

**Always put the verbatim excerpt in `ev`.** A pair judged without its context
is the exact failure the pair-consent rule exists to prevent.

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

Then `WebFetch` the URL and run `read_decisions.py` against the same items
file, writing the rulings beside it:

```bash
python ~/.claude/skills/_shared/review-artifact/read_decisions.py \
    --html <saved-artifact.html> --items "$REVIEW/review_items.json" \
    --out "$REVIEW/decisions.json"
```

### Verdict mapping — feeds Phase 4 unchanged

| verdict | action |
|---|---|
| **approve** | apply the correction: `add_to_glossary.py --wrong <token> --right <canonical> --section <matching the canonical's EXISTING row>` (the canonical from the note when the card had none; no canonical anywhere → treat as discuss) |
| **reject**, `reject_as: known` (`n` reads "not a misspelling — add to the known set") | append `<token> — <context excerpt> — <date>` to `notes/vtt_known_additions.md`; no glossary row |
| **reject**, `reject_as: ignore` | `state.py ignore "<token>"` |
| **discuss** + note naming a canonical | treat as approve with the GM's canonical, not the proposed one |
| **discuss**, no note | back to the shell, grouped with the other discussed pairs |
| **unmarked** | undecided — leave the pair for the next run and say so |

Then Phase 5 as written: **lint before applying.** `lint_glossary.py` exit 1
blocks the run — a batch of approvals is exactly when a `doubling` or
`conflict` row does the most damage.

## Important conventions

- **Speaker labels are stable.** `Thorin (Joe):` does not contain
  misspellings of "Thorin" worth catching — the helper strips speaker
  labels before scanning. If you suspect a label is wrong, that's a
  separate manual fix.
- **Possessive `'s` is auto-handled.** The applier extends each wrong-form
  to also catch its possessive (`Lavagul'` → `Lavagul's` → `Glabbagool's`).
- **Never map a bare first name to a full "First Last" canonical.** If the
  surname is independently corrected by another row, the two fire together
  and *double* the surname (this run: `Kellen → Kalan Strongbranch` plus
  `Strongbench → Strongbranch` turned "Kellen Strongbench" into
  "Kalan Strongbranch **Strongbranch**"). Map a bare first name to the bare
  first-name canonical (`Kellen → Kalan`) and let the surname row fix the
  surname independently; reserve full-name wrong-forms for inputs that
  actually contain a surname token (`Callan Strongfeld → Kalan Strongbranch`).
  **`lint_glossary.py` does not catch this** — the row is fine in isolation and
  only doubles when the transcript already supplies the surname, so grep the
  *candidate* for repeated surnames every run. It recurs: this pass found
  `Toblin → Toblen Stonehill` turning "Toblin Stonehill" into
  "Toblen Stonehill **Stonehill**"; fixed by demoting it to `Toblin → Toblen`.
- **Don't silently expand the user's variant lists.** If the user says
  "add X as a misspelling of Y", add exactly X — not your guesses about
  related forms. (See memory: `feedback_scope_discipline`.)
- **Don't replace inside speaker labels or VTT cue metadata.** The
  applier uses word-boundary regex on the full text — generally safe, but
  if a wrong-form is also a real word ("May" the month vs "May" the
  surname), prefer skipping rather than replacing. Flag to the user.
- **The glossary lives in `notes/`, which is excluded from the mempalace.**
  This is intentional — the glossary is a cleanup-pass reference, not
  campaign canon. Don't try to mine it.
- **Glossary and record are different objects; keep them straight.** The
  glossary (`notes/vtt_transcription_corrections.md`) is a *standing rule set*,
  campaign-wide and reusable, so every row must be safe applied blind to any
  future transcript. The record (`<session-dir>/transcript_corrections.yaml`) is
  *what actually happened to this one tape*, cue-scoped and auditable. A fix too
  dangerous to generalise belongs only in the record. Nothing belongs only in a
  file you edited by hand.

## Why this design

The glossary is a hand-curated **boundary** between sloppy transcription
and canon. The user reviews every addition. The skill never invents
canonical forms — it only:

- applies what the user has already approved (Phase 1, Phase 5), and
- surfaces unknowns and asks (Phase 3).

This matches the global rule: *LLMs are renderers, not architects. Good
pattern: LLM extracts → human reviews and imposes structure → LLM renders
inside that structure.* Phase 1 is deterministic extraction; Phase 3 is
the human checkpoint; Phase 5 is deterministic rendering.

Phase 7 exists because that checkpoint used to leave no trace. The pass applied
what the GM approved, wrote the cleaned tape, and kept the *rules* in the
glossary — but not what any individual cue became, and not the one-off edits
that never earned a rule at all. So the tape everything downstream measures
verbatim against was, in the end, unreviewable: on Phandalin ch46, 74
substitutions nobody could enumerate, three of them inventing a surname. The
record closes that gap without moving any decision away from the GM: the
glossary still holds the approved rules, and the record now holds the approved
*results*. That is also why the applier's `--output` has no default — the one
path it used to default to is the one it must never write.
