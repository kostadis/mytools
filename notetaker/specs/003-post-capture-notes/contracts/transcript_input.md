# Contract — Transcript Input File

**Feature**: 003-post-capture-notes
**Consumed by**: `parse_transcript_file()` in
`src/notetaker/stages/capture/adapters/zoom_transcript_parsers.py`
**Produces**: `TranscriptSchema` (existing,
`src/notetaker/contracts/transcript.py`)

The dispatcher accepts exactly three input shapes. Format is detected from
file content; extension is a tiebreaker only.

---

## Shape A — Browser-scrape block format

Produced by the documented post-capture browser snippet (originally
`mytools/scrape.js`). Plain text.

**Block separator**: `\n\n----\n\n` (two newlines, four hyphens, two
newlines).

**New-speaker block (3 or more lines)**:

```text
<Speaker name>
<HH:MM:SS>  or  <MM:SS>
<utterance text, may span multiple lines>
```

The Zoom Audio Transcript panel shows `MM:SS` for recordings shorter than
one hour and `HH:MM:SS` for longer ones; the documented scrape snippet
harvests whatever the panel shows, so both shapes are accepted. `MM:SS` is
interpreted as `0:MM:SS`.

The third line and any subsequent lines (up to the next `\n\n----\n\n`) are
all part of the utterance text.

**Continuation block (single line)**:

```text
<utterance text>
```

A continuation block has no speaker line and no timestamp. It is attributed
to the most recent new-speaker block. Its `start_seconds` is the previous
new-speaker block's `start_seconds` (the format does not provide a finer
timestamp for continuations).

**End-of-file**: a trailing blank block or trailing whitespace is tolerated.

**Detection**: file contains the literal `\n\n----\n\n` separator OR the
first non-blank line is followed by a line matching
`^(?:\d{1,2}:)?\d{1,2}:\d{2}$` (accepts both `HH:MM:SS` and `MM:SS`).

**Mapping to `Utterance`**:
- `start_seconds` ← `HH:MM:SS` parsed to seconds (continuation blocks
  inherit).
- `end_seconds` ← `start_seconds + 5.0` (heuristic; no end time available).
- `speaker` ← speaker name (continuation blocks inherit).
- `text` ← block body, stripped.

---

## Shape B — WebVTT (`.vtt`)

Zoom Cloud Recording's downloadable transcript format. Subset of W3C
WebVTT.

**File header**:

```text
WEBVTT
```

(possibly followed by a blank line and metadata lines; ignored).

**Cue**:

```text
[<cue-id>]
HH:MM:SS.mmm --> HH:MM:SS.mmm
<v Speaker Name>cue text
```

The `<v ...>` voice span is optional. When present, the speaker label is
extracted; when absent, `speaker = "Unknown"` (FR-004 explicit behaviour).
A cue payload may span multiple lines until the next blank line.

**Detection**: first non-blank line begins with `WEBVTT` (case-sensitive,
per the WebVTT spec).

**Mapping to `Utterance`**:
- `start_seconds` ← cue start time, converted to fractional seconds.
- `end_seconds` ← cue end time, converted to fractional seconds.
- `speaker` ← `<v ...>` content, or `"Unknown"`.
- `text` ← cue payload with the `<v ...>` span removed; whitespace
  collapsed; trailing newlines stripped.

---

## Shape C — Notetaker `transcript.json`

The exact format written by the existing live transcript scrape and
already validated by `TranscriptSchema`. No translation needed beyond
loading and schema validation.

**Detection**: file parses as JSON and the parsed object validates against
`TranscriptSchema`.

**Mapping to `Utterance`**: identity (it is already the schema).

---

## Refusal contract (FR-004a)

If none of the three detection rules match, the dispatcher raises an
exception whose message names all three supported shapes and points at the
HOWTO documentation. The CLI surface translates this into a non-zero exit
with the same message printed to stderr.

The error message format (must be stable for tests):

```text
Unsupported transcript format. Expected one of:
  - browser-scrape block format (.txt produced by the documented browser snippet)
  - WebVTT (.vtt downloaded from Zoom Cloud Recording)
  - notetaker transcript.json (produced by a successful live capture)

See HOWTO.md "Obtaining a transcript" for the supported procedures.
```

---

## Test coverage required

Unit tests in `tests/unit/test_zoom_transcript_parsers.py`:

1. Each of the three shapes parses to the same `TranscriptSchema` for the
   same logical content (parameterised over fixtures
   `transcript_block.txt`, `transcript.vtt`, `transcript.json`).
2. Block format: continuation blocks inherit speaker and timestamp.
3. WebVTT: cues without `<v ...>` get `speaker = "Unknown"`; cues with
   multi-line payloads concatenate correctly.
4. Detection precedence: a `.txt` file containing valid VTT content is
   detected as VTT (content-first sniffing).
5. Refusal: a file with random text raises with the documented message.
6. Trailing blank block / trailing whitespace tolerated for all shapes.
