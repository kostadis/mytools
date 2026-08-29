---
name: project-245-narrate-fixes
description: "Issue #245 Pass 5 fixes: PRs CG#246 + campaigns#140 open (awaiting user merge); Opus5-vs-Fable5 benchmark pending on the SUBSCRIPTION backend; genre re-sync + roster follow-up outstanding."
metadata: 
  node_type: memory
  type: project
  originSessionId: 1eb87043-8d0f-4224-bc43-440b3e746c71
  modified: 2026-08-09T14:36:26.210Z
---

State as of 2026-08-09. Issue CampaignGenerator#245 (Pass 5 narration prompt defects) is
implemented on two open PRs, **not merged** (user gate):

- **CG #246** (`fix/245-narrate-prompt-defects`, worktree `~/src/CampaignGenerator-245`,
  kept until merge): GM-table-speech escape hatch (content-based, model self-flags via
  `<!-- table-speech reclassified: … -->`; `assemble.py` strips it, per-scene file keeps
  it), HARD BANS tic-family block in `base.md`, multi-line genre block formatting,
  anti-restatement length directive, dual-format roster parser with species, `_`-skip in
  voice/examples loaders, `cache_system=True`, golden regenerated at tip only.
- **campaigns #140**: 4 Phandalin voice specs scope-noted (constraints 1–8 = in-fiction
  speech only), "ever the X" ×2 removed, soma.md Ch08/11 deleted.

Verified live: opus-5 render of ch46 scene 02 fired the hatch on 13 spans incl. all four
issue-named patterns; 0 tics/1597 words.

**Next steps (after user merges):**
1. **Benchmark = claude-opus-5 vs claude-fable-5 ONLY** (user ruling: DGX renders were for
   learning, NOT the experiment; no Sonnet, no DeepSeek arm). All renders/tests on the
   `claude-code` SUBSCRIPTION backend, never the API. 6 ch46 scenes × 2 models, score with
   /voice-critic, flags per 1000 words by category; the scene-02 opus render in scratchpad
   `render_opus_scene02/` is the first data point. Post comparison to #245; only then
   decide `DEFAULT_MODEL`.
2. **Before benchmarking, re-sync Phandalin's `config/session_doc.yaml` `narrate.genre`**
   from `voice/_genre.md` — it is a pasted COPY; editing `_genre.md` does not propagate.
3. **Roster follow-up issue (not yet filed):** Hillsfar/obelisk/OOTA/stormgiants/toee
   party.md layouts still parse to empty roster (now loud via stderr warning); Hillsfar +
   OOTA layouts are trivially parseable.
4. ch46 evidence caveat: original 36 flags were DeepSeek-V4-Flash-on-DGX output, not
   Sonnet — cite accordingly when posting the comparison.

Related: [[reference-worktree-editable-install-shadowing]], [[project_alias_identity_not_substitution]].
