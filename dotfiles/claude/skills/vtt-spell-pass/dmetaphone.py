#!/usr/bin/env python3
"""Vendored Double Metaphone.

Self-contained port of Lawrence Philips' Double Metaphone algorithm
(after the widely-used BSD port by Andrew Collins / oubiwann's `metaphone`
package). Vendored — not pip-installed — so the vtt-spell-pass skill stays
zero-dependency across every machine the dotfiles land on.

`doublemetaphone(word) -> (primary, secondary)` returns two phonetic codes
(secondary may be empty). Two words are phonetic neighbours when any of
their non-empty codes coincide; see `codes()` / `match()` for the helper
the clusterer actually calls.

This is a *recall* aid: every mapping it suggests is confirmed by a human
in the spell-pass, so a rare miscode degrades clustering quality at worst,
never canon.
"""

from __future__ import annotations

VOWELS = frozenset("AEIOUY")


def _is_vowel(s: str, pos: int) -> bool:
    return 0 <= pos < len(s) and s[pos] in VOWELS


def doublemetaphone(word: str) -> tuple[str, str]:
    if not word:
        return "", ""

    primary: list[str] = []
    secondary: list[str] = []
    s = "".join(ch for ch in word.upper() if ch.isalpha())
    if not s:
        return "", ""

    length = len(s)
    last = length - 1
    pos = 0
    # Padding so slice lookahead never IndexErrors.
    s_pad = s + "      "

    def sub(a: int, b: int) -> str:
        return s_pad[a:b]

    def add(p: str, sec: str | None = None) -> None:
        if p:
            primary.append(p)
        secondary.append(sec if sec is not None else p)

    # Skip silent leading letters.
    if sub(0, 2) in ("GN", "KN", "PN", "WR", "PS"):
        pos += 1

    # Initial 'X' sounds like 'S'.
    if s[0:1] == "X":
        add("S")
        pos += 1

    while pos < length:
        c = s_pad[pos]

        if c in VOWELS:
            # Only the leading vowel is encoded.
            if pos == 0:
                add("A")
            pos += 1
            continue

        if c == "B":
            add("P")
            pos += 2 if s_pad[pos + 1] == "B" else 1

        elif c == "Ç":
            add("S")
            pos += 1

        elif c == "C":
            # Various Germanic / soft-c cases.
            if (
                pos > 1
                and not _is_vowel(s, pos - 2)
                and sub(pos - 1, pos + 2) == "ACH"
                and s_pad[pos + 2] != "I"
                and (
                    s_pad[pos + 2] != "E"
                    or sub(pos - 2, pos + 4) in ("BACHER", "MACHER")
                )
            ):
                add("K")
                pos += 2
            elif pos == 0 and sub(0, 6) == "CAESAR":
                add("S")
                pos += 2
            elif sub(pos, pos + 4) == "CHIA":
                add("K")
                pos += 2
            elif sub(pos, pos + 2) == "CH":
                if pos > 0 and sub(pos, pos + 4) == "CHAE":
                    add("K", "X")
                    pos += 2
                elif (
                    pos == 0
                    and (
                        sub(pos + 1, pos + 6) in ("HARAC", "HARIS")
                        or sub(pos + 1, pos + 4) in ("HOR", "HYM", "HIA", "HEM")
                    )
                    and sub(0, 5) != "CHORE"
                ):
                    add("K")
                    pos += 2
                elif (
                    sub(0, 4) in ("VAN ", "VON ")
                    or sub(0, 3) == "SCH"
                    or sub(pos - 2, pos + 4) in ("ORCHES", "ARCHIT", "ORCHID")
                    or sub(pos + 2, pos + 3) in ("T", "S")
                    or (
                        (
                            sub(pos - 1, pos) in ("A", "O", "U", "E")
                            or pos == 0
                        )
                        and (
                            s_pad[pos + 2] in "BFHLMNRVW " or s_pad[pos + 2] == ""
                        )
                    )
                ):
                    add("K")
                    pos += 2
                else:
                    if pos > 0:
                        add("X", "K") if sub(0, 2) == "MC" else add("X")
                    else:
                        add("X")
                    pos += 2
            elif sub(pos, pos + 2) == "CZ" and sub(pos - 2, pos) != "WI":
                add("S", "X")
                pos += 2
            elif sub(pos + 1, pos + 4) == "CIA":
                add("X")
                pos += 3
            elif sub(pos, pos + 2) == "CC" and not (pos == 1 and s[0] == "M"):
                if (
                    s_pad[pos + 2] in "IEH"
                    and sub(pos + 2, pos + 4) != "HU"
                ):
                    if (
                        (pos == 1 and s_pad[pos - 1] == "A")
                        or sub(pos - 1, pos + 4) in ("UCCEE", "UCCES")
                    ):
                        add("KS")
                    else:
                        add("X")
                    pos += 3
                else:
                    add("K")
                    pos += 2
            elif sub(pos, pos + 2) in ("CK", "CG", "CQ"):
                add("K")
                pos += 2
            elif sub(pos, pos + 2) in ("CI", "CE", "CY"):
                if sub(pos, pos + 3) in ("CIO", "CIE", "CIA"):
                    add("S", "X")
                else:
                    add("S")
                pos += 2
            else:
                add("K")
                if sub(pos + 1, pos + 3) in (" C", " Q", " G"):
                    pos += 3
                elif (
                    s_pad[pos + 1] in "CKQ"
                    and sub(pos + 1, pos + 3) not in ("CE", "CI")
                ):
                    pos += 2
                else:
                    pos += 1

        elif c == "D":
            if sub(pos, pos + 2) == "DG":
                if s_pad[pos + 2] in "IEY":
                    add("J")
                    pos += 3
                else:
                    add("TK")
                    pos += 2
            elif sub(pos, pos + 2) in ("DT", "DD"):
                add("T")
                pos += 2
            else:
                add("T")
                pos += 1

        elif c == "F":
            add("F")
            pos += 2 if s_pad[pos + 1] == "F" else 1

        elif c == "G":
            if s_pad[pos + 1] == "H":
                if pos > 0 and not _is_vowel(s, pos - 1):
                    add("K")
                    pos += 2
                elif pos == 0:
                    if s_pad[pos + 2] == "I":
                        add("J")
                    else:
                        add("K")
                    pos += 2
                elif (
                    (pos > 1 and s_pad[pos - 2] in "BHD")
                    or (pos > 2 and s_pad[pos - 3] in "BHD")
                    or (pos > 3 and s_pad[pos - 4] in "BH")
                ):
                    pos += 2
                else:
                    if (
                        pos > 2
                        and s_pad[pos - 1] == "U"
                        and s_pad[pos - 3] in "CGLRT"
                    ):
                        add("F")
                    elif pos > 0 and s_pad[pos - 1] != "I":
                        add("K")
                    pos += 2
            elif s_pad[pos + 1] == "N":
                if pos == 1 and _is_vowel(s, 0) and not _is_slavo_germanic(s):
                    add("KN", "N")
                elif (
                    sub(pos + 2, pos + 4) != "EY"
                    and s_pad[pos + 1] != "Y"
                    and not _is_slavo_germanic(s)
                ):
                    add("N", "KN")
                else:
                    add("KN")
                pos += 2
            elif sub(pos + 1, pos + 3) == "LI" and not _is_slavo_germanic(s):
                add("KL", "L")
                pos += 2
            elif pos == 0 and (
                s_pad[pos + 1] == "Y"
                or sub(pos + 1, pos + 3) in (
                    "ES", "EP", "EB", "EL", "EY", "IB", "IL", "IN", "IE",
                    "EI", "ER",
                )
            ):
                add("K", "J")
                pos += 2
            elif (
                (sub(pos + 1, pos + 3) == "ER" or s_pad[pos + 1] == "Y")
                and sub(0, 6) not in ("DANGER", "RANGER", "MANGER")
                and s_pad[pos - 1] not in "EI"
                and sub(pos - 1, pos + 2) not in ("RGY", "OGY")
            ):
                add("K", "J")
                pos += 2
            elif (
                s_pad[pos + 1] in "EIY"
                or sub(pos - 1, pos + 3) in ("AGGI", "OGGI")
            ):
                if (
                    sub(0, 4) in ("VAN ", "VON ")
                    or sub(0, 3) == "SCH"
                    or sub(pos + 1, pos + 3) == "ET"
                ):
                    add("K")
                elif sub(pos + 1, pos + 5) == "IER ":
                    add("J")
                else:
                    add("J", "K")
                pos += 2
            else:
                add("K")
                pos += 2 if s_pad[pos + 1] == "G" else 1

        elif c == "H":
            if (
                (pos == 0 or _is_vowel(s, pos - 1))
                and _is_vowel(s, pos + 1)
            ):
                add("H")
                pos += 2
            else:
                pos += 1

        elif c == "J":
            if sub(pos, pos + 4) == "JOSE" or sub(0, 4) == "SAN ":
                if (
                    (pos == 0 and s_pad[pos + 4] == " ")
                    or sub(0, 4) == "SAN "
                ):
                    add("H")
                else:
                    add("J", "H")
                pos += 1
            elif pos == 0:
                add("J", "A")
                pos += 1
            else:
                if (
                    _is_vowel(s, pos - 1)
                    and not _is_slavo_germanic(s)
                    and s_pad[pos + 1] in "AO"
                ):
                    add("J", "H")
                elif pos == last:
                    add("J", "")
                elif (
                    s_pad[pos + 1] not in "LTKSNMBZ"
                    and s_pad[pos - 1] not in "SKL"
                ):
                    add("J")
                pos += 2 if s_pad[pos + 1] == "J" else 1

        elif c == "K":
            add("K")
            pos += 2 if s_pad[pos + 1] == "K" else 1

        elif c == "L":
            if s_pad[pos + 1] == "L":
                if (
                    pos == length - 3
                    and sub(pos - 1, pos + 3) in ("ILLO", "ILLA", "ALLE")
                ) or (
                    (
                        sub(last - 1, last + 1) in ("AS", "OS")
                        or s[last] in "AO"
                    )
                    and sub(pos - 1, pos + 3) == "ALLE"
                ):
                    add("L", "")
                    pos += 2
                else:
                    add("L")
                    pos += 2
            else:
                add("L")
                pos += 1

        elif c == "M":
            if (
                sub(pos - 1, pos + 2) == "UMB"
                and (pos + 1 == last or sub(pos + 2, pos + 4) == "ER")
            ) or s_pad[pos + 1] == "M":
                add("M")
                pos += 2
            else:
                add("M")
                pos += 1

        elif c == "N":
            add("N")
            pos += 2 if s_pad[pos + 1] == "N" else 1

        elif c == "Ñ":
            add("N")
            pos += 1

        elif c == "P":
            if s_pad[pos + 1] == "H":
                add("F")
                pos += 2
            elif s_pad[pos + 1] in "PB":
                add("P")
                pos += 2
            else:
                add("P")
                pos += 1

        elif c == "Q":
            add("K")
            pos += 2 if s_pad[pos + 1] == "Q" else 1

        elif c == "R":
            if (
                pos == last
                and not _is_slavo_germanic(s)
                and sub(pos - 2, pos) == "IE"
                and sub(pos - 4, pos - 2) not in ("ME", "MA")
            ):
                add("", "R")
            else:
                add("R")
            pos += 2 if s_pad[pos + 1] == "R" else 1

        elif c == "S":
            if sub(pos - 1, pos + 2) in ("ISL", "YSL"):
                pos += 1
            elif pos == 0 and sub(0, 5) == "SUGAR":
                add("X", "S")
                pos += 1
            elif sub(pos, pos + 2) == "SH":
                if sub(pos + 1, pos + 5) in ("HEIM", "HOEK", "HOLM", "HOLZ"):
                    add("S")
                else:
                    add("X")
                pos += 2
            elif sub(pos, pos + 3) in ("SIO", "SIA") or sub(pos, pos + 4) == "SIAN":
                if not _is_slavo_germanic(s):
                    add("S", "X")
                else:
                    add("S")
                pos += 3
            elif (
                (pos == 0 and s_pad[pos + 1] in "MNLW")
                or s_pad[pos + 1] == "Z"
            ):
                add("S", "X")
                pos += 2 if s_pad[pos + 1] == "Z" else 1
            elif sub(pos, pos + 2) == "SC":
                if s_pad[pos + 2] == "H":
                    if sub(pos + 3, pos + 5) in ("OO", "ER", "EN", "UY", "ED", "EM"):
                        if sub(pos + 3, pos + 5) in ("ER", "EN"):
                            add("X", "SK")
                        else:
                            add("SK")
                    else:
                        if (
                            pos == 0
                            and not _is_vowel(s, 3)
                            and s_pad[pos + 3] != "W"
                        ):
                            add("X", "S")
                        else:
                            add("X")
                    pos += 3
                elif s_pad[pos + 2] in "IEY":
                    add("S")
                    pos += 3
                else:
                    add("SK")
                    pos += 3
            else:
                if pos == last and sub(pos - 2, pos) in ("AI", "OI"):
                    add("", "S")
                else:
                    add("S")
                pos += 2 if s_pad[pos + 1] in "SZ" else 1

        elif c == "T":
            if sub(pos, pos + 4) == "TION":
                add("X")
                pos += 3
            elif sub(pos, pos + 3) in ("TIA", "TCH"):
                add("X")
                pos += 3
            elif sub(pos, pos + 2) == "TH" or sub(pos, pos + 3) == "TTH":
                if (
                    sub(pos + 2, pos + 4) in ("OM", "AM")
                    or sub(0, 4) in ("VAN ", "VON ")
                    or sub(0, 3) == "SCH"
                ):
                    add("T")
                else:
                    add("0", "T")
                pos += 2
            else:
                add("T")
                pos += 2 if s_pad[pos + 1] in "TD" else 1

        elif c == "V":
            add("F")
            pos += 2 if s_pad[pos + 1] == "V" else 1

        elif c == "W":
            if sub(pos, pos + 2) == "WR":
                add("R")
                pos += 2
            elif pos == 0 and (_is_vowel(s, pos + 1) or sub(pos, pos + 2) == "WH"):
                if _is_vowel(s, pos + 1):
                    add("A", "F")
                else:
                    add("A")
                pos += 1
            elif (
                (pos == last and _is_vowel(s, pos - 1))
                or sub(pos - 1, pos + 5) in ("EWSKI", "EWSKY", "OWSKI", "OWSKY")
                or sub(0, 3) == "SCH"
            ):
                add("", "F")
                pos += 1
            elif sub(pos, pos + 4) in ("WICZ", "WITZ"):
                add("TS", "FX")
                pos += 4
            else:
                pos += 1

        elif c == "X":
            if not (
                pos == last
                and (
                    sub(pos - 3, pos) in ("IAU", "EAU")
                    or sub(pos - 2, pos) in ("AU", "OU")
                )
            ):
                add("KS")
            pos += 2 if s_pad[pos + 1] in "CX" else 1

        elif c == "Z":
            if s_pad[pos + 1] == "H":
                add("J")
                pos += 2
            else:
                if sub(pos + 1, pos + 3) in ("ZO", "ZI", "ZA") or (
                    _is_slavo_germanic(s) and pos > 0 and s_pad[pos - 1] != "T"
                ):
                    add("S", "TS")
                else:
                    add("S")
                pos += 2 if s_pad[pos + 1] == "Z" else 1

        else:
            pos += 1

    p = "".join(primary)
    sec = "".join(secondary)
    # Canonical contract: secondary is blank when it never diverged.
    return p, ("" if sec == p else sec)


def _is_slavo_germanic(s: str) -> bool:
    return (
        "W" in s
        or "K" in s
        or "CZ" in s
        or "WITZ" in s
    )


def codes(word: str) -> set[str]:
    """Non-empty Double Metaphone codes for `word`."""
    p, sec = doublemetaphone(word)
    return {c for c in (p, sec) if c}


def match(a: str, b: str) -> bool:
    """True when `a` and `b` share any non-empty Double Metaphone code."""
    ca, cb = codes(a), codes(b)
    return bool(ca and cb and (ca & cb))


if __name__ == "__main__":
    import sys

    for w in sys.argv[1:]:
        print(f"{w}\t{doublemetaphone(w)}")
