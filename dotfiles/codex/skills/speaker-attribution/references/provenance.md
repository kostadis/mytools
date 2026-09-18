# Transcript provenance and input preparation

Read before joining speaker turns to a transcript. Filenames, adjacent files,
and high text overlap cannot alone prove a recording match.

## Fingerprints and endpoint checks

`transcript_provenance.py` compares four-gram sets with
`|A intersection B| / min(|A|, |B|)`. Historical examples: independent ASR for
the same audio scored 49.9–61.4%; different sessions in one campaign scored
0.8–3.0%. The defaults use 25% for a likely match and 5% as the noise floor.
Investigate ambiguous results rather than treating thresholds as guarantees.

The scanner defaults to at least 500 tokens per text and 20 speaker-marked
blocks for Markdown/text; VTT needs no speaker labels. A short transcript can
be skipped. Lower `--min-tokens` when appropriate, but do not misrepresent the
weaker sample. `--include-prose` admits summaries and is usually inappropriate.
Fewer than two qualifying texts returns an insufficient-comparison message.

Reports include groups spread across directories and concatenations matching
two recordings whose individual transcripts do not match each other. Set
overlap is independent of order, so also inspect chronology and partial matches.
Do not join afternoon cues to morning audio. `--limit-seconds` only selects cues
starting before a cutoff on the same timeline; it does not subtract an offset.

The helper's audio-vouching heuristic uses filename stems. If **every** text in
a directory gets an audio-mismatch warning, there may simply be no stem match
between `session_<date>_transcript.vtt` and `GMT<date>_Recording.m4a`. Its warning
is not proof that the text describes another recording. Confirm opening and
closing words against the actual audio and check duration. If `ffprobe` is
unavailable, an M4A/MP4 `mvhd` atom can supply duration; account for the atom
version before interpreting integer widths. Duration does not verify words.

Show the GM specific suspected misfilings before moving files. Resolving an
endpoint match does not require asking the GM to rename a sound file merely
because the automated heuristic lacked a stem match.

## Independent evidence versus derivatives

A cleaned transcript, Markdown conversion, chapter summary, or renamed export
is not independent corroboration of its source. Compare transformation history,
line structure, timestamps, errors, and speaker tallies. Identical tallies are
a strong derivative clue, not mathematical proof. Timestamp stripping can make
siblings score higher against each other than against their common parent.

Inventory separately:

- acoustic clustering/turn sources and their origin;
- text/timing sources;
- derivative cleanup layers;
- chat sidecars such as `GMT<date>_RecordingnewChat.txt`.

Do not count the same Descript clustering twice because it has both JSON and
Markdown exports. A named voice-profile export still needs identity review.
Zoom's labels can be useful if they actually distinguish participants; in the
shared-microphone case, one host label carries no speaker information.

## Descript conversion

Use `descript_turns.py` on a timestamped export with blocks like:

```text
[00:17:16] Speaker 2: You're gonna be [00:17:17] there for two weeks?
```

The Codex helper accepts plain and Markdown-bold speaker labels, including
`[00:17:16] **Nikhil:** ...`. Confirm the reported inventory has actual names
or cluster IDs, without stray `**` or colons.

```bash
python3 "$SKILL_DIR/descript_turns.py" \
  --input "$DESCRIPT_EXPORT" \
  --md "$RUN/descript.md" --turns "$RUN/descript_turns.json" \
  --audio-duration "$AUDIO_SECONDS"
```

The converter anchors starts on timestamped words rather than block headers:
leading silence can otherwise shift an utterance by minutes. Ends are estimated
from the last word stamp plus one second; they are more useful than starts-only
joins, but not exact word-level timing. Inspect unexpected gaps and boundary
disagreements before assigning names.

`--md` emits `[timestamp] **Speaker:** text`. `--turns` emits an envelope with
`turns`, `audio_duration`, `model`, `num_speakers_requested`, and `device_used`.
Each turn carries `start`, `end`, and `speaker`. Use the **JSON** as the second
source to `diarize_label.py --md`, despite that option's name. Retain the converted
Markdown separately for quotes and auditing. `--audio-duration` supplies metadata;
it does not slice a whole-day text export.

Read clusters below the 3% word-share threshold. They can be a GM's NPC voice,
crosstalk, or a real person in the room. Size alone neither creates nor removes
a participant. A voice-profile name is also a proposal, not verified identity.
