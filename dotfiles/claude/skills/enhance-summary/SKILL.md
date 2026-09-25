---
name: enhance-summary
description: Generate the Stage 1 enhanced session summary by running CampaignGenerator's installed enhance_summary CLI against a reviewed VTT and gm-assist.md, then verify its quoted dialogue against that same VTT with sd_verify_quotes. The CLI and its bundled prompts are the command path — never hand-write a replacement summary or substitute a direct model call. Guards the destination against silent overwrite of reviewed work. Use when the user asks for the enhanced summary, the Stage 1 summary, or to run enhance_summary. For the whole pipeline end to end use /session-doc-run; for chapters with no recording behind them use /chapter-enhance. Invoke as /enhance-summary [session-dir].
tools: Read, Bash, Glob, AskUserQuestion
---

# Enhanced summary

Generate the artifact through CampaignGenerator's installed `enhance_summary`
command, using its bundled prompts. Do not hand-write a replacement summary or
substitute a direct model call. The CLI is the command path the Session Doc
Editor drives; actual browser interaction is unnecessary unless requested.

This skill owns **one stage**. `/session-doc-run` runs the full pipeline
(enhance_summary → scene_extract → sd_narrate → assemble) with gates between
stages; use that when the goal is the whole run. `/chapter-enhance` builds a
summary from chapter *prose* when there is no recording at all — a different
input and a different schema discipline. This skill is for the recorded case.

## Resolve inputs and preserve reviewed work

Use the campaign and session directory established by the conversation. Resolve:

- The exact session VTT, preferably the established spell-corrected cleaned
  VTT. Do not select another transcript merely because its filename sorts first.
- The reviewed `gm-assist.md`, which supplies the structural specification and
  approved GM rulings.
- The destination, normally `<session>/session-summary.md`.

Reuse existing Stage 0 decisions and manifests. The normal pipeline is reviewed
VTT and GM-assist → enhancement → Stage 1 consistency → recap removal → scene
extraction. Do not rerun reviews or create missing upstream artifacts
implicitly. If a required input is absent or consequentially ambiguous, ask. If
Stage 0 is not complete, disclose that rather than calling the output reviewed.

**Check whether the destination already exists.** The CLI overwrites it without
a snapshot. A request to generate an absent summary is sufficient authority;
replacing an existing *reviewed* summary is not covered by it — get explicit
regeneration authority with `AskUserQuestion`. Preserve a non-overwriting
snapshot before an authorized replacement, and name the downstream artifacts
that become stale. Do not rebuild them automatically.

## Use the UI-equivalent command

Locate `enhance_summary` with `command -v` and read `enhance_summary --help`.
When command parity or settings are uncertain, inspect the installed
CampaignGenerator checkout (normally `~/src/CampaignGenerator`):

- `server/routers/scene_editor.py::_build_enhance_cmd` and `_selection_args`
- `session_doc/enhance_summary.py` for prompt construction and output behaviour

The UI command deliberately omits `--party`, `--party-config`, and
`--players-config`. Preserve that by default; adding them changes the speaker
preflight and is not routine plumbing. Do not add `--allow-speaker-mismatch` to
conceal an input problem.

Human recording labels do not identify the in-fiction speaker of every line,
especially when one player voices several characters. Voicing rulings made only
in conversation are not automatically passed to the generator. Flag attribution
limitations for later review; do not rewrite the VTT or modify global party
configuration as part of enhancement.

Use `--backend claude-code` for this saved-login workflow unless the user
chooses another backend. The backend vocabulary is shared across every
model-bearing CG CLI (`campaignlib/api/client.py::add_backend_args`):
`anthropic`, `dgx`, `openrouter`, `claude-code`, `codex-cli`. On
`claude-code`, effort and thinking are `--claude-code-effort` and
`--claude-code-thinking` / `--no-claude-code-thinking`; `xhigh` and `max`
require thinking enabled or the call is refused. `--codex-reasoning-effort`
belongs to the `codex-cli` backend and has no effect here.

Reuse explicitly established model and reasoning settings; otherwise resolve
the UI's configured selection (`config/session_doc.yaml`, `backends.active`)
rather than guessing a model. Do not silently fall back to a metered API or
downgrade settings.

Command shape:

```bash
enhance_summary <session>/<cleaned-transcript>.vtt \
  --gmassist <session>/gm-assist.md \
  --output <session>/session-summary.md \
  --backend claude-code
```

Add `--claude-code-effort <level>` only when the user has chosen one. Run from
the campaign root with resolved paths, and keep generation logging enabled.

**Last known-good (the Chapter 09 run, on `codex-cli`).** A dated example, not
a default: the model and effort are historical settings, and this goes stale
visibly rather than silently. Either backend is fine from here when the user
picks it.

```bash
enhance_summary <session>/<cleaned-transcript>.vtt \
  --gmassist <session>/gm-assist.md \
  --output <session>/session-summary.md \
  --backend codex-cli \
  --model gpt-5.6-sol \
  --codex-reasoning-effort medium
```

`--batch` means the Anthropic Message Batches API, not a batch review page. It
is Anthropic-backend only and is **not** compatible with `claude-code`. A user
choosing batch *adjudication* has not authorized changing the generation
backend or enabling that flag.

Before generation, state which transcript and GM-assist go to which backend and
where the result will be saved. Follow execution permissions and reuse prior
transmission approval only within its scope. If a permission prompt blocks
transmission, obtain the missing approval; do not bypass it by changing the
backend, tool, or payload packaging.

Run a single pollable process and give progress updates. A quiet call can take
several minutes; silence alone is not failure. On an actual failure, inspect
exit status, logs, and any output before retrying. Preserve partial results,
and never claim success merely because a file exists.

## Verify and hand off

Confirm a successful exit and a nonempty, plausibly complete summary containing
`## Summary` and `## Scenes`. Compare its scene structure against the reviewed
GM-assist for obvious omissions or truncation. Keep the generation log in the
session's `logs/` directory. This inspection is **not** Stage 1 consistency —
do not report it as such.

Run the installed local quote verifier against the exact generation VTT:

```bash
sd_verify_quotes \
  --vtt <session>/<cleaned-transcript>.vtt \
  --summary <session>/session-summary.md \
  --out <session>/quote_report_stage1.md \
  --report-only
```

If the console script is unavailable, use the CampaignGenerator environment's
`python -m session_doc.sd_verify_quotes` with the same arguments. This check
calls no model and leaves the summary unannotated. Preserve prior reports when
they belong to a reviewed version being regenerated.

Read the report: **exit 1 means findings; exit 2 means the check failed to
run.** Those are different outcomes — do not collapse them. Report verified,
near, unverified, and refused/unscored counts as applicable.

Only covered blockquote wording is checked — not inline quotations, speaker
identity, completeness, or campaign consistency. Examine flagged quotes in the
VTT: an interruption or laughter can split an otherwise supported quote across
cues. Record any manual resolution separately, with cue evidence. Do not change
the verifier's classification or silently repair dialogue.

**"No quotes found" is zero coverage, not a pass.** Count `grep -c '^> ' session-summary.md` before reading the verifier's result. An enhancement can put every quote inline instead: the OOTA ch02 run (codex-cli, gpt-5.6-sol, 2026-09-25) wrote 40 curly-quoted spans and not one blockquote, so `sd_verify_quotes` exited 0 having checked nothing. Then run the inline sweep over the same VTT and report its counts instead:

```bash
python3 ~/.claude/skills/staged-consistency/verify_quotes.py \
  --doc <session>/session-summary.md --vtt <session>/<cleaned-transcript>.vtt
```

On ch02 it surfaced the two defects the blockquote verifier could not see: a reworded quote (*"deal with"* for *"if he wants to be dealt with, he can be dealt with"*) and a quote spliced across the GM's asides without an ellipsis.

**A labelled blockquote used to read as "No quotes found" too, and now does not.** The enhancement can also write every Memorable Moments quote as `> **Zalthir:** “…”`. Until CampaignGenerator `d4e8047` (2026-09-25) the verifier's pattern required the quote mark straight after `>`, so OOTA ch03's 26 such lines were all skipped. It now accepts the label and uses it as the speaker hint (26 checked: 24 verified, 1 near, 1 unverified). If a run on an older install says "No quotes found" while `grep -c '^> '` is nonzero, that is this gap: update CampaignGenerator, or run the inline sweep. When a `'^> '` count and the verifier's checked count disagree, find out why before reporting either.

End with the output path, generation result, quote-check result, and any
unresolved findings. Stage 1 consistency
(`/staged-consistency` Stage 1, which runs `/consistency-check` on `session-summary.md`) is the next review step when requested. Do not
automatically apply consistency edits, remove recap, extract scenes, or
generate narration. Ordinary enhancement needs no review artifact and no
manifest of its own.
