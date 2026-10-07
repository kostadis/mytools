#!/usr/bin/env python3
"""Project raw-recording diarization turns onto an EDITED transcript timeline.

For a session whose transcripts were made from an edited export (Descript's
"remove gaps / filler" or hand cuts) while the only audio is the RAW
recording. The two timelines differ by many small cuts, so neither a single
offset nor --limit-seconds can join them. This helper uses the words instead:

  1. word-timestamped ASR of the RAW audio (spark/words_remote.py), and
  2. the edited-timeline VTT (the text layer the join will label),

are aligned token by token (difflib, matching runs >= --min-run). Each anchored
word looks up the diarization speaker at its own raw timestamp, and the cue
takes the duration-weighted majority. Cues with no anchored word get two
bounded second chances, both tagged in the output:

  local   the cue's words are searched only inside the raw window between its
          anchored neighbours (>= --local-min of its tokens for 3+ word cues;
          1-2 word cues must occur exactly once in that window);
  interp  the neighbours' offsets agree within --interp-tol seconds (no cut
          between them), so the cue's raw span is interpolated.

Anything else is left unlabelled and listed, never guessed. The output is an
ordinary turns envelope on the EDITED timeline, one turn per labelled cue, so
diarize_label.py joins and cross-validates it unchanged.

  python3 project_turns.py --words words.json --vtt edited.vtt \\
      --turns turns_raw.json --output turns_edited.json
"""
from __future__ import annotations

import argparse
import bisect
import collections
import difflib
import json
import re
import sys
from pathlib import Path

TOK = re.compile(r"[a-z0-9']+")


def norm(text: str) -> list[str]:
    return TOK.findall(text.lower())


def ts(stamp: str) -> float:
    parts = stamp.split(":")
    if len(parts) == 2:
        parts.insert(0, "0")
    h, m, s = parts
    return int(h) * 3600 + int(m) * 60 + float(s)


def load_cues(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    cues, i = [], 0
    while i < len(lines):
        if "-->" in lines[i]:
            a, b = (x.strip().split()[0] for x in lines[i].split("-->"))
            text = []
            i += 1
            while i < len(lines) and lines[i].strip():
                text.append(lines[i])
                i += 1
            cues.append({"start": ts(a), "end": ts(b), "text": " ".join(text)})
        i += 1
    return cues


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--words", required=True, type=Path,
                    help="raw-audio word timestamps: {\"words\": [[start, end, word], ...]}")
    ap.add_argument("--vtt", required=True, type=Path, help="edited-timeline transcript to be labelled")
    ap.add_argument("--turns", required=True, type=Path, help="diarization envelope on the RAW timeline")
    ap.add_argument("--output", required=True, type=Path, help="turns envelope on the EDITED timeline")
    ap.add_argument("--min-run", type=int, default=4, help="shortest exact token run used as an anchor")
    ap.add_argument("--local-min", type=float, default=0.6)
    ap.add_argument("--interp-tol", type=float, default=1.0)
    a = ap.parse_args()

    for p in (a.words, a.vtt, a.turns):
        if not p.is_file():
            sys.exit(f"missing input: {p}")
    if a.output.resolve() in {a.words.resolve(), a.vtt.resolve(), a.turns.resolve()}:
        sys.exit("--output would overwrite an input")

    cues = load_cues(a.vtt)
    if not cues:
        sys.exit(f"no cues parsed from {a.vtt}")
    edited = [(ci, t) for ci, c in enumerate(cues) for t in norm(c["text"])]
    raw = [(s, e, t) for s, e, w in json.loads(a.words.read_text())["words"] for t in norm(w)]
    if not raw:
        sys.exit(f"no words in {a.words}")

    sm = difflib.SequenceMatcher(None, [t for _, t in edited], [t for *_, t in raw], autojunk=False)
    anch: dict[int, list[tuple[float, float]]] = collections.defaultdict(list)
    for blk in sm.get_matching_blocks():
        if blk.size >= a.min_run:
            for k in range(blk.size):
                anch[edited[blk.a + k][0]].append(raw[blk.b + k][:2])

    env = json.loads(a.turns.read_text())
    turns = sorted(env["turns"], key=lambda t: t["start"])
    if not turns:
        sys.exit(f"no turns in {a.turns}")
    starts = [t["start"] for t in turns]

    def overlap(s: float, e: float) -> collections.Counter:
        got: collections.Counter = collections.Counter()
        for t in turns[max(0, bisect.bisect_right(starts, s) - 50):]:
            if t["start"] > e:
                break
            ov = min(e, t["end"]) - max(s, t["start"])
            if ov > 0:
                got[t["speaker"]] += ov
        return got

    # per-cue offset (raw - edited), used to bound and interpolate the rest
    coff = {ci: sum(s for s, _ in w) / len(w) - (cues[ci]["start"] + cues[ci]["end"]) / 2
            for ci, w in anch.items()}
    keys = sorted(coff)

    out, unlabelled, shares = [], [], []
    how_n: collections.Counter = collections.Counter()
    for ci, c in enumerate(cues):
        words, how = anch.get(ci), "word"
        if not words:
            j = bisect.bisect_left(keys, ci)
            if not 0 < j < len(keys):
                unlabelled.append(ci)
                continue
            prev, nxt = keys[j - 1], keys[j]
            lo = max(e for _, e in anch[prev]) - 1.0
            hi = min(s for s, _ in anch[nxt]) + 1.0
            win = [w for w in raw if lo <= w[0] and w[1] <= hi]
            ct = norm(c["text"])
            if len(ct) >= 3 and win:
                m = difflib.SequenceMatcher(None, ct, [t for *_, t in win], autojunk=False)
                blocks = [b for b in m.get_matching_blocks() if b.size >= 2]
                if sum(b.size for b in blocks) / len(ct) >= a.local_min:
                    words = [win[b.b + k][:2] for b in blocks for k in range(b.size)]
                    how = "local"
            elif ct and win:
                hits = [i for i in range(len(win) - len(ct) + 1)
                        if [w[2] for w in win[i:i + len(ct)]] == ct]
                if len(hits) == 1:
                    words = [w[:2] for w in win[hits[0]:hits[0] + len(ct)]]
                    how = "local"
            if not words and abs(coff[prev] - coff[nxt]) <= a.interp_tol:
                o = (coff[prev] + coff[nxt]) / 2
                words, how = [(c["start"] + o, c["end"] + o)], "interp"
            if not words:
                unlabelled.append(ci)
                continue
        votes: collections.Counter = collections.Counter()
        for s, e in words:
            votes.update(overlap(s, max(e, s + 0.05)))
        if not votes:
            unlabelled.append(ci)
            continue
        spk, v = votes.most_common(1)[0]
        share = v / sum(votes.values())
        shares.append(share)
        how_n[how] += 1
        out.append({"start": c["start"], "end": c["end"], "speaker": spk,
                    "raw_start": round(min(s for s, _ in words), 2),
                    "raw_end": round(max(e for _, e in words), 2),
                    "vote_share": round(share, 3), "how": how})

    anchored = sum(len(v) for v in anch.values())
    env_out = dict(env, turns=out, audio_duration=cues[-1]["end"] + 1.0,
                   projection={"method": "project_turns.py word-anchored projection",
                               "raw_turns": str(a.turns), "raw_words": str(a.words),
                               "edited_vtt": str(a.vtt),
                               "anchored_words": anchored, "edited_words": len(edited),
                               "labelled": dict(how_n), "unlabelled_cues": unlabelled})
    a.output.write_text(json.dumps(env_out, indent=1), encoding="utf-8")

    print(f"edited words anchored exactly: {anchored}/{len(edited)} ({anchored / len(edited):.1%})")
    print(f"cues {len(cues)}: labelled {len(out)} (word {how_n['word']}, local {how_n['local']}, "
          f"interp {how_n['interp']}), unlabelled {len(unlabelled)}")
    if shares:
        shares.sort()
        print(f"per-cue vote share: median {shares[len(shares) // 2]:.2f}, "
              f"{sum(s < 0.6 for s in shares)} cues under 0.60")
    print(f"wrote {a.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
