# md-to-vtt

Convert a **speaker-labelled Zoom markdown transcript** into WebVTT so
CampaignGenerator's session-doc pipeline can read it.

```bash
python md_transcript_to_vtt.py \
  "summaries/20250528-chapter-03-new/GMT20250528-035553_Recording (1).cleaned.dedup.md" \
  "summaries/20250528-chapter-03-new/session_20250528_transcript.speakers.vtt"
```

No dependencies beyond the standard library.

## Why this exists

Old session directories hold two kinds of transcript:

| File | Speaker labels | Timing |
|---|---|---|
| `GMT*.md` (Zoom export) | **yes** — `**kostadis:**`, `**dave:**`, … | no |
| `session_*.vtt` (whisper/`audio-to-vtt`) | **no** | yes |

CampaignGenerator's Stage 1/2 (`enhance_summary`, `scene_extract`) only read
`*.vtt`. So the file with the attribution was invisible to the pipeline, and the
file the pipeline used couldn't say who was talking — every quote had to be
attributed by inference. This script closes that gap.

The Session Doc Editor resolves the transcript as
`sorted(session_dir.glob("*.vtt"))[0]` (`server/routers/scene_editor.py:_vtt_path`),
so **a stale unlabelled VTT silently wins**. After converting, rename the
unlabelled siblings out of the glob:

```bash
mv session_20250528_transcript.cleaned.vtt \
   session_20250528_transcript.cleaned.vtt.unused-no-speakers
```

## Two input shapes

| Markdown line | Cue timing |
|---|---|
| `**kostadis:** text` | **synthetic** — monotonic, proportional to utterance length |
| `[01:30:40] **kostadis:** text` | **real** — the source's own stamps, one-second resolution |

The timestamped shape (Zoom's newer export, and MacWhisper's) gives a start and
no end, so ends are derived: each cue runs for its estimated spoken length,
clipped at the next cue's start, and never stretched across a silence.
Utterances that share a second — Zoom emits runs of them — split that second
between them in proportion to their text, so cues stay ordered and never
overlap. The NOTE header says which mode produced the file.

Bare `[HH:MM:SS]` markers *inside* a line are the exporter's minute ticks, not
speech. They are stripped. A line that is a timestamp with no `**speaker:**`
(the exporter drops one occasionally) is appended to the previous cue and
reported — same policy as a dangling continuation, for the same reason.

## Output shape

```
WEBVTT

NOTE Converted from the speaker-labelled Zoom transcript <source>.
...

1
00:00:00.000 --> 00:00:01.000
dave: Bye Dave
```

`session_doc.io.parse_vtt` strips the header, cue numbers, timestamps and NOTE
lines, so what actually reaches the model is `speaker: text` per line. That also
matches the `--party` speaker pre-flight, which tests
`line.startswith(f"{name}:")`.

`parse_vtt` discards timings entirely, so for the pipeline only the
`speaker: text` payload matters. The timings matter to `campaignlib.vtt` (the
lossless reader that keys corrections on cue index) and to anything that plays
the tape against audio.

## Gotchas learned the hard way

- **One-line `NOTE ...` comments, never a multi-line NOTE block.** `parse_vtt`
  drops only lines that *start* with `NOTE`; a block leaks its continuation
  lines straight into the model's dialogue.
- **Check the Zoom `.md` for a doubled transcript before converting.** Phandalin
  ch03's `.md` and `.cleaned.md` each contain the whole session *twice*; only
  `.cleaned.dedup.md` is single-copy. Feeding a doubled transcript wastes half
  the context window.
- **Dangling continuation lines** (a bare `because-` on its own line) are
  appended to the preceding speaker's cue and reported, never dropped or
  assigned a guessed speaker.
- **A display name the campaign does not know is silently unattributed.**
  `scene_extract` rewrites labels via `config/players.yaml` `display_names`,
  matching `line.startswith(f"{name}:")` — exact and case-sensitive. The
  pre-flight only fails when *zero* lines match, so a transcript labelling one
  person `Nikhil` (known) and the other `kostadis` (not — the config has
  `Kostadis Roussos`) passes the check with the GM's every line unattributed.
  Check the `Speaker map` line the run prints against the labels in the tape.
- **Unattributed speakers** (`**Speaker 7:**`) are passed through verbatim.
  Attribution is a precision decision — rule on it yourself, upstream.

## Downstream: running enhance_summary

```bash
cd <campaign-dir>
PYTHONUNBUFFERED=1 enhance_summary <dir>/session_<date>_transcript.speakers.vtt \
  --gmassist <dir>/gm-assist.md \
  --output   <dir>/session-summary.md \
  --max-tokens 30000 \
  --backend claude-code
```

- `PYTHONUNBUFFERED=1` — progress `print()`s lack `flush=True`, so redirected to
  a file they buffer and the run looks hung for minutes.
- `--max-tokens 30000` — the 16384 default makes `claude -p` hit its ceiling and
  **auto-continue across two assistant turns**, which risks a seam at the
  boundary *and* is slower (the second turn re-processes context). Measured on
  Phandalin ch03/ch04: 7m46s with a seam warning at 16384 vs 6m28s clean at
  30000. Sonnet-4-6 reports `maxOutputTokens: 32000`.
- The `claude-code` backend does **not** stream (`_ClaudeCodeStream` in
  `campaignlib/api/backends.py` runs `subprocess.run` to completion, then yields
  one chunk). Use `--backend anthropic` if you want token-by-token progress.
