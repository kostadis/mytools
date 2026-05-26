# How to use `transcript_to_mp3.py`

Convert a Zoom closed-caption transcript into a single MP3 with a different voice per speaker. Uses Microsoft's free `edge-tts` service — no API key, no ffmpeg.

## 1. Install

```bash
uv venv .venv
uv pip install --python .venv/bin/python edge-tts
```

That is the only dependency. Python 3.9+. (Plain `pip install edge-tts` works too on systems that aren't PEP 668-locked.)

## 2. Get a transcript

Two input formats parse natively — the script auto-detects which one you have.

**Zoom** (Save Closed Caption → `.txt`):

```
[Speaker Name] HH:MM:SS
What they said.

[Other Speaker] HH:MM:SS
What they said.
```

**Otter** (markdown export):

```
**Speaker Name**HH:MM:SS

What they said.

More of what they said.

**Other Speaker**HH:MM:SS

What they said.
```

Otter's blank-line-separated paragraphs within a single speaker turn are collapsed into one TTS line before synthesis.

## 3. Map speakers to voices

Edit `VOICE_MAP` at the top of `transcript_to_mp3.py`. Keys must match the speaker name *exactly* as it appears in the transcript (the bit between `[ ]` for Zoom, or between `** **` for Otter).

```python
VOICE_MAP = {
    "Kostadis Roussos":  "en-US-GuyNeural",
    "Dimos Stathakis":   "en-US-ChristopherNeural",
    "Nicholas Roussos":  "en-US-RogerNeural",
}
DEFAULT_VOICE = "en-US-GuyNeural"
```

Any speaker not in the map falls back to `DEFAULT_VOICE`.

To see every available voice:

```bash
.venv/bin/edge-tts --list-voices
```

Useful en-US voices: `GuyNeural`, `ChristopherNeural`, `RogerNeural`, `EricNeural`, `TonyNeural`, `BrianNeural` (male); `JennyNeural`, `AriaNeural`, `MichelleNeural`, `SaraNeural` (female).

## 4. Run

```bash
.venv/bin/python transcript_to_mp3.py <transcript> <output.mp3>
```

Example:

```bash
.venv/bin/python transcript_to_mp3.py meeting_saved_closed_caption.txt session.mp3
```

The transcript file can be `.txt` (Zoom) or `.md` (Otter) — same command either way.

You'll see per-utterance progress:

```
Parsing transcript: meeting_saved_closed_caption.txt
  342 utterances after grouping
  'Dimos Stathakis' → en-US-ChristopherNeural
  'Kostadis Roussos' → en-US-GuyNeural
  [1/342] Kostadis Roussos     'Hello!'...
  [2/342] Kostadis Roussos     'Let me get Nick.'...
  ...
Assembling 342 chunks → session.mp3
Done! session.mp3 (18.4 MB)
```

## 5. Caching and re-runs

Chunks are cached next to the output in `<output>.chunks/` along with a `manifest.json` keyed by `voice|text`.

- **Re-running with the same inputs** → all chunks served from cache, only the assemble step runs.
- **Changed `VOICE_MAP`** → only chunks for affected speakers are regenerated.
- **Edited transcript** → only changed utterances are regenerated.
- **TTS failures** are retried with exponential backoff. If a chunk still fails, it's skipped and *not* cached, so the next run will retry it. The final message reports how many were skipped.

To force a full rebuild, delete the `.chunks/` directory.

## 6. Notes and gotchas

- **Consecutive utterances from the same speaker are merged** before synthesis, so the voice doesn't restart mid-thought.
- **~400ms of silence** is inserted between utterances (16 silent MP3 frames concatenated raw — that's why no ffmpeg is needed).
- **Speaker-name matching is exact and case-sensitive.** If Zoom logged someone as `"Nick Roussos"` in one block and `"Nicholas Roussos"` in another, they'll get different voices unless both are in `VOICE_MAP`.
- **No rate limiting beyond a 100ms sleep** between calls. Long transcripts (thousands of utterances) work fine but take a while on first run; cached re-runs are near-instant.
- **The output MP3 is a concatenation of per-chunk MP3 streams.** Most players handle this without complaint; some strict tools may want a `ffmpeg -i input.mp3 -c copy output.mp3` re-mux.
