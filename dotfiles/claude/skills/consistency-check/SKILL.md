---
name: consistency-check
description: Run a consistency check on a session document (first-pass recap, enhanced recap, or final narration) against the campaign's context files, then adjudicate what the docs can't settle against the session transcript. Handles backfilled old chapters, where the grounding docs describe a much later party and prep often does not exist. Use when the user invokes /consistency-check [document-path].
tools: Bash, Read, Write, Edit, Glob, AskUserQuestion
---

# Consistency Check

Run `check_consistency.py` on a specified document from the current campaign workspace, fact-checking it against grounding docs + the DM's session prep, adjudicating what the docs can't settle against the VTT, then recording exactly what content was used and how every finding was ruled.

## Workflow

### 1. Identify the document

If the user passed a path argument, use it. Otherwise ask: "Which document do you want to check — the enhanced sections, the final narration, or something else? (Provide the path.)"

Resolve the path relative to CWD. Common targets:
- `summaries/<date-or-NNN>/session-summary.md` (or the enhance_summary `--output`) — enriched recap
- `summaries/<NNN>/session_<date>_<slug>.md` — GMAssistant-exported recap
- `vtt_roleplay_extractions/enhanced_sections.md` — enhanced recap (post-Pass 2)
- `session-doc.md` (or whatever the narration `--output` was set to) — final narration

**Read the document yourself before running.** It grounds the entity/beat list (who/what appears), tells you which prep is relevant, and lets you anticipate the likely findings.

**Note the session's transcripts while you're there — and check whether any of them carry SPEAKER LABELS.** `ls` the same directory; you will very likely need a transcript in step 4.7. Among `.vtt` files the `*.retranscribed.cleaned.vtt` variant (when present) is the best one. But a session dir may *also* hold a Zoom-exported **`.md` transcript with per-speaker labels** (`**dave:** …`, `**kostadis:** …`) sitting alongside the unlabelled VTTs — and nothing in the filename advertises it. Check every candidate:

```bash
ls -la summaries/<NNN>/*.vtt summaries/<NNN>/*.md
grep -oE '^\*\*[a-zA-Z][a-zA-Z ._-]{1,30}:\*\*' <candidate>.md | sort | uniq -c | sort -rn
```

**When the run's questions are about attribution — who cast it, who was hit, who said it — a speaker-labelled transcript is worth far more than a cleaner unlabelled one.** In one run the VTTs had *no* speaker labels at all and every single attribution ruling came from the Zoom `.md`; the VTT alone could not have settled any of them. Say in the manifest which file you used and why.

Labels are still imperfect — the GM's block routinely absorbs other people's lines, and dedup passes merge turns — so **rule on content and use labels as corroboration**, never the reverse.

The speaker list is also a *roster check*: count the distinct speakers against the party. **A missing player changes how the recap fails** — see the absent-player failure mode in step 4.7.

**Establish the document's CLASS and LINEAGE — this changes everything downstream.** `ls` the session dir and work out where your target sits in the pipeline, because a recap generated *from another recap* fails in a completely different way than a first-pass recap does.

```bash
ls -la summaries/<NNN>/ && md5sum summaries/<NNN>/*.md
ls -t logs/ summaries/<NNN>/logs/ 2>/dev/null | head      # which script produced it, and when
```

Two things to look for:

- **Is your target an `enhance_summary` output?** A `session-summary.md` that is much larger than the sibling `session_<date>_<slug>.md` / `gm-assist.md` is the enhanced layer, built from that sibling **plus the VTT**. The `logs/` entry names the script and timestamp. When that is the shape, the source recap becomes a required context file (step 3) and the **enhancement failure modes** in step 4.7 apply.
- **How OLD is this session, and do the grounding docs still describe that party?** Read the date off the document and compare it against the campaign's current state. A **backfilled chapter** — an early session recapped long after the fact, often as part of a data-fixing sweep over old transcripts — is a *third document class* with its own dominant failure mode, and it is invisible unless you deliberately look for it. In one run a **2025-05-28** session was checked against a `party.md` / `world_state.md` describing the party as it stood in **2026, around chapter 45**. The tape had the GM saying *"Bards don't do much at level one"*; the docs described level-6 characters with two years of accumulated spells, items and titles. Roughly a quarter of the findings were that gap and nothing else. Confirm the era from the tape rather than assuming:

  ```bash
  grep -niE "level (one|two|1|2)\b|first level|we're level" <transcript> | head
  ```

  When the target is a backfill, the **temporal-mismatch** guidance in step 5 applies and you should say so up front — to the user and in the manifest — because it reframes a low report hit-rate as expected rather than alarming.

- **Is there a prior `*.sources.yaml` in this directory?** If so, **read it before running.** It tells you which fixes were already applied, what the GM ruled and why, and what was left `OPEN` in `carry_forward`. In one run `gm-assist.md` turned out to be byte-identical (same md5) to the previously-checked-and-corrected recap, which meant every inherited fix was already clean and the entire run was about newly-added material.

**But treat a prior manifest's rulings as hypotheses, not settled facts.** They were themselves produced under time pressure from a partial VTT read, and two of them were wrong in one run:

- A ruling recorded *"no on-tape link"* between the freed captives and the villain's reveal, and cut the recap's inference on that basis. The GM's confirmation was **eight lines further down the transcript** than the grep window that produced the ruling. The enhancement pass later restored the true fact and looked like a regression.
- An applied fix had *moved* a scene's bullets earlier in the document to "fix chronology." The tape showed the original order was right; the fix was the regression.

So: read the prior manifest for context and for its `carry_forward` work items, then **re-verify any of its claims your current findings touch** — especially negative claims ("X never appears", "the party never learned Y"). Record corrections to it in this run's `carry_forward` with `status: CORRECTION`.

### 2. Locate the campaign workspace + verify config resolves

Run `pwd`. **`check_consistency.py`'s config auto-detection is narrower than it looks** — `find_default_config()` checks exactly two places:

1. `Path.cwd() / "config.yaml"` — CWD only, **no upward search**
2. otherwise `<CampaignGenerator repo root>/config/config.yaml` — **the toolkit's own config, not the campaign's**

So running from a session subdirectory (`summaries/007/`) does **not** find the campaign config one or two levels up. It silently falls through to CampaignGenerator's config and checks the recap against the wrong campaign — or dies on missing paths. Two safe options:

- **Run from the campaign workspace root** (the dir holding `config.yaml` + `docs/`). Preferred: `base_dir` then resolves `docs/*` correctly and the document is just a relative path. Or
- **Pass `--config <abs-path-to-campaign-config.yaml>` explicitly.**

**Config-move gotcha.** `load_config` sets `base_dir = config_path.parent`, so `documents[].path` resolves against the **config file's own directory**. A workspace that moved `config.yaml` into `config/` makes `docs/campaign_state.md` resolve to `config/docs/...` → `file not found`. Fixes: rewrite the config's paths relative to its own dir (`../docs/...`), or point `--config` at one using absolute paths (a throwaway in the scratchpad works — only `campaign_state` + `world_state` are auto-loaded).

Watch for a workspace holding **both** `config.yaml` and `config/config.yaml` with identical relative paths (obelisk does). Only the root one resolves correctly, and only when CWD is the workspace root.

**Phandalin is the harder variant: it has NO root `config.yaml` at all.** Its only config is `config/config.yaml`, whose `documents[].path` entries are relative (`docs/campaign_state.md`) and therefore resolve to `config/docs/…` and fail. Auto-detection cannot save you — with no root config it falls through to CampaignGenerator's own. Every Phandalin run needs an explicit `--config` pointing at a throwaway absolute-path config in the scratchpad; only `campaign_state` + `world_state` need to be correct in it:

```yaml
documents:
  - { label: campaign_state, path: /home/kroussos/Phandalin/Phandalin/docs/campaign_state.md }
  - { label: world_state,    path: /home/kroussos/Phandalin/Phandalin/docs/world_state.md }
```

**Locate the script; don't assume the path.** It has moved — it now lives at `<repo>/session_doc/check_consistency.py`, not the repo root, and the repo may be `~/CampaignGenerator` **or** `~/src/CampaignGenerator`. `ls` before you build the command.

Sanity check after the run: the header should read `Context  : N document(s)` with N = 2 (auto-loaded) + your `--context` count, and there should be **no** `Warning: context file not found` lines.

### 2.5. Discover + choose session prep — REQUIRED, do not skip

Recaps are built from the VTT transcript, which is lossy. The DM's session prep is the authoritative record of what was intended at the table — names, exact quotes, sigils, place names, intel reveals. **Prep is the only source that catches transcription errors** (mishearings, dropped beats, swapped homophones). Skipping it means the check is blind to its highest-value finds.

**First, date-bound the search — for an old session the prep may simply not exist.** Before hunting, list the prep candidates *with their dates* and compare against the session date. Campaigns adopt prep discipline partway through, so a backfilled early chapter frequently predates the entire prep corpus:

```bash
ls -la notes/session_prep/ notes/sessions/ 2>/dev/null      # dates in the names AND the mtimes
grep -rl -iE "<2-3 distinctive beats/NPCs from the document>" notes/ docs/planning.md 2>/dev/null
```

If the session predates every prep file and the beat-grep matches only the glossaries, **there is no prep** — say so plainly, confirm it with the user, and move on. That is a finding about the corpus, not a failed search, and it should be recorded in the manifest as `session_prep_used: false` with the reason. Do not burn the run hunting for a file that was never written, and do not silently substitute a *different* session's prep because it was the nearest match — off-session prep is worse than no prep, because the check will report legitimate differences as contradictions.

Note that a missing prep layer is **much less costly on a first-pass recap in a campaign with mature glossaries** than the paragraph above implies: in one prepless run, four of the recap's PC-name errors were literal rows in `vtt_transcription_corrections.md`, so the glossaries carried nearly the whole load that prep normally carries.

**Then sweep the WHOLE `notes/` tree, and do not assume a `session_prep/` subdir exists.** Prep layout is per-campaign convention, and there are at least three shapes in the wild:

- **Dated prep dir** — `notes/session_prep/2026-05-31.md`
- **Scattered across subdirs** — OOTA/Candlekeep kept only 4 files in `notes/session_prep/` while the bulk of the arc prep lived in `notes/sessions/` and its `handouts/` subdir
- **Flat, location-named** — obelisk has no prep subdir at all; the prep for the Redbrand Hideout session is `notes/redbrand_hideout.md`, a co-GM working doc headed *"Not canon yet — staging for the Redbrand Hideout session."* **A file named for the dungeon/location/arc, marked as staging, IS the session prep.** Match on the document's beats and locations, not on the filename containing "prep" or a date.

```bash
ls notes/ notes/session_prep/ notes/prep/ notes/sessions/ notes/sessions/handouts/ \
   notes/canon/ notes/threads/ notes/npcs/ docs/npcs/ 2>/dev/null
```

Then **categorize** candidates by relevance to *this* session (use the entities/beats you got from reading the document in step 1):
- **HIGH** — the dated/named/location prep doc for this exact session; in-world handouts (letters, petitions, papers) tied to its beats; the player NPC/name tracker; **the VTT glossary files** (see step 3).
- **MEDIUM** — arc background: locations, evidence maps, runsheets, day-by-day prep, superseded cuts; `docs/planning.md`, `docs/recent_events.md`, the previous session's recap.
- **LOW** — adjacent but off-session (other locations, party/companion handouts).

The campaign-standard sources (step 3) are **always** included, so this choice is only about the *session prep*. Present a **tiered choice** and let the user pick (recommend the focused set — too many context files dilute/overload the check with off-page material):
- **Focused prep set (recommended):** the session's prep doc + the VTT glossaries + the relevant in-world handouts + the NPC tracker, on top of the standard sources (~5–6 files).
- **Minimal:** the session prep doc + `docs/party.md`.
- **Broad:** focused + runsheets/evidence-maps/planning/previous-session recap.
- **Let me pick:** enumerate the full tagged list.

Ask explicitly — e.g. via AskUserQuestion — and **do not proceed without an explicit answer.** The "I'll just check against `docs/party.md`" default once produced a report that flagged imaginary rules issues while missing real transcription errors — that failure mode is exactly what this step prevents. If the user says `none`, proceed but **note in the final report** that the check ran without prep and may miss transcription errors.

**Pre-read the glossaries before you ask.** Skimming `notes/vtt_*` while building the tiers routinely surfaces one or two findings outright (e.g. the recap said "Desa Rook" while `vtt_known_additions.md` recorded the confirmed **Dosa Rook**). Naming a concrete likely catch in the tier prompt makes the choice real for the user instead of abstract.

### 3. Build the command

```
python <repo>/session_doc/check_consistency.py <document> \
  [--config <campaign-config.yaml>] \
  --backend claude-code \                  # default to the subscription, not the metered Anthropic API key
  --context <file1> <file2> ...            # NOTE: --context is nargs="+" — ONE flag, many files
  --output summaries/<session>/consistency_report_<tag>.md
```

- `--backend claude-code` routes generation through the `claude` CLI in headless mode, billing the Pro/Max subscription instead of the metered API — use it by default. The script's own default (`--backend anthropic`) hits the API key, which can fail outright if that key's credit balance is low (seen in practice) even though the subscription is otherwise available and preferred.
- `--context` takes **multiple files after a single flag** (`nargs="+"`). Do **not** repeat the flag — a later `--context` overwrites the earlier one and silently drops files.
- **Always include the campaign-standard sources** (none are in the config auto-load):
  - `docs/party.md` — the PCs.
  - **`docs/entity_registry.yaml`** — the canonical registry of every entity, with its **aliases** and notes. This is the highest-yield source for the most common finding class (misspelled / mis-titled / mis-attributed entity names): the alias lists let the check separate a legitimate alternate name from a transcription error — e.g. `Asha` / `Asha Vandry` are canonical aliases of **Asha Vandree**, whereas `Bookworm` is *not* an alias of **Bookwyrm**, so it's a real error. Feed the **`.yaml`** for alias-level checking. Its generated human-readable companion `docs/entity_inventory.md` (canonical names + notes, no aliases) is a lighter alternative only when the context budget is tight. If the campaign has no registry yet, skip it (it's an enhancement, not a hard dependency).
  - **`notes/vtt_transcription_corrections.md`** — the campaign's wrong→right proper-noun glossary, the single source of truth for ASR garbles. It is *literally a table of the errors you are hunting*; include it whenever it exists.
  - **`notes/vtt_known_additions.md`** — names confirmed real during a `/vtt-spell-pass` but not yet promoted to the registry. Catches the newest names, which are exactly the ones the registry cannot vouch for yet.
  - **The SOURCE recap, when the target is an enhanced recap** (step 1). If you are checking an `enhance_summary` output, pass the `gm-assist.md` / `session_<date>_<slug>.md` it was built from. This is the single highest-value context file for that document class: it is already human-reviewed, so every difference between it and the enhanced version is *something the enhancement pass added*, which is exactly the material under test. Without it the check has no way to distinguish "detail recovered from the VTT" from "detail invented." Offer it as its own tier option ("Focused + source recap") rather than burying it.
- Then add every prep/handout file the user confirmed in step 2.5.
- **Quote paths with spaces** (in-world handout filenames often have them, e.g. `"notes/sessions/Kalan to Janussi - Second Petition.md"`).
- Save the report with `--output` into the session's summary directory.

### 4. Run the check

Execute and wait. Confirm the `Context : N document(s)` count and the absence of `context file not found` warnings (see step 2).

**Two script quirks that look like results but aren't:**

- **The `No issues found.` banner is an unreliable false negative.** `check_consistency.py` counts occurrences of the literal string `**Location**`, but models routinely emit `**Location:**` (colon *inside* the bold), so `issue_count` comes back 0 while the body lists a dozen issues. **Always trust the report body over the banner**, and derive your own count by grepping the saved report for its actual heading pattern. **`^### ` is a guess, not the pattern** — the model also numbers findings as bold runs under `##` section headers (`**1. Moesko is a half-orc, not an orc**`), where `grep -c "^### "` returns a confident **0** on a report carrying twelve findings. That is the same false zero as the banner, arrived at a second way. Look at the file before counting it:

```bash
grep -n "^## \|^### \|^\*\*[0-9]" <report>    # find the shape, THEN count it
```

Count whichever form is actually present, and say in the manifest which one you counted.
- **`--backend claude-code` can hit its output ceiling and auto-continue**, printing a loud `WARNING: claude -p hit its output ceiling mid-generation and AUTO-CONTINUED across N assistant turns` with a possible seam at the boundary. When you see it, **inspect the saved report before trusting it**: `grep -n "^### "` for contiguous, correctly-numbered sections and check the tail is a complete entry, not a mid-sentence cut. Report what you found. If the report *is* damaged, re-run with a raised `CLAUDE_CODE_MAX_OUTPUT_TOKENS`.

### 4.5. Record the sources used — REQUIRED (YAML manifest)

Write a manifest of exactly what content fed the check into the session's **summary directory** (the dir containing the checked document), named to pair with the report — `<report-stem>.sources.yaml` (e.g. `consistency_report_ch58.sources.yaml`); fall back to `<document-stem>.consistency_sources.yaml` if no report was saved. This is the provenance record — what the recap was judged against, so a later reader can reproduce or audit the check.

Write the `sources` half now; you will append the ruling half in step 6.

```yaml
consistency_check:
  timestamp: "<ISO-8601, from `date -Iseconds`>"
  campaign: "<workspace dir or name>"
  document_checked: "<relative path>"
  document_class: "<first-pass recap | enhanced recap | narration> [ + backfill]"
  report: "<relative path to saved report, or null>"
  config: "<config path used>"
  model: "<model the script reported>"
  backend: "claude-code"
  issues_found: <int — counted from the report body, NOT the banner>
  session_prep_used: true            # false if the user said `none` OR none exists
  entity_registry_used: true         # false if the campaign has no registry
  session_date: "<the session's own date, not today's>"
  temporal_gap: |                    # OMIT unless this is a backfilled chapter
    Session predates the grounding docs' current state by <N chapters / N years>.
    Party era from tape: <e.g. level 1>. Docs describe: <e.g. level 6, ch~45>.
    Findings rejected as anachronistic: <list>.
  speaker_map: |                     # whenever a speaker-labelled transcript exists
    <speaker> = <character>, derived from tape (not assumed from campaign docs).
    Absent players and who actually ran their PC.
  sources:
    auto_loaded:                     # from config _DEFAULT_CONFIG_DOCS
      - { label: campaign_state, path: docs/campaign_state.md }
      - { label: world_state,    path: docs/world_state.md }
    context:                         # every --context file, with why it was chosen
      - { path: docs/party.md,             role: "PCs (campaign-standard)" }
      - { path: docs/entity_registry.yaml, role: "canonical entity registry + aliases (campaign-standard)" }
      - { path: notes/vtt_transcription_corrections.md, role: "ASR garble glossary (campaign-standard)" }
      - { path: notes/<prep>.md,           role: "session prep (authoritative)" }
      - { path: notes/sessions/handouts/<...>.md,  role: "in-world handout / NPC tracker" }
  notes: |
    Caveats worth recording — config workaround used, prep was `none`,
    auto-continuation seam checked, session diverged from prep (step 5).
```

### 4.7. Adjudicate what the docs can't settle — against the VTT

**The grounding docs cannot resolve every finding, and the report knows it** — it will say things like *"the contradiction cannot be resolved from grounding docs alone — a VTT review is needed"* or *"flag for VTT review."* **Treat that as a work item, not a finding to hand back.** Go read the transcript. Handing the user an open question you could have closed in one grep is the main way a run under-delivers.

Grep the session transcript around the disputed beat. **Pick the file by what the question needs:** for *attribution* questions prefer a speaker-labelled Zoom `.md` (step 1) over any VTT; for *wording/quote* questions prefer `*.retranscribed.cleaned.vtt`, then `*.cleaned.vtt`. Three classes justify the trip:

1. **Internal contradictions** — the recap says one thing in the Summary and another in Scenes. One of them is right; the tape says which.
2. **Attribution questions** — who did/said/killed/freed what. These are *precision decisions*: never guess, always adjudicate.
3. **Facts that appear in no grounding doc at all** — props, equipment, improvised solutions. The check is **structurally blind** here: with nothing to contradict, it cannot flag them. Only the VTT can. In one run the recap invented an entire `Items → Rope` entry because it summarized the GM's offer (*"I'm assuming you have some rope"*) instead of the player's correction (*"I have a whip, so I'm gonna use the whip as a rope"*). Equipment and inventory are the common case and they propagate into future rulings.

**Watch specifically for retracted GM slips.** The single highest-value VTT catch is a name the GM misspoke, was corrected on, and fixed *on tape* — which the summarizer then transcribed in its **uncorrected** form:

> **GM:** "…all right **Veyra** kind of moves over here…"
> **Player:** "You put it in a different category."
> **GM:** "Oh, I pulled a different character. You're right. **I meant Sister Maela.**"

The recap's Scenes section credited Veyra. No grounding doc could ever catch this, because the docs record the *outcome*, not the retraction. When a finding involves a character name in a moment of table confusion, grep the surrounding ±20 lines for the correction pattern — `"I meant"`, `"sorry"`, `"you're right"`, `"hold on"`, `"different character"`.

#### A garbled PC name can be TWO characters fused — not one misspelling

**This is the trap the glossary itself sets, and applying the glossary row mechanically will silently create the error you were trying to fix.** The corrections table maps wrong→right one-to-one (`Sema → Soma`), which invites a global replace. But a summarizer that has lost the speaker signal for one PC will sometimes park *two* characters' actions under a single invented name — and the glossary will happily resolve all of them onto whichever real PC the string most resembles.

In one run `Sema` appeared 8 times. Six were genuinely **Soma** (tortle druid, she/her). Two were **Brewbarry** (goliath barbarian, he/him) — the near-death pseudopod hit and the rage-and-fists kill. A blind `Sema → Soma` would have credited the barbarian's rage, his fists and his 1-HP brush with death to a druid who was unconscious at the time, and would have looked *more* canonical afterwards, not less.

The tell was in the recap itself: **the same paragraph named `Soma` for Earth Tremor and `Sema` for the rage-kill.** A document that uses both forms in one breath is not misspelling one character — it thinks they are two people.

So, before any global replace of a PC name:

```bash
grep -n "<wrong-form>" <document>          # read EVERY instance in context, not the count
```

For each instance ask *which PC's abilities are being described* — class features are the discriminator, and they are usually unambiguous. Rage, Stone's Endurance and a halberd are the barbarian; Shell Defense is the tortle; a racial trait is not a class. Then confirm each cluster against the tape before touching the text. Split the fix: batch the instances that are a plain spelling error, and take the re-attributions to the user **one at a time with the transcript quote**, because they change who did what.

The same logic applies to a *class or race epithet* attached to the garble. `"Sema, the tortle barbarian"` names no one in the party — it welds the tortle **druid** to the goliath **barbarian**. When a recap gives you a race+class pair, check the pair against `party.md`; a mismatched pair is the loudest possible signal that two characters have been merged.

**The same discriminator rescues a garbled WEAPON or object, not just a garbled name — and this is where a well-intentioned deletion does real damage.** A recap detail can look invented because the noun that would confirm it was misheard, differently, by every transcript you have. On Phandalin ch08 the recap said *"Brewbarry delivers a final, lethal blow with his halberd to one of the harpies."* The tape's only `halberd` was the GM joking that Brewbarry threw hand axes *"like you were using halberds"* — so the first ruling was that the kill was fabricated, and the fix was to delete the bullet. Widening the grep overturned it. At the kill, the two transcripts disagree on the noun and agree on nothing else:

```
whisper : "So can I hit from here with my helmet?"
descript: "so can I hit from here with my- ... club?"
next line: "Without raging?"          <- rage is the barbarian
then    : "That is a kill."
```

**Two independent ASR passes garbling the same word into two different nouns is positive evidence that a real word was spoken there** — and the actor is settled by the class feature in the surrounding lines, exactly as for a garbled name. Never rule an event fabricated on the absence of a *noun*; rule on the absence of the *action*. Deleting a true event is the most expensive edit in this skill, because nothing downstream will ever restore it.

The corollary bit here too: the real defect ran the *opposite* way from the report's framing. The Scenes section was right and the **Summary** was wrong — it omitted the kill and called the character "missing everything in sight." When an internal contradiction involves an event one section has and another lacks, check whether the fix is an addition before assuming it is a deletion.

**Pronouns travel with this class of error and `party.md` is authoritative for them.** Fix them in the same edit as the name, not as a follow-up pass — a corrected name with the wrong pronouns reads as a *new* error to the next reviewer. In the run above the recap had "Brewbarry swung **her** halberd" and used he/him for Soma throughout.

#### The absent-player failure mode — why attribution collapses in the first place

When a player is missing, someone else runs their PC — commonly the GM, sometimes another player (campaign `CLAUDE.md` files often record who covers whom). **Both have now been observed in the same campaign**: on one Phandalin tape the GM ran Brewbarry despite `CLAUDE.md` naming Gary, and on ch08 it really was Gary — established acoustically, where `Brewbarry` and `Valphine` vocatives resolved to a single diarization cluster. The doc is a hypothesis every session; the tape is the answer. If the session has been through `/speaker-attribution`, its manifest already carries a tape-derived `speaker_map` — read it instead of re-deriving. **That PC's actions then come out of the wrong mouth for the entire session, and the summarizer has no clean speaker signal for them.** Every attribution error in one run traced back to exactly this: Stéphane was absent, the GM ran Brewbarry, and Brewbarry's rage, his kill and his near-death all got parked on a character the summarizer invented.

Detect it early — the speaker roster from step 1 is the cheapest possible check:

```bash
grep -oE '^\*\*[a-z]+:\*\*' <transcript>.md | sort | uniq -c    # fewer speakers than PCs?
grep -niE "<PC name>|rage|action surge|<their signature ability>" <transcript> | head -20
```

When the roster is short, **assume that PC's attributions are unreliable and check every one of them**, rather than spot-checking. Do not trust the campaign doc's stated cover arrangement either: one campaign's `CLAUDE.md` said Gary covers Brewbarry when Stéphane is out, but on that tape the **GM** was visibly running him (*"All right, Brewbarry So an 11 hits maybe?"*, *"Then I will rage"*, *"I think I'm punching this guy"*). Derive the speaker→character map from the tape and record it in the manifest — it is the single most useful artifact for whoever checks the next session.

#### Enhancement-pass failure modes (when the target is an enhanced recap)

An `enhance_summary` output is an LLM re-reading the VTT to add texture to an already-reviewed recap. It adds real detail — and it fabricates, drifts, and duplicates in five recurring ways. **None of these are catchable from grounding docs**, because the facts involved (which PC, which weapon, which number, what order) appear in no grounding doc at all. For this document class the VTT is not optional.

1. **Invented precise dice values.** The tape has the player rolling but never says the number, and the recap supplies one anyway — *"an investigation roll of 28"*, *"his first swing (a 7)"*. Neither existed on tape. **Test every specific roll value**: `grep -nE "\b28\b|twenty-eight" <vtt>`. If the only hits are WebVTT timestamps, it is invented. Note that the *adjacent* values are often real — in the same run the cellar-door "19" was verbatim on tape and a "24" traced to a garbled player line — so verify each one individually rather than sweeping the section.
2. **Attribution drift toward the prominent character.** The heal, the kill, or the clever line migrates to whoever the recap treats as the protagonist. In one run Maela's crypt *Cure Wounds* was credited to Zenvon in **four** separate sections; the tape had the GM saying *"No, Pip, because Pip's the closest… You get 10 more hit points, **Pip**"*. Zenvon was never healed at all and finished the fight at 4 HP.
3. **Event duplication alongside event loss.** One real hit gets split into two described attacks while a genuinely separate event is dropped. Same run: Zenvon's opening nat-20-for-8 and his dagger killing blow were both real, but his *middle* kill — scimitar via Nick for 12 — vanished from the recap entirely. Reconstruct the whole exchange before ruling on any single blow.
4. **Quote truncation with the marker left in.** Look for a literal `*(truncated)*`, an em-dash-then-nothing, or an ellipsis ending a quote block. The source recap frequently has the line complete; the tape always does.
5. **DM asides relocated onto the wrong result.** A memorable GM remark gets attached to the wrong mechanical outcome. In one run *"it does a lot less damage than the sound effects"* was moved off the 2-point Firebolt it described and onto an 8-point one — where the GM had actually said the **opposite** (*"this time it did sound that way"*).

#### Adjudication discipline

Two habits, both learned by getting it wrong mid-run:

**Read the sequence forward to its end before ruling on any part of it.** Ruling from the first matching grep hit produces confident, wrong answers. In one run the first hit showed a scimitar kill and the conclusion was "the recap's dagger killing blow is invented" — reading forty lines further revealed **two** kills by the same PC, and the dagger blow was real. The actual defect was the omitted first kill. `sed -n '<start>,<end>p'` the whole combat or scene; don't grep a keyword and stop.

**A negative finding is only as wide as your grep window.** "X never appears on tape" and "the party never learned Y" are the claims most likely to be wrong, and they are also the ones that get acted on destructively (cutting a true fact out of a recap). Before asserting an absence: search the concept, not just the token (`the family`, `that family`, `same family` — not only `Dendrar`), and read ±20 lines around every hit. One run's ruling missed the GM's confirmation by eight lines and cut a true inference on that basis.

**When the tape genuinely cannot settle it, say so and ask.** Some numbers are unrecoverable — the GM miscounts aloud mid-fight, or the arithmetic of a combat doesn't close. In one run the recap said four skeletons, the tape's own event sequence implied five, and the grounding docs said six; the GM's live count was audibly muddled. That is a GM question, not a finding. Do not silently pick the middle, and do not treat the reviewer's own reconstruction as authoritative over the person who ran the fight.

Quote the transcript verbatim when you present the adjudication, and record it in the manifest (step 6). Note in the manifest that the VTT was **consulted by hand**, not passed as `--context` — it is provenance for the ruling, not an input to the check.

### 5. Present findings — triage, don't dump

Report the issue count (yours, from the body), then show the report. **Triage the findings into buckets** rather than treating them uniformly:

- **Clear-cut errors** (name/spelling/title, internal attribution settled by the VTT, place-name inconsistencies, mechanics miscategorized, chronology) — recommend applying.
- **Canon judgment (needs the user's table knowledge)** — a "new fact" the recap asserts that no doc establishes, or a recap beat that contradicts prep because **play diverged**. Only the user knows what actually happened at the table; ask, don't guess.
- **Minor/optional** — mechanical nitpicks, phrasing, normalization.

Failure modes to check *the report itself* for before recommending anything:

**Grep the target for the quoted text before you believe any finding — the check attributes context text to the document under audit.** Everything in `--context` is in the model's window, and it does not reliably keep straight which file a sentence came from. The signature is a finding whose **Location** names a section of the target but whose quoted "current text" is not in the target at all; it is in a context file. This costs nothing to test and it is the cheapest filter in this step, so run it first, on every finding, before any other adjudication:

```bash
grep -nF "<distinctive fragment of the quoted text>" <target-document>
```

No hit in the target ⇒ the finding is a false positive *against this document*, whatever its merits elsewhere. Do not edit the target to satisfy it. Then grep the context files for the same fragment to find where the text actually lives, and decide separately whether that document needs anything — often it does not, because the pass under audit already fixed it.

This bites hardest at **Stage 1 of `/staged-consistency`**, where passing `gm-assist.md` as context is mandatory and the two documents are near-paraphrases of each other, so a fragment "looks like" the target. One Stage 1 run had **three of seven** actionable findings in this class, all quoting gm-assist prose: a fearlessness line and an overstated promise that the enhancement pass had already dropped or hedged correctly, plus the framing half of a fourth. Every one would have been an edit re-introducing an error into a document that had it right.

Note the direction this runs. A finding in this class is weak evidence that **the enhancement pass did its job** — it fixed something and the checker is quoting the unfixed upstream. Read a cluster of them as a good sign about the target, and say so when presenting, so the rejections don't read as the check being broken.

**A table ruling is not a rules error — and this is the single largest false-positive class.** The check reads the campaign's stated character levels and flags anything the rules don't permit at that level: Action Surge at Level 1, a third 1st-level slot, `Cure Wounds` rolled as `2d8+2`. But the recap records *what the GM did*, and the GM outranks the PHB at their own table. In one run **7 of 12 findings** were this class, and every one was wrong — the GM had ruled the sidekicks to 2nd level (making two of the findings moot outright) and had knowingly misread `Cure Wounds` at the table and wanted it recorded as played.

Before accepting **any** mechanics finding, grep the VTT for the GM declaring it:

```bash
grep -niE "action surge|2d8|spell slot|saving throw|wisdom" <vtt>
```

A GM saying *"He will use an action surge to attack the next one"* **is** the rule in that session. When you find the declaration, reject the finding and record the quote. When the finding also reveals that the grounding docs disagree with the GM about something structural — character levels being the recurring case — that is a `carry_forward` item, because it will re-trigger this same false-positive class on every future run until the docs are fixed.

**The grounding docs describe the party NOW; a backfilled chapter describes the party THEN.** On an old session (step 1) this is the second-largest false-positive class, and it is easy to mistake for real drift because the report's evidence is always a genuine quote from a genuine doc. The check has no notion of campaign time: it reads `world_state.md`'s spell list, `party.md`'s loadout and the stated character levels as if they were true on the session date. They describe a party that may be dozens of chapters and two real-world years further on.

The signature is a finding of the form *"X is not in this character's documented kit."* In one run three such findings — Thunderwave, Starry Wisp, and daggers — were all rejected, every one confirmed verbatim on a tape where the party was **level 1** and the docs described **level 6**.

Before accepting any finding whose evidence is a documented spell list, item list, or character level:

```bash
grep -niE "<spell/item>" <transcript>          # was it used at the table, on this date?
```

If the tape confirms it, the **recap is right and the grounding doc is merely silent about that era** — an absence of documentation is not a contradiction. Reject the finding, record the quote, and put the doc gap in `carry_forward` if it will re-trigger. Never "fix" a backfilled recap to match a later state; that rewrites history to match the present, which is exactly backwards.

Say the expected hit-rate out loud when you present findings on a backfill, so a pile of rejections doesn't read as the document being clean *or* the check being broken.

**The report can point at the correct half of a contradiction.** When the check finds the recap contradicting itself, it must guess which side is right — and it has no evidence to guess with. In one run the recap's `Spells` section correctly placed a DM aside and its `Summary`/`Scenes` misplaced it; the report recommended "fixing" the correct one. **Never accept the report's choice of direction.** Once a finding is an internal contradiction, the only question the report has actually answered is *that* the document disagrees with itself; *which* side to keep is always a VTT question.

**Module truth ≠ party knowledge.** Grounding docs encode what the GM and module know; the recap records what happened at the table. A finding of the form *"the recap says 'Human Boy' but `campaign_state.md` identifies him as Nars Dendrar"* is only a fix if the party **learned the name on-screen**. Grep the VTT. In one run the captives were never named at the table and the party never connected them to the villain's later reveal — applying the report's "fix" would have burned a live plot hook. Same test applies to any suggestion that adds a canonical name, title, or relationship the recap left vague. **Offer the user the choice** (keep anonymous / keep anonymous + bracketed GM-side note / name them outright) rather than picking.

Watch for the recap making the connection *itself* — an unearned inference like *"the very same family the party had already rescued"* is the summarizer reasoning past what the table established, and is worth cutting even when the underlying identification is correct.

**Module vocabulary is not table vocabulary — and neither is an error.** When a finding's only evidence is *phrasing* repeated across `campaign_state.md` / `world_state.md` / prep, with no backing entry in `entity_registry.yaml`, it is a register difference, not a factual error. Before recommending anything, run two checks:

1. **Is it in the registry?** No entry ⇒ no canonical form ⇒ no error.
2. **Does it trace to the module?** `grep` `docs/background/` (the bible, the inventory, the monster extractions). If the phrasing is the published text's own, the grounding docs **inherited** it; they did not drift into it.

One run flagged the recap's "red cloaks" against the docs' "scarlet cloaks." "Scarlet" was absent from the registry — but `docs/background/obelisk.md` had *"criminals who wear scarlet cloaks"* and *"a creature wearing the scarlet cloak of the Redbrands"* verbatim from the module. So both were right: **the module says scarlet, the table says red, and they are the same garment.** The GM's ruling was to change nothing anywhere — recap keeps table vocabulary, reference layer keeps module vocabulary — and to fix the *skill* so the pair stops surfacing.

**Never bulk-replace a color//adjective/title across a campaign.** In that same run a blanket `scarlet→red` would have corrupted "Scarlet drapes" (room decor), a mind flayer's "scarlet robe", and two faction names ("the Scarlet Fist", "the Scarlet Company"). Enumerate and read every hit before proposing a scope.

**Corollary — `docs/background/` is source, not working prose.** Module text, bibles, and their extractions are the reference layer. Never "correct" them to match a recap; the recap is downstream of them. If a finding's fix would edit `docs/background/`, that is a strong signal the finding is inverted.

**Don't trust the report's "No issues found with:" footer either.** It is the same model asserting things are *verified*, and it inherits the same blind spots. One run's footer listed *"the Dendrar family composition (two women + young boy = Mirna, Nilsa, Nars)"* as checked-and-clean — but that equation is module knowledge the party never learned on screen, and writing it into the recap would have burned a live hook. Read the footer as findings, not as clearance.

**Findings often implicate the grounding docs too.** When a name is wrong in the recap *and* in `campaign_state.md` / `world_state.md` (the check will sometimes say so outright), fixing only the recap leaves the corpus inconsistent and guarantees the finding recurs next session. Don't silently expand scope — record these under `carry_forward` in the manifest and surface them in the closing summary.

**When the GM does authorise a grounding-doc fix, propagate the whole class, and check the direction first.** A VTT-confirmed correction usually lands in more places than the recap: an attribution error will sit in `world_state.md`'s timeline *and* in the per-character "Recent notable actions" lines in `party.md`. Grep for the wrong form across all four grounding docs before editing, and re-read `carry_forward` from prior manifests — old `OPEN` items are often the same class and can be closed in the same pass.

But check which way the error actually runs. In one run the GM ruled "six skeletons, four killed, two left" and asked for the grounding docs to be fixed — inspection showed `campaign_state.md` and `world_state.md` **already said six**, and it was the *recap* that said four. The instruction was right about the fact and wrong about the location. Survey before you edit, and say plainly which file was actually wrong.

**Play-divergence caveat.** When the session went off the prep's rails (players do), the check will flag large prep-vs-recap contradictions that are *legitimate divergence, not errors* — the recap reflects actual play. Flag these as informational; do not "fix" the recap to match superseded prep. The high-value catches are name/title/quote/**transcription** errors.

Ask which fixes to apply. Apply only approved ones, **one at a time, via Edit**, citing the report's **Suggested fix**. Users commonly say "fix the clear-cut ones, then go 1x1" — batch the unambiguous set, then present each judgment call singly with its evidence and a concrete diff, and wait for a ruling on each.

**Order the batch so edits don't collide.** When one fix rewrites a line another fix also touches (a name normalization inside a sentence you're re-attributing), do the rewrite first and spell the corrected name into it, rather than editing the same line twice.

### 6. Record the outcome — REQUIRED

Append the ruling half to the manifest from step 4.5. The sources record what the recap was *judged against*; this records **how it was judged**, which is what a later reader actually needs.

```yaml
  resolution:
    reviewed_by: GM
    reviewed: "<date>"
    gm_rulings_this_run:              # standing rulings the GM stated in conversation,
      - "<e.g. 'the sidekicks are all 2nd level' — records WHY findings were rejected,
         and flags that the grounding docs now disagree with the GM>"
    applied:
      - { finding: 1, fix: "<what changed, with counts>" }
    partially_applied:
      - finding: 10
        ruling: "<the user's decision in their words>"
        fix: "<what was actually changed>"
        rationale: "<why the report's suggestion was narrowed>"
    rejected:
      - finding: 12
        ruling: "<the user's decision>"
        rationale: "<the evidence — incl. registry checks and VTT quotes that contradicted it>"
  vtt_adjudicated: |
    Which findings were settled against the transcript, the VTT path, verbatim
    quotes, and the ruling. Note that the VTT was consulted by hand and was NOT
    a --context input. Record your OWN mid-run corrections here too — a first
    reading that was overturned by a wider read is the most useful thing a later
    reader can learn from.
  carry_forward:
    - status: OPEN | DONE | CORRECTION | WONTFIX | NOTE
      item: "<what, and enough evidence that the next run doesn't re-derive it>"
    # Typical entries:
    # - Errors this run found in the GROUNDING DOCS rather than the recap.
    # - Structural disagreements between the GM and the docs (levels, counts) that
    #   will re-trigger a false-positive class every run until fixed.
    # - Entities now settled and ready for /entity-triage promotion.
    # - CORRECTION entries overturning a PRIOR manifest's ruling, with the evidence.
```

Use `status:` on every `carry_forward` entry. An un-statused list rots — the next run cannot tell a live work item from a closed one, and `OPEN` items get silently re-derived from scratch (one rope-vs-whip item survived two runs that way).

Validate it parses (`python -c "import yaml; yaml.safe_load(open(...))"`), then verify the recap is clean — grep for every wrong form you fixed, and show the `git diff`.

Close with: what was applied / partially applied / rejected, **what the VTT caught that the check structurally could not**, and the carry-forward list. Don't commit unless asked.

## Notes

- `check_consistency.py` auto-loads `campaign_state` + `world_state` from config; everything else — `party.md`, `entity_registry.yaml`, the VTT glossaries, prep — must be passed via `--context` (step 3 makes them standard).
- **`docs/entity_registry.yaml` is the canonical entity tracker** — every entity with its aliases and notes, generated alongside `docs/entity_inventory.md`. Because it encodes aliases, it is the best source for the highest-frequency finding class (name/title/attribution errors); include it on every run when it exists. It is also the **arbiter for rejecting findings**: if a name the check flags has no registry entry, the "correct" form it proposes may be nothing more than inherited module phrasing. Same registry the `entity-triage` and `vtt-spell-pass` skills build on. Its authority is real but bounded — see the next three bullets on what must never be written into it, and on `registry check`'s known false positives.
- **"The registry has the wrong name" is usually "the registry has no name."** When a bad name reaches the grounding docs, check for *absence* before assuming a wrong entry — `grep -ciE "<name>|<variants>" docs/entity_registry.yaml`, and beware substring false hits (searching `wick` matches *Tumblewick Rollins* and *Pip Thistlewick*). In one run neither of the session's two new NPCs was registered at all across 374 entities; both were still staged in `notes/vtt_known_additions.md` as unpromoted. **That silence is the root cause** — with no entry to contradict it, a summarizer-invented spelling propagated into three grounding docs unchallenged. The fix is promotion (`/entity-triage`), not correction, and it belongs in `carry_forward`.
- **Garbles are not aliases. The registry holds *identity*; the glossary holds *transcription repair*.** Aliases are legitimate alternate ways to refer to the entity — titles, short forms, in-world epithets (`Professor Orryn Voss`, `Sildar`, `the Spider`). ASR mishearings (`Oren Voss`, `Clarg`, `Glastaff`, `Dessa`) are **errors**, and they belong in `notes/vtt_transcription_corrections.md`, never in `entity_registry.yaml`. Writing a garble into the registry as an alias tells every downstream consumer — `check_consistency.py` above all — that the garble is a *correct* form, which suppresses true findings. If a GM asks you to "fix the registry" for a misspelling, apply this test to each variant before writing anything.
- **`registry check`'s grouping drift is a known false-positive source — do not action it blindly** (CampaignGenerator#216). It compares the registry against `docs/ensemble/aliases.json`, which is *generated from the garble glossary* and therefore contains mishearings by design. Every garble whose canonical entity is registered appears as `aliases.json groups ['Klarg', 'Clarg'] but registry resolves them to ['Klarg', 'MISSING']`. The only way to silence it is `registry alias` — which writes the garble into the registry and does exactly the damage described above. Treat that section as informational; the genuinely useful signal is the `MISSING`-on-*both*-sides case, which means the entity isn't registered at all.
- **Two different files are named `aliases.json`.** `docs/aliases.json` is the identity projection, written by `registry project` from `entity_registry.yaml` (canonical → legitimate aliases). `docs/ensemble/aliases.json` is the garble map, written by `docs/ensemble/build_aliases.py` from the corrections glossary (canonical → mishearings). Same shape, opposite meaning. Check which one you're reading before drawing a conclusion, and note that the garble map goes stale — regenerate it (14 → 53 entries in one run) rather than trusting its current contents.
- **Adding a glossary row is a behavior change; verify the wrong-form actually occurs in a VTT first.** `grep -ril "<form>" summaries/*/*.vtt`. A form that appears in **no** transcript is a summarizer invention, not a transcription error — adding it achieves nothing because the spell pass only ever sees VTTs, and the real fix belongs in the recap that contains it. When a new row overlaps a shorter existing one (`Sister Vera` vs `Vera`), it is safe: `apply_replacements.py` sorts longest-first by design. Confirm by running the applier to a scratch output and reading the replacement log — never in place.
- **Registry CLI invocation:** `python -m entity_registry.registry <verb>` **from the CampaignGenerator repo root**. Calling `entity_registry/registry.py` directly dies on a relative import (`from . import spell_canon`). Verbs include `add`, `alias`, `triage-candidates`, `merge`, `project`. A registry MCP exists at `entity_registry/registry_mcp.py` but is not necessarily registered in a given campaign's `.mcp.json` — check before assuming it's available; `configure_mcp <campaign-dir>` adds it (merge semantics; `--force` rebuilds and can drop servers).
- **A speaker-labelled transcript beats a cleaner unlabelled one for any attribution question.** Zoom `.md` exports carry `**name:**` prefixes that no `.vtt` in the same directory has. Check for one in step 1, name it in the manifest, and rule on content with labels as corroboration — dedup passes merge turns and the GM's block absorbs other voices.
- **Applying a glossary row globally is not always safe.** The corrections table is 1:1 by construction, but a summarizer that lost one PC's speaker signal can file two characters' actions under a single bad name. Read every instance in context and discriminate by *class feature* (rage/Stone's Endurance = barbarian; Shell Defense = tortle) before replacing. A race+class epithet that doesn't match anyone in `party.md` — "the tortle barbarian" in a party whose tortle is a druid — means two PCs have been merged.
- **Check the speaker roster against the party before anything else.** A missing player means someone else ran their PC all session, which is the usual root cause of attribution collapse. Don't trust the campaign doc's stated cover arrangement; derive the map from the tape.
- **Never edit a backfilled recap to match the present.** Grounding docs describe the party now; the recap describes the party then. A finding of the form "X isn't in this character's documented kit" is, on an old session, far more likely to be a doc that is silent about that era than a recap that is wrong. Confirm on tape and reject.
- **Three transcripts can give three answers.** A session dir may hold the raw `.vtt`, a glossary-`cleaned.vtt`, and a `retranscribed.cleaned.vtt`. Prefer the retranscribed one and say which you used. Instructive case: the raw ASR heard "Dessa", the glossary mapped it to "Dosa", the retranscription independently confirmed "Dosa Rook" — and the spelling that reached the docs was "**Desa**", which appears in *no* transcript. A wrong name that matches neither the garble nor the truth is a **summarizer invention**, not a transcription error, and no glossary will ever catch it.
- **Session prep is the highest-value context for *this session's* facts** — it catches VTT transcription errors nothing else can. Discovering it (step 2.5) across the whole `notes/` tree, and choosing a focused set, is the most important part of a good *run*.
- **The VTT is the highest-value source for the findings the run can't close** (step 4.7) — retracted GM slips, attribution, and facts absent from every doc. Prep makes the check smart; the transcript makes the *review* decisive.
- **Different document classes fail differently, and the run should be shaped accordingly.** A **first-pass recap** fails on *names* — transcription garbles, misspellings, mis-titles — and prep plus the glossaries catch most of it. An **enhanced recap** inherits those fixes clean and fails instead on *numbers, attribution and ordering*, none of which any grounding doc records. A **backfilled old chapter** (a first-pass recap of a session from long ago, typically part of a sweep to fix historical data) fails on names *and* attribution, usually has **no prep at all**, and generates a large class of false positives where the check compares a young party against grounding docs describing the present one — in one run 3 of 13 findings were purely that gap, and the two worst real defects (a garble that fused two PCs, and every heal credited to the wrong character) were invisible to the check and came only from a speaker-labelled transcript. On the enhanced class expect the report's hit rate to be poor — in one run **8 of 12 findings could not be applied as written** (7 rejected outright as table-accurate, 1 correct about the contradiction but pointing the wrong way) — and expect the VTT to supply most of the real errors (that same run: six the check could not see, including a heal credited to the wrong PC in four sections). Say which class you are checking in the manifest, and don't let a low report hit-rate read as "the document was clean."
- The check is **advisory** — review every suggested fix before applying; never bulk-apply. The report is another LLM's unreviewed output: it can be confidently wrong about which side of a discrepancy is correct, and it can be confidently wrong that a table ruling is a rules violation.
- **The reviewer is fallible too, and mid-run self-correction is normal.** Both of the reviewer's own errors in one run came from ruling before reading far enough — one from a grep window eight lines too narrow, one from stopping at the first matching combat hit. When you overturn your own earlier reading, say so plainly to the GM *before* they act on it (it changes which edits get made), and record it in `vtt_adjudicated`. A finding you stated and then corrected is more useful documented than quietly dropped.
- Config resolution (step 2) is a known `check_consistency.py` limitation — CWD-only lookup with a fallback to the toolkit's own config. Run from the workspace root or pass `--config`; verify before blaming the check.
- The YAML manifest (steps 4.5 + 6) is not optional — it is how the campaign records what each recap was judged against **and how each finding was ruled**.
