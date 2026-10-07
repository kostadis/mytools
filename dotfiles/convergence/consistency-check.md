# Convergence report: consistency-check

Paths are relative to `/home/kostadis/src/mytools/dotfiles/`. Claude citations refer to the **working copy** (with uncommitted edits); lines added by those edits are marked **(U)**.

## 1. Summary

The two versions share a skeleton but are far apart in depth. Claude is 536 lines and Codex is 265. Codex is a condensed port: it keeps the step order, the prep-tier procedure and the manifest schema, and drops most of Claude's rationale, worked examples and false-positive classes. Claude is the original (first commit `4210f6f` 2026-05-25, hardened through `6c7b240` 2026-09-04). Codex was forked from it on 2026-08-27 (`5b6d721`/`b98c9d8` "Route consistency skills through Codex CLI"). Since then three commits changed both sides together on 2026-09-18 (`50afe91` stop passing registry as context, `621c6cf` record resolved consistency context, `23fa8ed` show prep context costs). Those parts now match nearly word for word: the registry is auto-loaded and not passed through `--context`, the manifest has `resolved_path`, and the prep tiers are sized in characters.

Claude has an uncommitted working-copy edit (+71/−2 lines) with five changes:
- (a) A warning that a throwaway absolute-path config silently drops the entity registry, with a symlink fix and an offline `find_registry` check.
- (b) Moving the `Context : N` sanity check to the first seconds of the run, and computing the expected N before launch.
- (c) A wider finding-count grep, plus a four-run table showing that report delimiters change from run to run and that the bullet pattern can over-count 4×.
- (d) Three new false-positive classes: grounding-doc/canon claims that the tape contradicts, quote findings that are really tape problems, and real-name scrubs treated as attribution changes.
- (e) Per-cue fixes for common-word ASR garbles inside quotes.

The format table names `gpt-5.6-sol` as the model. That suggests these lessons came from Codex-backend runs, which makes them directly relevant to the Codex side.

## 2. File inventory

| file | codex | claude | status |
|---|---|---|---|
| `SKILL.md` | 265 lines | 536 lines (working copy; 467 committed + edit) | differs |
| `agents/openai.yaml` | absent | n/a | not present on either side (other Codex skills have one, this one does not) |
| helper scripts | none | none | — |

## 3. Only in Codex

Each item was checked against Claude by concept, not just wording.

1. **Fail closed on backend failure, with no silent provider switch.** `codex/skills/consistency-check/SKILL.md:26-29`: "If Codex reports a missing executable, missing login, incompatible model, or timeout, surface that failure and stop. Do not silently select another backend." Also `:161-163`: "do not treat partial output as a report." Claude has no equivalent stop rule. It sets `--backend claude-code` as the default and explains why (`claude:196`), and it only handles auto-continuation (`claude:234`). The backend name is a platform difference; the fail-closed principle is not.
2. **"Scene extraction" as a document class and a common target.** `codex:41` lists `summaries/<date>/scene_extractions_new/0N_*.md`, and `codex:50` says "`scene extraction`: per-scene extraction containing quote blocks". Claude's classes are first-pass / enhanced / narration (+ backfill) (`claude:247`, `claude:532`), and its common targets (`claude:17-21`) include no scene files. Claude's staged-consistency does run this skill on scene files, so the class exists in practice but is not described here.
3. **Find the campaign root by walking upward.** `codex:56-57`: "Find the campaign root by walking upward from the document or CWD until you find `docs/`, `summaries/`, and `config/`." Claude runs `pwd` and relies on the CWD being the root (`claude:67-75`). See the related layout conflict in §5.
4. **`gm-assist.md` named as a first-pass recap target.** `codex:39,48`. Claude names `session_<date>_<slug>.md` and treats gm-assist only as the source recap (`claude:47`, `claude:202`). This is minor, and Claude's staged skill covers it.

## 4. Only in Claude

Grouped by workflow step. Unless noted, Codex has neither the concept nor the wording. "Partial" means Codex has a one-line version without the operative detail.

### Step 1: identify the document
1. **Look for speaker-labelled transcripts.** `claude:25-36`: "check whether any of them carry SPEAKER LABELS", with a grep recipe. Also: "rule on content and use labels as corroboration, never the reverse." Partial in Codex: `codex:220-221` says "Prefer a speaker-labelled Zoom `.md` for attribution", but gives no detection step or labels-as-corroboration rule.
2. **Use the speaker roster as a party check.** `claude:36`, `claude:345-352`: "count the distinct speakers against the party. A missing player changes how the recap fails." Not in Codex consistency-check. Codex staged-consistency has it at `codex/skills/staged-consistency/SKILL.md:99-101`.
3. **Class and lineage detection.** `claude:38-54`: md5sum and `logs/` to spot an `enhance_summary` output, and a grep of the tape for level to confirm the era of a backfill.
4. **Read a prior `*.sources.yaml` first, and treat its rulings as hypotheses.** `claude:56-63`: "treat a prior manifest's rulings as hypotheses, not settled facts … re-verify any of its claims your current findings touch." Not in Codex consistency-check; Codex staged has it (`codex staged:101-102`).

### Step 2: config
5. **How config auto-detection works.** `claude:67-79`: `find_default_config()` looks at CWD only, then falls back to CampaignGenerator's own config. Also the config-move gotcha, and the obelisk case with both a root and a `config/` config.
6. **(U) The registry is dropped by the throwaway config.** `claude:89-114`: "That recipe alone silently drops the entity registry — the registry resolves by a DIFFERENT mechanism than `documents[]`." The fix is `ln -s <campaign>/docs "$CFG/docs"` plus an offline `find_registry("<CFG>")` check. This conflicts directly with Codex's recipe (§5 C2).
7. **(U) Early sanity check and expected N.** `claude:118-127`: "Sanity check in the first seconds of the run, not after it", with `grep -c "skipping canon section" <log>  # must be 0`, and "Compute the expected N before you launch and state it." Codex only has "Confirm the context count is plausible" after the run (`codex:157`).

### Step 2.5: prep
8. **Date-bound the prep search, and don't substitute prep from another session.** `claude:133-142`: "off-session prep is worse than no prep". Codex has no date bound. It records prep-less runs (`codex:124`) but does not warn against using the nearest match.
9. **Three prep layouts, including flat location-named files.** `claude:144-148`: "A file named for the dungeon/location/arc, marked as staging, IS the session prep." Partial in Codex: `codex:97` says "location or arc files directly under `notes/`".
10. **Pre-read the glossaries before asking.** `claude:184`.
11. **An explicit answer is required.** `claude:182`: "do not proceed without an explicit answer." Codex just says "Ask the user to choose" (`codex:121`).

### Step 3: the command
12. **`--context` is nargs="+", so a repeated flag overwrites.** `claude:197`. Partial in Codex: `codex:139` says "one `--context` flag followed by all context paths", without the overwrite warning.
13. **Quote paths that contain spaces.** `claude:204`.
14. **Why the source recap is the highest-value context,** and the offer of a "Focused + source recap" tier. `claude:202`. Codex includes the file (`codex:133`) but has neither the rationale nor the tier.

### Step 4: run and count
15. **Why the `No issues found` banner lies, and `^### ` is a guess too.** `claude:213-219`. Partial in Codex: `codex:159-160` tells you to count from headings, which is the exact method Claude warns can return 0 (§5 C4).
16. **(U) Delimiters change from run to run; bullet counts over-count.** `claude:221-233`: "The bullet pattern can OVERCOUNT as badly as the numbered one undercounts … Run every pattern, take the one that matches the body."

### Step 4.7: VTT adjudication
Codex compresses this whole block into `codex:219-229`.
17. **Treat "VTT review needed" as a work item.** `claude:292`: "Treat that as a work item, not a finding to hand back."
18. **Three classes that justify a trip to the tape**, including facts absent from every doc (the rope/whip case). `claude:294-298`. Partial in Codex: `codex:219-221` lists the classes.
19. **Retracted GM slips, with a ±20-line correction-pattern grep.** `claude:300-306`. Partial in Codex: `codex:220` names "retracted GM slips" but gives no method.
20. **A garbled PC name can be two characters fused**, discriminated by class feature, with race+class epithet checks and pronouns fixed in the same edit. `claude:308-324`, `:339`. Partial in Codex: `codex:228` says "A glossary replacement can merge two PCs if speaker attribution was lost."
21. **A garbled noun is evidence a word was spoken.** `claude:326-337`: "Never rule an event fabricated on the absence of a noun; rule on the absence of the action."
22. **The absent-player failure mode.** `claude:341-352`: "The doc is a hypothesis every session; the tape is the answer." Record the `speaker_map` too.
23. **Five enhancement-pass failure modes:** invented dice values, attribution drift, duplication with loss, truncation markers, relocated DM asides. `claude:354-362`. Not in Codex consistency-check; Codex staged lists them at `codex staged:209-212`.
24. **Adjudication discipline:** read forward to the end of the sequence, a negative finding is only as wide as the grep window, and if the tape can't settle it, ask. `claude:364-374`. Partial in Codex: `codex:229` says "Read the whole sequence before ruling on one grep hit."
25. **The VTT is consulted by hand, not passed as context.** `claude:374`. Not in Codex consistency-check; Codex staged has it (`codex staged:370-372`).

### Step 5: triage filters
26. **Grep the target for the quoted text first,** because the check attributes context text to the target. `claude:386-396`. Not in Codex consistency-check; Codex staged has it for Stage 1 only (`codex staged:199-203`).
27. **(U) A canon or grounding-doc citation can still be wrong; verify on tape** (the Jorlan and Sharpshooter cases). Also grep `docs/distill/planning_extractions/` and `docs/ensemble/`, and don't trust the report's own citations. `claude:398-407`.
28. **(U) A finding about a quoted line may be a tape problem.** Fix it in `transcript_corrections.yaml` per cue, never as a glossary row. `claude:409-411`.
29. **(U) A real-name scrub is an attribution change.** `claude:413`: "Verify the speaker on the tape before applying any real-name scrub, and re-run `sd_verify_quotes` afterwards."
30. **Table ruling vs rules error:** grep for the GM's declaration and carry forward any doc-level disagreement. `claude:415-423`. Partial in Codex: `codex:224` says "A table ruling is not automatically a rules error."
31. **Backfill anachronism:** "X not in documented kit" is doc silence, not error. `claude:425-437`. Partial in Codex: `codex:225`.
32. **The report can point at the wrong half of a contradiction.** `claude:439`: "Never accept the report's choice of direction."
33. **Module truth ≠ party knowledge,** with a three-way choice offered to the GM, plus unearned inferences. `claude:441-443`. Partial in Codex: `codex:226`.
34. **Module vs table vocabulary:** a registry check, a `docs/background/` trace, no bulk colour/title replace, and `docs/background/` is never edited. `claude:445-454`. Partial in Codex: `codex:227`.
35. **Don't trust the "No issues found with:" footer.** `claude:456`.
36. **Findings implicate grounding docs:** record them in carry_forward, propagate the whole class, check direction first. `claude:458-462`.
37. **Play-divergence caveat.** `claude:464`. Partial in Codex: `codex:216` puts "prep-vs-play divergence" in the judgment bucket.
38. **Order a batch of edits so they don't collide.** `claude:468`.

### Steps 4.5 and 6: manifest
39. **Extra manifest fields:** `model`, `temporal_gap`, `speaker_map` (`claude:250, 262-268`), `gm_rulings_this_run` (`claude:478-480`), and structured `partially_applied` (`claude:483-487`). Codex's schema (`codex:169-200, 239-256`) has none of these beyond an empty `partially_applied: []`.
40. **Record your own mid-run reversals in `vtt_adjudicated`,** and say what the VTT caught that the check could not. `claude:492-497`, `:513`, `:534`.
41. **Fallback manifest name** `<document-stem>.consistency_sources.yaml` when no report was saved. `claude:238`.

### Notes
42. **Registry doctrine:** garbles are not aliases; `registry check` false positives (CampaignGenerator#216); two different `aliases.json` files; verify a wrong form occurs in a VTT before adding a glossary row; the registry CLI invocation and its MCP. `claude:518-524`. None of this is in Codex.
43. **Three transcripts can give three answers;** a name matching neither the garble nor the truth is a summarizer invention. `claude:529`.
44. **Failure profile per document class,** with expected hit rates. `claude:532`.

## 5. Conflicts

**C1. Campaign layout and the default config location.**
- Codex `:59-69`: "Current campaign layout is: `<campaign>/config/config.yaml` … Pass `--config <campaign>/config/config.yaml` explicitly. Do not require a root `config.yaml`."
- Claude `:74-75`: "Run from the campaign workspace root (the dir holding `config.yaml` + `docs/`). Preferred." Claude treats `config/config.yaml` as a gotcha (`:77-81`).
- These assume opposite layouts. Codex assumes every campaign has moved its config into `config/`; Claude assumes a root `config.yaml` is normal and names Phandalin as the exception. The uncommitted edit (`:114`) now says `out-of-the-abyss` is also config-only.

**C2. The throwaway absolute-path config recipe (the most consequential conflict).**
- Codex `:71-79`: "After the run … If it reports missing context files … create a temporary absolute-path config and rerun. The minimum useful config is:" (campaign_state + world_state only).
- Claude (U) `:89`: "That recipe alone silently drops the entity registry … `find_registry(base_dir)` … looks for `<the config file's own folder>/docs/entity_registry.yaml`." Claude `:99-112` requires a `docs` symlink beside the config and an offline check before the run.
- Codex's recipe produces a run with no AUTHORITATIVE CANON section, and only one stderr line to show for it. Claude also contradicts itself here: committed `:77` ("only `campaign_state` + `world_state` are auto-loaded") and `:81` ("only `campaign_state` + `world_state` need to be correct in it") are no longer accurate given (U) `:89`.

**C3. When to sanity-check the context count.**
- Codex `:156-157`: "Validation after the run: Confirm the context count is plausible."
- Claude (U) `:118`: "Sanity check in the first seconds of the run, not after it", plus "Compute the expected N before you launch" (`:127`).

**C4. How to count findings.**
- Codex `:160`: "Count issues from report headings, not from the command banner."
- Claude `:213`: "`^### ` is a guess, not the pattern". Also (U) `:233`: "A single grep is never sufficient. Print all the candidate counts."
- Codex's rule is the heading method Claude documents as returning a confident false zero.

**C5. Where the CampaignGenerator repo lives.**
- Codex `:143-144`: "Prefer `/home/kroussos/src/CampaignGenerator`; fall back to `/home/kroussos/CampaignGenerator`", hard-coded into the command at `:149`.
- Claude `:116`: "the repo may be `~/CampaignGenerator` or `~/src/CampaignGenerator`. `ls` before you build the command."
- Codex's absolute paths are for the `kroussos` user. On this machine (`kostadis`) neither path exists. Claude also hard-codes `/home/kroussos/Phandalin/...` in its example at `:85`.

**C6. How findings are presented.**
- Codex `:231`: "Present findings in severity order."
- Claude `:378-382`: "Triage the findings into buckets" (clear-cut / canon judgment / minor), with no severity ordering.
- Codex's classes at `:213-217` are Claude's buckets. The difference is ordering by severity versus grouping by bucket.

**C7. Default backend and failure behaviour.**
- Codex: `--backend codex-cli`; stop on any failure; other backends only on explicit request (`:23-29`).
- Claude: `--backend claude-code` because the API key's credit may fail (`:196`). No stop rule; auto-continue is inspected, not refused (`:234`).
- The backend name is platform-specific (§6). Whether a failed backend may be swapped is a policy conflict.

## 6. Platform-only differences

These are not convergence candidates by default.

- **Frontmatter:** Claude has `tools: Bash, Read, Write, Edit, Glob, AskUserQuestion` (`claude:4`). Codex has `metadata.short-description` (`codex:4-5`).
- **Port header:** Codex `:13-15`: "This is the Codex port of the Claude skill. Do not edit `…/claude/skills/consistency-check/`." It also has a "Codex Compatibility" block (`:17-29`).
- **Asking questions:** `AskUserQuestion` (`claude:182`) versus "Ask user questions in chat" (`codex:19`).
- **Editing:** `Edit` "one at a time" (`claude:466`) versus `apply_patch` (`codex:21, 233`). Codex also uses `update_plan` (`codex:20`).
- **Artifacts:** Codex `:22` says "There is no Codex `Artifact` review flow here." Claude's consistency-check doesn't use one either, so there is no real difference.
- **Backend:** `claude-code` versus `codex-cli`, and the subscription/billing rationale for each (`claude:196`; `codex:23-25`).
- **Auto-continuation:** the `claude -p` output-ceiling warning and `CLAUDE_CODE_MAX_OUTPUT_TOKENS` (`claude:234`) are specific to the `claude-code` backend. Codex's manifest `notes` still mentions "auto-continuation inspection" (`codex:198-199`), which is a leftover with nothing behind it on the codex-cli backend.
- **`agents/openai.yaml`:** absent for this skill.

## 7. Script diffs

Neither side ships a helper script, so there is nothing to diff.

## 8. Open questions for the GM

1. **Registry-drop fix (C2).** Should the uncommitted symlink recipe and `find_registry` check replace Codex's "minimum useful config" and Claude's own `:77`/`:81` wording?
   *Suggestion:* yes, on both sides. The mechanism belongs to `check_consistency.py` and does not depend on the harness, and the evidence table suggests these runs were done on the Codex backend.
2. **Commit the uncommitted Claude edits?** In whole or in part: (a) registry symlink, (b) early N check, (c) count-format table, (d) three false-positive classes, (e) per-cue quote garbles.
   *Suggestion:* treat (a)–(c) as method fixes to port to Codex as well. (d)–(e) are adjudication lessons; see Q6.
3. **Canonical campaign layout (C1).** Is `config/config.yaml` now standard everywhere, as Codex assumes, or is a root `config.yaml` still preferred, as Claude says?
   *Suggestion:* decide per machine or campaign and write the rule once. Both skills currently hold half the truth.
4. **Repo path (C5).** Hard-coded `/home/kroussos/...` or discovered with `ls`?
   *Suggestion:* discover. The hard-coded Codex paths do not exist on the `kostadis` machine.
5. **Backend failure policy (C7).** Adopt Codex's "fail closed, never silently switch backend, partial output is not a report" on the Claude side?
   *Suggestion:* the principle looks harness-neutral. Only the backend name differs.
6. **How much of Claude's adjudication corpus should Codex carry** (§4 items 17–38, 42–44)? Codex staged-consistency tells the model to "Apply the `consistency-check` false-positive filters" (`codex staged:325-327`) and says `consistency-check` "owns the check method" (`codex staged:40-44`). Yet Codex consistency-check defines those filters only as six one-line bullets (`codex:223-229`), and the grep-target-first filter exists only in Codex staged. So Codex's delegation contract has almost nothing behind it.
   *Suggestion:* port at least items 17, 20–24, 26–27, 29–33 and 36 as method. Worked examples could stay Claude-only if length matters for Codex.
7. **Counting method (C4).** Adopt Claude's "run every pattern, pick the one matching the body" on both sides?
8. **Presentation (C6).** Severity order or triage buckets? Staged-consistency uses a severity table on both sides, which argues for converging on one.
9. **Manifest schema (item 39).** Add `model`, `speaker_map`, `temporal_gap`, `gm_rulings_this_run` and structured `partially_applied` to Codex, so manifests written by either harness can be read the same way?
10. **Scene-extraction class (§3 item 2).** Should Claude consistency-check name "scene extraction" as a document class, with its own failure profile (verbatim fidelity), since staged-consistency runs it on scene files?
