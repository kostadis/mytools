# Convergence report: speaker-attribution-text

Paths are relative to `/home/kostadis/src/mytools/dotfiles/`. "codex" means
`codex/skills/speaker-attribution-text/`, "claude" means
`claude/skills/speaker-attribution-text/`. Line numbers are from the working tree as
of 2026-09-24. The working tree has no uncommitted changes in either skill.

## 1. Summary

This pair has almost converged. The helper script and the reference doc are
byte-identical. The two `SKILL.md` bodies differ only in:

- punctuation and emphasis;
- how `SKILL_DIR` is resolved;
- one added Claude paragraph on batch review through the shared review artifact.

Git history shows a Codex-to-Claude port. Codex created the skill on 2026-09-18
(`8bfd959`). Claude's copy was added on 2026-09-20 (`20069d6`), whose commit message
says: "These three existed only under codex/skills/. Port direction for this change
is codex -> claude". Neither side has changed since. No substantive rule exists on
only one side. The remaining differences are harness adaptations plus one small
wording difference in strength ("should" vs "must").

## 2. File inventory

| file | codex | claude | status |
|---|---|---|---|
| `SKILL.md` | 146 lines | 159 lines | differs (port adaptations + review-artifact paragraph) |
| `references/evidence.md` | 95 lines | 95 lines | identical |
| `scripts/attribution.py` | 260 lines | 260 lines | identical |
| `agents/openai.yaml` | 4 lines | — | only-codex (Codex harness metadata) |

## 3. Only in Codex

Nothing substantive. I compared the two `SKILL.md` files with a word-level diff
(`git diff --no-index --word-diff`), and every Codex sentence has a Claude counterpart.

- The one Codex sentence Claude dropped is at codex `SKILL.md:122-124`: "An optional review page should never reintroduce a checkpoint the user has already waived." Claude does not lose it. It restates it more strongly inside its new review paragraph (claude `SKILL.md:148-150`: "A review page must never reintroduce a checkpoint the user has already waived").
- Codex's description has one extra trigger phrase, "requests to learn participants' phrasing from neighboring sessions" (codex `SKILL.md:3`). This is trigger vocabulary, not a workflow rule (see Section 6).

## 4. Only in Claude

1. **Batch review of ambiguous cues through the shared review artifact.** claude `SKILL.md:144-150`: "If the user wants to review ambiguous cues in a batch rather than in chat, use the shared review artifact (`~/.claude/skills/_shared/review-artifact/CONTRACT.md`) — one page for the run, published with `capabilities: {"artifact": {}}`, then stop and wait for the save … in accepted best-guess mode there is nothing to gate, so offer the page only as a record or for the genuinely ambiguous subset."
   Codex mentions an optional review only in passing (codex `SKILL.md:31-32`, `122-124`). It names no mechanism and does not point to `codex/skills/_shared/review-page/CONTRACT.md`, although that file exists. Two parts of this are real guidance, not just mechanism: "stop and wait for the save" and "offer the page only as a record or for the genuinely ambiguous subset".
2. **Description guarantees.** claude `SKILL.md:3`: "Output is written losslessly to a NEW file; the source transcript is never modified. When audio or acoustic turns exist, use /speaker-attribution instead." Both facts are in both bodies: codex `SKILL.md:15-16` for the routing, and codex `SKILL.md:133-138` and `140` for new outputs and preserving originals. Only Claude surfaces them in the description, so this is placement, not content.

## 5. Conflicts

No incompatible instructions. One difference in strength:

- **Style-classifier dependency.** codex `SKILL.md:81-82`: "missing dependencies or sparse references should not block contextual work." claude `SKILL.md:84-85`: "missing dependencies or sparse references must not block contextual work." Claude also bolds "Its score is not the probability that a cue belongs to that person." The intent is the same; Claude is stronger. This is probably a porting touch-up rather than a deliberate policy change.

## 6. Platform-only differences

- **`SKILL_DIR`.** Codex: "Resolve `SKILL_DIR` to this installed skill" (codex `SKILL.md:52-53`). Claude hard-codes `SKILL_DIR=~/.claude/skills/speaker-attribution-text` (claude `SKILL.md:58`).
- **Frontmatter.** Claude adds `tools: Read, Bash, Glob, Grep, Write, AskUserQuestion` (claude `SKILL.md:4`). `AskUserQuestion` is listed but the body never references it. Claude's description ends "Invoke as /speaker-attribution-text [session-dir]". Codex's names `$speaker-attribution-text`.
- **`agents/openai.yaml`** exists only in Codex: display name "Text Speaker Attribution" and a `$speaker-attribution-text` default prompt.
- **Review mechanism.** Claude uses `_shared/review-artifact` with Artifact `capabilities`. The Codex counterpart would be `_shared/review-page`, which it does not reference (see Section 4, item 1, and Question 1).
- **Cross-skill reference style.** Claude says `/speaker-attribution`; Codex says "the separate `speaker-attribution` skill" (claude `SKILL.md:16-17`, codex `SKILL.md:15-16`).

## 7. Script diffs

None. `scripts/attribution.py` is identical on both sides (`diff -u` is empty). It is a
standard-library tool with two subcommands:

- `prepare --source --speaker… [--reference…] [--context…] --output`
- `render --decisions --output --record`

## 8. Open questions for the GM

1. **Should Codex gain the batch-review paragraph?** This would point Codex to `codex/skills/_shared/review-page/CONTRACT.md`, adapted for Codex's no-callback page (the GM pastes or downloads the decision JSON).
   *Suggestion:* yes. The guidance "offer the page only as a record or for the genuinely ambiguous subset in best-guess mode" is harness-independent and worth having on both sides.
2. **"should not" vs "must not" block on a missing classifier.** Pick one.
   *Suggestion:* "must not", since contextual reading is the core method and the classifier is optional by design.
3. **Description content.** Should the Codex description also state "source never modified / new file" and "use speaker-attribution when audio exists"? Should Claude's add Codex's "learn participants' phrasing from neighboring sessions" trigger phrase?
4. **`AskUserQuestion` in Claude's `tools:`.** It is declared but never referenced. Keep it as available, reference it in the "Request missing facts" step (claude `SKILL.md:40-41`), or drop it?
5. **Cross-link from the acoustic skill.** Neither `speaker-attribution` SKILL.md names this skill as the fallback when audio is missing. Codex's `speaker-attribution` does say to report the missing input (codex `speaker-attribution/SKILL.md:30-34`). Should both acoustic skills point to `speaker-attribution-text` explicitly? This question belongs to the other pair's report but is decided most naturally here.
