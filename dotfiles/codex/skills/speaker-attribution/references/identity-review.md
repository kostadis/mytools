# Identity review

Read when acoustic clusters are ready for the GM to identify, when auditing
existing voice-profile names, and before writing the final result.

**Attribution is a scope-and-identity decision, so no model makes one here.**
Provenance is set arithmetic; diarization is an acoustic model with a known
failure mode and a guard against it; the join is deterministic, and its only
claim (*these two independent clusterings agree*) is a number anyone can check.
This step is an evidence table with the quotes attached, ranked but explicitly
undecided, handed to the person who was in the room. The deterministic tools
propose and count; the GM supplies identity decisions. A confident label on the
wrong voice is worse than no label, because nothing downstream re-checks
speaker identity: a name written here is inherited by every extraction, quote
and narration after it.

Commands below use `$SKILL_DIR` for the skill's scripts directory and `$RUN`
for the run's scratch directory; SKILL.md says how each is resolved.

## Inputs, not questions

Use the participants and player/character facts the GM has already given.
Count people, GM included. Do not ask again for facts already provided. A known
roster establishes the possible identities, not which cluster belongs to whom:
never equate a known PC owner with an acoustic cluster ID.

## Strong clues are put to the GM, never auto-decided

These signals have been right often enough to matter and wrong-shaped often
enough to need a person. For each, state the clue, its strength and the
incident behind it, then ask. Never auto-select a voice, discard a transcript
or re-cluster on one of these alone.

| clue | what it may mean | what else it may mean | incident |
|---|---|---|---|
| one cluster dominates speech (>70%) | collapsed clustering | a GM-heavy session | `3.1` at 84% (acoustic-workflow.md) |
| identical per-file turn tallies | one file derives from the other | a coincidence: never observed, but not excluded | Phandalin ch08 (provenance.md) |
| a cluster goes quiet across a typed chat absence | that cluster is the absent person | a quiet player who never left; a typed account label | Gary, Phandalin ch02 (below) |
| two PC names land on one cluster | one person ran both PCs that session | shared or per-scene control | Brewbarry/Valphine (below) |
| a voice-profile name is not on the roster, or a rostered player's profile is nearly empty | the profile is mislabelled and holds a real player | a genuine room voice | `<non-player>` = Mike, OOTA ch02 (below) |
| one cluster's lines use two PCs' abilities | two players merged in one cluster | one player covering another's PC | Zalthir's fire and Daz's Shape Water, OOTA ch02 (below) |

## Anonymous clusters

Diarization gives voices, never names. The names are in the text, because
people address each other:

```
[91:05] SPEAKER_02: Daein. Sorry. Felkur's not there, right?
[91:08] SPEAKER_00: Everyone's there.
```

`name_clusters.py` reads the scratch cluster-ID draft (never a file in the
session directory) and ranks each candidate by **who answers when the name is
spoken**, scoring mentions for vocative shape so GM narration ("Daein convinced
Korkan to lead a charge") does not drown the actual address. It reports; it
does not decide.

```bash
python3 "$SKILL_DIR/name_clusters.py" "$RUN/clusters.vtt" \
  --name Daein --name Felkur --name Bramgrim --name Akritas --name Nicholas
```

Use the actual session roster. Present cluster IDs, speech shares, candidate
names, reply counts, and representative exchanges with timestamps. The
highest-ranked bin is a proposal. Weak samples, third-person references and
`SPLIT` results stay unresolved. **A `SPLIT` is unresolved evidence; do not
select the largest bin.**

*Evidence — Felkur, Bramgrim, Akritas, Daein.* On the real session it produced:

- `Felkur → SPEAKER_00, 100% of 3 vocative answers`: correct.
- `Bramgrim → SPLIT` and `Akritas → SPLIT`: **correct, and the finding.** Those
  two PCs had no owner; they were reassigned per scene ("do you want to bring
  Bramgrim or Akritas?"). A name can map to a *scene*, not a person.
- `Daein → SPLIT, 50%`: the tool could not close it, and was right not to. The
  player's real name **is** Daein, so every narration mention looks like an
  address. A human closed it in one sentence.

That last case is the skill working, not failing.

**Name/PC collision.** Where a player's real name collides with their PC's,
label with the player's nickname and note why in the header.

### Probe with the names people actually say

The tool can only score names that get spoken. At a table that is usually **PC
names, not real ones**. *Evidence:* on Phandalin ch08 only one of four real first
names was ever used vocatively, while every PC name was. Run both passes and
weight the evidence by how much there is:

```bash
python3 "$SKILL_DIR/name_clusters.py" "$RUN/clusters.vtt" --name Dave --name Wade --name Gary --name Kostadis
python3 "$SKILL_DIR/name_clusters.py" "$RUN/clusters.vtt" --name Vukradin --name Soma --name Valphine --name Brewbarry
```

Expect the real-name pass to be nearly empty and the PC pass to carry the run.
Expect, too, that a player's **own** PC comes back `SPLIT`: nobody addresses him
by it, so every hit is third-person narration. That is the tool working.

Preserve the source spelling in quotations. An existing approved spell-pass
copy can help find known variants, but do not invent corrections or rewrite
transcript text during attribution. Short acknowledgements crossing a cue
boundary are unreliable anchors; prefer longer distinctive exchanges, or
playable audio excerpts for the GM to identify.

### Two PC names on one cluster

**A STRONG CLUE that one person ran both that session, not a collision to
dismiss and not a mapping to adopt.** *Evidence:* `Brewbarry` (47%) and
`Valphine` (38%) both landed on SPEAKER_02, which showed Gary covering an absent
player, from the audio, with no reference to the campaign's own notes. Those
notes elsewhere record a session where the **GM** did the covering instead. So
put it to the GM with that history; one character pointing to several voices
can equally reflect shared control by scene.

Neither result authorizes a permanent player/character mapping. Derive it per
session and never carry it forward. Do not infer PC ownership from a speaker
label or a D&D Beyond account: `party.md` listing every PC under one account is a
strong tell that characters float. Verify per scene when the party splits. A GM
can voice a PC as well as NPCs.

### Closing a SPLIT: the chat sidecar

`name_clusters.py` is blind to exactly one case: **a player who is not in the
room.** An absent player never answers his own vocative; the replies after his
name are other people noticing he is gone, so the tool spreads them across
every cluster and reports `SPLIT`. That is correct behaviour and cannot be fixed
from the audio.

Zoom's chat sidecar can help. Look beside the recording:

```
GMT<date>_RecordingnewChat.txt
00:26:59<TAB>Gary Young:<TAB>Kid needs a phonecall. Sorry a few minutes please
```

It is a **human-typed real name on the session clock**, independent of ASR
spelling (it cannot be a garble), and it is **evidence from silence**, so it
works exactly where vocative scoring cannot. Use it as an absence probe: speech
per cluster inside the stated window, padded either side.

```bash
python3 - "$RUN/turns.json" 1266 1885 <<'PY'
import json, sys; from collections import defaultdict
d = json.load(open(sys.argv[1])); A, B = float(sys.argv[2]), float(sys.argv[3])
per = defaultdict(float)
for t in d["turns"]:
    if t["end"] > A and t["start"] < B:
        per[t["speaker"]] += min(t["end"], B) - max(t["start"], A)
for k, v in sorted(per.items()): print(f"{k}: {v:6.1f}s")
PY
```

*Evidence — Gary, Phandalin ch02,* where `Gary → SPLIT` and the tool could not
close it:

```
SPEAKER_00: 155.7s   SPEAKER_01: 126.7s   SPEAKER_02:   8.2s   SPEAKER_03: 157.1s
```

`SPEAKER_02`, and its single longest silence of the whole session (5.6 min,
00:25:09→00:30:48) sits on the chat timestamp, on the diarization's own
timeline with no reference to the second clustering.

**It is a STRONG CLUE, not a decision.** Compare the silent interval with
surrounding activity and other anchors. Quiet players need not be absent, and a
typed name can be an account label. Present the per-cluster seconds, the
silence and the chat line, and ask the GM which voice it is. Reach for it before
giving up on a `SPLIT`.

## Existing named voice profiles (audit)

Descript names clusters once someone builds voice profiles, and the export then
reads `**kostadis:**`, `**dave:**`: real people, not `Speaker 3`. **That does not
mean the work is done, or that the names are right.** Voice profiles are a
recognition guess, and the GM will usually say so. The job changes shape: from
naming anonymous clusters to **auditing an existing name→voice mapping** against
an independent one. Everything upstream is unchanged: still diarize, still
cross-validate. Keep the named source unaltered.

**A profile's name can be wrong in a way no bijection shows: it can name
someone who is not a participant at all.** Check every profile name against the
roster before reading the matrix. *Evidence — OOTA ch02:* Descript's profiles
were `Kostadis`, `ben`, `joe`, `gabe`, `mike`, and one named for a member of the
GM's household who is not a player (shown here as `<non-player>`). The GM said
so, and a first reading took `<non-player>` for a
room voice. The profile's lines said otherwise:

```
[00:00:00] Kostadis: Hey, Mike. hear me?          [00:00:01] <non-player>: I can hear
[00:04:12] <non-player>: Ben, I don't know if it's just me but, the volume … on your mic seems lower
[00:07:27] <non-player>: Okay, But I can, I can mess with water ...
[00:23:46] <non-player>: perception check?      (the GM: "And now we're with Daz. … Roll a perception check")
[00:30:24] <non-player>: … and then I could do shape water and cause the spit to freeze
```

The profile answers Mike's name, comments on another player's Zoom microphone,
rolls during Daz's spotlight, and casts Shape Water, which is on Daz's sheet and
no other PC's. The GM ruled `<non-player>` = Mike. Descript's own `mike` profile held
37 words. **Read the lines against the PC sheets; the sheet decides what a line
can mean.** A room voice talks to the GM about the room. A player talks about
their character's abilities.

A clean bijection at the usual agreement band means the *mapping* is right and
the residual is boundary noise:

```
SPEAKER_00 ↔ kostadis  84%      33.5% speech  vs  35.8% words
SPEAKER_03 ↔ dave      82%      27.7%             27.8%
SPEAKER_01 ↔ wade      91%      27.7%             24.5%
SPEAKER_02 ↔ gary      81%      11.1%             11.9%
```

Two things make this trustworthy rather than circular: the shares agree as well
as the labels, and each row has exactly one dominant column. A row that splits
across two columns is a merged or swapped profile, a much worse problem than a
few misplaced turns. It can equally be one person's **registers** (a GM's
narration voice), and then the row is fine and the columns merge under one name.
Read the lines to tell which. A column holding two rows is the reverse: two
people pyannote could not separate (acoustic-workflow.md, *A GM's registers*). A
clean mapping can still contain individual boundary errors.

What the GM needs is **not** a relabelled VTT but a **disagreement queue**,
ranked by words at stake. Apply only a **GM-confirmed** cluster-to-player
mapping to calculate proposed names. For each named utterance, intersect its
span with the diarization turns, aggregate overlap by cluster, and list the ones
that disagree above a stated coverage floor, typically 75%. Keep lower-coverage
cases as unresolved. If the label map itself is unresolved, queue its evidence
before proposing cue-level rewrites that depend on it.

Each item records:

- source path, cue/utterance identity, timestamp span, and verbatim dialogue;
- current name, proposed player, acoustic cluster, and covered fraction;
- word count, supporting evidence, and an initially unset decision.

*Evidence:*

```
202 turns disagree at >=75% coverage (of 1457 turns, 586 words = 4.7%)
   dave     -> wade      99      kostadis -> wade      79
   gary     -> wade      70      dave     -> kostadis  61
```

Report total compared words, disputed words, the largest single disagreement
(16 words here) and the **directional bias**: 248 of those words leaked *into*
one speaker. A lopsided table means a profile is over-claiming, which is
actionable; a symmetric one is just turn boundaries. "4.7%, largest single
disagreement 16 words" is a decision the GM can take in one breath; 202 raw
findings is not.

It is a disagreement measure, not a measured error rate. Ask for precise cue
decisions, or an explicit acceptance that the measured disagreement remains
unresolved. Accepting the headline never approves a silent relabel: the
disagreeing cues stay flagged `[?]` (or keep their current label, for an audit)
unless ruled on one by one.

## GM decisions

The name→voice mapping is the precision decision this skill exists to serve.
Every mapping, every `Room (not at table)` confirmation and every cue change
needs an explicit GM answer. Reuse an earlier ruling only when its exact
sources, turns and mapping still apply.

A batch review page, when the GM chooses one, carries **one card per mapping or
cue decision**, each stating what approval and rejection do, with quotes,
timestamps and uncertainty as evidence. Escape transcript HTML. Cards start
unmarked and are never pre-filled; a recommendation goes in the card's text.
An unmarked card stays unresolved. Building or changing a page is never
approval; only the GM's returned decisions are.

Persist the explicit decisions to a file and hash it. Before writing final
names, confirm the sources and turns still match the reviewed versions.

## Writing the approved result

Drafts (cluster-ID VTTs, reports, queues) stay in the run's scratch directory.
**Nothing named goes into the session directory before the GM approves the
name→voice mapping.** The final `<stem>.speakers.vtt` is written **once**, after
approval, as a new file; originals are never modified.

- Save the approved mapping as JSON. Re-run the join on the **original
  speakerless text** with `--names "$RUN/approved_names.json"` (and any approved
  `--md-label` file). Both options also accept inline JSON
  (`--names '{"SPEAKER_00":"Nicholas"}'`), but a file leaves an auditable record
  whose hash goes into the run record. Never feed a labelled result back in as
  unlabelled speech.
  For a named audit, preserve labels until the exact changes are approved;
  prepare a separate unlabelled comparison copy if needed, stripping only
  recognized metadata.
- **Label with players, not characters,** and say so in the header
  (`--note "Labels identify human players, not characters."`). Characters move
  between players; the voice does not. Use **short player names**; display-name
  mapping to `config/players.yaml` belongs to the downstream session pipeline,
  so do not rename the output to suit it. Record player/PC relationships
  separately, and do not rename PCs in a glossary merely because the same
  player speaks their lines.
- Leave unmapped voices anonymous or `UNKNOWN`; an unresolved human identity
  must not become a plausible-looking name. A GM-confirmed outside voice is
  `Room (not at table)` and keeps its speech unless removal was requested.
- Headers say: player labels, the acoustic source, the second source if any
  (or the GM-accepted single-source limitation), a note identifying the approved
  mapping, and that `[?]` marks unresolved disagreement.

Run it **before** scene extraction. Running it after means re-extracting.

### Verify the written file

Check, and report:

- the selected cue count, and every cue omitted by a time limit;
- exact dialogue payloads, apart from the inserted labels;
- timestamps and cue identifiers;
- spoken numbers, crosstalk, unresolved `UNKNOWN` labels and `[?]` markers
  preserved;
- no original file changed (re-hash the inputs);
- when anyone spans several diarization clusters, the name-level disagreement
  count against the second clustering, since the file's `[?]` flags miss those
  cues (acoustic-workflow.md, *When one person spans several clusters*).

```bash
python3 - "$SKILL_DIR" "$BEST_VTT" "$SESSION_DIR/<stem>.speakers.vtt" "<approved labels, comma-separated>" [limit-seconds] <<'PY'
import sys; from pathlib import Path
sys.path.insert(0, sys.argv[1])
from diarize_label import load_vtt
src, out = (load_vtt(Path(p), None) for p in sys.argv[2:4])
labels = set(sys.argv[4].split(","))
limit = float(sys.argv[5]) if len(sys.argv) > 5 else None
kept = [c for c in src if limit is None or c["s"] < limit]
print(f"source cues {len(src)} · selected {len(kept)} · written {len(out)} · "
      f"omitted by time limit {len(src) - len(kept)}")
bad = 0
for s, o in zip(kept, out, strict=True):
    head, sep, rest = o["text"].partition(": ")
    label = head.removesuffix(" [?]")
    if (not sep or rest != s["text"] or o["timing"] != s["timing"]
            or (s["cue_id"] and o["cue_id"] != s["cue_id"])
            or not (label in labels or label.startswith(("SPEAKER_", "UNKNOWN")))):
        bad += 1; print("MISMATCH", s["timing"], repr(o["text"][:60]))
print("payloads, timings and ids match" if not bad else f"{bad} cues differ")
PY
```

When `--limit-seconds` was not passed, the join used the envelope's
`audio_duration` as the limit; pass that value here.

### Run record

Save a run record beside the new output: source paths and SHA-256 hashes (audio,
text, turns, second source), model and speaker count, provenance findings,
independent-source status (or the GM's single-source acceptance), join method,
agreement with its denominator, the GM's decisions with the hash of the
approved mapping/decisions file, and the unresolved cues. Report the resulting
file and its remaining uncertainty.

## Checkpoints, and why none is optional

1. **After provenance:** if it reports MISFILED or a stray transcript, the GM
   decides what moves where.
2. **After the join:** the GM confirms the agreement percentage (with its
   denominator) and the speech split before anything is built on them. A
   collapsed clustering looks exactly like a valid one downstream. An existing
   acceptance of these exact results need not be requested again.
3. **After identity review:** the cluster→name mapping, and any cue-level
   rulings. Nothing further along re-checks speaker identity.

The house pattern, applied where speaker identity is decided: *deterministic
extraction → human checkpoint → a model renders inside the verified structure.*
The rough pass is the ceiling.
