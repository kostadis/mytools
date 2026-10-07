# Convergence report: voice-critic

Compared: `codex/skills/voice-critic/` vs `claude/skills/voice-critic/` (paths relative to `/home/kostadis/src/mytools/dotfiles/`). Below, `codex/SKILL` means `codex/skills/voice-critic/SKILL.md`, `codex/REF` means `codex/skills/voice-critic/references/checks-and-report.md`, and `claude/SKILL` means `claude/skills/voice-critic/SKILL.md`.

## 1. Summary

This pair is **highly divergent**. The two are not a port and its original: they are two separate writings of the same checks. Codex (173 + 112 reference lines) is a compact rule set with no examples. It sits later in the pipeline: it knows about `dialogue-edit` revisions, and it has a full apply-after-decisions loop with frozen hashes. Claude (407 lines, plus a 327-line reference HTML page) carries the measured cases behind every rule: Phandalin ch48, ch50 and ch2, the #245 benchmark, #276, #300 and #301. It also carries inline scan scripts and a fixed proof-sheet design.

**Lineage.** Claude came first. It was created 2026-05-25 (`4210f6f`) and reworked through August. The #125, #126, #128 realignment happened 2026-08-12/13, and the sage and em-dash provenance notes were added 2026-08-16/18. It was last touched 2026-09-04 (`1c74e92`). Codex was added 2026-09-18 (`8bfd959`) as the "Codex/Astra counterpart" (`codex/SKILL:10`) and has not changed since. `20069d6`'s claim that the remaining pairs are "in sync" does not hold for this pair.

**Which side is more developed.** Claude is richer in operational knowledge: the reasons behind each rule, the exact scans, the design spec. Codex is more current on workflow: `dialogue-edit` integration, provenance and hash discipline, the apply loop, and more careful epistemic hedging.

## 2. File inventory

| file | codex | claude | status |
|---|---|---|---|
| `SKILL.md` | 173 | 407 | differs (independent rewrite) |
| `references/checks-and-report.md` | 112 | — | only-codex (its content sits inline in Claude's Phases 1–7) |
| `reference/proof-sheet.html` | — | 327 | only-claude (the page Phase 8 says to copy; ch02 scene 04, 2026-09-02) |
| `agents/openai.yaml` | 4 | — | only-codex (platform metadata) |

Note the directory names: Codex uses `references/`, Claude uses `reference/` (singular).

## 3. Only in Codex

1. **Critiquing `dialogue-edit` revisions.** `codex/SKILL:25-30`: "After dialogue-edit: read `dialogue_edit.sources.yaml`, application records, promotion status, and hashes. An explicitly selected approved revision outranks a directory scan. Never critique `candidate.md` as approved." Claude has no mention of dialogue-edit anywhere (grep: 0 hits). Claude's directory rule (`claude/SKILL:36,61`) would pick the raw or scrubbed scene, which is exactly the wrong version that `dialogue-edit/SKILL.md` warns about.
2. **Where reports go for dialogue-edit revisions.** `codex/SKILL:116-118`: "For dialogue-edit revisions, put reports under a separate `<session>/voice_critic/<run>/` … leave frozen dialogue-edit records intact. Preserve previous completed reviews with a new run/path when necessary." Claude has no equivalent.
3. **Edited dialogue counts as protected speech.** `codex/REF:14-16`: "Treat dialogue as protected, including GM-approved dialogue-edit rewrites, which are protected edited speech rather than verbatim transcript. Honor recorded tape divergences." Claude calls quotes "VTT-captured speech … must stay exactly as extracted" (`claude/SKILL:65`). Claude mentions tape divergence only by reference to scrub (`:247`).
4. **Extra inputs.** `codex/SKILL:48-51`: read `config/players.yaml`, "campaign register/ruling records. In particular, read `notes/scrub_register_policy.md`". `codex/SKILL:79`: "`writing_brief.md` when the effective generation path includes it". `codex/SKILL:80`: "Use retained prompt logs for historical rules when available." Claude has none of these (grep 0 for each).
5. **Resolving the exact reviewed extraction.** `codex/SKILL:59-63`: "Resolve the exact reviewed extraction from narration run/source records … Never choose the newest extraction or infer a source solely from a similar filename." Claude hard-codes `scene_extractions/` vs `scene_extractions_smoothed/` (`claude/SKILL:180-181, 218`). See also Conflict 6.
6. **GM voicing PCs.** `codex/SKILL:57`: "Stage directions matter when the GM voices PCs; do not equate player and speaker." Claude has no equivalent.
7. **Observability of model and effort.** `codex/SKILL:13-14`: "Record model/effort only when observable; a skill name is not runtime evidence." Claude has no equivalent. Claude's fable-vs-opus rate claims (`:222`) are background knowledge, not run records.
8. **Batch across the session, not scene by scene.** `codex/SKILL:37-38`: "Prepare all requested scenes together … Do not impose a scene-at-a-time approval cycle." Claude publishes one page for the critique, which is in practice the same thing, but it never states the rule.
9. **Running `voice_lint` on per-scene files through a temporary assembled document.** `codex/SKILL:96-99`: "If it requires assembled headings, build a temporary analysis document with an exact source/line mapping; exclude duplicate raw/scrubbed variants. Never count report prose or review copies as narration." Claude notes that assembled "is also the shape `voice_lint` assumes" (`:28`) but runs `voice_lint <narration-files>` directly (`:145`) and gives no mapping step.
10. **Measurement discipline for prose counts.** `codex/REF:5-12`: "Recognize straight and curly quotes, multiline speech, and attribution outside quotes; a naïve quote regex is not a reliable parser … State the measurement boundary and denominator … Never present estimates as exact counts." Claude's Scan C script (`:195-211`) is exactly a naïve regex (`startswith('"')`). It has no curly-quote handling.
11. **Mixed rulebook versions in one aggregate.** `codex/REF:75-76`: "Resolve mixed rulebook versions per render; do not merge contradictory thresholds into a made-up global cap." Claude detects sibling digest drift (`:110`) but says nothing about how to build a ledger across versions. The proof sheet shows three rulebook versions in one session (`reference/proof-sheet.html:125`). **Partial.**
12. **Hatch absence vs. inability to inspect.** `codex/REF:67-69`: "On assembled input, where assembly may strip them, inspect available selected source scenes; otherwise say hatch review unavailable rather than 'none.' Record actual absence separately from inability to inspect." Claude's template says "Empty section with 'none' when there are none" (`:315`). Claude knows `assemble.py` strips hatches (`:324`), but its template has no "unavailable" state for assembled input.
13. **Zero-findings output.** `codex/SKILL:126-128`: "Zero findings still gets a report and a readable page; if the builder requires nonempty items, write a static report page with no dummy decision." Claude has "Zero flags … is a legitimate … result" (`:249`) but no page-level rule. **Partial.**
14. **Three finding classes.** `codex/SKILL:133-135`: "Distinguish confirmed breach, plausible editorial concern, and scope decision. Unresolved identity/source issues get discussion or referral, not an executable speculative replacement." Claude's proof sheet has breach and plausible severities (`:345-346`), and scope calls sit in a separate section (`:360`). The "no executable speculative replacement" rule is Codex-only.
15. **The frozen-decision apply loop.** `codex/SKILL:137-152`: "Freeze a sidecar mapping of IDs to exact old/new spans, original target hashes, reference hashes, and review ID … Validate review ID, item IDs, hashes, and unique spans before writing; a changed proposal or stale target needs a fresh review rather than a guessed merge." Claude has no hash or review-ID binding. Its apply step is a free "second pass" (`:384`).
16. **Status vocabulary for the review record.** `codex/REF:110-112`: "distinguish open, rejected, deferred, resolved, and not-run states. A resolved style review does not certify unperformed consistency, coverage, or upstream fidelity checks." Also `codex/SKILL:171-172`: "Do not claim full consistency or fidelity certification from a voice review." Claude has no equivalent.
17. **Referrals to other workflows.** `codex/REF:51-53`: "Missing events, source errors, identity disputes, and table mechanics get evidence-backed referrals to coverage/consistency/scrub workflows." Claude has the same idea but only for Scan C findings (`:220`: table-speak → `/scrub`, wrong label → `/session-summary-consistency`). **Partial.** Codex adds coverage for missing events.

## 4. Only in Claude

1. **Why this skill drifts.** `claude/SKILL:15`: "A critic that carries its own hand-typed copy of the rules is not checking the pipeline — it is checking a fork … Do not retype a regex or a word list into this file." Codex has the rule in one line (`codex/SKILL:81`: "Never copy a stale list of bans into this skill") but none of the reasoning.
2. **The declared-roster rule and its history.** `claude/SKILL:73-93`: the `party.yaml` example, `load_declared_voices`/`get_voice_note` exact match, #175/#247/#301 (a 51,073-character global block), and "when the source and this file disagree, the source wins and you fix this file." Codex gives the rule (`codex/SKILL:53-56`) but not the API names, the history, or the self-repair instruction.
3. **`[no spec available]` is usually a lookup bug.** `claude/SKILL:93, 389`: "since `sd_narrate` refuses to start without a declared spec, a report tagged `[no spec available]` is far more likely to be a lookup bug on your side" (#300). Codex has no equivalent.
4. **The party doc can be silently partial.** `claude/SKILL:95`: "its roster block can be silently *partial* … (campaigns#144)". Codex only lists "roster/party coverage" as a report field (`codex/REF:97`).
5. **The migration command.** `claude/SKILL:119`: "an unrun migration, `python -m server.migrate_narrate_genre --campaign-dir <DIR>`. Report it as the report's first line." Codex says only "Report a missing expected rulebook prominently; do not run migrations" (`codex/SKILL:77`). It does not name the migration or put it first in the report.
6. **The pre-#276 flattening measurement.** `claude/SKILL:111`: "Zero newlines in a multi-thousand-character value means this render received the rulebook as a single-line `GENRE:` label … 3 of 62 rendered scenes are in the required tense." Codex has the concept but not the zero-newline test. See Conflict 4 for the tone difference.
7. **HARD BANS are moves, not wordings.** `claude/SKILL:126`: "the bans are **moves, not wordings**: behavioral taxonomy in any shell, and recap framing." Codex reads `base.md` (`codex/SKILL:78`) but never says this.
8. **What to extract from the rulebook** (`claude/SKILL:132-136`). Two items are Claude-only:
   - The worked em-dash example, contrasting Phandalin's "never as a connective" with out-of-the-abyss's permission-only rule. Codex has the principle in a generic form (`codex/REF:32-34`).
   - **Content protections**: "'never sanitize the escapee names' … A paraphrase of `Leemoogoogoon` as 'the Sea Mother's rival' is a rulebook breach, not a style preference." Codex does not mention content protections or sanitisation at all (grep 0).
9. **The `voice_lint` output streams, in detail.** `claude/SKILL:148-158` describes what it checks. It also lists the five skip causes: "Only the third and fourth mean *this campaign has no filing register*. The others mean the rulebook did not arrive." Codex covers the general principle (`codex/SKILL:102-105`, `codex/REF:81`) but not the five-cause breakdown.
10. **Scan A2 as a runnable diff, with its evidence.** `claude/SKILL:164-189`: the ch48 table (0 → 59 trailing dashes), the `grep -rhc '—"$'` loop, and "Prefer the raw extraction's punctuation, which is the pre-smoothing capture." Codex has the concept (`codex/REF:35-40`) but no command and no source-preference rule.
11. **The Scan C script and its clearance rules.** `claude/SKILL:193-218`: the Python script, the tagged two-hander and chorus exemptions, and "Where the smoothed layer says `UNKNOWN` or `unconfirmed`, leave that line untagged." Codex has the prose rule (`codex/REF:41-45`) but no script.
12. **Scans are a floor, not a ceiling (#245).** `claude/SKILL:222`: "every mechanical scan returned **zero** tic hits across all 12 scenes, while reading the same prose found three confirmed instances … fable flags at roughly half opus's rate." Codex has only "Scans surface candidates; the full reading establishes findings" (`codex/REF:50`).
13. **The eight-category reading taxonomy.** `claude/SKILL:228-235`. Codex lacks two of the categories:
    - **Rulebook conflict** (#3), including tense/POV breaches.
    - **Cliché / on-the-nose simile** (#6), as a category of its own.

    Codex folds cliché into "Generic prose, clichés, and emotional commentary" (`codex/REF:21`).
14. **Fable's recurring profile.** `claude/SKILL:237`: the four model-default failure modes to "Check … explicitly even when the scans return zero." Codex mentions portable tics and bookkeeping (`codex/REF:28-31`) but not the "fable profile" framing, and does not require checking even when scans are clean.
15. **The "Do NOT flag" list.** `claude/SKILL:239-245`. Codex has most of it (`codex/REF:22-24`: "Plain action, short sentences, and direct feeling are not defects … Examples may deliberately license"). Two items are Claude-only: "prose that echoes a *global* example: it is obeying instructions", and do not flag hatch contents.
16. **The concrete sage-note format and precedent.** `claude/SKILL:247`: "`*Marginal note in a later hand: "<term>" — <in-world explanation>. — <sage persona>*` … (Phandalin: **Kostadinious the Sage**) … Precedent: Jimble the Unmoved, Phandalin ch3 scene 07". Codex says only "consult the campaign's established sage convention" (`codex/REF:61-63`).
17. **An example budget ledger with the fable-era caps.** `claude/SKILL:253-272`: "more than one 'the shape of X' across the entire doc means the pass failed … 1–2 load-bearing narration em-dashes". These are presented as examples of rulebook caps. Codex deliberately carries none (`codex/REF:79`: "No default numerical budgets live here"). This is compatible, since Claude also says "Do not carry a default here" (`:255`).
18. **The resolution table template.** `claude/SKILL:286-297` gives the full Inputs-resolved table. Codex lists the fields in prose (`codex/REF:94-98`).
19. **The whole fixed design spec for the proof sheet.** `claude/SKILL:330-375` covers tokens, fonts, layout, card stripes and the `vc-<session>-s<NN>-r<N>` storage key, plus `reference/proof-sheet.html`. Mostly this is platform (§6). The substantive parts are Claude-only:
    - "Never render a skipped check in the same style as a passing one" (`:356`). Codex has the idea at `codex/SKILL:125-126`, so it is shared in principle.
    - "Where a finding is a convergence between two narrators, **put both quotes in the same card**" (`:358`). Codex has this too (`codex/SKILL:132-133`), so it is shared.
    - The per-scene grid "short bar" diagnostic (`:359`).
20. **Keep the review surface honest.** `claude/SKILL:377-379`: "patch the artifact rather than leaving it asserting a state that is no longer true … record any claim of yours that turned out to be wrong." Codex has "Update the review surface's resolved state and corrected counts" (`codex/SKILL:166-167`), which is similar. The "record your own wrong claims" part is Claude-only.
21. **Fixes get wiped by `/scrub`.** `claude/SKILL:383`: "`/scrub` regenerates `.scrubbed.md` from the raw `.md`, so the next scrub run on that scene silently wipes every voice fix … Write a `voice_fixes_<session>.md`." Codex has the `voice_fixes` file (`codex/SKILL:165`) and a related warning, "Never … silently lose prior dialogue edits by regenerating from raw narration" (`codex/SKILL:159-160`). It never names the `/scrub` hazard.
22. **The collision example.** `claude/SKILL:384`: "Phandalin ch50: a replacement reading `I set it beside the rest` landed two scenes from an existing `I set it on the shelf`." The rule itself is shared (`codex/SKILL:163-164`).
23. **Examples settle register disputes, with a worked case.** `claude/SKILL:390`: Brewbarry's "Order is bullies. They bully barbarians." The rule is shared (`codex/REF:26-27`).
24. **Checking an ordering claim, with a worked case.** `claude/SKILL:392`: ch50's wrong "eleven lines moved out of order". The rule is shared (`codex/REF:46-48`).
25. **Output style rules.** `claude/SKILL:394`: "No commentary on the critique itself … State the strongest specific issue and stop." `claude/SKILL:401`: "**Lead with a rulebook problem when there is one.**" `claude/SKILL:405-407` lists reminders, including the `sd_narrate --scene <N>` re-run path. Codex has none of these.
26. **Missing examples.** `claude/SKILL:395`: "No invented examples. If the per-character examples are absent, don't fabricate the 'right' voice." Codex's "grounded in examples only" label (`codex/SKILL:83-85`) covers part of this. **Partial.**

## 5. Conflicts

1. **What to do when a narrator has no spec.**
   - Claude `:43`: "if both are missing, skip that scene with a one-line note rather than fabricating a critique."
   - Codex `codex/SKILL:84-85`: "if neither resolves, skip that narrator's voice judgment while retaining independently supported checks."

   One skips the scene; the other skips only the voice category.

2. **Whether a doc-wide cap breach means re-rendering.**
   - Claude `:407`: "Budget breaches usually cannot be spot-edited into compliance — a doc-wide cap breach is a re-render signal."
   - Codex `codex/REF:86-88`: "Recommend spot edits or regeneration based on the actual distribution and cost, not an assumption that any breach requires regenerating the whole document."

   Claude's own `:391` (rank the instances, name the target count) leans toward Codex's position, so Claude is internally inconsistent here too.

3. **Where applied fixes are written.**
   - Claude `:383`: fixes "belong in the `.scrubbed.md` file (not the raw `.md`) so `assemble.py` picks them up."
   - Codex `codex/SKILL:155-158`: "Default to a separate derived revision before promotion … For an existing raw/scrubbed pair, mirror the approved voice change to both where the exact span applies."

   The two disagree on the default destination (in-place `.scrubbed.md` vs. a separate revision), and on raw-only vs. mirroring to both files.

4. **How strongly to attribute findings to a flattened pre-#276 rulebook.**
   - Claude `:111`: "register findings about tense and register as *probably delivery, not authorship*, and say so in the verdict."
   - Codex `codex/SKILL:69-71`: "report suspicious flattening and delivery uncertainty, without claiming it proves the cause of a prose defect."

   Claude assigns a probable cause; Codex forbids asserting one.

5. **Orphan-quote fixes: whether an action beat may be added.**
   - Claude `:218`: "Add speaker tags and action beats around the quotes; never touch a word inside them."
   - Codex `codex/REF:44-45`: "Tagging is a prose proposal, not permission to rewrite dialogue or invent an action beat."

6. **The source for tags and for dash provenance.**
   - Claude `:218` names `scene_extractions_smoothed/NN_*.md` as the attribution source. Claude `:184` says "Prefer the raw extraction's punctuation."
   - Codex `codex/SKILL:59-63` uses whatever reviewed extraction the run records name. It traces "through selected narration, reviewed extraction, predecessor, and tape" (`codex/REF:35-37`).

   If a campaign's narration was rendered from another layer (for example after `no-mech`), Claude's hard-coded directories point at the wrong file.

7. **Whether the provenance delta counts as the finding.**
   - Claude `:184`: "**A nonzero delta is the finding.** Then adjudicate only the deltas."
   - Codex `codex/REF:37`: "A count delta is a candidate, not proof of a false interruption."

   Both adjudicate afterwards, so the difference is mostly wording, but it affects how the ledger reports the delta.

8. **Whether italic spans count as prose.**
   - Claude `:63-66`: strip `*…*` italic spans, "never flag inside".
   - Codex `codex/REF:8-10`: "Italic inner thought remains relevant to voice/tense judgment, but exclude it from counts when the actual rule/checker's budget scope excludes it."

   One excludes italics from all reading; the other excludes them only from counts, and only when the scope says so.

9. **Whether approval authorizes writing.**
   - Claude `:385`: "**Never auto-apply rewrites.**" Claude `:383` treats applying as something "the user subsequently" does.
   - Codex `codex/SKILL:146-148`: "Apply approved exact replacements when requested or already authorized by the review's stated approve consequence. No repeat confirmation is needed for the same replacement."

10. **The triage vocabulary and how decisions return.**
    - Claude `:365`: "act / keep / defer", persisted in `localStorage`, returned by a **Copy decisions** paste. Claude `:369`: "Do **not** reach for the `artifact` runtime capability here."
    - Codex `codex/SKILL:120-122, 139-141`: the shared `build_review.py` with approve / reject / discuss, Copy output / Save output, and "localStorage and file timestamps do not [authorize]."

    Part of this is platform. The verdict vocabulary and the choice of the shared builder over a bespoke page are real design differences. Claude's own `_shared/review-artifact` (approve/reject/discuss, `capabilities: {"artifact": {}}`) is what Claude's `dialogue-edit`, `scrub` and the others use. Claude voice-critic explicitly rejects it.

11. **Whether publishing the page is optional.**
    - Claude `:328`: "**Always publish**, once the reports are written."
    - Codex `codex/SKILL:109-110`: a page is "the default review surface. Reuse an explicit chat-only preference."

12. **Whether to change `voice_lint`.**
    - Claude `:386`: "If a check needs a pattern this skill does not have, add it to `voice_lint`."
    - Codex `codex/SKILL:104-105`: "Do not edit the checker or reproduce its hardcoded rule lists during an ordinary critique."

    These are compatible if Claude's line means "as separate work", but they read as opposite defaults.

13. **Which per-scene file to pick.**
    - Claude `:36,61` says "prefer … `.scrubbed.md` … Fall back to the raw `.md`".
    - Codex `codex/SKILL:23-24` agrees for normal assembly. It is then overridden by dialogue-edit provenance (`codex/SKILL:25-30`), which Claude lacks.

    This is a conflict only when a dialogue-edit revision exists.

## 6. Platform-only differences

- Frontmatter:
  - Claude `tools: Read, Glob, Grep, Bash, Write` (`claude/SKILL:4`).
  - Codex `metadata.short-description` (`codex/SKILL:4-5`), plus `agents/openai.yaml` ("Voice Critic (Astra)").
  - **Note:** Claude's `tools:` allowlist does **not include `Artifact`**, yet Phase 8 requires the `Artifact` tool. This may be a latent bug on the Claude side (see Q9).
- The review surface:
  - Claude: the `Artifact` tool with a bespoke fixed design, a `reference/proof-sheet.html` template, and "Do not load `artifact-design`" (`:332`).
  - Codex: a local standalone page via `../_shared/review-page/build_review.py`; "No Claude Artifact tool or hosted publish step is required" (`codex/SKILL:110-111`).
- `codex/SKILL:10-14` is a preamble for Codex/Astra: "does not select a model, launch a model runner".
- Directory naming: `references/` vs `reference/`.

## 7. Script diffs

Neither side ships a script file. The differences are in inline code:

- **Claude only:** the Scan A2 trailing-dash diff (`claude/SKILL:179-182`, bash `grep | paste | bc`) and the Scan C orphan-quote finder (`claude/SKILL:195-211`, Python). The Scan C finder detects only lines that both start and end with an ASCII `"`. It misses curly quotes and multi-line quotes, which is the limitation Codex's `REF:5-7` warns about.
- **Codex only:** no inline code. It relies on `voice_lint` and the shared `build_review.py`.
- `reference/proof-sheet.html` (Claude) is a template, not a script. It has an inline `localStorage` triage script with a Copy-decisions fallback.

## 8. Open questions for the GM

1. **Should voice-critic know about dialogue-edit?** Codex handles approved revisions, `candidate.md`, promotion records and `<session>/voice_critic/<run>/`. Claude does not, even though Claude's `dialogue-edit` hands off to it. Suggestion: port Codex's selection rules (`codex/SKILL:25-30, 116-118`) into Claude. Otherwise Claude's directory scan critiques the pre-edit text.
2. **Where do applied voice fixes go by default?** The options are Claude's in-place `.scrubbed.md` with a `voice_fixes` replay record, or Codex's separate derived revision that mirrors raw and scrubbed. Suggestion: Codex's separate revision fits the dialogue-edit model and removes Claude's "/scrub wipes it" hazard. Keep Claude's explicit `/scrub` warning in either case.
3. **Does a doc-wide cap breach mean re-rendering?** Claude `:407` says it usually does. Codex says to decide by distribution and cost. Suggestion: Codex's wording, plus Claude's "rank and name the target count" (`:391`). That removes Claude's internal tension.
4. **Missing spec: skip the scene or only the voice category?** Suggestion: Codex (skip only the voice judgment), because rulebook, em-dash and orphan checks do not need a voice spec.
5. **Orphan-quote fixes: are action beats allowed?** Claude allows added "action beats"; Codex forbids inventing one.
6. **Which verdict vocabulary and return path should the review page use?** Claude uses a bespoke proof sheet with act/keep/defer and a Copy paste-back. Codex uses the shared builder with approve/reject/discuss. Should Claude move onto `_shared/review-artifact`, which the other Claude review skills use, or keep its bespoke page? Suggestion: this is the largest design question. Weigh Claude's reason for keeping the bespoke page ("republishing … overwrites the review document", `:369`) against consistency with dialogue-edit, which is the step directly before this one.
7. **Should the flattened-rulebook finding be stated as "probable cause" (Claude) or "uncertainty only" (Codex)?**
8. **How much of Claude's case material and scripts should Codex absorb?** Candidates are the Scan A2 and Scan C commands, the content-protection category, the migration command, the `[no spec]` lookup-bug heuristic, the five `voice_lint` skip causes, and the sage-note format. And should Claude adopt Codex's measurement discipline (curly quotes, stated denominator, a hatch "unavailable" state) and its frozen-hash apply loop? Suggestion: most of Codex's discipline items are cheap to add to Claude. Codex would benefit most from the content-protection category and the Scan A2 command, whose absence makes the concept hard to run.
9. **Is Claude's `tools:` line missing `Artifact`?** Phase 8 cannot run under that allowlist if it is enforced. Suggestion: verify, then add it; this is independent of the other convergence choices. `claude/skills/voice-smooth` has the same gap.
10. **"Always publish" vs. "default page, honour a chat-only preference": which one?**
