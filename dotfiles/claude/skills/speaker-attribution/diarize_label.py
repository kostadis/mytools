#!/usr/bin/env python3
"""Attach diarization turns to a speakerless real-timeline VTT, cross-validate
against a second independent clustering, and emit a labelled VTT.

This is the single-room case: everyone shares one microphone, so the conference
tool's own speaker labels carry NO information (Zoom labels all 866 cues of a
three-person session with the host's name). Diarization is not a second opinion
here -- it is the only signal. That makes cross-validation mandatory rather
than optional, because there is nothing else to catch a collapsed clustering.

The second opinion comes free: Descript (or any editor that diarizes on import)
has already clustered the same audio with a different embedding model. Its
cluster IDs are anonymous and usually too numerous -- 6 clusters for 3 people --
but agreement between the two is meaningful precisely because they share no
information. One is pyannote's speaker embedding, the other is Descript's.

Expect ~80% word-level agreement. Measured: 81.3% (Hillsfar, 3 speakers, one
room), 82.2% (Phandalin ch04, 4 speakers, mixed remote). Below ~70%, one of the
two has failed -- find out which before building on either.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import json
import re
from pathlib import Path

_CUE = re.compile(r"(\d\d):(\d\d):(\d\d)[.,](\d+)\s*-->\s*(\d\d):(\d\d):(\d\d)[.,](\d+)")
_MD_UTT = re.compile(r"\[(\d\d):(\d\d):(\d\d)\]\s*\*\*([^*]+?):?\*\*\s*(.*?)(?=\n\n|\Z)", re.S)
_INLINE_TS = re.compile(r"\[\d\d:\d\d:\d\d\]")


def fmt(sec: float) -> str:
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def load_vtt(path: Path, limit: float | None) -> list[dict]:
    cues, cur = [], None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _CUE.match(line.strip())
        if m:
            a = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + float("0." + m[4])
            b = int(m[5]) * 3600 + int(m[6]) * 60 + int(m[7]) + float("0." + m[8])
            cur = {"s": a, "e": b, "t": []}
            cues.append(cur)
        else:
            s = line.strip()
            if cur is not None and s and not s.isdigit() and not s.startswith(("WEBVTT", "NOTE")):
                cur["t"].append(s)
    for c in cues:
        c["text"] = " ".join(c["t"]).strip()
    cues = [c for c in cues if c["text"]]
    if limit is not None:
        cues = [c for c in cues if c["s"] < limit]
    return cues


def load_md(path: Path) -> list[tuple[float, str]]:
    """Anonymous-cluster transcript: (start_seconds, cluster_id). No end times --
    Descript emits a start stamp per utterance and nothing else."""
    out = []
    for m in _MD_UTT.finditer(path.read_text(encoding="utf-8", errors="replace")):
        t = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3])
        out.append((t, m[4].strip()))
    out.sort()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--turns", required=True, help="turns.json from diarize_remote.py")
    ap.add_argument("--vtt", required=True, help="real-timeline, speakerless VTT (the good text)")
    ap.add_argument("--md", help="second clustering for cross-validation (e.g. Descript export)")
    ap.add_argument("--names", help='JSON: {"SPEAKER_00": "Nicholas", ...}')
    ap.add_argument("--output", help="labelled VTT; omit to report only")
    ap.add_argument("--note", action="append", default=[], help="extra NOTE line in the output header")
    ap.add_argument("--limit-seconds", type=float,
                    help="ignore cues past this offset (use when the VTT spans more than this audio)")
    args = ap.parse_args()

    d = json.loads(Path(args.turns).read_text(encoding="utf-8"))
    turns = d["turns"]
    limit = args.limit_seconds if args.limit_seconds is not None else d.get("audio_duration")
    cues = load_vtt(Path(args.vtt), limit)
    if not cues:
        print("no cues in range -- check --limit-seconds and the VTT timeline")
        return 1

    starts = [t["start"] for t in turns]
    for c in cues:
        ov = collections.Counter()
        i = max(0, bisect.bisect_left(starts, c["s"]) - 1)
        for t in turns[i:]:
            if t["start"] >= c["e"]:
                break
            if t["end"] > c["s"]:
                ov[t["speaker"]] += min(t["end"], c["e"]) - max(t["start"], c["s"])
        c["py"] = ov.most_common(1)[0][0] if ov else None
        c["mixed"] = len(ov) > 1

    speech = collections.Counter()
    for t in turns:
        speech[t["speaker"]] += t["end"] - t["start"]
    total = sum(speech.values())
    print(f"audio {d.get('audio_duration', 0)/60:.1f} min · {len(turns)} turns · "
          f"{total/60:.1f} min speech · model {d.get('model')} · {d.get('device_used')}")
    for s, v in speech.most_common():
        print(f"   {s}  {v/60:6.1f} min  {100*v/total:5.1f}%")
    top = 100 * max(speech.values()) / total
    if top > 70:
        print(f"   ⚠ largest cluster is {top:.0f}% of speech — clustering has probably collapsed.")
        print("     Re-run with speaker-diarization-community-1 and an explicit num_speakers.")
    print(f"\n{len(cues)} cues · {sum(c['mixed'] for c in cues)} span >1 turn (crosstalk)")

    mapping: dict[str, str] = {}
    if args.md:
        utts = load_md(Path(args.md))
        u_starts = [u[0] for u in utts]
        for c in cues:
            i = bisect.bisect_right(u_starts, c["s"]) - 1
            c["de"] = utts[i][1] if i >= 0 else None

        words = collections.Counter()
        for c in cues:
            if c["py"] and c.get("de"):
                words[(c["de"], c["py"])] += len(c["text"].split())
        pys = sorted(speech)
        des = sorted({de for de, _ in words}, key=lambda x: -sum(words[(x, p)] for p in pys))
        print("\ncross-validation — words, second clustering (rows) × diarization (cols)")
        print(f"{'':14s}" + "".join(f"{p:>13s}" for p in pys) + "     share")
        for de in des:
            row = [words[(de, p)] for p in pys]
            tot = sum(row)
            if not tot:
                continue
            best = max(range(len(pys)), key=lambda i: row[i])
            print(f"{de:14s}" + "".join(f"{v:13d}" for v in row) + "   "
                  + " / ".join(f"{100*v/tot:.0f}%" for v in row))
            # only clusters carrying real weight get to define the mapping
            if tot >= 0.05 * sum(words.values()) and 100 * row[best] / tot >= 60:
                mapping[de] = pys[best]
            else:
                print(f"{'':14s}   ↑ {tot} words, no clear home — treated as a spurious split")

        ag = dis = 0
        for c in cues:
            exp = mapping.get(c.get("de"))
            if exp and c["py"]:
                w = len(c["text"].split())
                if exp == c["py"]:
                    ag += w
                else:
                    dis += w
        if ag + dis:
            pctv = 100 * ag / (ag + dis)
            print(f"\nword-level agreement: {pctv:.1f}%")
            if pctv < 70:
                print("   ⚠ below 70% — the two signals disagree. One is broken; find out which")
                print("     before labelling anything.")

    names = json.loads(Path(args.names).read_text(encoding="utf-8")) if args.names else {}
    if args.output:
        out = ["WEBVTT", "", "NOTE",
               f"Speakers: {d.get('model')}, num_speakers={d.get('num_speakers_requested')}.",
               f"Text: {Path(args.vtt).name} (real timeline)."]
        if args.md:
            out.append(f"Cross-validated against {Path(args.md).name}.")
        out += [f"{n}" for n in args.note]
        out += ["[?] marks a cue where the two clusterings disagree.", ""]
        n = 0
        flagged = 0
        for c in cues:
            exp = mapping.get(c.get("de"))
            flag = " [?]" if (exp and c["py"] and exp != c["py"]) else ""
            flagged += bool(flag)
            n += 1
            out += [str(n), f"{fmt(c['s'])} --> {fmt(c['e'])}",
                    f"{names.get(c['py'], c['py'] or 'UNKNOWN')}{flag}: {c['text']}", ""]
        Path(args.output).write_text("\n".join(out), encoding="utf-8")
        print(f"\nwrote {args.output} — {n} cues, {flagged} flagged [?]")
        if not names:
            print("   labels are raw cluster IDs. Name them with name_clusters.py, then re-run")
            print("   with --names.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
