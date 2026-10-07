# Convergence report: voice-smooth

Compared: `codex/skills/voice-smooth/SKILL.md` (436 lines) vs `claude/skills/voice-smooth/SKILL.md` (417 lines) (paths relative to `/home/kostadis/src/mytools/dotfiles/`). Below, `codex:` and `claude:` refer to those two files.

## 1. Summary

The two files are **conceptually close but textually divergent**. Codex is a faithful condensation of Claude, with the Phandalin case material and most of the rationale stripped out. Its structure and step order are the same, and on the substance it is almost the same skill. Claude is the original and the more developed side. It was created 2026-07-12 (`d70f1c6`) and grew through the ch48, ch3 and ch4 lessons; the most recent changes were `8da7ac5` (2026-09-02) and `6c7b240` (2026-09-04, the declared-voice resolver). Codex was first ported 2026-08-29 (`567fbc0`, 209 lines) and rewritten 2026-09-18 (`8bfd959`, 436 lines) to catch up with the Claude post-09-04 text. `20069d6` states that "the Claude version already carries every concept in it except a rules recap". That is **mostly true**. Codex does add a handful of small but real guardrails, listed in §3.

**A lineage finding worth knowing.** Commits `5092639` and `43f6e9c` (2026-08-19) added an "Artifact mode (batch review)" section and a mode question to Claude voice-smooth, both wired to `_shared/review-artifact`. That section was **lost in the conflict resolution of merge `d81cc3f` (2026-08-30)**:

| commit | "Artifact mode" occurrences | lines |
|---|---|---|
| `b4bea66` | 3 | 184 |
| `d81cc3f` | 0 | 331 |

Today `claude/skills/_shared/review-artifact/CONTRACT.md:4,57` still names `voice-smooth` as one of its callers, but the skill no longer calls it. Instead it describes a different, older "downloads" artifact (`claude:220-240`).

## 2. File inventory

| file | codex | claude | status |
|---|---|---|---|
| `SKILL.md` | 436 | 417 | differs (condensed rewrite of the same content) |
| `agents/openai.yaml` | — | — | neither |

Neither side has references or scripts. Both embed shell snippets.

## 3. Only in Codex

1. **Ancillary edits need their own approval of the exact content.** `codex:33-35`: "Glossary changes, durable knowledge-boundary records, or campaign-instruction pointers are ancillary edits. Make them only after the user explicitly approves their exact destination and content." Also `codex:204`: "Obtain separate approval before those durable edits." Claude treats the knowledge record as step 2 of a confirmed boundary (`claude:161`) and the glossary write-back as "part of the same ruling" (`claude:295`). See Conflict 2.
2. **No paid or remote backend without approval.** `codex:47-48`: "Do not invoke a paid or remote backend unless the user has approved that backend and scope." Claude has no equivalent.
3. **Ask when both scene directories exist.** `codex:88-89`: "If both exist and campaign convention or freshness does not identify the active source, ask before choosing." Claude says only "Detect it" (`claude:60, 67`).
4. **Resume from an approved calibration.** `codex:356-357`: "If `voice_smooth.sources.yaml` already records an approved calibration for the same session and source set, verify it and resume rather than re-asking." Claude has no resume path (grep "resume": 0).
5. **An explicit definition of "ready".** `codex:364-366`: "The layer is ready only when calibration is approved, every scope decision is approved, every substantive word change has a verdict, every `discuss` item is resolved, and no item remains undecided." Claude's equivalent is spread across `claude:239-240, 328, 413`. **Partial:** same substance, not stated as a single gate.
6. **Using `sha256sum` to prove transcripts are independent.** `codex:287-289`: "Group byte-identical files with `sha256sum`, then confirm independence with a distinctive clean phrase." Claude uses only the phrase grep (`claude:261-265`).
7. **Stricter structural invariants.** `codex:381-387`: "every source scene has exactly one matching smoothed file … every `from:` target exists … no new fused speaker header or orphaned quote block was introduced." Claude checks counts (`claude:349-353`) but not the `from:` targets, one-to-one matching, or orphaned quote blocks.
8. **The manifest records verification results and is inspected after parsing.** `codex:409`: "structural and delta-audit results". `codex:411-412`: "inspect the parsed top-level keys. Do not mark the run ready if any required decision or verification remains open." Claude validates only that the manifest parses (`claude:389`).
9. **A safe temp directory.** `codex:162`: `review_tmp=$(mktemp -d)`. Claude writes `/tmp/q_$f.txt` (`claude:120`). Codex's version avoids collisions and stale files, and honours the scratch-directory convention.
10. **A compact rules recap.** `codex:424-437`. Claude has a longer "Conventions" section (`claude:396-413`) covering the same rules. This is the "rules recap" that `20069d6` mentions.

## 4. Only in Claude

1. **The IS / IS NOT framing.** `claude:42-47`: "IS NOT — narration … IS NOT — critique." Codex has only the one-line opening (`codex:10-13`).
2. **The resolver's failure mode.** `claude:99`: "a bare `load_party_config` leaves `voice:` as a `str` and `load_declared_voices` dies on `'str' object has no attribute 'exists'`." Codex says `resolve_party_config` "is required" (`codex:131`) but not why.
3. **The orphan first-name pitfall.** `claude:103`: "Do not compute orphans by first-name-splitting a declared key … `"sister maela dawnforge".split()[0]` is `sister`, which reports `maela_voice.md` as an orphan when it is correctly declared." Codex has the "orphan census, not resolver" rule (`codex:148-149`) but not this pitfall.
4. **Where NPC characterization comes from.** `claude:108`: "(`docs/npcs/`) **or the session prep docs** (`notes/session_prep/`, `notes/sessions/`) … Never flatten a distinctive NPC into GM-neutral when a source gives you a voice." Codex names no paths and has no "never flatten" rule (`codex:144-146`).
5. **Rescue-before-cut command.** `claude:131-133`: `comm -23 /tmp/q_<losing>.txt /tmp/q_<keeper>.txt`. Codex has the rule (`codex:176-177`) but no command.
6. **The splice regex, used in both the survey and verification.** `claude:142`: `grep -rn '[a-z0-9…"]\*\*\[\?\(GM\|<PC names>\)'`, and again at `claude:353`. Codex gives neither command (`codex:183-185, 386`).
7. **Durable knowledge records.** `claude:161`: "a hand-authored dossier at `docs/<Subject>.md` with a *what the party actually knows* table … Phandalin keeps `docs/KP.md` and `docs/Margaster.md`." Codex just says "a durable knowledge record in `docs/`" (`codex:202-203`).
8. **Stage-direction splits: the second-to-third-person rule and the rationale.** `claude:180`: why a fused quote is "poison for `session_doc`" (the quote-lock). `claude:189`: "Convert second person to third inside the direction only when the direction is unambiguously about the NPC." `claude:193`: "Report the count at review." Codex has the split rules (`codex:233-245`) but not the person-conversion rule or the rationale. It does report the counts (`codex:360`).
9. **A calibration statistic for confident readings.** `claude:201`: "**one of the three was wrong** … A third strike rate on lines that felt certain is the calibration to carry." Codex has no equivalent.
10. **A running checklist.** `claude:207`: "Collect them per scene and show a running checklist so the GM can see how many are left." Codex has no equivalent.
11. **Which transcript to trust for what.** `claude:250`: "Zoom export was better on **proper nouns**, the re-transcription better on **sentence completion** … Record what you actually observed this session." Also `claude:381`: record "what each is good at". Codex records "independent reading groups" (`codex:400`) but not the per-transcript strengths.
12. **Zoom's own text export as the independent reading.** `claude:267`: "Zoom's own text export (`GMT<date>_Recording.md` …) … is the only true independent reading in the directory." Codex has no equivalent.
13. **A filter for the anchor grep.** `claude:278`: `| grep -vE '\-\->|^[0-9]+[-:]$'`, which strips VTT timing lines. Codex's `rg` form (`codex:295`) omits it.
14. **Glossary mechanics.** Codex compresses all of this into `codex:313-320`:
    - `claude:301`: "`add_to_glossary.py --section` searches within a single section … Check first — many 'new' variants are already there (7 of 28)."
    - `claude:302`: the pipe table that is "parsed with the columns **backwards** … `Brewbarry → Brubit`".
    - `claude:311`: what `split_section` and `chained` warnings mean.

    Codex keeps the rules but drops the diagnostics.
15. **Why the heading is a contract.** `claude:318-322`: CampaignGenerator#250 R5, the R1/R3 contract axis, #304. Codex keeps the rule (`codex:336-337`) without the pointers.
16. **The calibration question and aggressiveness example.** `claude:331, 335`: "'we got a nail Bookwyrm' → 'we've got to nail Bookwyrm' … Ask: *'Approve these, edit specific ones, or want a different smoothing pass on any character?'*" Codex paraphrases the question (`codex:353`).
17. **The delta-audit diff command.** `claude:364-369`. Codex has the rule (`codex:389-392`) with no command. **Note:** Claude's loop is hard-coded to `for n in 01 02 03 04 05`, which silently audits only 5 scenes.
18. **The YAML indentation trap.** `claude:389`: "keys that follow a list at the same indent level get swallowed into the sequence." Codex has no equivalent.
19. **Correct characterisation in the voice file, not here.** `claude:400`: "When a player corrects a characterization, the voice file wins; update it there, not here." Codex has no equivalent.
20. **The no-card rule never suppresses reporting.** `claude:410`: "A rule that stops you editing a transcript must never stop you saying *'this sentence contradicts the one before it.'* When in doubt, surface it." Codex has no equivalent. This is a substantive guardrail.
21. **Registry-settled spelling examples.** `claude:404`: `Utgartian` → `Uthgardtian`, etc. Codex keeps the rule (`codex:76-79`).
22. **The "Why this design" section.** `claude:415-417`.
23. **A worked example for every rule** (Phandalin ch3, ch4 and ch48). Codex removes all of them.

## 5. Conflicts

1. **The `from:` frontmatter path.**
   - Claude `:317`: "`from: ../scene_extractions/NN_slug.md`" is hard-coded, even when the source was `scene_extractions_new/`.
   - Codex `:328`: "`from: ../<scene-dir-name>/NN_slug.md`".

   Codex is correct for the `_new` case.

2. **The approval gate for durable and glossary edits.**
   - Claude `:161`: "**Record it durably.** … plus a pointer from the campaign's `CLAUDE.md`." Claude `:295`: "offer to add it … as part of the same ruling."
   - Codex `:204`: "Obtain separate approval before those durable edits." Codex `:33-35` requires approval of the "exact destination and content".

3. **When a PC's declared voice is missing.**
   - Claude `:105`: "say so *before* smoothing their lines rather than rendering them from nothing."
   - Codex `:137-138`: "Before smoothing a PC, **stop** if their declaration is absent or its declared file is missing."

   Claude also treats "declares no `voice:` entry" as "a statement, not an accident" (`:85`), which suggests it is not a blocker. Codex blocks both cases.

4. **The review surface for a long queue.**
   - Claude `:222-235`: an `Artifact` with `capabilities: {"downloads": true}`, Approve / Reject / Discuss, a downloaded Markdown record, and the WSL2 `/mnt/c/...` read-back.
   - Codex `:40-43`: "write a normal Markdown or JSON review file in the session directory, then read the GM's decisions back from chat or a named decision file."
   - Neither uses its own harness's `_shared` review machinery. Claude's `_shared/review-artifact/CONTRACT.md` specifies `capabilities: {"artifact": {}}` and lists voice-smooth as a caller (§1).

   The delivery mechanism is platform-driven. The choice of machinery is a real design decision.

5. **Verdict naming.**
   - Codex `:277-280`: `approve` / `revert` / `discuss` / unmarked.
   - Claude `:228, 233`: Approve / **Reject** / Discuss / UNDECIDED.

   The semantics are the same; "revert" and "reject" are two names for one action.

6. **Where the durable knowledge pointer lives.**
   - Claude `:161, 407`: the campaign's `CLAUDE.md`.
   - Codex `:203-204`: "the campaign's persistent Codex instruction or index file, usually `AGENTS.md`."

   This is mainly a platform difference, but a campaign used from both harnesses would need **both** pointers, or a shared one.

7. **When a truncated cue may be completed.**
   - Claude `:33`: "Completing a cue the recorder cut, **when the meaning is recoverable**."
   - Codex `:60-61`: "when **every reading** makes the completion unambiguous."

   Codex's bar is stricter.

8. **Internal inconsistency in Claude, which Codex avoids.** Claude `:28` says of this layer that "nothing downstream of it is a record of anything". Claude `:410` then says "The rule governs the smoothed layer, **which is a record**." Codex has no such statement.

## 6. Platform-only differences

- Frontmatter: Claude `tools: Read, Bash, Write, Edit, Glob, AskUserQuestion` (`claude:4`). Codex `metadata.short-description` (`codex:4-5`).
- **Note:** Claude's `tools:` has no `Artifact` (or `WebFetch`), but `claude:224` says "Build it with the `Artifact` tool". This looks like the same gap as voice-critic. The `Artifact, WebFetch` entries that `5092639` added were dropped in the `d81cc3f` merge.
- Codex compatibility block (`codex:37-48`):
  - ask in chat, not with `AskUserQuestion`;
  - no Artifact callback;
  - use `apply_patch`;
  - "Do not edit `~/src/mytools/dotfiles/claude/skills/voice-smooth/` when changing this skill" (`codex:15-16`).
- Search tools: `rg` (Codex) vs `grep` (Claude).
- The lint path:
  - Claude hard-codes `~/src/mytools/dotfiles/claude/skills/vtt-spell-pass/lint_glossary.py` (`claude:307`).
  - Codex says "the installed `vtt-spell-pass/lint_glossary.py`" (`codex:319`).
- `AGENTS.md` vs `CLAUDE.md` for the knowledge pointer (Conflict 6).

## 7. Script diffs

No script files on either side. The inline snippets differ only in form:

- **Duplicate survey.** The same algorithm on both sides:
  - Codex uses `rg`, `mktemp` and `sort -u` (`codex:161-173`).
  - Claude uses `grep`, `sed 's/^> //'` and `/tmp/q_*` (`claude:118-123`). Claude strips the `> ` prefix; Codex does not. Both compare consistently, so the results are equivalent.
- **Voice-resolver one-liner.** Identical in behaviour (`codex:109-129` vs `claude:87-97`).
- **Verify block.** Claude adds the splice-count check (`claude:353`). Codex adds nothing executable, but lists more invariants (§3.7).
- **Delta audit.** Claude only, and its loop is hard-coded to scenes 01–05 (§4.17).
- **Neither side is a strict superset.** Claude has more commands; Codex has more invariants.

## 8. Open questions for the GM

1. **Should Claude voice-smooth get its lost `_shared/review-artifact` batch mode back?** The mode was merged away in `d81cc3f`, and the other option is to keep the older "downloads" artifact. `CONTRACT.md` still lists voice-smooth as a caller, so today one of the two is wrong. Suggestion: restore from `43f6e9c` and reconcile it with the post-09-02 text, or remove voice-smooth from `CONTRACT.md`. Either way, make them agree.
2. **Should Codex use `_shared/review-page` for the long queue, instead of an ad-hoc Markdown or JSON file?** Its sibling Codex skills do. Suggestion: yes, if Q1 goes the shared-machinery way. It makes the two sides symmetric.
3. **Does a glossary or durable knowledge write-back need a separate, exact-content approval (Codex), or is it part of the garble ruling (Claude)?** Suggestion: Codex's gate. These edits outlive the session, and the `Brewbarry → Brubit` incident (`claude:302`) shows how a write-back can go wrong.
4. **A PC with no declared voice: stop (Codex) or flag and continue (Claude)?** Also, is "declares no `voice:`" deliberate (Claude `:85`) or a blocker?
5. **Should `from:` use the actual scene directory?** Suggestion: yes, as Codex does. Claude's hard-coded path is wrong for `scene_extractions_new/`.
6. **The bar for completing a truncated cue: "meaning recoverable" (Claude) or "every reading makes it unambiguous" (Codex)?**
7. **Should the Codex-only guardrails be ported to Claude?** They are resume-from-calibration, ask when both scene dirs exist, the `sha256sum` grouping, the stricter invariants (`from:` targets exist, 1:1 files), recording verification results in the manifest, `mktemp`, and no paid backend without approval. Suggestion: all are cheap and none conflicts with Claude's text.
8. **Which Claude-only items should Codex absorb?** Suggestion: at minimum the "no-card rule never governs reporting" guardrail (`claude:410`), NPC-source paths with "never flatten", the second-to-third-person split rule, and the splice regex. Those are rules, not anecdotes.
9. **Should Claude's delta-audit loop cover every scene?** Suggestion: glob every scene instead of hard-coding `01..05`. This is a bug fix independent of convergence.
10. **Should Claude's `tools:` include `Artifact`, and `WebFetch` if the shared contract returns?**
11. **Should Claude `:410` stop calling the smoothed layer "a record", since `:28` says it is not?**
12. **For campaigns used from both harnesses: should the knowledge pointer go in both `CLAUDE.md` and `AGENTS.md`?**
