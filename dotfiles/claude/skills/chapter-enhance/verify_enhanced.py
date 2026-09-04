#!/usr/bin/env python3
"""Deterministic checks for a chapter-enhance session-summary.

The point: this pass is ALLOWED to be longer than its source, so length cannot
be used as an invention detector the way chapter-summarise uses it. These
checks replace that signal by tracing every claim back to the chapter.

Exit 0 = clean, 1 = at least one FAIL.
"""
import argparse, re, sys, unicodedata
from difflib import SequenceMatcher

REQUIRED = ["## Summary", "## Scenes", "## NPCs"]

# Words that legitimately appear capitalised at the start of a sentence and
# would otherwise flood the proper-noun check with noise.
# Sentence-initial words carrying an English inflection are verbs, not names.
INFLECTED = re.compile(r".+(ed|ing|ly|s)$")

SENTENCE_STARTERS = set("""
a about after again against all also although among an and another any are around as at
away back be because been before being both but by came can could despite did do does
doing done down during each either enough even every fewer finally first for four from
further get given giving had has have having he her here hers him his how however i if in
inside into is it its just last later left less let like made make many may me might more
most much must my near never new next no nor not nothing now of off on once one only or
other others our out outside over own past per perhaps rather said same say says second
seeing seen several she should since so some someone something still such take taken than
that the their them then there these they thing think third this those though three
through thus to together too two under until up upon us use used using very was we well
were what when where whether which while who whom whose why will with within without
would yes yet you your
""".split())

def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")

def norm(s):
    s = (s.replace("’", "'").replace("‘", "'")
          .replace("“", '"').replace("”", '"')
          .replace("—", " ").replace("–", " ")
          .replace("\\!", "!"))
    s = strip_accents(s)
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()

def tokens_ci(text):
    text = strip_accents(text).replace("’", "'")
    toks = set()
    for w in re.findall(r"[A-Za-z][A-Za-z']*", text):
        w = w.lower()
        toks.add(w)
        toks.add(re.sub(r"'s$", "", w))   # possessive stem
    return toks

def body_only(md):
    """Drop our own headings/footer so they don't pollute the scans."""
    md = re.sub(r"(?m)^\s*\*Enhanced summary derived from.*$", "", md, flags=re.S)
    md = re.sub(r"(?m)^Date:.*$", "", md)
    return md

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapter", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--quiet-typos", action="store_true")
    a = ap.parse_args()

    src = open(a.chapter, encoding="utf-8").read()
    out = open(a.summary, encoding="utf-8").read()
    nsrc, obody = norm(src), body_only(out)
    src_tok = tokens_ci(src)
    fails, warns = [], []

    print(f"chapter : {a.chapter}")
    print(f"summary : {a.summary}")
    print("=" * 72)

    # 1 -- structure -------------------------------------------------------
    missing = [h for h in REQUIRED if h not in out]
    (fails if missing else print)  # noqa
    if missing:
        fails.append(f"missing required section(s): {', '.join(missing)}")
    else:
        print("PASS  structure       all required sections present")

    if "Exported from GMAssistant" in out:
        fails.append("provenance footer falsely claims GMAssistant export")

    # 2 -- verbatim quote trace -------------------------------------------
    # Pair quotes SEQUENTIALLY (1st-2nd, 3rd-4th, ...). A regex with a length
    # filter silently pairs a closing quote with the NEXT opening one whenever a
    # short quote like "No" falls under the threshold, and then reports the
    # narration between them as an unsourced quotation.
    quotes = []
    for line in obody.splitlines():
        parts = line.split('"')
        if len(parts) < 3:
            continue
        for k in range(1, len(parts), 2):        # odd segments are inside quotes
            frag = parts[k].strip()
            if len(frag) >= 8:
                quotes.append(frag)
    bad_q = []
    for q in sorted(set(quotes)):
        for part in re.split(r"\.\.\.|…|\" / \"", q):
            p = norm(part)
            if len(p) < 8:
                continue
            if p not in nsrc:
                bad_q.append((q, p))
    if bad_q:
        fails.append(f"{len(bad_q)} quoted fragment(s) NOT verbatim in chapter")
        for q, p in bad_q[:12]:
            print(f"      quote: \"{q[:90]}\"")
            print(f"       norm: {p[:90]}")
    else:
        print(f"PASS  quotes          {len(set(quotes))} distinct, all verbatim in chapter")

    # 3 -- proper-noun invention ------------------------------------------
    # Only MID-SENTENCE capitals are real proper-noun evidence. A capital after
    # '.', a bullet, a heading or an opening quote is just sentence position and
    # would otherwise bury the signal in noise.
    scan = re.sub(r"(?m)^#+ .*$", "", obody)          # our own section headings
    scan = re.sub(r"(?m)^\s*[->*]+\s*", "\n", scan)   # bullet / blockquote markers
    scan = strip_accents(scan).replace("\u2019", "'")
    SENT_END = set(".!?:;\n\"'*-—(/[")
    invented, initial_only = set(), set()
    lower_anywhere = set(re.findall(r"(?<![A-Za-z])[a-z][a-z']+",
                                    strip_accents(obody + " " + src).replace("\u2019", "'")))
    for m in re.finditer(r"\b[A-Z][A-Za-z]{2,}(?:'s|’s)?\b", scan):
        w = m.group(0)
        stem = re.sub(r"['’]s$", "", w).lower()
        if stem in src_tok or stem in SENTENCE_STARTERS:
            continue
        if stem.endswith("s") and stem[:-1] in src_tok:   # simple plural
            continue
        before = scan[:m.start()].rstrip(" ")
        initial = (not before) or before[-1] in SENT_END
        if not initial:
            invented.add(w)
        elif stem not in lower_anywhere and not INFLECTED.match(stem):
            # Sentence-initial capitals are not exempt -- a real run let
            # "Alphonse" through that way. But a stopword list cannot cover
            # English, so use the property that separates names from ordinary
            # words: an ordinary word ("asked", "present") also occurs
            # lowercased somewhere in these two documents; a proper name never
            # does. Reported as a WARN, since the test is a heuristic.
            initial_only.add(w)
    invented = sorted(invented)
    if invented:
        fails.append(f"{len(invented)} mid-sentence capitalised word(s) absent "
                     f"from chapter: " + ", ".join(invented[:15]))
    else:
        print("PASS  proper nouns    no name in summary is absent from the chapter")
    if initial_only:
        warns.append("sentence-initial capital(s) never seen lowercased, so probably "
                     "names, and absent from the chapter: " + ", ".join(sorted(initial_only)[:10]))

    # 4 -- invented numbers ------------------------------------------------
    src_nums = set(re.findall(r"\d+", src))
    out_nums = set(re.findall(r"\d+", body_only(re.sub(r"(?m)^#.*$", "", out))))
    new_nums = sorted(out_nums - src_nums, key=lambda x: (len(x), x))
    if new_nums:
        warns.append("numbers in summary but not in chapter: " + ", ".join(new_nums[:15]))
    else:
        print("PASS  numbers         no count/figure absent from the chapter")

    # 5 -- expansion ratio (reported, never a gate) -----------------------
    sw, ow = len(src.split()), len(out.split())
    print(f"INFO  size            chapter {sw} words -> summary {ow} words "
          f"({ow/max(sw,1)*100:.0f}%)")

    # 6 -- source defects, for the fix-at-source queue --------------------
    if not a.quiet_typos:
        names = [w for w in re.findall(r"\b[A-Z][a-z]{3,}\b", src)]
        freq = {}
        for n in names:
            freq[n] = freq.get(n, 0) + 1
        variants = []
        uniq = sorted(freq)
        for i, x in enumerate(uniq):
            for y in uniq[i + 1:]:
                if abs(len(x) - len(y)) > 2:
                    continue
                r = SequenceMatcher(None, x.lower(), y.lower()).ratio()
                if 0.82 <= r < 1.0 and min(freq[x], freq[y]) <= max(freq[x], freq[y]) / 4:
                    lo, hi = (x, y) if freq[x] < freq[y] else (y, x)
                    variants.append(f"{lo} (x{freq[lo]}) vs {hi} (x{freq[hi]})")
        if variants:
            print("QUEUE source names    likely misspelling(s) in the CHAPTER "
                  "- report, do not fix silently:")
            for v in variants[:12]:
                print(f"        - {v}")

    # ---------------------------------------------------------------------
    print("=" * 72)
    for w in warns:
        print(f"WARN  {w}")
    for f in fails:
        print(f"FAIL  {f}")
    print("RESULT:", "CLEAN" if not fails else f"{len(fails)} FAILURE(S)")
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main())
