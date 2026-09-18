# Identity review

Read when acoustic clusters are ready for the GM to identify, or when auditing
existing voice-profile names. The deterministic tools propose and count; the
GM supplies identity decisions.

## Anonymous clusters

`name_clusters.py` scores who answers when a candidate name is spoken, with
vocative-shaped lines separated from third-person narration. Probe real names
and PCs using repeated `--name` arguments. A player name never spoken at the
table contributes no evidence. Preserve the source spelling in quotations;
an existing approved spell-pass copy can help find known variants, but do not
invent corrections or rewrite transcript text during attribution.

Present the cluster IDs, speech shares, candidate names, reply counts, and
representative exchanges with timestamps. The highest-ranked bin is a proposal.
Weak samples, third-person references, and `SPLIT` results stay unresolved.

Two character names pointing to one voice may mean one player covered both.
One character pointing to several voices can reflect shared control by scene.
Neither result authorizes a permanent player/character mapping. Use explicit
session information; do not derive ownership from a D&D Beyond account or copy
ownership from another session. A GM can voice a PC as well as NPCs.

Short acknowledgements crossing a cue boundary are often unreliable anchors.
Prefer longer distinctive exchanges or playable audio excerpts for the GM to
identify. A known participant roster establishes possible identities, not which
cluster belongs to whom. With two people, do not assume the longest cluster is
the GM or force cues to alternate.

## Typed chat and absence anchors

Look for a Zoom `RecordingnewChat.txt` sidecar. A timestamped message such as
`Gary: Kid needs a phonecall. Sorry a few minutes please` is a human-typed name,
independent of ASR spellings. Compare speech per cluster inside that window:

```python
from collections import Counter

def speech_in_window(turns, start, end):
    seconds = Counter()
    for turn in turns:
        overlap = min(turn['end'], end) - max(turn['start'], start)
        if overlap > 0:
            seconds[turn['speaker']] += overlap
    return seconds
```

Compare the silent interval with surrounding activity and other anchors. Quiet
players need not be absent, and typed names can be account labels; use the
evidence to ask the GM, not to auto-select a voice. Absence can explain why
vocative replies split across other speakers.

## Existing named voice profiles

A clean correspondence between independent clusters and names, with compatible
speech shares, supports the mapping. A named row splitting over several primary
clusters suggests merged or swapped profiles. A clean dominant mapping can
still contain individual boundary errors.

Prepare an audit queue without altering the named source. For each named
utterance, intersect its span with primary turns and aggregate overlap by
cluster. Apply only a **GM-confirmed** cluster-to-player mapping to calculate a
proposed name. Show disagreements above a stated coverage floor, typically
75%, ranked by words at stake. Retain lower-coverage cases as unresolved.

Each item records:

- source path, cue/utterance identity, timestamp span, and verbatim dialogue;
- current name, proposed player, acoustic cluster, and covered fraction;
- word count, supporting evidence, and an initially unset decision.

Report the total compared words, disputed words, largest affected utterance,
and directional counts (for example, words claimed as Dave that the independent
mapping assigns to Wade). Directional concentration may reveal an over-claiming
profile. It is a disagreement measure, not a measured true error rate.

Ask for precise cue decisions or an explicit acceptance of remaining uncertainty.
Do not turn acceptance of a headline rate into approval of a silent relabel.
If a label map is unresolved, queue its evidence before proposing cue-level
rewrites that depend on it.

## Codex review and handoff

Use chat by default. Reuse earlier rulings when their exact source and mapping
still apply. If the user wants a batch page and the shared renderer is installed,
read `${CODEX_HOME:-$HOME/.codex}/skills/_shared/review-page/CONTRACT.md` and use
its generic schema. Keep one mapping or cue change per consent unit; evidence
includes quotes, timestamps, uncertainty, and the consequence of approval.
Escape transcript HTML. Page creation or modification is never approval.

Persist explicit decisions alongside source hashes. Before writing final names,
confirm the sources and turns still match the reviewed versions. Leave unmapped
voices anonymous or `UNKNOWN`; an unresolved human identity must not become a
plausible-looking name. Final headers say player labels, acoustic source, second
source if any, and unresolved disagreement semantics.

Hand the reviewed VTT and any session-specific player/character notes to the
requested downstream workflow. Do not rename PCs in the glossary merely because
the same player speaks their lines.
