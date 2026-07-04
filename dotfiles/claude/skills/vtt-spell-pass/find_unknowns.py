#!/usr/bin/env python3
"""Find proper-noun candidates in a VTT transcript that are NOT in the
campaign's known-names set.

Inputs:
  --vtt <path>         VTT transcript file
  --glossary <path>    notes/vtt_transcription_corrections.md
  --npcs-dir <path>    docs/npcs/
  --extra-known <path> Optional plain-text file, one canonical name per line
                       (PCs, players, common module proper nouns, etc.)

Outputs JSON to stdout:
  {
    "applied_replacements": [{"wrong": "...", "right": "...", "count": N}, ...],
    "unknown_propers": [
      {"token": "Vulking Valve", "count": 3, "contexts": ["...line excerpt..."]},
      ...
    ],
    "known_names": [...]   # for debugging
  }

Heuristics:
- Glossary tables are parsed for both the wrong-list (left col) and the
  canonical form (right col, with **bolding** stripped).
- NPC dossiers contribute the H1 title plus any "Aliases:" / "Also known as:"
  lines, plus a humanised version of the filename.
- A token is a "proper noun candidate" if it is:
    * a Capitalised word (or hyphenated/apostrophe'd run)
    * OR a multi-word run of Capitalised words (max 4)
  AND it appears at least once mid-sentence (not only sentence-initial),
  filtering out ordinary capitalised-after-period words.
- Speaker labels (`Name (Player):` at line start) are stripped before
  scanning so character names in labels don't get flagged.
- Possessive `'s` is stripped for matching.
- Stopwords (a small list of common false positives) are filtered out.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

STOPWORDS = {
    # Days, months, common capitalised non-names
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
    # Pronouns / sentence starters that get capitalised
    "I", "I'm", "I've", "I'll", "I'd",
    # D&D mechanical terms that surface in transcripts
    "DM", "GM", "DC", "AC", "HP", "XP", "PC", "NPC", "STR", "DEX", "CON",
    "INT", "WIS", "CHA",
    # Generic conversational
    "Yeah", "Okay", "OK", "Yes", "No", "Right", "Cool", "Nice", "Sure",
    "Actually", "Anyway", "Anyways", "Also", "But", "And", "Or", "So",
    "Then", "There", "Thanks", "Thank", "Hello", "Hi", "Hey", "Oh",
    "Well", "Wait", "Look", "Listen", "Maybe", "Perhaps", "Sorry",
    "Definitely", "Probably", "Alright", "Welcome", "Goodbye",
    # Pronouns & conjunctions that get capitalised mid-sentence (Otter
    # capitalises after commas, em-dashes, quotes — surfaces a lot)
    "You", "Your", "Yours", "We", "Us", "Our", "Ours", "They", "Them",
    "Their", "Theirs", "He", "She", "It", "His", "Hers", "Its",
    "That", "This", "These", "Those", "There", "Here", "Where", "When",
    "What", "Why", "How", "Who", "Whom", "Whose", "Which",
    "If", "Unless", "Because", "Although", "Though", "While", "Whereas",
    "Let", "Make", "Take", "Give", "Get", "Go", "Come", "Sounds",
    "Mr", "Mrs", "Ms", "Dr", "Sir", "Lord", "Lady",
    "God", "Lord", "Christ", "Jesus",
    # Common D&D mechanics that are capitalised
    "Insight", "Perception", "Investigation", "Persuasion", "Deception",
    "Intimidation", "Athletics", "Acrobatics", "Stealth", "Survival",
    "Arcana", "History", "Religion", "Nature", "Medicine",
}


def parse_glossary(path: Path) -> tuple[list[tuple[str, str]], set[str]]:
    """Parse the markdown corrections file.

    Returns (replacements, canonicals) where:
      replacements = list of (wrong_form, canonical) pairs
      canonicals   = set of canonical forms (right-col text, stripped of
                     **bold**, parentheticals)
    """
    if not path.exists():
        return [], set()

    replacements: list[tuple[str, str]] = []
    canonicals: set[str] = set()

    bold_re = re.compile(r"\*\*(.+?)\*\*")
    paren_re = re.compile(r"\s*\([^)]*\)\s*$")

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("|---") or line.startswith("| Wrong"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 2:
            continue
        wrong_col, right_col = cols[0], cols[1]

        m = bold_re.search(right_col)
        canonical = m.group(1).strip() if m else right_col
        canonical = paren_re.sub("", canonical).strip()
        if canonical:
            canonicals.add(canonical)

        for variant in wrong_col.split(","):
            v = variant.strip()
            if v:
                replacements.append((v, canonical))

    return replacements, canonicals


def parse_npc_dossiers(npcs_dir: Path) -> set[str]:
    names: set[str] = set()
    if not npcs_dir.exists():
        return names

    alias_re = re.compile(r"^\s*[-*]?\s*(?:aka|also known as|aliases?)\s*[:\-]\s*(.+)$", re.I)
    h1_re = re.compile(r"^#\s+(.+?)\s*$")

    for p in npcs_dir.glob("*.md"):
        if p.name.startswith("."):
            continue
        # Humanise filename: asha_vandree.md -> Asha Vandree
        humanised = " ".join(w.capitalize() for w in p.stem.split("_"))
        names.add(humanised)

        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for line in text.splitlines()[:60]:
            mh = h1_re.match(line)
            if mh:
                names.add(mh.group(1).strip())
            ma = alias_re.match(line)
            if ma:
                for alias in re.split(r"[,/;]", ma.group(1)):
                    a = alias.strip().strip("`*\"'")
                    if a:
                        names.add(a)
    return names


def load_extra(paths: Path | list[Path] | None) -> set[str]:
    """Load verified-noun dictionaries. Accepts a single Path (back-compat),
    a list of Paths, or None. Each file is a flat one-name-per-line dump;
    blank lines and lines starting with '#' are ignored."""
    if not paths:
        return set()
    if isinstance(paths, Path):
        paths = [paths]
    names: set[str] = set()
    for path in paths:
        if not path or not path.exists():
            continue
        names |= {
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
    return names


# Otter/Zoom speaker labels at line start. Two patterns:
#   1) "Name (Player):"  — campaign-style label
#   2) "First Last:"     — Otter default (1-3 capitalised words then colon)
SPEAKER_RE = re.compile(
    r"^\s*(?:"
    r"[A-Z][\w'\-]+(?:\s+[A-Z][\w'\-]+){0,3}\s*\([^)]+\)"
    r"|"
    r"[A-Z][\w'\-]+(?:\s+[A-Z][\w'\-]+){0,2}"
    r")\s*:\s*",
    re.M,
)
TIMESTAMP_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d+\s*-->\s*\d{2}:\d{2}:\d{2}\.\d+\s*$", re.M)
WEBVTT_RE = re.compile(r"^WEBVTT.*$", re.M)
CUE_NUM_RE = re.compile(r"^\d+\s*$", re.M)

PROPER_RE = re.compile(
    r"\b([A-Z][a-z'\-]+(?:[ \-][A-Z][a-z'\-]+){0,3})\b"
)
SENTENCE_END = re.compile(r"[.!?]\s+")


def extract_text(vtt_text: str) -> str:
    # Strip cue metadata; keep dialogue body
    lines = []
    for line in vtt_text.splitlines():
        if WEBVTT_RE.match(line):
            continue
        if TIMESTAMP_RE.match(line):
            continue
        if CUE_NUM_RE.match(line):
            continue
        # Strip speaker labels
        line = SPEAKER_RE.sub("", line)
        lines.append(line)
    return "\n".join(lines)


def find_propers(text: str, known: set[str]) -> dict[str, dict]:
    """Find capitalised tokens that look like proper nouns and aren't known.

    Returns {token: {"count": int, "contexts": [str, ...]}} for unknown tokens.
    """
    # Build lowercase-stripped known set for matching
    known_lc = {k.lower() for k in known}

    # Track sentence-initial vs mid-sentence positions
    # A token is "real proper noun" if it appears mid-sentence at least once
    # OR if its single-word form is also seen mid-sentence
    mid_sentence_tokens: set[str] = set()
    all_hits: dict[str, dict] = defaultdict(lambda: {"count": 0, "contexts": []})

    # Build sentence-position map
    for paragraph in text.split("\n"):
        # Split into sentences (rough)
        sentences = re.split(SENTENCE_END, paragraph)
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            for m in PROPER_RE.finditer(sent):
                tok = m.group(1)
                if m.start() > 0:
                    mid_sentence_tokens.add(tok)
                    # Each word of multi-word also counts as mid-sentence
                    for w in tok.split():
                        mid_sentence_tokens.add(w)
                else:
                    # Sentence-initial: also count as legit if the sentence
                    # body IS just this token (one-word answer like
                    # "Bukraden."). Stopword-style sentence-leaders ("Yeah.",
                    # "Sounds.") still get filtered downstream by STOPWORDS.
                    remainder = (sent[: m.start()] + sent[m.end():]).strip(" .,!?\"'")
                    if not remainder:
                        mid_sentence_tokens.add(tok)
                        for w in tok.split():
                            mid_sentence_tokens.add(w)

    # Now collect unknown propers, gating on mid-sentence appearance
    seen_contexts: dict[str, list[str]] = defaultdict(list)
    for paragraph in text.split("\n"):
        for m in PROPER_RE.finditer(paragraph):
            tok = m.group(1)
            tok_clean = re.sub(r"'s$", "", tok)
            # Skip if it's known (any case)
            if tok_clean.lower() in known_lc:
                continue
            # Skip if any word is a stopword AND it's a single token
            if " " not in tok_clean and tok_clean in STOPWORDS:
                continue
            # Multi-word: if any constituent is purely a stopword, drop it only if all are
            if " " in tok_clean:
                parts = tok_clean.split()
                if all(p in STOPWORDS for p in parts):
                    continue
            # Must appear mid-sentence somewhere (filters sentence-initial false positives)
            if tok_clean not in mid_sentence_tokens and not any(
                w in mid_sentence_tokens for w in tok_clean.split()
            ):
                continue
            all_hits[tok_clean]["count"] += 1
            if len(seen_contexts[tok_clean]) < 3:
                # Capture surrounding context
                start = max(0, m.start() - 40)
                end = min(len(paragraph), m.end() + 40)
                ctx = paragraph[start:end].strip()
                seen_contexts[tok_clean].append(ctx)

    for tok, ctxs in seen_contexts.items():
        all_hits[tok]["contexts"] = ctxs

    return dict(all_hits)


def apply_replacements_dryrun(text: str, replacements: list[tuple[str, str]]) -> list[dict]:
    """Count how many times each known wrong-form would be replaced.

    Does not modify text — that happens in a separate pass after user approval.
    """
    out = []
    for wrong, right in replacements:
        # Word-boundary, case-sensitive (transcripts are mixed case; prefer
        # exactness to avoid clobbering in-progress NPC names)
        pattern = re.compile(r"\b" + re.escape(wrong) + r"\b")
        n = len(pattern.findall(text))
        if n:
            out.append({"wrong": wrong, "right": right, "count": n})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vtt", required=True, type=Path)
    ap.add_argument("--glossary", required=True, type=Path)
    ap.add_argument("--npcs-dir", required=True, type=Path)
    ap.add_argument("--extra-known", type=Path, nargs="*", default=[],
                    help="One or more flat one-name-per-line dictionaries of "
                         "verified nouns (e.g. notes/proper_nouns_adventure.txt)")
    ap.add_argument("--min-count", type=int, default=1,
                    help="Only report unknowns appearing at least this many times")
    args = ap.parse_args()

    vtt_text = args.vtt.read_text(encoding="utf-8")
    text = extract_text(vtt_text)

    replacements, canonicals = parse_glossary(args.glossary)
    npc_names = parse_npc_dossiers(args.npcs_dir)
    extra = load_extra(args.extra_known)

    # Known set = canonicals + npc names + extras + already-classified
    # wrong-forms (so we don't re-ask about misspellings the user already
    # decided about) + their constituent words.
    wrong_forms = {w for w, _ in replacements}
    known = set(canonicals) | npc_names | extra | wrong_forms
    # Add single-word forms of multi-word names so "Asha" alone is also known
    for name in list(known):
        for w in name.split():
            if len(w) > 2:
                known.add(w)

    applied = apply_replacements_dryrun(text, replacements)
    unknowns = find_propers(text, known)

    filtered = {
        k: v for k, v in unknowns.items() if v["count"] >= args.min_count
    }
    # Sort by count desc, then alphabetically
    sorted_items = sorted(filtered.items(), key=lambda kv: (-kv[1]["count"], kv[0]))

    out = {
        "vtt": str(args.vtt),
        "applied_replacements": applied,
        "unknown_propers": [
            {"token": k, "count": v["count"], "contexts": v["contexts"]}
            for k, v in sorted_items
        ],
        "known_names_count": len(known),
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
