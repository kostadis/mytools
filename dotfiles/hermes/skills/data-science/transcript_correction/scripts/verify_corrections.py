#!/usr/bin/env python3
"""Ad-hoc verifier: confirm glossary corrections landed correctly.

Usage: python3 verify_corrections.py DIR FILE [FILE ...]

For each FILE, compares it against FILE + ".bak" and checks:
  1. No documented garble tokens remain in the corrected file.
  2. Canonical forms are present (not regressed vs backup).
  3. CRLF line endings preserved (file still WebVTT-CRLF).
  4. Every changed line differs ONLY by a name substitution.

Exits non-zero on any failure. Pair this with apply_glossary.py; run it from a
/tmp path with a hermes-verify- prefix, then delete it.
"""
import os
import re
import sys

GARBLES = [
    r"\bToblin\b", r"\bVera\b", r"\bMela\b", r"\bXenovan\b", r"\bXenobon\b",
    r"\bXenophon\b", r"\bZenobon\b", r"\bZenovon\b", r"\bGlastaff\b", r"\bClarg\b",
    r"\bDarren Edermeth\b", r"\bOren Voss\b", r"\bTresender Manor\b",
    r"\bTressander Manor\b", r"\bEldermath Orchard\b", r"\bNethrel\b", r"\bTribor Trail\b",
]
CANON = [r"\bToblen\b", r"\bVeyra\b", r"\bSister Maela\b", r"\bZenvon\b"]
PAIRS = [
    ("Toblin", "Toblen"), ("Vera", "Veyra"), ("Sister Mela", "Sister Maela"),
    ("Mela", "Maela"), ("Xenovan", "Zenvon"), ("Xenobon", "Zenvon"),
    ("Xenophon", "Zenvon"), ("Zenobon", "Zenvon"), ("Zenovon", "Zenvon"),
]


def count(path, pattern):
    rx = re.compile(pattern, re.IGNORECASE)
    n = 0
    with open(path, "r", encoding="utf-8", newline="") as f:
        for line in f:
            if rx.search(line):
                n += 1
    return n


def main():
    dir_ = sys.argv[1]
    files = sys.argv[2:]
    fails = 0
    for fn in files:
        p = os.path.join(dir_, fn)
        bak = p + ".bak"
        for g in GARBLES:
            if count(p, g) != 0:
                print(f"FAIL {fn}: garble {g} still present")
                fails += 1
        for cpat in CANON:
            if count(p, cpat) < count(bak, cpat):
                print(f"FAIL {fn}: canonical {cpat} count dropped")
                fails += 1
        with open(p, "rb") as f:
            if b"\r\n" not in f.read(4096):
                print(f"FAIL {fn}: CRLF line endings lost")
                fails += 1
        with open(p, "r", encoding="utf-8", newline="") as f:
            newlines = f.read().split("\n")
        with open(bak, "r", encoding="utf-8", newline="") as f:
            oldlines = f.read().split("\n")
        for a, b in zip(oldlines, newlines):
            if a == b:
                continue
            norm_a = a
            for wrong, right in PAIRS:
                norm_a = re.sub(r"\b" + wrong + r"\b", right, norm_a, flags=re.IGNORECASE)
            if norm_a.strip() != b.strip():
                print(f"FAIL {fn}: non-name change: {a[:80]!r} -> {b[:80]!r}")
                fails += 1
                break
    if fails == 0:
        print("PASS: all corrections verified (garbles gone, canon present, CRLF intact, name-only diffs)")
    else:
        print(f"{fails} check(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
