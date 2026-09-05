---
name: scene-extract
description: Run scene_extract over a session VTT when the party's PCs are voiced by one or more people — survey the transcript's real speaker labels, build the voicing map, check every label resolves through players.yaml, pick an attribution strategy at a human checkpoint, run with a sane output ceiling, then verify the output and hand back a speaker-attribution review queue. Invoke as /scene-extract [session-dir].
tools: Bash, Read, Edit, AskUserQuestion
---

# scene-extract (shared / multi-voiced PCs)

Stage 2 of the session-doc pipeline: turn a human-verified `session-summary.md` scene structure plus the session VTT into per-scene verbatim extractions.

The hard part is never the extraction. It is **speaker attribution**, and it is a precision decision. `scene_extract` rewrites VTT display names to character names deterministically via a one-player-to-one-character map. Real tables violate that: sidekicks get voiced by whoever is closest, the GM speaks as NPCs *and* as party members, and two people may share a PC. Every one of those cases produces a *confidently wrong* label that no downstream pass can detect.

This skill front-loads the voicing map, makes the attribution tradeoff explicit before spending anything, and ends by handing the GM a reviewable queue instead of a clean-looking file.

## Workflow

### 1. Locate the session and its inputs

If the user passed a path, use it. Otherwise `pwd` to confirm a campaign workspace (`docs/`, `summaries/`, `config.yaml`), then `ls -t summaries/ | head -10` and ask which session.

Confirm all three exist before continuing:
- the VTT (prefer `*.cleaned.vtt` over the raw Zoom file if both are present)
- `session-summary.md` with a `## Scenes` section
- `docs/party.md`

Sanity-check the scene count yourself — `parse_gmassist_scenes` (`campaignlib/scenes.py`) reads `### ` headings **only between `## Scenes` and the next `##`**. Do not count `###` headings across the whole file; `## Locations` / `## NPCs` / `## Items` sections also use them and are correctly excluded.

### 2. Read the VTT's actual speaker labels — do not assume

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

If the survey's counts do not sum to the labelled-cue count, a label is missing from your list. And read the first few cues with your own eyes before concluding anything about attribution — a survey is evidence, not proof.

### 3. Build the voicing map (the core step)

Ask the user directly. Do not infer it from `party.md`, which records who *owns* a character, not who *speaks* for one.

For each display name found in step 2, establish:
- which PC they primarily play
- **which additional characters they voice** — sidekicks, henchmen, familiars, an absent player's PC
- whether the GM also voices party members (very common with Essentials Kit sidekicks)

State the map back to the user before proceeding. A typical answer is lopsided:

> `Kostadis Roussos` → GM (also voices Veyra, Maela, Pip)
> `Nikhil` → Zenvon Foreput (also voices Veyra, Maela, Pip)

That shape — two speakers, five voiced characters — is the case this skill exists for.

### 4. Gate: is every display name in `players.yaml`?

**The speaker map no longer comes from `party.md`.** It is built by
`campaignlib.players_config.speaker_map(players, party)` from two config files:

- `config/players.yaml` — one entry per *person*, with `display_names` (every label a recording might carry), `plays` (their characters) and `gm: true` for whoever runs the game.
- `config/party.yaml` — the character roster the `plays` entries resolve against.

`party.md` is still passed as `--party`, but only as prose context; the map does not come from it. The old `extract_player_character_map` / `--gm-player` path is gone.

Two rules fall out of `speaker_map`'s two-pass build, and both matter:

1. A player's display names map to the first of their `plays` **that the roster actually has**. A binding to a character `party.yaml` lacks contributes *nothing* rather than inventing a label.
2. Game masters are applied **last and overwrite**, so a person who both runs the game and voices sidekicks gets `GM` on every line and their characters' names on none (FR-021a). This is deliberate — a transcript label records *who spoke*, not in what capacity — and it is the source of the sidekick review queue in step 9. It is not a bug to work around.

**The failure mode is a display name nobody recorded.** `display_names` is a literal list with no aliasing beyond what you write in it, so a player whose Zoom handle is a fantasy name (`Filavandrel (Fil)`) rather than their own goes entirely unrewritten while everything looks fine. Fix it in `players.yaml`; never hand-rewrite the VTT.

### 5. Gate: dry-run the map before spending anything

```bash
python -c "
from campaignlib.players_config import load_players_config, speaker_map
from campaignlib.party_config import load_party_config
from campaignlib.npc import normalize_vtt_speakers
from pathlib import Path
sm = speaker_map(load_players_config(Path('config/players.yaml')),
                 load_party_config(Path('config/party.yaml')))
out = normalize_vtt_speakers(Path('<vtt>').read_text(), sm).splitlines()
print('speaker_map:', sm)
print('GM lines:', sum(1 for l in out if l.startswith('GM:')))
print('UNREWRITTEN:', sum(1 for l in out if l.startswith(tuple(<every display name from step 2>))))"
```

`normalize_vtt_speakers` now takes `(vtt_text, speaker_map)` — the three-argument form with a separate `gm_player` is gone, and so is the flag that fed it.

`UNREWRITTEN` must be 0. If it isn't, a label from step 2 is missing from `players.yaml` — add it there and re-check, rather than reaching for `--allow-speaker-mismatch`.

### 6. Human checkpoint: choose the attribution strategy

**Do not skip this and do not pick for the user.** When one person voices several characters, no deterministic rewrite is correct, and there is no flag that expresses it — `--party` maps one player to exactly one character, and the system prompt's `Character (Player)` rule *strips* the parenthetical rather than preserving it.

Present the two real options with their failure modes, via AskUserQuestion:

- **Rewrite, review after** — labels resolve to `GM` and the primary PCs. Correct for GM narration, NPC voices, and each player's own PC, which is the bulk of any transcript. Voiced-sidekick lines land on the wrong speaker and *must* be caught downstream.
- **No rewrite, assign by hand** — drop `--party`/`--party-config`/`--players-config`, pass `--allow-speaker-mismatch`. Nothing is silently wrong; every quote needs a human ruling, and GM narration loses its `GM` label too.

Recommend the first for tables where the GM narrates sidekick actions in third person most of the time (the usual case), but say plainly that it creates reviewable debt. Record the choice.

### 7. Run

```bash
/home/kroussos/.venvs/main/bin/scene_extract <vtt> \
  --summary <session-dir>/session-summary.md \
  --output-dir <session-dir>/scene_extractions \
  --backend claude-code \
  --party docs/party.md \
  --party-config config/party.yaml \
  --players-config config/players.yaml \
  --max-tokens 32000 \
  --force
```

- `--backend claude-code` routes through `claude -p` headless and **strips `ANTHROPIC_API_KEY`** so billing lands on the subscription (`campaignlib/api/backends.py:338`). Without it the run falls through to the metered API whenever that key is set. `--batch` is Anthropic-only and fails fast here.
- **`--max-tokens 32000`, not the 8192 default.** At 8192 scenes silently lose content and continuation seams collide mid-heading. Observed: a scene truncated from 264 to 205 lines, and a heading emitted as `**[The Cellar — Read**[The Cellar — Read-Aloud Description]**`.
- `--force` snapshots each prior file to `<name>.md.prev` when content differs — keep those for diffing.
- Run it in the background. Python block-buffers stdout when it is not a tty, so the log stays empty until exit; watch the output directory (or `.prev` files on a re-run) for progress instead of tailing the log.

### 8. Verify the output — do not trust the banner

The `WARNING: claude -p hit its output ceiling` banner fires on `num_assistant_events > 1` (`campaignlib/api/backends.py:439`). That is a turn-count heuristic, **not** ceiling detection: it appears on essentially every scene even at 32k, where a 13 KB output is nowhere near the limit. Ignore the banner and check the artifacts.

```bash
python - <<'PY'
import glob, collections, re, os
D = "<session-dir>/scene_extractions"
# Every character name the extractor may emit, plus GM. From the step-3 voicing
# map — include short AND full forms (e.g. "Zenvon", "Zenvon Foreput").
SPEAKERS = ["GM", "<character>", "<character short form>"]
files = sorted(f for f in glob.glob(os.path.join(D, "*.md")) if not f.endswith(".prev"))
print(f"{len(files)} scene file(s)\n")
for f in files:
    lines = [l.rstrip() for l in open(f) if l.strip()]
    t = open(f).read()
    # Speaker labels only. `**[Scene Tag]**` action beats are structurally
    # identical to a bare `**GM**` label, so they CANNOT be told apart by shape —
    # match against the known speaker names from step 3 instead.
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

- **Do not flag a final line as truncated just because it lacks terminal punctuation.** Speakers trail off constantly; `...would start attacking them, right"` is a complete quote block. Confirm real truncation by diffing against `.md.prev` or checking whether the line ends mid-word.
- **Label format varies per scene and per run.** Expect a mix of `**GM**` / `**[GM]**` and full vs. short character names (`**Zenvon Foreput**` vs `**Zenvon**`) across files. This is model variance, unrelated to `max_tokens` — it will not re-run away. Report it so downstream parsing handles all shapes.
- **Cross-scene duplicate quotes are partly inherent.** Adjacent scenes share boundary moments, so the same exchange is extracted twice. Report the count; only investigate if it spikes.

### 9. Build and hand over the attribution queue

This is the deliverable, and the reason step 6 was a checkpoint rather than a default.

```bash
python - <<'PY'
import glob, re, os
D = "<session-dir>/scene_extractions"
tot = 0
for f in sorted(x for x in glob.glob(os.path.join(D, "*.md")) if not x.endswith(".prev")):
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

This works because the extractor annotates the context field (`**GM** — *voicing Sister Maela*`) rather than silently absorbing the line. Split the queue for the user:

- **Label is correct** — the GM narrating a sidekick in third person (`*narrating Pip's turn*`). `GM` is the right speaker; leave it.
- **Label is wrong** — the GM or a player voicing a sidekick in first person (`*voicing Sister Maela*` → `"I think we should help the helpless"`). These corrupt POV narration and must be fixed.

Present the queue with `file:line` for each entry. Then stop:

> Attribution queue ready — N blocks. Fix these before `/voice-smooth`, or run `/session-summary-consistency` first to catch quote-level transcription errors in the same pass.

**Do not auto-advance to `/voice-smooth` or `/fable-narration`.** A misattributed line that survives this queue gets baked into the wrong narrator's POV, and no later stage checks speaker identity.

## Notes

- Working directory drifts after any `cd` in a Bash call. Use absolute paths in the verification scripts — a glob that silently matches nothing reports `TOTAL: 0`, which reads exactly like "no problems found."
- If the pre-flight aborts with `speaker-mismatch`, the message blames a wrong/stale VTT. That is one cause; a display name missing from `players.yaml` is at least as likely, and a label your step-2 survey never saw is likelier still. Check steps 2, 4 and 5 before concluding the recording is wrong.
- Scale `--max-tokens` up, never down. The cost is on the subscription and a re-run is cheap; silent content loss is not recoverable without noticing it first.
- Related: `/gmassist-precheck` runs before this (validates the scene structure), `/session-summary-consistency` and `/voice-smooth` run after.
