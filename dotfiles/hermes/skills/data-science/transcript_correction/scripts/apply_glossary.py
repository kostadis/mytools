#!/usr/bin/env python3
"""Apply a source-of-truth glossary to transcript/artifact files.

Usage: python3 apply_glossary.py FILE [FILE ...]

- Word-boundary-safe, case-insensitive substitutions (no substring bleed:
  e.g. \bMela\b -> Maela won't touch "Melavera").
- Reads/writes in BINARY so CRLF line endings (required by WebVTT) are
  preserved exactly. Only the proper nouns change.
- RULE: only include TRUE garbles here. Do NOT include title/short-form or
  player->character mappings (e.g. Sildar -> Sildar Hallwinter, Nikhil -> Zenvon)
  -- a word-boundary applier would double-expand them. Those belong in the
  glossary file's separate alias generator.

Edit CORRECTIONS to match the campaign's glossary source of truth.
"""
import re
import sys

CORRECTIONS = [
    # PCs
    (r"\bXenophon\b", "Zenvon"),
    (r"\bZenobon\b",  "Zenvon"),
    (r"\bZenovon\b",  "Zenvon"),
    (r"\bXenovan\b",  "Zenvon"),
    (r"\bXenobon\b",  "Zenvon"),
    (r"\bVera\b",     "Veyra"),
    (r"\bMela\b",     "Maela"),
    # NPCs and creatures
    (r"\bClarg\b",         "Klarg"),
    (r"\bToblin\b",        "Toblen"),
    (r"\bGlastaff\b",      "Glasstaff"),
    (r"\bDarren Edermeth\b", "Daran Edermath"),
    (r"\bOren Voss\b",     "Orryn Voss"),
    # Locations
    (r"\bTresender Manor\b",  "Tresendar Manor"),
    (r"\bTressander Manor\b", "Tresendar Manor"),
    (r"\bEldermath Orchard\b", "Edermath Orchard"),
    (r"\bNethrel\b",       "Netheril"),
    (r"\bTribor Trail\b",  "Triboar Trail"),
]

COMPILED = [(re.compile(p, re.IGNORECASE), repl) for p, repl in CORRECTIONS]


def apply(text):
    for rx, repl in COMPILED:
        text = rx.sub(repl, text)
    return text


def main():
    files = sys.argv[1:]
    if not files:
        print("usage: python3 apply_glossary.py FILE [FILE ...]")
        sys.exit(2)
    for path in files:
        with open(path, "rb") as f:
            raw = f.read()
        text = raw.decode("utf-8")
        corrected = apply(text)
        a = text.split("\n")
        b = corrected.split("\n")
        n_lines = sum(1 for x, y in zip(a, b) if x != y)
        with open(path, "wb") as f:
            f.write(corrected.encode("utf-8"))
        print(f"{path}: {n_lines} lines changed")


if __name__ == "__main__":
    main()
