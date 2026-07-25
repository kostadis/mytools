#!/usr/bin/env python3
"""Flag where a Zoom transcript likely missed/mangled a campaign proper noun,
using the vocabulary-biased retranscription as the signal.

Zoom's transcript is the base text -- this never rewrites it. A plain diff
between Zoom's text and the retranscription is noisy because two independent
ASR passes disagree on phrasing, fillers, and punctuation almost everywhere,
not just on proper nouns. Anchoring on campaign-vocabulary membership instead
of "did the words change" cuts that noise out: for each cue group, this
checks whether a vocabulary term shows up (confidently) in the
retranscription but not (even loosely) in Zoom's own text for that same
span, and only reports those spots.

Usage:
  proper_noun_review.py <zoom.vtt> <retranscribed.vtt> [--campaign-root DIR] [--output PATH]
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vocab  # noqa: E402
import vtt_scaffold  # noqa: E402

_WORD_RE = re.compile(r"[A-Za-z']+")

# How confidently a vocab term must show up in the retranscription to count
# as "the biased ASR actually heard this name". A near-exact fuzzy match
# (not a strict 1.0) absorbs minor ASR noise right around the biased word
# itself (e.g. a trailing 's', a dropped apostrophe).
PRESENT_THRESHOLD = 0.90


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _best_match(term_tokens: list[str], text_tokens: list[str]) -> tuple[float, str]:
    """Best fuzzy-match score for `term_tokens` (a vocab term's words) as a
    contiguous window anywhere in `text_tokens`, plus the matched substring.
    Skips windows whose length can't possibly reach PRESENT_THRESHOLD --
    difflib's ratio is bounded by 2*min(len)/(len(a)+len(b))."""
    w = len(term_tokens)
    if w == 0 or len(text_tokens) < w:
        return 0.0, ""
    target = " ".join(term_tokens)
    target_len = len(target)
    best_score, best_window = 0.0, ""
    for i in range(len(text_tokens) - w + 1):
        window = text_tokens[i:i + w]
        window_str = " ".join(window)
        max_possible = 2 * min(target_len, len(window_str)) / (target_len + len(window_str))
        if max_possible < PRESENT_THRESHOLD:
            continue
        score = _ratio(target, window_str)
        if score > best_score:
            best_score, best_window = score, window_str
    return best_score, best_window


def _exact_window_present(term_tokens: list[str], text_tokens: list[str]) -> bool:
    """True if `term_tokens` (already lowercased) appears verbatim, case-
    insensitively, as a contiguous window in `text_tokens` (already
    lowercased). Deliberately exact, not fuzzy: the whole point of this tool
    is to catch near-miss spellings ("Toblin" for canonical "Toblen") that a
    fuzzy threshold would wave through as "close enough" -- that near-miss
    *is* the miss. Zoom only counts as "already right" if it has the exact
    canonical spelling."""
    w = len(term_tokens)
    if w == 0 or len(text_tokens) < w:
        return False
    for i in range(len(text_tokens) - w + 1):
        if text_tokens[i:i + w] == term_tokens:
            return True
    return False


@dataclass
class Finding:
    term: str
    retranscription_snippet: str
    retranscription_score: float
    zoom_best_snippet: str
    zoom_best_score: float


@dataclass
class FlaggedGroup:
    start: float
    end: float
    speaker: str
    zoom_text: str
    retranscription_text: str
    findings: list[Finding]


def review(
    zoom_groups: list[vtt_scaffold.CueGroup],
    retr_cues: list[vtt_scaffold.Cue],
    vocabulary: list[str],
    present_threshold: float = PRESENT_THRESHOLD,
) -> list[FlaggedGroup]:
    if len(zoom_groups) != len(retr_cues):
        raise ValueError(
            f"cue-group count mismatch: zoom={len(zoom_groups)} retranscribed={len(retr_cues)} "
            "-- likely a --max-group-seconds mismatch, or these aren't a matched pair")

    vocab_terms = [(term, _tokenize(term)) for term in vocabulary]
    flagged: list[FlaggedGroup] = []

    for group, retr in zip(zoom_groups, retr_cues):
        if vtt_scaffold.is_system_caption_speaker(group.speaker):
            continue
        if group.original_text.strip().lower() == retr.text.strip().lower():
            continue

        zoom_tokens = _tokenize(group.original_text)
        retr_tokens = _tokenize(retr.text)
        zoom_tokens_lower = [t.lower() for t in zoom_tokens]
        findings: list[Finding] = []
        for term, term_tokens in vocab_terms:
            retr_score, retr_snippet = _best_match(term_tokens, retr_tokens)
            if retr_score < present_threshold:
                continue
            term_tokens_lower = [t.lower() for t in term_tokens]
            if _exact_window_present(term_tokens_lower, zoom_tokens_lower):
                continue
            zoom_score, zoom_snippet = _best_match(term_tokens, zoom_tokens)
            findings.append(Finding(term, retr_snippet, retr_score, zoom_snippet, zoom_score))

        if findings:
            flagged.append(FlaggedGroup(
                start=group.start, end=group.end, speaker=group.speaker,
                zoom_text=group.original_text, retranscription_text=retr.text,
                findings=findings))

    return flagged


def render_report(
    flagged: list[FlaggedGroup], total_groups: int, zoom_path: Path, retr_path: Path,
) -> str:
    lines = [
        f"# Proper-noun review: {zoom_path.name} vs {retr_path.name}",
        "",
        "Zoom's transcript is the base text below -- nothing here has been changed.",
        "Each entry means the vocabulary-biased retranscription found a campaign name",
        "that doesn't clearly appear in Zoom's own text for that same span. Confirm real",
        "fixes through `/vtt-spell-pass`; this is a report, not an edit.",
        "",
        f"Scanned {total_groups} cue groups, flagged {len(flagged)}.",
        "",
    ]
    for g in flagged:
        lines.append(f"## [{vtt_scaffold.seconds_to_timestamp(g.start)} -> "
                      f"{vtt_scaffold.seconds_to_timestamp(g.end)}] {g.speaker}")
        lines.append(f"**Zoom:** {g.zoom_text}")
        lines.append("")
        lines.append(f"**Retranscription:** {g.retranscription_text}")
        lines.append("")
        for f in g.findings:
            zoom_note = (f'"{f.zoom_best_snippet}" ({f.zoom_best_score:.2f})'
                         if f.zoom_best_snippet else "no match")
            lines.append(f"- **{f.term}** -- retranscription: \"{f.retranscription_snippet}\" "
                         f"({f.retranscription_score:.2f}); Zoom's closest: {zoom_note}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zoom_vtt", type=Path, help="Zoom's original .vtt (the base text)")
    ap.add_argument("retranscribed_vtt", type=Path,
                    help="The .retranscribed.vtt (or .cleaned.vtt) from retranscribe.py")
    ap.add_argument("--campaign-root", type=Path, default=None,
                    help="Campaign root (default: auto-detected by walking up from <zoom_vtt>)")
    ap.add_argument("--max-group-seconds", type=float, default=25.0,
                    help="Must match the value retranscribe.py used to produce <retranscribed_vtt>")
    ap.add_argument("--present-threshold", type=float, default=PRESENT_THRESHOLD)
    ap.add_argument("--output", type=Path, default=None,
                    help="Report path (default: '<retranscribed-stem>.proper_nouns.md')")
    return ap


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)

    if not args.zoom_vtt.exists():
        print(f"ERROR: {args.zoom_vtt} not found", file=sys.stderr)
        return 1
    if not args.retranscribed_vtt.exists():
        print(f"ERROR: {args.retranscribed_vtt} not found", file=sys.stderr)
        return 1

    campaign_root = args.campaign_root or vocab.find_campaign_root(args.zoom_vtt.resolve().parent)
    if not campaign_root:
        print("ERROR: no campaign root found/given -- nothing to check names against.", file=sys.stderr)
        return 1
    vocabulary = vocab.gather_vocabulary(campaign_root)
    print(f"Campaign root: {campaign_root} ({len(vocabulary)} vocabulary terms)")

    zoom_cues = vtt_scaffold.parse_zoom_vtt(args.zoom_vtt.read_text(encoding="utf-8", errors="replace"))
    zoom_groups = vtt_scaffold.group_cues(zoom_cues, max_group_seconds=args.max_group_seconds)
    retr_cues = vtt_scaffold.parse_zoom_vtt(
        args.retranscribed_vtt.read_text(encoding="utf-8", errors="replace"))

    try:
        flagged = review(zoom_groups, retr_cues, vocabulary,
                          present_threshold=args.present_threshold)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    report = render_report(flagged, len(zoom_groups), args.zoom_vtt, args.retranscribed_vtt)
    output_path = args.output or args.retranscribed_vtt.with_name(
        args.retranscribed_vtt.stem + ".proper_nouns.md")
    output_path.write_text(report, encoding="utf-8")
    print(f"Scanned {len(zoom_groups)} cue groups, flagged {len(flagged)}. Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
