#!/usr/bin/env python3
"""Which text file transcribes which recording? Answer it by fingerprint, not
by filename.

A session directory's filenames are an assertion, not evidence. Files get
dropped in the wrong folder, named for the day they were processed rather than
the day they were recorded, and inherit a date from a sibling. Downstream, a
transcript aligned against the wrong .m4a produces speaker labels that are
uniformly, confidently wrong -- there is no error, just garbage.

The test is n-gram set overlap between token streams:

    overlap(A,B) = |grams(A) & grams(B)| / min(|grams(A)|, |grams(B)|)

Two ASR passes over the SAME audio disagree on fillers, punctuation and proper
nouns everywhere, so this never approaches 100%. But the separation is not
subtle. Measured on the Hillsfar tree, 4-grams:

    same audio (Zoom ASR vs Descript ASR)     49.9%
    same audio (Zoom ASR vs Whisper)          61.4%
    different sessions, same campaign,          0.8 - 3.0%
      same players, same NPC names

An order of magnitude of daylight. Above ~25% is the same recording; under ~5%
is unrelated. Nothing has landed in between.

Order-independent by construction (it compares SETS), so a timeline offset, a
concatenation, or a truncated tail cannot fake a match or hide one.

Why NOT union-find over the "same recording" relation
-----------------------------------------------------
A single transcript covering a whole game day is often the concatenation of a
morning and an afternoon recording. It matches BOTH, while the two halves match
each other at the noise floor. Transitive closure silently fuses them into one
"recording" and the misfiling report becomes nonsense. So this reports each
file's matches directly and names that pattern -- SPANS -- instead of chaining.
"""
from __future__ import annotations

import argparse
import itertools
import re
import sys
from pathlib import Path

AUDIO_EXT = {".m4a", ".mp3", ".wav", ".mp4", ".m4v"}
_VTT_SPEAKER = re.compile(r"^[A-Za-z][A-Za-z .'-]{0,40}:\s*")
_MD_SPEAKER = re.compile(r"\*\*[^*]+\*\*")
_TIMECODE = re.compile(r"\d\d:\d\d:\d\d[.,]\d+\s*-->")
_BRACKET_TS = re.compile(r"\[\d\d:\d\d:\d\d\]")
# A Descript/Zoom export is a transcript; a chapter summary is prose ABOUT one.
# Prose shares proper nouns with its own transcript but almost no 4-grams, so it
# lands near the noise floor and only adds clutter. Require speaker markup.
_TRANSCRIPT_MD = re.compile(r"^\s*(\[\d\d:\d\d:\d\d\]\s*)?\*\*[^*\n]{1,40}:?\*\*", re.M)


def vtt_tokens(path: Path) -> list[str]:
    out, in_cue = [], False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if _TIMECODE.match(line.strip()):
            in_cue = True
            continue
        s = line.strip()
        if not s or s.isdigit() or s.startswith(("WEBVTT", "NOTE")):
            continue
        if in_cue:
            out.append(_VTT_SPEAKER.sub("", s))
    return re.findall(r"[a-z']+", " ".join(out).lower())


def md_tokens(path: Path) -> list[str]:
    s = path.read_text(encoding="utf-8", errors="replace")
    s = _BRACKET_TS.sub(" ", _MD_SPEAKER.sub(" ", s))
    return re.findall(r"[a-z']+", s.lower())


def is_transcript(path: Path, include_prose: bool) -> bool:
    if path.suffix.lower() == ".vtt":
        return True
    if path.suffix.lower() not in {".md", ".txt"}:
        return False
    if include_prose:
        return True
    head = path.read_text(encoding="utf-8", errors="replace")
    # a real export labels every utterance; a report that merely uses **bold**
    # for emphasis will not clear a couple of dozen.
    return len(_TRANSCRIPT_MD.findall(head)) >= 20


def grams(toks: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)}


def fmt_hms(sec: float) -> str:
    h, rem = divmod(int(round(sec)), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def vtt_span(path: Path) -> tuple[float, float] | None:
    first = last = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"(\d\d):(\d\d):(\d\d)[.,](\d+) --> (\d\d):(\d\d):(\d\d)[.,](\d+)", line.strip())
        if m:
            a = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + float("0." + m[4])
            b = int(m[5]) * 3600 + int(m[6]) * 60 + int(m[7]) + float("0." + m[8])
            first = a if first is None else first
            last = b
    return (first, last) if first is not None else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="+", help="session dirs (or a whole summaries/ tree)")
    ap.add_argument("-n", "--ngram", type=int, default=4)
    ap.add_argument("--same", type=float, default=25.0, help="%%%% at/above which two texts are the same recording")
    ap.add_argument("--noise", type=float, default=5.0, help="%%%% at/below which two texts are unrelated")
    ap.add_argument("--min-tokens", type=int, default=500)
    ap.add_argument("--include-prose", action="store_true",
                    help="also compare narrative .md with no speaker markup (noisy)")
    args = ap.parse_args()

    docs: dict[Path, set] = {}
    audio: list[Path] = []
    for r in args.roots:
        root = Path(r)
        for p in (sorted(root.rglob("*")) if root.is_dir() else [root]):
            if not p.is_file() or "Zone.Identifier" in p.name:
                continue
            if p.suffix.lower() in AUDIO_EXT:
                audio.append(p)
                continue
            try:
                if not is_transcript(p, args.include_prose):
                    continue
                toks = md_tokens(p) if p.suffix.lower() in {".md", ".txt"} else vtt_tokens(p)
            except Exception as e:                                    # noqa: BLE001
                print(f"  ! unreadable: {p} ({e})", file=sys.stderr)
                continue
            if len(toks) >= args.min_tokens:
                docs[p] = grams(toks, args.ngram)

    if len(docs) < 2:
        print("need at least two transcripts with content to compare")
        return 1

    pct: dict[frozenset, float] = {}
    for a, b in itertools.combinations(docs, 2):
        inter = len(docs[a] & docs[b])
        pct[frozenset((a, b))] = 100 * inter / max(1, min(len(docs[a]), len(docs[b])))

    def score(a: Path, b: Path) -> float:
        return pct[frozenset((a, b))]

    matches = {a: sorted((b for b in docs if b is not a and score(a, b) >= args.same),
                         key=lambda b: -score(a, b)) for a in docs}

    print(f"{len(docs)} transcripts, {len(audio)} audio files, {args.ngram}-grams")
    print(f"same-recording ≥{args.same:g}%   noise floor ≤{args.noise:g}%\n")

    # Spanning files must be identified BEFORE grouping. A whole-day transcript
    # matches two recordings that do not match each other; if it is swept into
    # the first group that claims it, it silently fuses two recordings and the
    # misfiling report becomes nonsense.
    spanning = [(a, matches[a]) for a in sorted(docs)
                if len(matches[a]) >= 2
                and any(score(x, y) < args.same
                        for x, y in itertools.combinations(matches[a], 2))]
    span_set = {a for a, _ in spanning}

    seen, groups = set(span_set), []
    for a in sorted(docs):
        if a in seen:
            continue
        members = sorted({a, *(p for p in matches[a] if p not in span_set)})
        seen.update(members)
        groups.append(members)

    for i, members in enumerate(sorted(groups, key=lambda g: (-len(g), g)), 1):
        dirs = sorted({m.parent for m in members})
        print(f"── recording {i} " + "─" * 50)
        for m in members:
            sp = vtt_span(m)
            when = f"{fmt_hms(sp[0])}–{fmt_hms(sp[1])}" if sp else "no timeline"
            peer = f"  [{score(m, members[0]):.0f}% vs first]" if m is not members[0] and len(members) > 1 else ""
            print(f"     {m}   ({when}){peer}")
        near = sorted(a for a in audio if a.parent in dirs)
        for a in near:
            print(f"     audio: {a}")
        if not near:
            print("     audio: none in these directories")
        if len(dirs) > 1:
            print(f"     ⚠ MISFILED — one recording's transcripts sit in {len(dirs)} directories:")
            for d in dirs:
                print(f"         {d}/")
        print()

    for a, peers in spanning:
        sp = vtt_span(a)
        print(f"── SPANS MULTIPLE RECORDINGS " + "─" * 38)
        print(f"     {a}")
        if sp:
            print(f"     covers {fmt_hms(sp[0])}–{fmt_hms(sp[1])}, and matches:")
        for b in peers:
            print(f"       {score(a, b):5.1f}%  {b}")
        print("     → a whole-day transcript spanning back-to-back recordings.")
        print("       Slice it per recording before joining anything to audio.\n")

    # The dangerous case is not a bare .m4a -- it is a transcript sitting beside
    # an .m4a it does not transcribe. That reads as a matched pair to every
    # human and every downstream tool.
    for g in groups:
        for m in g:
            stray = [a for a in audio if a.parent == m.parent]
            if stray and not any(a.stem.split(".")[0] in m.name or m.stem.split(".")[0] in a.name
                                 for a in stray):
                print(f"⚠ {m}")
                print(f"    sits beside audio it does NOT transcribe: "
                      f"{', '.join(a.name for a in stray)}")
                print(f"    its real recording is not in this tree.")
    for a in sorted(audio):
        if not any(a.parent == m.parent for g in groups for m in g) and \
           not any(a.parent == s.parent for s, _ in spanning):
            print(f"⚠ audio with no transcript at all in its directory: {a}")

    grey = [(v, *sorted(k)) for k, v in pct.items() if args.noise < v < args.same]
    if grey:
        print("\n⚠ ambiguous pairs, between the noise floor and the threshold.")
        print("  These have not occurred in practice — investigate before trusting either verdict:")
        for v, a, b in sorted(grey, reverse=True):
            print(f"    {v:5.1f}%  {a}  <->  {b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
