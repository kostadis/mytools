#!/usr/bin/env python3
"""Put human names on anonymous diarization clusters, from the transcript alone.

Diarization tells you there are three voices. It cannot tell you which is which,
and in a single-room recording no file carries a name -- the conference tool
labelled every cue with the host's name, and the editor's clusters are
"Speaker 3". Yet the names are almost always sitting in the text, because people
address each other:

    GM:          "Daein. Sorry. Felkur's not there, right?"
    SPEAKER_00:  "Everyone's there."

Three seconds, both players pinned. This mines that pattern and RANKS the
candidates. It does not decide -- attribution is a precision decision and the
output is a review table for a human.

The signal is second-person address, and the discriminator is who ANSWERS:

  ADDRESSED  cluster X says <name>, a different cluster Y replies inside the
             window  ->  evidence that Y is <name>.  Strong.
  MENTIONED  cluster X says <name> with no reply, or replies to itself
             ->  weak, and mildly negative for X: people name others more than
             themselves.

Narration is the noise floor, and it is loud. A GM recapping last session says
character names constantly in the third person -- "Daein convinced Korkan to
lead a charge" -- and each one drags a reply into the window. So mentions are
scored for VOCATIVE SHAPE (is this an address, or is it prose about someone?)
and the two are reported side by side. On the Hillsfar session that is the
difference between "SPLIT, do not pick a winner" and a clean 75%.

Two traps this is built around:

  * A player's real name and their character's name may be the SAME WORD. If a
    player is called Daein and plays Daein, "Daein has plus eight" is both a
    character reference and a direct address, and no amount of parsing separates
    them. Rank the cluster, then confirm with a human.

  * Characters get passed around. When two players share four PCs, a name maps
    to a SCENE, not a person. If a name's evidence is split across clusters,
    that is the finding -- do not resolve it by picking the larger number.
"""
from __future__ import annotations

import argparse
import collections
import re
from pathlib import Path

_CUE = re.compile(r"(\d\d):(\d\d):(\d\d)[.,](\d+)\s*-->\s*(\d\d):(\d\d):(\d\d)[.,](\d+)")
_LABEL = re.compile(r"^([A-Za-z0-9_ ]{1,40}?)(?:\s*\[\?\])?:\s*(.*)$")


def load(path: Path) -> list[dict]:
    cues, cur = [], None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _CUE.match(line.strip())
        if m:
            cur = {"s": int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + float("0." + m[4]),
                   "e": int(m[5]) * 3600 + int(m[6]) * 60 + int(m[7]) + float("0." + m[8]),
                   "spk": None, "text": ""}
            cues.append(cur)
            continue
        s = line.strip()
        if cur is None or not s or s.isdigit() or s.startswith(("WEBVTT", "NOTE", "[?]")):
            continue
        lm = _LABEL.match(s)
        if lm and cur["spk"] is None:
            cur["spk"], s = lm[1].strip(), lm[2]
        cur["text"] = (cur["text"] + " " + s).strip()
    return [c for c in cues if c["text"] and c["spk"]]


def fmt(sec: float) -> str:
    return f"{int(sec // 60):02d}:{sec % 60:05.2f}"


def vocative(text: str, pat: re.Pattern) -> bool:
    """Is the name being USED to address someone, rather than narrated about?

    Deliberately shape-based, not semantic. "Daein, as you're leaving..." and
    "Could you ask Daein?" are addresses; "Daein convinced Korkan to lead a
    charge against the fire giant" is prose. The tells are position and length:
    a vocative sits at a clause edge and the utterance around it is short,
    because you are speaking TO someone, not describing them."""
    m = pat.search(text)
    if not m:
        return False
    before, after = text[:m.start()], text[m.end():]
    at_edge = (
        len(before.strip()) == 0                              # "Daein, what do you do?"
        or before.rstrip().endswith((",", ".", "?", "!"))     # "...right? Daein, you there?"
        or after.lstrip()[:1] in {",", "?", "!", ""}          # "Could you ask Daein?"
    )
    second_person = re.search(r"\byou(?:r|rs)?\b", text, re.I) is not None
    return at_edge and (len(text.split()) <= 14 or second_person)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vtt", help="labelled VTT (cluster IDs are fine)")
    ap.add_argument("--name", action="append", required=True,
                    help="candidate name; repeat. Include PCs AND real first names/nicknames")
    ap.add_argument("--window", type=float, default=12.0,
                    help="seconds after a naming in which a reply counts as an answer")
    ap.add_argument("--quotes", type=int, default=4, help="example exchanges to print per name")
    args = ap.parse_args()

    cues = load(Path(args.vtt))
    clusters = sorted({c["spk"] for c in cues})
    print(f"{len(cues)} cues · clusters: {', '.join(clusters)}\n")

    addressed = collections.defaultdict(collections.Counter)
    voc_addressed = collections.defaultdict(collections.Counter)
    mentioned = collections.defaultdict(collections.Counter)
    examples = collections.defaultdict(list)

    for name in args.name:
        pat = re.compile(rf"\b{re.escape(name)}\b", re.I)
        for i, c in enumerate(cues):
            if not pat.search(c["text"]):
                continue
            mentioned[name][c["spk"]] += 1
            is_voc = vocative(c["text"], pat)
            for nxt in cues[i + 1:]:
                if nxt["s"] > c["e"] + args.window:
                    break
                if nxt["spk"] != c["spk"]:
                    addressed[name][nxt["spk"]] += 1
                    if is_voc:
                        voc_addressed[name][nxt["spk"]] += 1
                        if len(examples[name]) < args.quotes:
                            examples[name].append((c, nxt))
                    break

    for name in args.name:
        tot_a = sum(addressed[name].values())
        tot_m = sum(mentioned[name].values())
        print(f"── {name} " + "─" * (58 - len(name)))
        if not tot_m:
            print("     never spoken. No evidence either way.\n")
            continue
        tot_v = sum(voc_addressed[name].values())
        print(f"     {'cluster':<14}{'ANSWERS a vocative':>20}{'any reply':>12}{'says it':>10}")
        for cl in clusters:
            v, a, m = voc_addressed[name][cl], addressed[name][cl], mentioned[name][cl]
            bar = "█" * round(12 * v / tot_v) if tot_v else ""
            vs = f"{v:>3} ({100*v/tot_v:3.0f}%)" if tot_v else f"{v:>3}   -  "
            print(f"     {cl:<14}{vs:>12} {bar:<13}{a:>6}{m:>10}")
        # the vocative column decides when it has any weight at all; the raw
        # reply column is a fallback, and it is much noisier
        pool, tot_p, why = (voc_addressed[name], tot_v, "vocative") if tot_v >= 3 \
            else (addressed[name], tot_a, "all-reply")
        if tot_p:
            best, n = pool.most_common(1)[0]
            share = 100 * n / tot_p
            if share >= 60:
                print(f"     → likely {best} — {share:.0f}% of {tot_p} {why} answers")
            else:
                print(f"     → SPLIT across clusters ({why}). Likely a shared/floating character,")
                print(f"       or a name everyone uses in the third person. Do not pick a winner.")
            if tot_v < 3:
                print(f"       (only {tot_v} vocative uses — weak. Read the quotes yourself.)")
        for c, nxt in examples[name]:
            print(f"       [{fmt(c['s'])}] {c['spk']}: {c['text'][:120]}")
            print(f"       [{fmt(nxt['s'])}] {nxt['spk']}: {nxt['text'][:120]}")
            print()
        print()

    print("Every line above is evidence, not a decision. Confirm with the GM before")
    print("writing names into anything.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
