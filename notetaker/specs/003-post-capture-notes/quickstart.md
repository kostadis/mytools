# Quickstart — Post-Capture Notes

**Feature**: 003-post-capture-notes
**Audience**: a user with a notetaker installation who has already
captured a meeting recording and now wants polished Markdown notes.

---

## Prerequisites

1. A completed notetaker run for the recording, at minimum through the
   `understand` stage. You should see a populated
   `~/.local/share/notetaker/cache/<url-hash>/understanding/slide_content.json`.
2. The Anthropic SDK environment configured exactly as for the existing
   pipeline (`ANTHROPIC_API_KEY` exported).
3. Python venv with the project installed in editable or wheel form
   (`pip install -e .`).

---

## Step 1 — Get the transcript

The supported path is the post-capture browser snippet, because the live
in-pipeline transcript scrape is brittle (see spec FR-015).

1. Open the Zoom Cloud Recording in Chrome.
2. Open the recording's right-hand panel and switch it to **Audio
   Transcript**.
3. Right-click any utterance → **Inspect** (Chrome DevTools opens with
   that node selected).
4. In DevTools → **Console**, paste the contents of `mytools/scrape.js`
   from the user's `mytools` repository and press Enter. A red-bordered
   textarea appears at the top-left of the page containing the harvested
   transcript.
5. Paste `mytools/download.js` into the same console; this triggers a
   normal browser download of `zoom_chat.txt`.

You now have a transcript file you can hand to notetaker. Two alternatives
also work and require no copy-paste:

- If Zoom Cloud Recording offers a **Download → Audio Transcript** link
  for this recording, take that VTT file directly.
- If your previous notetaker run *did* successfully capture the live
  transcript (i.e., the cache contains a non-empty `transcript.json`),
  skip the file argument and the command will use the cached one.

---

## Step 2 — Produce the notes

With the recording URL or cache id in hand:

```bash
notetaker notes <recording-url-or-cache-id> path/to/zoom_chat.txt
```

What happens:

1. The command resolves the recording argument to its cache directory
   (same convention used elsewhere in notetaker).
2. The transcript file is sniffed (block format / VTT / `transcript.json`)
   and parsed into the canonical `TranscriptSchema`.
3. The slide content (`slide_content.json` from the understanding stage)
   and the parsed transcript are concatenated into
   `<cache>/<hash>/notes/working_doc.md` — deterministic, byte-stable.
4. Exactly one LLM render call runs against the working doc. On transient
   failure the command retries per the existing `[api]` policy.
5. On success, `<cache>/<hash>/notes/notes.md` is written and its absolute
   path is printed.

Console output on success looks like (after the standard `[notetaker] Logging to …` line and the structured-log records):

```text
working_doc: /home/<user>/.local/share/notetaker/cache/<hash>/notes/working_doc.md  (129,065 bytes)
input_tokens=35,014  output_tokens=4,171  cost=$0.1676
notes: /home/<user>/.local/share/notetaker/cache/<hash>/notes/notes.md
```

Format detection, slide/utterance counts, and per-attempt timing are emitted
as structured records to the run log file (and to stderr in console mode);
they are not duplicated to stdout, which carries only the final summary.

Open the notes file:

```bash
$EDITOR ~/.local/share/notetaker/cache/<hash>/notes/notes.md
```

---

## Step 3 — Iterate cheaply (optional)

If the rendered notes are wrong in style or structure, tweak the prompt
or model in `config.toml` (`[notes] model`, `[notes] max_output_tokens`)
and re-render WITHOUT redoing assembly:

```bash
notetaker notes <recording-url-or-cache-id> --re-render --force
```

`--re-render` reads the existing `working_doc.md` and skips parsing /
assembly. `--force` is needed because by default the command refuses to
overwrite an existing `notes.md`.

To preview the projected cost without spending:

```bash
notetaker notes <recording-url-or-cache-id> path/to/zoom_chat.txt --dry-run
```

---

## Step 4 — Inspect what the LLM saw

The working doc is the deterministic input to the render call and is the
right artifact to consult when the rendered notes look wrong:

```bash
$EDITOR ~/.local/share/notetaker/cache/<hash>/notes/working_doc.md
```

If the working doc is wrong (slides missing, utterances merged), the bug
is in parsing/assembly, not in the LLM. If the working doc is right but
the notes are wrong, the bug is in the prompt or model and `--re-render`
is the cheap fix.

---

## Retention

Both `working_doc.md` and `notes.md` are retained for 365 days by default
(`[notes] retention_days = 365`), independent of the 30-day frame purge
governed by `[cache] retention_days`. Frames, slide content, and live
transcript artifacts continue to follow the existing 30-day policy.

To opt into indefinite retention for the notes artifacts only, set
`[notes] retention_days = 0` in your config.

---

## What this replaces

The existing `notetaker synthesise` stage (which produces `summary.md`)
remains in the codebase but is no longer the documented happy path. If
you have an existing `summary.md` from a prior run, it is unaffected by
this feature. New runs should prefer `notetaker notes`.
