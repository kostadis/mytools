---
name: scene-extract
description: Generate per-scene verbatim extractions using CampaignGenerator's Session Doc Editor command path, then check output files and verify quotes against the source VTT. Use for $scene-extract, /scene-extract, or requests to extract campaign session scenes.
metadata:
  short-description: Extract scenes with the CampaignGenerator UI command
---

# Scene extraction

Maintain this Codex skill under `dotfiles/codex/skills/scene-extract/`;
leave the Claude version intact.

Use the same CampaignGenerator command the Session Doc Editor uses, followed
by lightweight local verification. Do not replace ordinary extraction with a
mandatory attribution interview, custom review workflow, or pipeline audit.

## Resolve the inputs and UI command

Use the session directory established by the user or conversation. Resolve:

- The reviewed `session-summary.md`, containing `## Scenes`.
- The exact VTT used to generate that summary, preferably the established
  cleaned transcript. Consult generation logs if multiple VTTs are ambiguous.
- The configured party document, `config/party.yaml`, and
  `config/players.yaml`, when the campaign uses speaker normalization.
- The established extraction directory; use `scene_extractions_new/` for
  a new run. Do not create competing output directories.

Reuse prior review decisions and known paths. Ask only for genuinely missing
inputs or consequential ambiguity. Do not automatically launch Stage 0/1
checks, recap removal, or summary regeneration as prerequisites.

Locate `scene_extract` with `command -v` and inspect `scene_extract --help`.
For UI parity, the source of truth is CampaignGenerator's
`server/routers/scene_editor.py::_build_reextract_cmd`, with settings in
`server/session_editor_config_shared.py::ExtractKnobs`. Inspect these when
flags or defaults need confirmation; use the installed checkout rather than
inventing a separate extraction wrapper.

Use the UI's configured party/player mapping by default. The command performs
its speaker-label preflight and reports the mapping and rewritten line count.
Recording-to-primary-PC/GM mapping does not establish the in-fiction speaker
of every line; do not claim that it does.

If the user explicitly requests preserved recording labels, omit `--party`,
`--party-config`, and `--players-config` together. If the command reports a
mapping problem, inspect the source labels and configuration; do not conceal
it with `--allow-speaker-mismatch` or rewrite the VTT.

## Conditional attribution preflight

Establish who voices whom in the skill, rather than asking the bundled model
to guess human identities. Reuse confirmed conversation answers and campaign
configuration. For recording labels whose mapping is missing or unclear, ask
only for the missing human identity, main PC (or GM role), and any additional
characters they voice, including GM-voiced sidekicks. Do not repeat an already
answered interview or require a label-strategy choice on every run; keep the
UI mapping default unless the user requests preserved recording labels.

Keep human identity, primary-PC normalization, and in-fiction voice distinct.
A player can voice another character, and a sidekick can be voiced by both
the GM and a player. A confirmed voicing map records possibilities, not proof
of who a particular line portrays. Keep unresolved line attribution explicit;
do not assign every utterance to the human's main PC or infer a voice from a
character's mere mention. Summarize new rulings concisely for reuse without
silently editing shared campaign configuration.

Before generation, check whether the installed UI-equivalent command has a
supported way to pass this confirmed voicing context into the bundled prompt.
If available, pass the recording-label-to-human mapping, primary PC/GM role,
additional voices, and any remaining uncertainty through that input, and
verify the prompt construction actually includes it. Preserve the bundled
prompt's distinction between transcript labels and character context.

The currently inspected command's party/player flags normalize labels; they
do not transmit an arbitrary shared-voice map. Do not invent a flag, assume
conversation answers reach the model, or repurpose the summary, VTT, or NPC
dossiers to smuggle them in. If no supported input exists, tell the user that
the map is available for subsequent attribution review only. Continue ordinary
UI-equivalent extraction with that limitation disclosed; if the user requires
the map to inform generation, pause for direction on a CampaignGenerator
integration change. Editing its code or bundled prompt is a separate task.

## Run the UI-equivalent command

Respect the user's backend, model, reasoning effort, and bundle choice.
For the saved-Codex-login approach, use `--backend codex-cli`; do not
substitute a metered API backend. Reuse choices already established in the
conversation. The following is the successful bundle-mode command shape,
with model and effort illustrating the user's selected settings rather than
universal defaults:

```bash
scene_extract <generation-vtt> \
  --summary <session>/session-summary.md \
  --output-dir <session>/scene_extractions_new \
  --backend codex-cli \
  --model gpt-6-astra \
  --codex-reasoning-effort medium \
  --party <campaign>/docs/party.md \
  --party-config <campaign>/config/party.yaml \
  --players-config <campaign>/config/players.yaml \
  --max-tokens 8192 \
  --batch-scenes \
  --batch-max-tokens 32000
```

Substitute resolved paths and requested settings. Honor configured token
budgets; absent overrides, the UI defaults are 8192 per scene and 32000 per
bundle group. Do not raise the per-scene budget merely for this workflow.
The Codex adapter may report that the output-token ceiling is ignored by its
backend; report that accurately if relevant, without treating it as failure.

For bundle mode use `--batch-scenes`. For per-scene mode render
`--no-batch-scenes` explicitly. If the user has not chosen, follow the UI's
resolved setting/backend default (inspect the extract route if needed).
`--batch` is the distinct Anthropic Message Batches feature, not bundle mode;
it is incompatible with `codex-cli` and with `--batch-scenes`. A batch
review-page preference alone does not select a generation mode.

Briefly state the resolved inputs, output scope, and model settings, then run
the command. Follow execution permissions for transmitting the transcript,
summary, and configured party context to the chosen backend. Reuse explicit
approval within its scope; if execution review rejects the transmission,
report the block and ask for approval rather than bypassing it.

Default execution skips existing files and supports resuming partial runs.
Use `--force` only for requested regeneration: changed prior files receive
`.prev` snapshots and review markers are cleared. Never delete existing
outputs or snapshots to force a fresh run.

Use a pollable process/session and provide concise progress updates.
A bundled call can remain quiet for several minutes before saving all scenes;
silence alone is not failure or grounds for a duplicate call. On an actual
failure, preserve diagnostics and partial outputs, report what completed,
and resolve the cause before retrying. Do not silently switch providers,
models, or reasoning effort.

## Verify and hand off

Confirm successful exit and one nonempty file per expected scene, with scene
summary and verbatim-moments sections. Use the command's parsed scene list,
or `campaignlib.scenes.parse_gmassist_scenes` if an independent count is needed;
headings elsewhere in the summary are not scenes. Exclude logs, snapshots,
review markers, and scaffolds from output counts. Investigate visibly
malformed or truncated output rather than reporting it as complete.

Run the local deterministic verifier against the exact generation VTT:

```bash
python3 -m session_doc.sd_verify_quotes \
  --vtt <generation-vtt> \
  --scene-extractions <selected-output-dir> \
  --out <session>/quote_report_scene_extract.md \
  --report-only
```

This check calls no model and does not annotate or edit the extractions.
Exit 1 means findings; exit 2 means verification failed to run. Read the
report when findings occur and summarize verified, near, unverified, and
refused results as applicable. Quote verification checks covered wording,
not speaker identity, completeness, or prose correctness.

Do not automatically create an attribution queue, HTML review page, or extra
manifest. Retain the command's generation log and quote report. If obvious
attribution concerns appear, flag them without silently fixing them; a full
attribution or consistency review is separate work when requested.

End with generated/expected scene counts, a link to the extraction directory,
and the quote-check outcome. Do not edit the VTT or source summary, smooth
dialogue, remove mechanics or recap, plan narration, or generate narration
as part of extraction.
