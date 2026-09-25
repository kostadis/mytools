# Transcript provenance and input preparation

Read before joining speaker turns to a transcript. **A filename is an
assertion, not evidence.** Filenames, adjacent files, and high text overlap
cannot alone prove a recording match. This is the step that bites; never skip
it.

Commands below use `$SKILL_DIR` for the skill's scripts directory and `$RUN`
for the run's scratch directory; SKILL.md says how each is resolved.

## Is this the right task?

This skill and `transcript-rebuild` (a transcript alignment/rebuild task)
assume opposite things:

| | transcript rebuild | **speaker attribution** |
|---|---|---|
| Zoom's speaker labels | ~93% correct, keep them | **zero information** in the shared-microphone case — one name on every cue; or real names that are a voice-profile guess known to be wrong |
| Diarization | second opinion, breaks ties | **the only acoustic signal** |
| The hard part | aligning labels onto real cue boundaries | **finding out who anyone is** |

If the transcripts carry reliable per-speaker names and the only problem is
that they sit on the wrong timeline, stop: that is a rebuild task. Do not redo
identity attribution to fix a timeline.

This skill covers two cases. **Naming:** everyone shared one microphone, so the
transcript has no usable names (Zoom labelled all 866 cues of one session with
the host's name, and the editor produced six anonymous clusters for three
people). **Auditing:** the second clustering already carries real names from
voice profiles, and the GM says they are wrong; the job is auditing that
name→voice mapping (see identity-review.md).

Zoom's labels can be useful if they actually distinguish participants. In the
shared-microphone case one host label carries no speaker information: take
timings and text from the best ASR, and take nothing from Zoom there but the
fact of the recording.

**No audio and no saved acoustic turns means stop, not guess.** A speakerless
VTT and a summary cannot identify voices. Report the specific missing input;
text-only inference is the separate `speaker-attribution-text` workflow, whose
every label is marked as an inference.

## Fingerprints

```bash
python3 "$SKILL_DIR/transcript_provenance.py" "$SESSION_DIR"
```

Widen to adjacent session directories (or a whole `summaries/` tree) when a
match is unclear. The script fingerprints every transcript by 4-gram set
overlap, `|A∩B| / min(|A|,|B|)`. It compares text; it does **not** listen to
audio or prove a filename's claim. Two ASR passes over the same audio disagree
on fillers and proper nouns everywhere, so this never nears 100%, but the
separation has been an order of magnitude and has never been ambiguous:

| | overlap |
|---|---|
| same audio, Zoom ASR vs Descript ASR | 49.9% |
| same audio, Zoom ASR vs Whisper | 61.4% |
| **different sessions**, same campaign, same players, same NPC names | **0.8 – 3.0%** |

The defaults use 25% (`--same`) for a likely match and 5% (`--noise`) as the
noise floor. These are historical separations, not guarantees; investigate an
ambiguous result rather than rounding it to a verdict.

The scanner requires at least 500 tokens per text and 20 speaker-marked blocks
for Markdown/text; VTT needs no speaker labels. A short transcript can be
skipped. Lower `--min-tokens` when appropriate, but do not misrepresent the
weaker sample. `--include-prose` admits summaries and is usually
inappropriate: **keep summaries out of the second-transcript inventory.** Fewer
than two qualifying texts returns an insufficient-comparison message.

It is a set comparison, so it is order-independent: an offset, a truncated
tail, or a concatenation cannot fake a match or hide one. For the same reason
it says nothing about chronology; inspect timing and partial matches too.

It reports three things that matter:

- **MISFILED** — one recording's transcripts spread across directories.
- **SPANS MULTIPLE RECORDINGS** — a whole-day transcript that is two
  back-to-back recordings concatenated. It matches both halves while the halves
  match each other at the noise floor.
- **sits beside audio it does NOT transcribe** — the genuinely dangerous one.
  It reads as a matched pair to every human and every downstream tool.

*Evidence — the Hillsfar misfiling.* On the real Hillsfar tree this found a
July 27 transcript filed under Aug 8 with a `session_20260808_` prefix.
Diarizing the Aug 8 audio and joining it to that file would have produced 1145
confidently-labelled cues, every one wrong, with no error anywhere. The best
text for the Aug 8 recording turned out to live in a third directory: a
whole-day file under Aug 10.

**GM checkpoint:** show the GM each specific suspected misfiling and ask what
moves where. Do not relocate files on your own reading.

## Whole-day transcripts and `--limit-seconds`

A whole-day transcript breaks two things at once. It defeats transitive
grouping in provenance (it matches two recordings that do not match each
other), and it silently mis-joins later: afternoon cues get joined against
morning diarization turns. Detect it here.

`diarize_label.py --limit-seconds` only keeps cues **starting before a cutoff on
the same timeline**. It is a prefix cut, not an offset: it fixes a
concatenation only when this recording is the first part of the file. When the
recording is a later part, the text must be sliced and retimed first, and that
slicing verified separately, before any join. `descript_turns.py
--audio-duration` supplies metadata; it does not slice a whole-day export.

## Endpoint checks and the vouching rule

Confirm a candidate match by hand: the two files should open and close on the
same words **within a second or two**, and the text's last cue should sit near
the audio's duration. Duration alone does not verify words.

The script's audio-vouching heuristic is per group and works by **filename
stem**: some member of the group has to be named after the `.m4a`. A session
whose transcripts are all named something else (`Chapter 08.md`,
`descript_transcript.md`, `session_<date>_transcript.vtt` beside
`GMT<date>_Recording.m4a`) has nothing to vouch it, so every transcript gets the
warning at once. **One stray transcript among matched pairs is the real signal;
a clean sweep of a whole directory is the absence of a stem match**, not proof
of misfiling. Settle it by endpoints and move on; there is no need to ask the
GM to rename a sound file because the heuristic lacked a stem match.

*Evidence — a clean sweep settled by endpoints:*

| | ends |
|---|---|
| `GMT20250813-040058_Recording.m4a` (mvhd) | 01:38:02.8 |
| `session_20250812_transcript.vtt` last cue | 01:38:01.1 |
| `descript_transcript.md` last word | 01:38:02 |

### Audio duration without `ffprobe`

A missing `ffprobe` is not a blocker: read the MP4 `mvhd` atom. **Account for
the atom version.** Version 0 stores creation time, modification time,
timescale and duration as four big-endian u32; version 1 stores the two times
and the duration as u64 (timescale stays u32), so a fixed-offset u32 read is
wrong for version-1 files.

```python
import struct, sys

def atoms(f, start, end):
    pos = start
    while pos + 8 <= end:
        f.seek(pos); size, kind = struct.unpack(">I4s", f.read(8)); hdr = 8
        if size == 1: size = struct.unpack(">Q", f.read(8))[0]; hdr = 16
        elif size == 0: size = end - pos
        yield kind, pos + hdr, pos + size
        pos += size

with open(sys.argv[1], "rb") as f:
    f.seek(0, 2); n = f.tell()
    moov = next((a, b) for k, a, b in atoms(f, 0, n) if k == b"moov")
    body = next(a for k, a, b in atoms(f, *moov) if k == b"mvhd")
    f.seek(body); version = f.read(4)[0]
    if version == 1: _, _, scale, dur = struct.unpack(">QQIQ", f.read(28))
    else:            _, _, scale, dur = struct.unpack(">IIII", f.read(16))
    print(f"{dur / scale:.1f} s")
```

## Independent evidence versus derivatives

The 4-gram grouping says two files describe the same audio. It does **not** say
whether one was *derived from* the other, and a derivative is worth nothing as
a second opinion: it carries the parent's every attribution error by
construction. A cleaned transcript, Markdown conversion, chapter summary, or
renamed export is not independent corroboration of its source. Compare
transformation history, line structure, timestamps, errors, and speaker
tallies. "Cross-validated against a second clustering" is a false claim when
the second clustering is the first one.

The overlap score is not the tell; timestamp stripping depresses it
misleadingly. Compare per-file speaker tallies:

```bash
for f in *.md; do echo "== $f"; grep -oP '^\**\K[a-z]+(?=:)' "$f" | sort | uniq -c | sort -rn; done
```

**Identical tallies are a STRONG CLUE of a derivative, not proof.** Independent
ASR passes have never been seen to agree on turn counts to the digit. State the
clue, its strength and the incident below, and ask the GM before treating a
file as a copy. Never discard a transcript on this clue alone.

*Evidence — Phandalin ch08.* A directory held what looked like three
transcripts. `Chapter 08.cleaned.md` and `Chapter 08.md` were
`descript_transcript.md` with the inline per-word timestamps stripped and a
spell-pass applied: two real text layers, not four. The overlap score misled
(69% against its own parent, *lower* than the 98% between the two siblings).
The tallies did not:

```
kostadis 466   dave 466   wade 323   gary 202      <- all three files, exactly
```

Inventory separately:

- acoustic clustering/turn sources and their origin;
- text/timing sources;
- derivative cleanup layers;
- chat sidecars such as `GMT<date>_RecordingnewChat.txt`.

Do not count the same Descript clustering twice because it has both JSON and
Markdown exports. A named voice-profile export is a proposal, not verified
identity; it still needs identity review.

## Choosing the text layer

Three transcripts of one recording are normal, and the best text is rarely the
one named after the session:

```
GMT<date>_Recording.transcript.vtt   Zoom ASR    real timeline, mangled text
GMT<date>_Recording.md/.txt          Descript    real timeline, decent text, anonymous clusters
session_<date>_transcript.vtt        Whisper     real timeline, best text, NO speakers
```

Take timings and text from the best ASR. Quality is visible at a glance: Zoom
rendered `Lodge of Faces` as *"the best answer for why"* and `Szith Morcane` not
at all.

## Descript conversion

Descript is the second clustering, and the only one here that picks its **own**
speaker count, so it is the only tool that can reveal a voice nobody budgeted
for. Its `.txt` export matches no input format of the join, and a per-word
timestamp stream runs through the body:

```text
[00:17:16] Speaker 2: You're gonna be [00:17:17] there for two weeks?
```

Convert once, up front:

```bash
python3 "$SKILL_DIR/descript_turns.py" \
  --input "$DESCRIPT_EXPORT" \
  --md "$RUN/descript.md" --turns "$RUN/descript_turns.json" \
  --audio-duration "$AUDIO_SECONDS"
```

The helper accepts plain and Markdown-bold speaker labels, including
`[00:17:16] **Nikhil:** ...`, so no `sed` pre-step is needed. (An older helper
parsed `**dave` as the label and left `**` on the text without erroring.)
Confirm the reported label inventory has actual names or cluster IDs, without
stray `**` or colons, before going on.

- `--md` emits `[timestamp] **Speaker:** text`. Keep it for quotes and auditing.
- `--turns` emits an envelope with `turns`, `audio_duration`, `model`,
  `num_speakers_requested`, and `device_used`; each turn carries `start`,
  `end`, and `speaker`. Pass **this JSON** to `diarize_label.py --md`, despite
  that option's name (acoustic-workflow.md has the numbers).
- The JSON also lets **Descript stand in as the primary clustering when no GPU
  is free.** Both Sparks running one tensor-parallel vLLM leave ~4 GB of 121 GB,
  and pyannote OOMs on the model load. Descript as primary leaves no
  independent second source; see the single-source rule in SKILL.md.

**Starts are anchored on words, not on the block header.** A header stamp is
when the block begins, and leading silence is timestamped too. *Evidence:* the
opening block of one session was headed `00:00:00` while its first word landed
at `00:16:16`; 24% of blocks in that file needed the correction, and the worst
offender was the greeting that named a player. Ends are estimated from the last
word stamp plus one second: better than starts-only joins, but not exact
word-level timing. Inspect unexpected gaps and boundary disagreements before
assigning names.

The converter reports cluster shares and tags clusters under 3% of words for
inspection. Read their lines before dismissing them: they can be a GM's NPC
voice, crosstalk, or a real person in the room (acoustic-workflow.md, the
coffee-room voice). Size alone neither creates nor removes a participant.

## Chat sidecars

While inventorying, note whether `GMT<date>_RecordingnewChat.txt` exists. It is
not a text layer and is usually one or two lines, but it is the only place in a
session where a **real name** is attached to a **timestamp** by the person
themselves. It is small and easy to miss; check the directory (and its history)
for it now, and keep it for identity review (identity-review.md, the chat
sidecar).
