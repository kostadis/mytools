---
name: scene-extract
description: Generate per-scene verbatim extractions using CampaignGenerator's Session Doc Editor command path and saved party/player mapping, behind a cheap speaker-label preflight that stops and asks when a transcript label does not resolve through players.yaml; then verify quotes against the source VTT and census the output for truncation and label shape. Use for $scene-extract, /scene-extract, or requests to extract campaign session scenes.
metadata:
  short-description: Extract scenes with the CampaignGenerator UI command
---

# Scene extraction

Maintain this Codex skill under `dotfiles/codex/skills/scene-extract/`
(linked from `~/.codex/skills/scene-extract`). Its rules are shared with the
Claude version under `dotfiles/claude/skills/scene-extract/`; keep them in
step when either changes. Mechanics stay harness-specific.

Use the same CampaignGenerator command the Session Doc Editor uses, with the
saved party/player mapping, followed by lightweight local verification. Do
not replace ordinary extraction with a mandatory attribution interview, a
per-run strategy choice, a custom review workflow, or a pipeline audit. The
one precision check that runs every time is cheap: confirm that every speaker
label in this recording resolves through `players.yaml`, and stop and ask
when one does not.

## Resolve the inputs and UI command

Use the session directory established by the user or conversation. Resolve,
as absolute paths:

- The reviewed `session-summary.md`, containing `## Scenes`.
- The exact VTT used to generate that summary, preferably the established
  cleaned transcript. Consult generation logs in `<session>/logs/` if
  multiple VTTs are ambiguous.
- The configured party document, `config/party.yaml`, and
  `config/players.yaml` (or an established session-local players file).
- `config/session_doc.yaml`. A workspace may have no root `config.yaml`,
  only `config/`.

Reuse prior review decisions and known paths. Ask only for genuinely missing
inputs or consequential ambiguity. Do not automatically launch Stage 0/1
checks, recap removal, or summary regeneration as prerequisites.

Locate `scene_extract` with `command -v` and inspect `scene_extract --help`.
For UI parity, the source of truth is CampaignGenerator's
`server/routers/scene_editor.py::_build_reextract_cmd`, with settings in
`server/session_editor_config_shared.py::ExtractKnobs`. Inspect these when
flags or defaults need confirmation; use the installed checkout rather than
inventing a separate extraction wrapper. Read backend, model, and effort from
`backends.active` / `active_profile` in `config/session_doc.yaml`, and check
that `active_profile` is not stale from another session.

## Resolve the output directory

Read `paths.scene_extractions_dir` from `config/session_doc.yaml`; it names
a subdirectory of the session and varies by campaign (obelisk uses
`scene_extractions_new`; Phandalin, toee, and out-of-the-abyss use
`scene_extractions_smoothed`).

- If it names a raw layer, `scene_extractions/` or `scene_extractions_new/`,
  use it.
- If it names `scene_extractions_smoothed/`, stop and ask. That is
  voice-smooth's derived layer, and extraction must never write into it:
  fresh verbatim would overwrite smoothed prose, and the next smoothing pass
  would read its own output as source.
- If it is unset, ask.

Do not create competing output directories.

## Speaker-label preflight

Use the UI's configured party/player mapping by default. Do not repeat an
already answered voicing interview or require a label-strategy choice on
every run. Before spending anything, survey the recording's real labels and
check each one against the saved mapping.

Match labels permissively, everything up to the colon:

```bash
grep -oP '^[^:]{1,40}(?=: )' <vtt> | sort | uniq -c | sort -rn | head -20
grep -c ':' <vtt>          # labelled cues; the survey counts must sum to this
sed -n '1,12p' <vtt>       # read the first cues directly
```

Zoom emits whatever the account name was, including parentheses, emoji, and
suffixes. A character-class pattern such as `[A-Za-z0-9 ._'-]+` silently
drops labels it did not anticipate: one run lost `Filavandrel (Fil)` (363
cues) that way, misdiagnosed the session as single-microphone, and launched
an unnecessary diarization run. If the survey does not sum to the labelled-cue
count, a label is missing from the survey.

The mapping is `campaignlib.players_config.speaker_map(players, party)`:
`players.yaml` records each person's `display_names`, `plays`, and `gm: true`;
`party.yaml` is the roster those `plays` resolve against. `party.md` is prose
context and the switch that enables rewriting; it records who owns a
character, not who speaks for one. Two consequences:

- A player's labels map to the first of their `plays` that the roster has.
  A binding to a character absent from `party.yaml` contributes nothing.
- Game masters are applied last and overwrite. A person who runs the game
  and voices sidekicks gets `GM` on every line (FR-021a). That records who
  spoke, not in what capacity; it is deliberate, not a bug to work around.

`display_names` is a literal list with no aliasing. Confirm without a model
call that no surveyed label survives the rewrite:

```bash
python3 -c "
from campaignlib.players_config import load_players_config, speaker_map
from campaignlib.party_config import load_party_config
from campaignlib.npc import normalize_vtt_speakers
from pathlib import Path
sm = speaker_map(load_players_config(Path('<abs players.yaml>')),
                 load_party_config(Path('<abs party.yaml>')))
out = normalize_vtt_speakers(Path('<abs vtt>').read_text(), sm).splitlines()
print('speaker_map:', sm)
print('UNREWRITTEN:', sum(1 for l in out if l.startswith(tuple(<surveyed labels>))))"
```

If every label resolves and `UNREWRITTEN` is 0, proceed without questions.
If any label does not resolve (a new or absent player, a stand-in, a new
display name), stop and ask in chat before extracting: name the label, its
cue count, and a sample line. That is exactly when the saved mapping is wrong
for this recording. The user decides whether to add the display name to
`players.yaml`, use a session-local players file, or preserve recording
labels. Do not edit shared campaign configuration silently, rewrite the VTT,
or conceal the problem with `--allow-speaker-mismatch`; that flag only skips
the CLI's preflight when a rewrite changed zero lines.

Use preserved recording labels only when the user asks for them: omit
`--party`, `--party-config`, and `--players-config` together. The CLI's
speaker-mismatch preflight runs only when a player map exists, so
`--allow-speaker-mismatch` is not needed in that mode.

Recording-to-primary-PC/GM mapping does not establish the in-fiction speaker
of every line; do not claim that it does. Keep human identity, primary-PC
normalization, and in-fiction voice distinct. A confirmed voicing map records
possibilities, not proof of who a particular line portrays; do not assign
every utterance to the human's main PC or infer a voice from a character's
mere mention.

## Voicing context does not reach the model

The party/player flags normalize labels; they do not transmit an arbitrary
shared-voice map. Check the installed command for a supported input before
assuming otherwise. Do not invent a flag, assume conversation answers reach
the model, or repurpose the summary, VTT, or NPC dossiers to smuggle the
voicing map in. If no supported input exists, the map is available for
subsequent attribution review only; say so. If the user requires the map to
inform generation, pause for direction on a CampaignGenerator integration
change. Editing its code or bundled prompt is a separate task.

## Run the UI-equivalent command

Respect the user's backend, model, reasoning effort, and bundle choice.
For the saved-Codex-login approach, use `--backend codex-cli`; do not
substitute a metered API backend. Reuse choices already established in the
conversation. The following is the successful bundle-mode command shape,
with model and effort illustrating the user's selected settings rather than
universal defaults:

```bash
"$(command -v scene_extract)" <generation-vtt> \
  --summary <session>/session-summary.md \
  --output-dir <session>/<raw extraction dir> \
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

Substitute resolved paths and requested settings.

Per-scene `--max-tokens` depends on the backend. On `codex-cli` it is
ignored: `codex exec` has no output-token flag (CampaignGenerator
`campaignlib/selection.py`, #414). Say so, pass the configured value for UI
parity, and rely on the post-run census to catch truncation. On backends that
enforce it (`claude-code`, which forwards it as
`CLAUDE_CODE_MAX_OUTPUT_TOKENS`, and `anthropic`, `dgx`, `openrouter`), pass
`--max-tokens 32000` per scene, or the configured value if higher; scale up,
never down. At 8192 one scene was truncated from 264 to 205 lines and a
heading was spliced as `**[The Cellar — Read**[The Cellar — Read-Aloud
Description]**`. Keep `--batch-max-tokens` for bundle mode (UI default 32000);
it is a per-group ceiling, independent of `--max-tokens`.

Always render `--batch-scenes` or `--no-batch-scenes` explicitly, as the
editor does; never rely on the CLI's default (off). If the user has not
chosen, match the UI's resolved setting: a pinned `extract.batch_scenes` in
`config/session_doc.yaml`, otherwise bundle mode when the active backend is
`claude-code` and per-scene otherwise. `--batch` is the distinct Anthropic
Message Batches feature, not bundle mode; it is incompatible with
`codex-cli` and with `--batch-scenes`, and the UI renders
`--no-batch-scenes` when it is selected. A batch review-page preference alone
does not select a generation mode.

Briefly state the resolved inputs, output directory, and model settings,
and what goes to which backend (the transcript, summary, and configured party
context), then run the command. Follow execution permissions for that
transmission. Reuse explicit approval within its scope; if execution review
rejects the transmission, report the block and ask for approval rather than
bypassing it.

Default execution skips existing files and supports resuming partial runs.
Use `--force` only for a regeneration the user asked for, and say before
running that it re-extracts every scene, snapshots changed prior content to
`<file>.prev`, and clears any `<file>.reviewed` marker. Never delete existing
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
it reads `###` headings only between `## Scenes` and the next `##`, so
headings elsewhere in the summary are not scenes. Exclude logs, `.prev`
snapshots, `.reviewed` markers, and scaffolds from output counts.

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

Then census the output for truncation and label shape, with absolute paths
(a glob that matches nothing prints zero and reads like a clean result):

```bash
python3 - <<'PY'
import glob, collections, re, os
D = "<abs output dir>"
SPEAKERS = ["GM", "<character>", "<character short form>"]  # raw labels if preserved
files = sorted(f for f in glob.glob(os.path.join(D, "*.md"))
               if not f.endswith((".prev", ".reviewed")))
print(f"{len(files)} scene file(s)")
names = "|".join(re.escape(n) for n in SPEAKERS)
for f in files:
    t = open(f).read()
    lines = [l.rstrip() for l in t.splitlines() if l.strip()]
    plain = len(re.findall(rf'^\*\*(?:{names})\*\*', t, re.M))
    brac = len(re.findall(rf'^\*\*\[(?:{names})\]\*\*', t, re.M))
    print(f"  {os.path.basename(f)[:34]:36} {len(lines):4}L  plain={plain:<4} brack={brac:<4}  last: {lines[-1][:44]}")
q = collections.defaultdict(set)
for f in files:
    for l in open(f):
        if l.startswith('> "'): q[l.strip()].add(os.path.basename(f)[:2])
print(f"cross-scene duplicate quotes: {sum(1 for v in q.values() if len(v) > 1)}")
PY
```

Speaker labels are matched against known names because `**[Scene Tag]**`
action beats have the same shape as `**[GM]**`. Read the census with care:

- A final line without terminal punctuation is not truncation by itself;
  speakers trail off. Confirm by diffing against `.prev` or finding a line
  that ends mid-word or mid-heading. Investigate real truncation rather than
  reporting the output as complete.
- Label shape varies by scene and run (`**GM**` vs `**[GM]**`, full vs short
  character names). It is model variance; report it so downstream parsing
  handles every shape.
- Adjacent scenes share boundary moments, so some cross-scene duplicate
  quotes are inherent. Report the count; investigate only a spike.

Do not automatically create an attribution queue, HTML review page, or extra
manifest. Retain the command's generation log and quote report. If obvious
attribution concerns appear, flag them without silently fixing them; a full
attribution or consistency review is separate work when requested. When the
user does request an attribution queue, list context annotations such as
`**GM** — *voicing Sister Maela*` with `file:line`, and split them into
third-person narration (label correct) and first-person voicing (label
wrong).

End with generated/expected scene counts, a link to the extraction directory,
the quote-check outcome, and the census findings. Do not edit the VTT or
source summary, smooth dialogue, remove mechanics or recap, plan narration,
or generate narration as part of extraction.
