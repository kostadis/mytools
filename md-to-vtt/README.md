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

**Timestamps are synthetic.** The markdown carries no timing, so cue times are
monotonic and proportional to utterance length. Nothing downstream reads them
(`parse_vtt` discards them), and the file's NOTE header says so.

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
