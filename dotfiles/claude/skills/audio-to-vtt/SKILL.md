---
name: audio-to-vtt
description: Re-transcribe a D&D session's Zoom .m4a recording into a more accurate WebVTT, using the campaign's own proper-noun vocabulary while keeping Zoom's existing speaker/timing boundaries. Runs faster-whisper on the DGX Spark via ~/src/mytools/audio-to-vtt. Invoke as /audio-to-vtt [audio-path] [vtt-path].
tools: Bash, Glob, Read, AskUserQuestion
---

# audio-to-vtt

Drives `~/src/mytools/audio-to-vtt/retranscribe.py` through its
recommended dry-run -> smoke-test -> confirm -> full-run sequence, so the
user never has to remember the flags or babysit a multi-minute Spark job
without knowing how long it'll take first.

This skill is operational glue only. It does not reimplement any of the
tool's logic (VTT parsing, vocabulary gathering, Spark orchestration,
glossary pass) — read `~/src/mytools/audio-to-vtt/README.md` and
`CLAUDE.md` if you need the design rationale or Spark-side setup/build
details. This skill assumes the Spark side is already set up (see that
README's "Setup" section) — it does not perform first-time Spark
bootstrap.

## Phase 1 — locate the audio/VTT pair

From `$ARGUMENTS`:

- Two paths given -> use them directly as `<audio>` `<vtt>`.
- Nothing given -> glob the current directory (and `summaries/*/` one
  level down, if present) for `*.m4a` files. For each candidate, look for
  a sibling `*.transcript.vtt` (same stem, or the most recently modified
  `.vtt` in the same directory if the stem doesn't match exactly — Zoom's
  own export naming isn't always identical between the audio and caption
  files). If more than one plausible pair exists, list them and ask which
  one via AskUserQuestion rather than guessing.

Do not pass `--campaign-root` unless the files sit outside a campaign
checkout (auto-detection walks up from `<vtt>` looking for
`docs/entity_registry.yaml` or `notes/vtt_transcription_corrections.md`,
and works for the normal `<campaign>/summaries/<date>/` layout).

## Phase 2 — dry run

```bash
python ~/src/mytools/audio-to-vtt/retranscribe.py <audio> <vtt> --dry-run
```

Show the user the cue-group count and vocabulary-candidate count/preview
from the output. This step never touches the Spark — it's a fast sanity
check that the VTT parsed correctly and a campaign root was found.

## Phase 3 — smoke test

```bash
python ~/src/mytools/audio-to-vtt/retranscribe.py <audio> <vtt> --smoke-test < /dev/null
```

Redirect stdin from `/dev/null` (or otherwise ensure no interactive input
is available) — the script's own "Continue with the full session? [y/N]"
prompt is meant for a human at a real terminal, not this skill; it
defaults to "no" on EOF and simply stops after printing the measurement.
That's what you want here: read the printed `device_used` and `RTF`, and
the extrapolated full-session estimate, from its output.

## Phase 4 — confirm with the user

Use AskUserQuestion with the real numbers from Phase 3, e.g.:

> "Smoke test measured RTF X (device: cuda/cpu). Full session (~N min of
> audio) is estimated at ~M minutes. Run the full transcription now?"

Options: proceed now / not right now. Do not proceed without an explicit
yes — a smoke-test estimate is informative, not a green light on its own,
and full runs can take anywhere from a few minutes to hours depending on
whether GPU is actually engaging (see CLAUDE.md's hardware notes for why
that isn't guaranteed on every box).

## Phase 5 — full run

If confirmed:

```bash
python ~/src/mytools/audio-to-vtt/retranscribe.py <audio> <vtt>
```

This can run for a while on a long session — prefer `run_in_background`
if your environment supports it, and report back when it completes rather
than blocking silently. Report the two output paths it prints
(`<stem>.retranscribed.vtt` and `<stem>.retranscribed.cleaned.vtt`) and
the glossary replacement count.

## Phase 6 — next step

Always end by telling the user to run:

```
/vtt-spell-pass <stem>.retranscribed.cleaned.vtt
```

so any new unknown proper nouns the re-transcription introduced (or
didn't fully fix) go through that skill's human-confirmation loop. Do not
invoke `/vtt-spell-pass` automatically — it's a separate, interactive,
per-cluster confirmation flow the user should run deliberately.
