---
name: scene-extract
description: Run scene_extract over a session VTT exactly as the Session Doc Editor would — same binary, saved party/player mapping, UI-resolved token and bundle settings, the configured raw output directory — behind a cheap speaker-label preflight that stops and asks the GM when a transcript label does not resolve through players.yaml. Then verify the output (sd_verify_quotes plus a truncation/label census). The speaker-attribution review queue is built only on request. Invoke as /scene-extract [session-dir].
tools: Bash, Read, Edit, AskUserQuestion
---

# scene-extract

Stage 2 of the session-doc pipeline: turn a human-verified `session-summary.md` scene structure plus the session VTT into per-scene verbatim extractions.

**Run exactly what the Session Doc Editor would run.** The UI command is the source of truth: CampaignGenerator's `server/routers/scene_editor.py::_build_reextract_cmd`, with its settings in `server/session_editor_config_shared.py::ExtractKnobs`. Use the saved party/player mapping in `config/players.yaml` + `config/party.yaml`. Do **not** re-interview the GM about who voices whom, and do not ask for an attribution strategy on every run — that mapping is configuration the GM already decided.

The one precision decision left is **whether the saved mapping fits this recording**. `scene_extract` rewrites VTT display names to character names deterministically, and a label nobody recorded — a new player, an absent player's stand-in, someone who renamed their Zoom account — produces lines that are silently wrong or silently unrewritten. So a cheap label survey runs first, and if any label does not resolve, you stop and ask before spending anything.

## Workflow

### 1. Locate the session and its inputs

If the user passed a path, use it. Otherwise `pwd` to confirm a campaign workspace (`docs/`, `summaries/`, `config/`), then `ls -t summaries/ | head -10` and ask which session.

Confirm these exist before continuing, and use absolute paths for all of them:
- the VTT — the exact transcript the summary was generated from (prefer `*.cleaned.vtt` over the raw Zoom file; if several are plausible, check the Stage 1 log in `<session>/logs/`)
- `session-summary.md` with a `## Scenes` section
- `docs/party.md`, `config/party.yaml`, `config/players.yaml` (or a session-local `players.session.yaml` handed over by `/session-doc-run`)
- `config/session_doc.yaml`

A workspace may have no root `config.yaml`, only `config/` — see `/session-doc-run` "Config resolution".

Sanity-check the scene count yourself — `parse_gmassist_scenes` (`campaignlib/scenes.py`) reads `### ` headings **only between `## Scenes` and the next `##`**. Do not count `###` headings across the whole file; `## Locations` / `## NPCs` / `## Items` sections also use them and are correctly excluded.

Do not launch Stage 0/1 checks, recap removal, or summary regeneration as prerequisites. `/gmassist-precheck` and `/remove-recap` are the GM's call.

### 2. Resolve the output directory — raw layer only

Read `paths.scene_extractions_dir` from `config/session_doc.yaml`. It is a subdirectory of the session directory, and it varies by campaign (obelisk: `scene_extractions_new`; Phandalin, toee, out-of-the-abyss: `scene_extractions_smoothed`).

- `scene_extractions` or `scene_extractions_new` — a raw layer. Use it.
- `scene_extractions_smoothed` — that is `/voice-smooth`'s **derived** layer. **Stop and ask the GM** (AskUserQuestion) which raw directory to write to. Extraction must never write into the derived layer: it would overwrite smoothed prose with fresh verbatim, and the next smoothing pass would read its own output as source.
- unset — ask. Do not pick one.

Do not create a competing output directory beyond the one you resolved.

### 3. Resolve the UI-equivalent command

Locate the binary with `command -v scene_extract` (the installed console script) and check `scene_extract --help` for the current flag surface. From `config/session_doc.yaml`, read:

- **backend / model / effort** — `backends.active` and `active_profile`. A stale `active_profile` pointing at another session's knobs is easy to miss; check it, and say which backend will run.
- **`extract.tokens`** — per-scene `--max-tokens` (UI default 8192; see step 6 for the override).
- **`extract.batch_tokens`** — `--batch-max-tokens` (UI default 32000).
- **`extract.batch_scenes`** — tri-state. If pinned `true`/`false`, that is the setting. If unset, the editor pre-selects bundle mode when the active backend is `claude-code` (no prompt caching) and per-scene otherwise. If the selection also carries `--batch` (Message Batches, anthropic only), bundle mode stands down.

The editor **always renders `--batch-scenes` or `--no-batch-scenes` explicitly**, never relying on the CLI's own default (off). Do the same, matching the UI's resolved setting — unless the GM chose otherwise for this run.

### 4. Preflight: survey the VTT's actual speaker labels

**Match the label permissively — everything up to the colon — or you will miss one.**

```bash
grep -oP '^[^:]{1,40}(?=: )' <vtt> | sort | uniq -c | sort -rn | head -20
```

Zoom emits whatever the person's account name was, and people put *anything* in that field: a fantasy handle, a nickname in parentheses, an emoji, a company suffix. A character-class pattern like `[A-Za-z0-9 ._'-]+` silently drops every label containing a character it forgot. One run used exactly that class against a VTT holding `Kostadis Roussos` (611 cues) and `Filavandrel (Fil)` (363) — the parentheses failed the class, the second speaker vanished from the survey, and the session was misdiagnosed as the single-mic no-attribution case. A diarization run followed from that.

Two cheap guards, both worth the seconds:

```bash
grep -c ':' <vtt>                      # labelled cues; compare to your survey's total
sed -n '1,12p' <vtt>                   # LOOK at it
```

If the survey's counts do not sum to the labelled-cue count, a label is missing from your list. Read the first few cues with your own eyes before concluding anything about attribution — a survey is evidence, not proof.

### 5. Preflight: does every label resolve through `players.yaml`?

The speaker map is built by `campaignlib.players_config.speaker_map(players, party)` from two config files:

- `config/players.yaml` — one entry per *person*, with `display_names` (every label a recording has used for them), `plays` (their characters) and `gm: true` for whoever runs the game.
- `config/party.yaml` — the character roster the `plays` entries resolve against.

`party.md` is still passed as `--party`, but only as prose context and as the gate that turns the rewrite on; the map does not come from it. `party.md` records who *owns* a character, not who *speaks* for one — never infer voicing from it.

Two rules fall out of `speaker_map`'s two-pass build, and both matter:

1. A player's display names map to the first of their `plays` **that the roster actually has**. A binding to a character `party.yaml` lacks contributes *nothing* rather than inventing a label.
2. Game masters are applied **last and overwrite**, so a person who both runs the game and voices sidekicks gets `GM` on every line and their characters' names on none (FR-021a). This is deliberate — a transcript label records *who spoke*, not in what capacity. It is not a bug to work around.

`display_names` is a literal list with no aliasing beyond what is written in it. Dry-run the map against the VTT — no model call, no cost:

```bash
python -c "
from campaignlib.players_config import load_players_config, speaker_map
from campaignlib.party_config import load_party_config
from campaignlib.npc import normalize_vtt_speakers
from pathlib import Path
sm = speaker_map(load_players_config(Path('<abs players.yaml>')),
                 load_party_config(Path('<abs party.yaml>')))
out = normalize_vtt_speakers(Path('<abs vtt>').read_text(), sm).splitlines()
print('speaker_map:', sm)
print('GM lines:', sum(1 for l in out if l.startswith('GM:')))
print('UNREWRITTEN:', sum(1 for l in out if l.startswith(tuple(<every label from step 4>))))"
```

`normalize_vtt_speakers` takes `(vtt_text, speaker_map)`; the old `gm_player` argument and `--gm-player` flag are gone.

**If `UNREWRITTEN` is 0 and every step-4 label appears in the map, proceed — no questions.** That is the ordinary case.

**If any label does not resolve, STOP and ask the GM via AskUserQuestion before extracting.** An unresolved label — a new or absent player, a stand-in covering someone's PC, a new display name — is exactly when the saved mapping is wrong for this recording. Name the label, its cue count, and the first line or two it speaks. The fixes are the GM's to choose:

- add the display name to `players.yaml` (a steady-state change — the GM's edit, not yours to make silently);
- use a session-local `players.session.yaml` for a one-off stand-in (`/session-doc-run` builds these);
- or run this session in preserve-labels mode (below).

Never hand-rewrite the VTT, and never reach for `--allow-speaker-mismatch` to get past it — that flag only skips the CLI's own preflight when the rewrite changed 0 lines, and using it hides a mapping problem rather than fixing one.

**Preserve-labels mode — only when the GM asks for it.** Omit `--party`, `--party-config` and `--players-config` together. The CLI's speaker-mismatch preflight only runs when a player map exists, so `--allow-speaker-mismatch` is **not** needed in this mode. Nothing is silently wrong, but every quote keeps its raw recording label and GM narration loses its `GM` label too.

### 6. Run

State what goes where before you run: the transcript, `session-summary.md`, and the party context (`party.md` and, with `--dossier-dir`, the NPC dossiers) go to the chosen backend. Name the backend. If a permission prompt or the GM rejects the transmission, report the block and ask — do not route around it.

The saved-mapping rewrite normalizes labels; it does **not** tell the model who voices whom. There is no flag that transmits an arbitrary shared-voice map. Do not invent one, and **never smuggle the voicing map into the model prompt** by editing the summary, the VTT, or the NPC dossiers. If the GM wants the voicing map to inform generation, that is a CampaignGenerator change — stop and say so.

```bash
nohup "$(command -v scene_extract)" <abs vtt> \
  --summary <session>/session-summary.md \
  --output-dir <session>/<raw dir from step 2> \
  --backend claude-code \
  --party <campaign>/docs/party.md \
  --party-config <campaign>/config/party.yaml \
  --players-config <campaign>/config/players.yaml \
  --max-tokens 32000 \
  --batch-scenes \
  --batch-max-tokens 32000 \
  > <session>/logs/scene_extract.log 2>&1 &
```

Substitute the step-3 backend/model/effort and **`--batch-scenes` or `--no-batch-scenes` — whichever the UI resolved**; render one, always.

- **`--max-tokens` per scene.** On backends that enforce it — `claude-code`, `anthropic`, `dgx`, `openrouter` — pass `--max-tokens 32000` per scene (or the configured value if it is higher): scale up, never down. At 8192 a scene truncated from 264 to 205 lines and a heading was spliced as `**[The Cellar — Read**[The Cellar — Read-Aloud Description]**`. On `codex-cli` it is ignored (`codex exec` has no output-token flag; CampaignGenerator `campaignlib/selection.py`, #414), so say so and rely on the step-7 census to catch truncation. `claude-code` forwards it as `CLAUDE_CODE_MAX_OUTPUT_TOKENS`.
- **`--batch-max-tokens`** governs a `--batch-scenes` group (UI default 32000); it is independent of `--max-tokens` and inert in per-scene mode.
- `--backend claude-code` routes through `claude -p` headless and **strips `ANTHROPIC_API_KEY`** so billing lands on the subscription (`campaignlib/api/backends.py:338`). Without it the run falls through to the metered API whenever that key is set. `--batch` is Anthropic-only, fails fast here, and cannot be combined with `--batch-scenes`.
- **Resume, don't force.** The default skips existing per-scene files, so a partial run resumes. Pass `--force` **only for a regeneration the GM asked for**, and say before running that it re-extracts every scene, snapshots changed prior content to `<file>.prev`, and **clears any `<file>.reviewed` marker** — review state is lost. Never delete outputs or snapshots to get a fresh run.
- Run it in the background. Python block-buffers stdout when it is not a tty, so the log stays empty until exit; a bundled call can be silent for minutes. Watch the output directory (or `.prev` files on a re-run) for progress. Silence is not failure and not grounds for a duplicate call. On a real failure, keep the log and partial outputs, report what completed, and fix the cause before retrying — do not silently switch backend, model or effort.

### 7. Verify the output — do not trust the banner

The `WARNING: claude -p hit its output ceiling` banner fires on `num_assistant_events > 1` (`campaignlib/api/backends.py:439`). That is a turn-count heuristic, **not** ceiling detection: it appears on essentially every scene even at 32k, where a 13 KB output is nowhere near the limit. Ignore the banner and check the artifacts.

**First, the deterministic quote verifier** — no model call, does not edit the extractions:

```bash
python3 -m session_doc.sd_verify_quotes \
  --vtt <same abs vtt the run used> \
  --scene-extractions <session>/<raw dir> \
  --out <session>/quote_report_scene_extract.md \
  --report-only
```

Exit 0 is clean; **exit 1 means findings; exit 2 means verification failed to run** — report exit 2 as "not verified", never as clean. On findings, read the report and summarise verified / near / unverified / refused counts. It checks wording only — not speaker identity, completeness, or truncation — so it does not replace the census.

**Then the truncation / label census.** Expect one nonempty file per scene, each with its scene summary and verbatim-moments sections; exclude logs, `.prev` snapshots, `.reviewed` markers and scaffolds from the count.

```bash
python - <<'PY'
import glob, collections, re, os
D = "<session>/<raw dir>"
# GM plus the character names the map rewrites to (short AND full forms,
# e.g. "Zenvon", "Zenvon Foreput"). In preserve-labels mode, the raw labels.
SPEAKERS = ["GM", "<character>", "<character short form>"]
files = sorted(f for f in glob.glob(os.path.join(D, "*.md"))
               if not f.endswith((".prev", ".reviewed")))
print(f"{len(files)} scene file(s)\n")
for f in files:
    lines = [l.rstrip() for l in open(f) if l.strip()]
    t = open(f).read()
    # Speaker labels only. `**[Scene Tag]**` action beats are structurally
    # identical to a bare `**GM**` label, so they CANNOT be told apart by shape —
    # match against the known speaker names instead.
    names = "|".join(re.escape(n) for n in SPEAKERS)
    plain = len(re.findall(rf'^\*\*(?:{names})\*\*', t, re.M))
    brac  = len(re.findall(rf'^\*\*\[(?:{names})\]\*\*', t, re.M))
    print(f"  {os.path.basename(f)[:34]:36} {len(lines):4}L  plain={plain:<4} brack={brac:<4}  last: {lines[-1][:44]}")
q = collections.defaultdict(set)
for f in files:
    for l in open(f):
        if l.startswith('> "'): q[l.strip()].add(os.path.basename(f)[:2])
print(f"\ncross-scene duplicate quotes: {sum(1 for v in q.values() if len(v) > 1)}")
PY
```

Read the results with these caveats:

- **Do not flag a final line as truncated just because it lacks terminal punctuation.** Speakers trail off constantly; `...would start attacking them, right"` is a complete quote block. Confirm real truncation by diffing against `.md.prev` or checking whether the line ends mid-word or mid-heading.
- **Label format varies per scene and per run.** Expect a mix of `**GM**` / `**[GM]**` and full vs. short character names (`**Zenvon Foreput**` vs `**Zenvon**`) across files. This is model variance, unrelated to `max_tokens` — it will not re-run away. Report it so downstream parsing handles all shapes.
- **Cross-scene duplicate quotes are partly inherent.** Adjacent scenes share boundary moments, so the same exchange is extracted twice. Report the count; only investigate if it spikes.

### 8. Hand off

Report: generated / expected scene counts, the output directory, the backend that ran, the `sd_verify_quotes` exit code and counts, and the census (any truncation, label shapes, duplicate count). Flag obvious attribution concerns you noticed without fixing them. Then stop:

> Extraction done — N/M scenes in `<dir>`. Next: `/session-summary-consistency`, then `/voice-smooth`. Say if you want the speaker-attribution queue built first.

**Do not auto-advance to `/voice-smooth` or `/fable-narration`.** Do not edit the VTT or the summary, smooth dialogue, remove mechanics or recap, or narrate as part of extraction.

## On request: the attribution review queue

Build this **only when the GM asks** — it is not the default deliverable. It targets the case the saved map cannot express: one person voicing several characters (sidekicks, henchmen, an absent player's PC), where the GM-overwrite rule labels every GM-voiced sidekick line `GM`.

If the voicing map is not already known from the conversation or earlier rulings, ask for just the missing pieces: which extra characters each person voices. Keep human identity, primary-PC normalization and in-fiction voice distinct — a voicing map records possibilities, not proof of who a particular line portrays.

```bash
python - <<'PY'
import glob, re, os
D = "<session>/<raw dir>"
tot = 0
for f in sorted(x for x in glob.glob(os.path.join(D, "*.md")) if not x.endswith((".prev", ".reviewed"))):
    hits = []
    for i, l in enumerate(open(f), 1):
        m = re.match(r'^\*\*\[?([^*\]—]+?)\]?\*\*\s*—\s*\*(.+?)\*', l)
        if m and re.search(r'<sidekick names, pipe-separated>', m.group(2)):
            hits.append((i, m.group(1), m.group(2)))
    tot += len(hits)
    if hits:
        print(f"\n{os.path.basename(f)}  ({len(hits)})")
        for i, s, c in hits:
            print(f"  :{i:<4} **{s}** — *{c[:58]}*")
print(f"\nTOTAL: {tot} blocks to rule on")
PY
```

This works because the extractor annotates the context field (`**GM** — *voicing Sister Maela*`) rather than silently absorbing the line. Split the queue for the GM:

- **Label is correct** — the GM narrating a sidekick in third person (`*narrating Pip's turn*`). `GM` is the right speaker; leave it.
- **Label is wrong** — the GM or a player voicing a sidekick in first person (`*voicing Sister Maela*` → `"I think we should help the helpless"`). These corrupt POV narration and must be fixed before `/voice-smooth`.

Present it with `file:line` for each entry, and stop.

## Notes

- Working directory drifts after any `cd` in a Bash call. Use absolute paths in the verification scripts — a glob that silently matches nothing reports `0 scene file(s)` or `TOTAL: 0`, which reads exactly like "no problems found."
- If the CLI's own preflight aborts with `speaker-mismatch`, the message blames a wrong/stale VTT. That is one cause; a display name missing from `players.yaml` is at least as likely, and a label the step-4 survey never saw is likelier still. Re-check steps 4 and 5 before concluding the recording is wrong.
- Related: `/gmassist-precheck` runs before this (validates the scene structure); `/session-summary-consistency` and `/voice-smooth` run after; `/session-doc-run` hands over any session-local `players.yaml`.
