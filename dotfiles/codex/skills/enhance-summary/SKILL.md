---
name: enhance-summary
description: Generate an enhanced campaign session summary using CampaignGenerator's enhance_summary CLI and the Session Doc Editor command path, then verify its quoted dialogue against the source VTT. Use for $enhance-summary, /enhance-summary, or requests to generate the Stage 1 enhanced summary.
metadata:
  short-description: Generate a CampaignGenerator enhanced session summary
---

# Enhanced summary

Maintain this Codex skill under `dotfiles/codex/skills/enhance-summary/`;
leave Claude skills intact.

This skill owns **one stage**: the recorded case, turning a reviewed VTT and
gm-assist into `session-summary.md`. Running the whole pipeline (enhancement,
scene extraction, narration, assembly) is a separate job, and so is building a
summary from chapter *prose* when there is no recording at all — a different
input and a different schema discipline.

Generate the artifact through CampaignGenerator's installed `enhance_summary`
command, using its bundled prompts. Do not hand-write a replacement summary
or substitute a direct model call. The CLI is the command path used by the
Session Doc Editor; actual browser interaction is unnecessary unless requested.

## Resolve inputs and preserve reviewed work

Use the campaign and session directory established by the conversation. Resolve:

- The exact session VTT, preferably the established spell-corrected cleaned VTT.
  Do not select another transcript merely because its filename sorts first.
- The reviewed `gm-assist.md`, which supplies the structural specification and
  approved GM rulings.
- The destination, normally `<session>/session-summary.md`.

Reuse existing Stage 0 decisions and manifests. The normal pipeline is reviewed
VTT and GM-assist → enhancement → Stage 1 consistency → recap removal → scene
extraction. Do not rerun reviews or create missing upstream artifacts implicitly.
If a required input is absent or consequentially ambiguous, ask for it. If
Stage 0 is not complete, disclose that rather than calling the output reviewed.

Check whether the destination already exists. The CLI overwrites it without a
snapshot. A request to generate an absent summary is sufficient; replacement
of an existing reviewed summary needs clear regeneration authority. Preserve a
non-overwriting snapshot before authorized replacement and identify downstream
artifacts that may become stale; do not rebuild them automatically.

## Use the UI-equivalent command

Locate `enhance_summary` with `command -v` and inspect `enhance_summary --help`.
When command parity or settings are uncertain, inspect the installed
CampaignGenerator checkout (normally `/home/kostadis/src/CampaignGenerator`):

- `server/routers/scene_editor.py::_build_enhance_cmd` and `_selection_args`.
- `session_doc/enhance_summary.py` for prompt construction and output behavior.

The currently inspected UI command deliberately omits `--party`,
`--party-config`, and `--players-config`. Preserve that behavior by default;
adding them changes the speaker preflight and is not routine plumbing.
Do not add `--allow-speaker-mismatch` to conceal an input problem.
Human recording labels do not identify the in-fiction speaker of every line,
especially when one player voices multiple characters. Conversation-only
voicing rulings are not automatically passed to the generator. Flag relevant
attribution limitations for subsequent review; do not rewrite the VTT or modify
global party configuration as part of enhancement.

Use `--backend codex-cli` for this saved-login workflow unless the user chooses
another backend. The backend vocabulary is shared across every model-bearing CG
CLI (`campaignlib/api/client.py::add_backend_args`): `anthropic`, `dgx`,
`openrouter`, `claude-code`, `codex-cli`. On `codex-cli`, reasoning effort is
`--codex-reasoning-effort`; on `claude-code` it is `--claude-code-effort` with
`--claude-code-thinking` / `--no-claude-code-thinking` (`xhigh` and `max`
require thinking enabled). Reuse explicitly established model and reasoning
settings; otherwise resolve the UI's configured selection
(`config/session_doc.yaml`, `backends.active`) rather than guessing a model.
Do not silently fall back to a metered API or downgrade settings.

Successful Chapter 09 command shape (model and effort are historical settings,
not universal defaults):

```bash
enhance_summary <session>/<cleaned-transcript>.vtt \
  --gmassist <session>/gm-assist.md \
  --output <session>/session-summary.md \
  --backend codex-cli \
  --model gpt-5.6-sol \
  --codex-reasoning-effort medium
```

Run from the campaign root with resolved paths. Keep generation logging enabled.
The `--batch` flag means Anthropic Message Batches, not a batch review page;
it is not compatible with `codex-cli`. A user choosing batch adjudication does
not authorize changing the generation backend or enabling that flag.

Before generation, state which transcript and GM-assist will go to which
backend and where the result will be saved. Follow execution permissions and
reuse prior explicit transmission approval only within its scope. If execution
review blocks transmission, obtain the missing approval; do not bypass the
block by changing the backend, tool, or payload packaging.

Run a single pollable process and provide progress updates. A quiet call can
take several minutes; silence alone is not failure. On an actual failure,
inspect the exit status, logs, and any output before retrying. Preserve partial
results and never claim success merely because a file exists.

## Verify and hand off

Confirm successful exit and a nonempty, plausibly complete summary containing
`## Summary` and `## Scenes`. Compare its scene structure with the reviewed
GM-assist for obvious omissions or truncation. Retain the generated log in the
session's `logs/` directory; do not claim this inspection is Stage 1 consistency.

Run the installed local quote verifier against the exact generation VTT:

```bash
sd_verify_quotes \
  --vtt <session>/<cleaned-transcript>.vtt \
  --summary <session>/session-summary.md \
  --out <session>/quote_report_stage1.md \
  --report-only
```

If the console script is unavailable, use the CampaignGenerator environment's
`python -m session_doc.sd_verify_quotes` with those arguments. This check calls
no model and leaves the summary unannotated. Preserve prior reports when they
belong to a reviewed version being regenerated.

Read the report: exit 1 means findings; exit 2 means the check failed to run.
Report verified, near, unverified, and refused/unscored counts as applicable.
Only covered blockquote wording is checked, not inline quotations, speaker
identity, completeness, or campaign consistency. Examine flagged quotes in
the VTT: an interruption or laughter can split an otherwise supported quote
across cues. Record any manual resolution separately, with cue evidence;
do not change the verifier's classification or silently repair dialogue.

"No quotes found" is zero coverage, not a pass. Count `grep -c '^> '` in the
summary first. On OOTA ch02 (2026-09-25) the enhancement wrote 40 curly-quoted
inline spans and no blockquotes, so `sd_verify_quotes` exited 0 having checked
nothing. In that case run the inline sweep against the same VTT and report its
counts:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/staged-consistency/verify_quotes.py" \
  --doc <session>/session-summary.md --vtt <session>/<cleaned-transcript>.vtt
```

On ch02 it surfaced a reworded quote and a quote spliced across the GM's asides
without an ellipsis, neither of which the blockquote verifier could see.

End with the output link, generation result, quote-check result and any
unresolved findings. Stage 1 consistency is the next review step when requested.
Do not automatically apply consistency edits, remove recap, extract scenes,
or generate narration. No extra HTML review queue or manifest is needed for
ordinary enhancement alone.
