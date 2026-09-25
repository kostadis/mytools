#!/usr/bin/env python3
"""Join acoustic speaker turns to a speakerless VTT without changing dialogue.

An optional second clustering supplies a word-weighted agreement report. The
caller must verify independence and recording provenance: a second file may be
a derivative, and agreement on a mapped subset is not a measured accuracy rate.
Without --md, output explicitly records that independent validation is absent.

Omit --output for a report. Anonymous labels may be written for review; --names
and --md-label accept mappings the GM has already approved. This tool computes
overlap, not human identity. See SKILL.md for the review checkpoints.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import json
import math
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
    """Read cue blocks, preserving numeric dialogue and timestamp settings."""
    cues = []
    raw = path.read_text(encoding="utf-8-sig")
    for block in re.split(r"\n[ \t]*\n", raw):
        lines = block.splitlines()
        if not lines:
            continue
        first = lines[0].strip()
        if (first == "WEBVTT" or first.startswith("WEBVTT ")
                or first == "NOTE" or first.startswith(("NOTE ", "NOTE\t"))
                or first in {"STYLE", "REGION"}):
            continue
        for index, line in enumerate(lines):
            m = _CUE.match(line.strip())
            if not m:
                continue
            a = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + float("0." + m[4])
            b = int(m[5]) * 3600 + int(m[6]) * 60 + int(m[7]) + float("0." + m[8])
            if b <= a:
                raise ValueError(f"invalid cue interval in {path}: {line}")
            payload = lines[index + 1:]
            text = "\n".join(payload)
            if text.strip():
                cues.append({"s": a, "e": b, "t": payload, "text": text,
                             "timing": line, "cue_id": lines[index - 1] if index else None})
            break
    if limit is not None:
        cues = [c for c in cues if c["s"] < limit]
    return cues


def overlap_by_speaker(turns, start: float, end: float) -> collections.Counter:
    """Include every overlapping turn, even a long turn preceding shorter ones."""
    overlap = collections.Counter()
    for st, en, speaker in turns:
        if st >= end:
            break
        if en > start:
            overlap[speaker] += min(en, end) - max(st, start)
    return overlap


def load_md(path: Path) -> list[tuple[float, float | None, str]]:
    """Anonymous-cluster transcript: (start, end, cluster_id).

    Two accepted shapes. The `[ts] **Speaker:**` text form carries starts only,
    so `end` is None and a cue can only be assigned to the nearest preceding
    utterance -- fine for the statistical cross-validation, where a stray cue in
    a silence gap washes out. A turns.json from descript_turns.py carries real
    spans, which lets a cue be assigned by max overlap exactly as the
    diarization join does. Prefer it: --md-label rewrites individual cues, and
    "whoever spoke last" is not good enough to rewrite a label on."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    s = raw.lstrip()
    # Sniff by PARSING, not by first character: the text form's own first line
    # is `[00:16:16] **Speaker:** ...`, which opens with '[' and would be taken
    # for a JSON array.
    if s[:1] in "{[":
        try:
            d = json.loads(s)
        except json.JSONDecodeError:
            d = None
        if d is not None:
            turns = d["turns"] if isinstance(d, dict) else d
            return sorted((float(t["start"]), float(t["end"]), t["speaker"]) for t in turns)
    out = []
    for m in _MD_UTT.finditer(raw):
        t = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3])
        out.append((float(t), None, m[4].strip()))
    out.sort()
    return out


def load_names(arg: str | None) -> dict[str, str]:
    """--names accepts inline JSON or a path to a JSON file.

    Inline is what SKILL.md shows and what a one-off run reaches for; a file
    keeps the mapping under version control across re-runs. Accepting only the
    file form failed with a FileNotFoundError whose "filename" was the JSON
    itself, which reads as a missing-file bug rather than a usage error."""
    if not arg:
        return {}
    s = arg.strip()
    return json.loads(s if s.startswith("{")
                      else Path(s).read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--turns", required=True, help="turns.json from diarize_remote.py")
    ap.add_argument("--vtt", required=True, help="real-timeline, speakerless VTT (the good text)")
    ap.add_argument("--md", help="second clustering for cross-validation (e.g. Descript export)")
    ap.add_argument("--names", help='inline JSON or a path to a JSON file: '
                                    '{"SPEAKER_00": "Nicholas", ...}')
    ap.add_argument("--md-label", help='inline JSON or a path: name cues by their '
                                       'SECOND-clustering id, overriding the diarization. '
                                       'For voices only the second tool can see, e.g. '
                                       '{"Speaker 6": "Room (not at table)"}')
    ap.add_argument("--md-label-coverage", type=float, default=0.5,
                    help="fraction of a cue the named cluster must hold (default 0.5)")
    ap.add_argument("--output", help="labelled VTT; omit to report only")
    ap.add_argument("--note", action="append", default=[], help="extra NOTE line in the output header")
    ap.add_argument("--limit-seconds", type=float,
                    help="ignore cues past this offset (use when the VTT spans more than this audio)")
    args = ap.parse_args()

    if args.output and Path(args.output).resolve() in {
            Path(p).resolve() for p in (args.vtt, args.turns, args.md) if p}:
        ap.error("--output must not overwrite an input file")
    if not 0.5 <= args.md_label_coverage <= 1.0:
        ap.error("--md-label-coverage must be between 0.5 and 1.0")

    d = json.loads(Path(args.turns).read_text(encoding="utf-8"))
    turns = sorted(d["turns"], key=lambda t: t["start"])
    if not turns:
        ap.error("no acoustic turns supplied")
    for t in turns:
        if (not all(isinstance(t.get(k), (int, float)) and math.isfinite(t[k])
                    for k in ("start", "end")) or t["start"] < 0
                or t["end"] <= t["start"] or not isinstance(t.get("speaker"), str)
                or not t["speaker"].strip()):
            ap.error("each acoustic turn needs a valid interval and speaker ID")
    limit = args.limit_seconds if args.limit_seconds is not None else d.get("audio_duration")
    cues = load_vtt(Path(args.vtt), limit)
    if not cues:
        print("no cues in range -- check --limit-seconds and the VTT timeline")
        return 1

    primary_spans = [(t["start"], t["end"], t["speaker"]) for t in turns]
    for c in cues:
        ov = overlap_by_speaker(primary_spans, c["s"], c["e"])
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
        print(f"   ⚠ largest cluster is {top:.0f}% of speech — check for collapse or a dominant speaker.")
        print("     A GM-heavy two-person session can be this uneven; review the acoustic evidence.")
    print(f"\n{len(cues)} cues · {sum(c['mixed'] for c in cues)} span >1 turn (crosstalk)")

    mapping: dict[str, str] = {}
    agreement = None
    compared_words = 0
    all_words = sum(len(c["text"].split()) for c in cues)
    if args.md:
        utts = load_md(Path(args.md))
        if any(not math.isfinite(st) or st < 0 or not isinstance(sp, str)
               or not sp.strip() or (en is not None and (not math.isfinite(en) or en <= st))
               for st, en, sp in utts):
            ap.error("second-source turns contain an invalid interval or speaker ID")
        u_starts = [u[0] for u in utts]
        spans = all(u[1] is not None for u in utts)
        if args.md_label and not spans:
            ap.error("--md-label requires real start/end spans; supply Descript turns JSON")
        for c in cues:
            if spans:
                ov = overlap_by_speaker(utts, c["s"], c["e"])
                top = ov.most_common(1)
                c["de"] = top[0][0] if top else None
                c["de_cov"] = top[0][1] / max(c["e"] - c["s"], 1e-9) if top else 0.0
            else:
                i = bisect.bisect_right(u_starts, c["s"]) - 1
                c["de"] = utts[i][2] if i >= 0 else None
                c["de_cov"] = None
        if not utts:
            print(f"⚠ --md {Path(args.md).name} parsed as 0 utterances — no cross-validation.")
            print("  Expected a descript_turns.py --turns JSON, or its --md text form")
            print("  ([00:17:16] **Speaker 2:** ...). A raw Descript .txt is neither; convert it.")
            return 1
        print(f"second clustering: {len(utts)} utterances, "
              f"{'real spans (max-overlap join)' if spans else 'starts only (nearest-preceding join)'}")

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
                print(f"{'':14s}   ↑ {tot} words, no qualifying mapping — review this cluster")

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
            agreement, compared_words = pctv, ag + dis
            print(f"\nword-level agreement: {pctv:.1f}% ({ag + dis}/{all_words} words mapped)")
            if pctv < 70:
                print("   ⚠ below 70% — the two signals disagree. One is broken; find out which")
                print("     before labelling anything.")
        else:
            print("\nword-level agreement unavailable — no qualifying mapped words")

    names = load_names(args.names)
    md_labels = load_names(args.md_label)
    if md_labels and not args.md:
        print("⚠ --md-label needs --md — that is where the second clustering's ids come from.")
        return 1
    if md_labels:
        unseen = sorted(set(md_labels) - {c.get("de") for c in cues})
        if unseen:
            print(f"⚠ --md-label names no cue in {', '.join(unseen)} — check the cluster ids "
                  f"against the cross-validation rows above.")
    if args.output:
        out = ["WEBVTT", "", "NOTE",
               f"Speakers: {d.get('model')}, num_speakers={d.get('num_speakers_requested')}.",
               f"Text: {Path(args.vtt).name} (real timeline)."]
        if args.md:
            if agreement is not None:
                out.append(f"Compared against {Path(args.md).name}: {agreement:.1f}% agreement "
                           f"among {compared_words}/{all_words} mapped words.")
                out.append("The caller must verify that the second clustering is independent.")
            else:
                out.append(f"Comparison with {Path(args.md).name} is inconclusive; "
                           "no mapped-word agreement available.")
        else:
            out.append("Single acoustic source; no independent cross-validation.")
        for cid, lab in sorted(md_labels.items()):
            out.append(f"'{lab}' is named from {Path(args.md).name} cluster {cid}, "
                       f"a voice the diarization could not separate.")
        out += [f"{n}" for n in args.note]
        out += ["[?] marks a cue where the two clusterings disagree.", ""]
        n = 0
        flagged = 0
        overridden = collections.Counter()
        for c in cues:
            exp = mapping.get(c.get("de"))
            flag = " [?]" if (exp and c["py"] and exp != c["py"]) else ""
            label = names.get(c["py"], c["py"] or "UNKNOWN")
            # A second-clustering override wins outright, and drops the [?]: the
            # disagreement it marks is the whole reason this cue is being named
            # from the other tool, not a warning the reader can act on.
            forced = md_labels.get(c.get("de"))
            if forced and (c.get("de_cov") is None or c["de_cov"] >= args.md_label_coverage):
                label, flag = forced, ""
                overridden[forced] += 1
            else:
                flagged += bool(flag)
            n += 1
            out += [c["cue_id"] or str(n), c["timing"],
                    f"{label}{flag}: {c['text']}", ""]
        Path(args.output).write_text("\n".join(out), encoding="utf-8")
        print(f"\nwrote {args.output} — {n} cues, {flagged} flagged [?]")
        for lab, k in overridden.most_common():
            print(f"   {k} cues labelled '{lab}' from the second clustering")
        if not names:
            print("   labels are raw cluster IDs. Name them with name_clusters.py, then re-run")
            print("   with --names.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
