#!/usr/bin/env python3
"""Deterministic proper-noun PHRASE candidate extraction — module-inventory Phase 1.

Two source modes, auto-detected by extension:

  - prose (.md / .txt): regex-scans for runs of 1-4 capitalised words.
    Markdown headers (# / ##) are collected separately as high-confidence
    section-title candidates. A single-word candidate is only kept if it
    appears at least once NOT at the start of a line (pure sentence-initial
    capitalisation is a weak signal); multi-word runs are always kept — that
    pattern is a much stronger name signal and rare as a false positive.

  - json (.json, 5etools-style book/adventure JSON): recursively walks the
    structure. String values under a "name"/"title"/"heading" key are
    high-confidence structural titles (5etools book JSON already spells these
    correctly — e.g. "Temple of Elemental Evil" — so no regex is needed).
    `{@tag Name|Source}` 5etools reference markup is extracted with its tag,
    mapped to a coarse category where the tag is unambiguous. Every other
    string leaf is scanned with the same phrase regex as the prose path,
    cited by a JSON breadcrumb path instead of a line number.

This is Phase 1 of the module-inventory skill: a cheap, deterministic pass
that gives the Phase 2 LLM grouping/description pass something concrete to
work from, instead of asking it to invent the candidate list from scratch.
Scope decisions (what counts as a name, what the categories are) are for a
human to review before promotion — this script only surfaces raw material.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

WORD = r"[A-Z][a-zA-Z'’\-]*"
PHRASE_RE = re.compile(rf"\b{WORD}(?:\s+{WORD}){{0,3}}\b")
HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TAG_RE = re.compile(r"\{@(\w+)\s+([^|}]+)")

STOPWORDS = {
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
    "Chapter", "Part", "Section", "Appendix", "Table", "Figure", "Page",
    "I", "I'm", "I've", "I'll", "I'd",
    "DM", "GM", "DC", "AC", "HP", "XP", "PC", "NPC", "STR", "DEX", "CON",
    "INT", "WIS", "CHA", "CR",
    "Yeah", "Okay", "OK", "Yes", "No", "Right", "Cool", "Nice", "Sure",
    "Actually", "Anyway", "Anyways", "Also", "But", "And", "Or", "So",
    "Then", "There", "Thanks", "Thank", "Hello", "Hi", "Hey", "Oh",
    "Well", "Wait", "Look", "Listen", "Maybe", "Perhaps", "Sorry",
    "Definitely", "Probably", "Alright", "Welcome", "Goodbye",
    "You", "Your", "Yours", "We", "Us", "Our", "Ours", "They", "Them",
    "Their", "Theirs", "He", "She", "It", "His", "Hers", "Its",
    "That", "This", "These", "Those", "Here", "Where", "When",
    "What", "Why", "How", "Who", "Whom", "Whose", "Which",
    "If", "Unless", "Because", "Although", "Though", "While", "Whereas",
    "Let", "Make", "Take", "Give", "Get", "Go", "Come", "Sounds",
    "Mr", "Mrs", "Ms", "Dr", "Sir", "Lord", "Lady",
    "The", "A", "An", "As", "At", "By", "For", "From", "In", "Into",
    "Of", "On", "Or", "To", "With",
}

TAG_CATEGORY = {
    "creature": "creature", "deity": "deity", "item": "item", "spell": "item",
    "class": "other", "race": "other", "background": "other",
    "condition": "other", "disease": "other", "action": "other",
    "skill": "other", "sense": "other", "hazard": "creature",
    "vehicle": "item", "object": "item", "trap": "other", "reward": "item",
    "optfeature": "other", "feat": "other", "table": "other", "book": "other",
    "adventure": "other", "variantrule": "other", "boon": "other",
}

# 5etools tags that wrap mechanics (dice, DCs, damage, formatting), not names —
# excluded outright rather than falling into TAG_CATEGORY's "other" bucket.
TAG_EXCLUDE = {
    "dice", "hit", "damage", "recharge", "chance", "dc", "d20", "scaledice",
    "scaledamage", "filter", "note", "i", "b", "s", "u", "5etools",
    "homebrew", "quickref", "footnote", "link", "loader", "area",
}


def _is_stop_phrase(phrase: str) -> bool:
    words = phrase.split()
    return all(w in STOPWORDS for w in words)


POSSESSIVE_RE = re.compile(r"['’]s$")


def _strip_possessive(phrase: str) -> str:
    return POSSESSIVE_RE.sub("", phrase)


def extract_prose_candidates(text: str, max_words: int = 4) -> dict:
    section_titles = []
    counts: dict[str, int] = {}
    lines_by_phrase: dict[str, list[int]] = {}
    mid_line_seen: set[str] = set()

    for lineno, line in enumerate(text.splitlines(), 1):
        h = HEADER_RE.match(line)
        if h:
            section_titles.append({"title": h.group(2).strip(), "line": lineno, "level": len(h.group(1))})

        for m in PHRASE_RE.finditer(line):
            phrase = _strip_possessive(m.group(0).strip())
            words = phrase.split()
            if len(words) > max_words or _is_stop_phrase(phrase):
                continue
            if len(phrase) < 3:
                continue
            counts[phrase] = counts.get(phrase, 0) + 1
            samples = lines_by_phrase.setdefault(phrase, [])
            if len(samples) < 8:
                samples.append(lineno)
            if m.start() != 0:
                mid_line_seen.add(phrase)

    candidates = []
    for phrase, count in counts.items():
        words = phrase.split()
        if len(words) == 1 and phrase not in mid_line_seen:
            continue  # single-word, sentence-initial-only: too weak to keep
        candidates.append({"phrase": phrase, "count": count, "lines": lines_by_phrase[phrase]})

    candidates.sort(key=lambda c: (-c["count"], c["phrase"]))
    return {"section_titles": section_titles, "candidates": candidates}


def _walk_json(obj, path: str, prose_buf: list[tuple[str, str]], structural: list[dict], tagged: list[dict]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            child_path = f"{path}.{k}"
            if k in ("name", "title", "heading") and isinstance(v, str) and v.strip():
                structural.append({"title": v.strip(), "path": child_path})
            _walk_json(v, child_path, prose_buf, structural, tagged)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _walk_json(item, f"{path}[{i}]", prose_buf, structural, tagged)
    elif isinstance(obj, str):
        for m in TAG_RE.finditer(obj):
            tag, ref = m.group(1).lower(), m.group(2).strip()
            if tag in TAG_EXCLUDE:
                continue
            name = ref.split("|")[0].strip()
            if name and not name[0].isdigit():
                name = name[0].upper() + name[1:] if name[0].isalpha() else name
                tagged.append({"name": name, "tag": tag, "category": TAG_CATEGORY.get(tag, "other"), "path": path})
        prose_buf.append((path, obj))


def extract_json_candidates(obj, max_words: int = 4) -> dict:
    prose_buf: list[tuple[str, str]] = []
    structural: list[dict] = []
    tagged: list[dict] = []
    _walk_json(obj, "$", prose_buf, structural, tagged)

    counts: dict[str, int] = {}
    paths_by_phrase: dict[str, list[str]] = {}
    for path, text in prose_buf:
        text = re.sub(r"\{@\w+\s+[^}]*\}", " ", text)  # strip tag markup before phrase scan
        for m in PHRASE_RE.finditer(text):
            phrase = _strip_possessive(m.group(0).strip())
            words = phrase.split()
            if len(words) > max_words or _is_stop_phrase(phrase) or len(phrase) < 3:
                continue
            counts[phrase] = counts.get(phrase, 0) + 1
            samples = paths_by_phrase.setdefault(phrase, [])
            if len(samples) < 8:
                samples.append(path)

    candidates = [
        {"phrase": phrase, "count": count, "paths": paths_by_phrase[phrase]}
        for phrase, count in counts.items()
    ]
    candidates.sort(key=lambda c: (-c["count"], c["phrase"]))

    # dedupe structural titles and tagged refs, keep first path seen + a count
    def _dedupe(items: list[dict], key: str) -> list[dict]:
        seen: dict[str, dict] = {}
        for item in items:
            k = item[key]
            if k not in seen:
                seen[k] = {**item, "count": 1, "paths": [item["path"]]}
                seen[k].pop("path", None)
            else:
                seen[k]["count"] += 1
                if len(seen[k]["paths"]) < 8:
                    seen[k]["paths"].append(item["path"])
        return sorted(seen.values(), key=lambda x: (-x["count"], x[key]))

    return {
        "section_titles": _dedupe(structural, "title"),
        "tagged_refs": _dedupe(tagged, "name"),
        "candidates": candidates,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path)
    ap.add_argument("--format", choices=["auto", "prose", "json"], default="auto")
    ap.add_argument("--max-words", type=int, default=4)
    ap.add_argument("--out", type=Path, default=None, help="default: stdout")
    args = ap.parse_args()

    fmt = args.format
    if fmt == "auto":
        fmt = "json" if args.source.suffix.lower() == ".json" else "prose"

    if fmt == "json":
        obj = json.loads(args.source.read_text(encoding="utf-8"))
        result = extract_json_candidates(obj, max_words=args.max_words)
    else:
        text = args.source.read_text(encoding="utf-8")
        result = extract_prose_candidates(text, max_words=args.max_words)

    result["meta"] = {"source": str(args.source), "format": fmt}
    out_text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(out_text, encoding="utf-8")
        print(f"wrote {args.out} ({len(result['candidates'])} phrase candidates)", file=sys.stderr)
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
