# Agent brief — batched VTT spell pass

Contract for a Stage A agent. One session directory per agent. This file carries
**only** mechanical constraints and GM rulings quoted verbatim. It never carries the
orchestrator's inferences, because a wrong entry here is inherited by five agents at once.

Wave 2 issue. Edits between waves are shown to the GM as a diff before the next launch.

## Changed since wave 2

- **The known set was repaired.** 16 stale entries were removed — names that sat in the
  known set while the glossary already treated them as wrong-forms, which silently
  suppressed real unknowns (`Miral`, `Xanthopoulos`, `Sister Kayla`, `Jenna Roscoe`…).
  17 new canonicals were added. Expect a different `known_names_count` than wave 2; that is
  intended, and it is pinned for your whole wave.
- **Never collapse a deliberate variant into its base name.** `Vukradinious` is its own
  canonical — a GM in-joke form. A wave-2 cluster proposed folding `Vucravinios` and
  `Vukradinhos` into `Vukradin`, which would have destroyed a standing GM ruling. Before
  proposing a collapse, grep the glossary for the longer form.
- **A name spoken wrongly *on purpose* is not a transcription error.** ch17 line 3265 is
  "No, not Falcon Hunter, Falcon the Hunter." A row flattens the correction into nonsense.
  Same class: chapter 10's self-corrected "Emerald Gauntlet", and players groping for a
  name aloud. If the speaker corrects themselves in the next breath, leave it.

## Changed since wave 1

- **`lowercase_in_target` is FIXED and now trustworthy.** In wave 1 it was computed against
  a lowercased haystack, so it was `true` for ~all members and carried no information. All
  five agents caught this independently and worked around it. It now does a case-sensitive
  search of the original text, so the brief's rule below can be applied as written.
- **A bare word that the canonical already contains is never a row.** Wave 1's
  `Grove → Whispering Grove` would have rewritten "Whispering Grove" into "Whispering
  **Whispering** Grove". Same failure as `Toblin → Toblen Stonehill`. Recommend the
  correction, and say in the rationale that it needs a targeted edit.
- **A short token can be two different things.** `Val → Valphine` was correct in one line
  and would have corrupted "Val Booker" — a different person — in another. When a token is
  short or common, check whether every occurrence is the same referent before recommending
  a row.

---

## Your job

Fill in judgment on an already-computed candidate list. The deterministic work — Phase 0,
Phase 1 including the mandatory apply-then-rescan, and every sibling lookup — is done by
`batch_scan.py` (shipped with the `vtt-spell-pass` skill, in its `batch/` dir). You classify,
you do not re-derive. The orchestrator gives you the campaign root; run from it:

```bash
cd <CAMPAIGN>          # e.g. $CAMPAIGNS_ROOT/Phandalin
python3 ~/.claude/skills/vtt-spell-pass/batch/batch_scan.py --campaign-dir . \
  --dir <YOUR_DIR> --scratch <YOUR_SCRATCH> [--npcs-dir notes/npcs]
```

Pass `--npcs-dir` only if the orchestrator named one; a path that does not exist is an error.

Takes about two minutes. It writes `notes/spell_pass_batch/<YOUR_DIR>/scan.json` with every
surviving candidate, its `verbatim` context, and what the sibling transcription says at that
same span. Then you read that file and write `proposals.json` beside it.

## Hard prohibitions

- **Never run** `add_to_glossary.py`, `state.py`, or edit
  `notes/vtt_transcription_corrections.md`. Those files are unlocked read-modify-write; a
  concurrent write silently destroys another agent's rows, and a lost row is a lost GM
  decision. The orchestrator is the sole writer.
- **Never write outside** `notes/spell_pass_batch/<YOUR_DIR>/` and your own scratch dir.
- **Never modify any transcript.** Stage A produces no cleaned output.
- **Never pick your own deliverable or sibling.** Both are pinned in `manifest.json`.
- **Never guess when blocked.** Put it in `agent_blocked_on[]`. An unanswered question is
  not a decision.

## The one thing that matters most: the sibling is contaminated

Your sibling is a `session_*_transcript.vtt`. These are **not** acoustic ASR. They are
LLM-based and D&D-tuned, and they fail *semantically* — substituting a plausible name they
already know, including one from a **different campaign**, for the name actually spoken.

GM, verbatim, on the confirmed case:

> "the llm got deluded and confused another party with this adventure, and so it mapped
> Valphine to Bramgrim (valphine is a cleric, and bramgrim is a cleric in the other
> adventure)"

So weight the sibling **by kind of content, never by score**. Set `kind` on every member:

| `kind` | When | What you may conclude |
|---|---|---|
| `ordinary_words` | sibling shows plain prose at the span | no name was spoken **in this chapter** |
| `campaign_correct_name` | sibling spells a known campaign name **and our token is a plausible garble of it** | confirms the proposed canonical |
| `different_name` | sibling shows a *different* plausible name | **nothing.** `requires_gm: true`, no recommendation |
| `inconclusive` | `score < 0.55`, or the span isn't covered | nothing. Surface it |
| `none` | no sibling text at all | nothing. Surface it |

Contamination swaps names for names; it does not invent coherent filler. That is why
`ordinary_words` is trustworthy and `different_name` is worthless.

**But `campaign_correct_name` can manufacture a FALSE confirm.** Apply a phonetic
plausibility gate before accepting one: could our token credibly be this canonical, badly
heard? If not, the sibling invented it. Confirmed case (wave 2): token **`Brr`**, sibling
read **"Brewbarry."** By the letter of the table that is a confirm. It is wrong — our line
is a player shivering at the DM's *"the cold, howling wind that buffets you."* `Brr` is not
a garble of `Brewbarry`; the transcriber filled in a character it knew. Same wave, token
`Renovation` drew the sibling text *"you interventionist"* from an exchange several lines
away, touching a live faction name. When the token and the canonical are not phonetic
neighbours, recommend `ignore` and say why.

Worked examples from chapter 08, all four kinds:

```
'Velphina'  x5  ours: "Uh, Velphina. She was attacking Velphina."
                sib:  "Not you. Not you. Valphine. She was attacking Valphine."
                -> campaign_correct_name. Confirms Valphine.

'Um'        x40 ours: "Yes. Um, can you put the number one and two for"
                sib:  "Yes. Can you put the number one and two for the two harpies..."
                -> ordinary_words. The cluster proposed 'Umi'. There is no name here.

'Fine'      x1  ours: "Fine. That's fine."
                sib:  "Yeah, that's fine."
                -> ordinary_words. The cluster bound this into the Valphine group.
                   It is not Valphine. This is why consent is per-member.

'V- Valphine' x1 ours: "next to, uh, V- Valphine and..."
                 sib:  "Like, next to Valphine and let me just make sure..."
                 -> false residual. The embedded name is ALREADY CORRECT; the scanner
                    only flagged it because it cannot split a capitalised run.
                    Put it in false_residuals_suppressed, do not ask about it.
```

## Recommendations you may set

- `confirm` — member is a misspelling of `proposed_canonical`. Requires
  `campaign_correct_name`, or an unambiguous reading you state in `rationale`.
- `different_canonical` — it is a misspelling of something else; name it.
- `new_canon` — a real name not yet in the known set.
- `ignore` — table chatter or ASR noise, no rule.
- `no_rule` — a name may exist but no correction is safe.
- `escalate` — you must not decide. Always with `requires_gm: true`.

**Auto-dismiss — the ONLY silent drop you may make.** The GM authorised dismissal on
positive counter-evidence only: a member may go to `auto_dismissed[]` iff
`count == 1` **AND** `kind == ordinary_words`. Never on `inconclusive`, never on count ≥ 2.
Auto-dismissed members keep their full evidence so the call is auditable.

Everything else reaches the GM. When in doubt, surface — the GM has stated they prefer
being asked over silent dismissal.

## Rules that have already cost a correction

- **Never map a bare first name to a `First Last` canonical.** `Toblin → Toblen Stonehill`
  turned "Toblin Stonehill" into "Toblen Stonehill Stonehill". Propose `Toblin → Toblen`
  and let the surname's own row fix the surname. `lint_glossary.py` cannot catch this.
- **A wrong-form that appears lowercase anywhere is not a glossary row.**
  `apply_replacements.py` matches with `re.IGNORECASE`. `batch_scan.py` sets
  `lowercase_in_target`; if it is true, recommend `no_rule` and say why — the orchestrator
  runs the corpus-wide check.
- **Fuzzy confidence is not evidence a name was spoken.** A garbled token scores just as
  well against a known name whether or not the audio contained a name at all. Chapter 08's
  high-confidence clusters include `Um → Umi`, `Good → gold`, `Beak → Boney`.
- **`verbatim` must be quoted, never paraphrased.** The GM decides from the actual line.

## GM rulings in force

> "daz was a typo, use dave" — chapter 07 only; no speaker exclusions anywhere in this batch.

> "Orsick is Orsik an in cannon hero of the war of the giants." — a name you don't
> recognise may still be canon. Recognition is the GM's, not yours.

> "Whispering Grove is canonical. Fix everything to it" — wave 1. Whispering Wood /
> Whispering Woods / Whisper Woods / Whisperwood(s) / Whisper Road all map to
> **Whispering Grove**. Rows already exist; do not re-propose them.

> "Map to Miraal, retire Miral" — wave 1. **Miraal** is the sea-elf banshee at the Tower of
> Storms. `Miral` has been retired as a canonical and Miral/Mirall/Mural now map to Miraal.
> **Meril** is a different NPC — Soma's druid mentor — and stays separate.

Wave 1 also added these canonicals to the known set, so their variants should now bind
rather than orphan: Harpy, Treant, Blighted Vine, Enclave Warrior, Naturalists, Stormlord,
Giant's Havoc.

> Wave 2 rulings. **Sridar** is the drow artifact collector (named on screen in ch17:
> "her name is… Sue Darth", sibling "Her name is Sridar"). **Iymrith** is the dragon, the
> Doom of the Desert — the correct spelling had never once survived transcription.
> **Dragon Slayer Sword** is correct, not "Dragon Slaying Sword".

Wave 2 added these canonicals: Tresendar Manor, Orc Raider, Orc Scout, Orc Brigand, Privy
Council, Overbright, Matron Mother, Searing Pain of Justice, Black Pearl, Vincent, plus
5e vocabulary (Goodberry, Mold Earth, Dominate Person, Levitate, Stone's Endurance, Cure
Wounds, Giant Strength).

## Output

Write `notes/spell_pass_batch/<YOUR_DIR>/proposals.json`: copy `scan.json` through, with
`kind`, `recommendation`, `rationale` and `requires_gm` filled on every member, plus
top-level `auto_dismissed[]`, `false_residuals_suppressed[]`, `agent_blocked_on[]`.

Then reply with a short summary only: counts by recommendation, anything you escalated, and
anything that surprised you. Do not paste the JSON.
