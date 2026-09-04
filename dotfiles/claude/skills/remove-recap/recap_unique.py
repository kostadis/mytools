#!/usr/bin/env python3
"""What would be LOST by cutting the recap.

A recap is supposed to be redundant -- it retells the previous chapter, which
already has its own document. It is not reliably redundant, and cutting it
blind destroys three kinds of content:

  1. GM ASIDES delivered while recapping. The GM corrects, clarifies, or
     reveals something the party did not know at the time. On obelisk ch10 the
     recap is where the party finally learns the magic sword is named Talon --
     an editorial annotation records "the GM notes the party has now learned
     the name". That is new canon, spoken during a recap, and the previous
     chapter's document cannot contain it.
  2. THIS chapter's bookkeeping, announced at the top. Level-ups, new
     subclasses, spells gained, rests taken. ch10's recap scene opens with
     Zenvon reaching 3rd level and taking Arcane Trickster -- that is chapter
     10 state, not chapter 8 history.
  3. Beats the previous chapter's record genuinely MISSED. Then the recap is
     the only record, and the finding is a gap upstream, not a cut here.

Deterministic: proper-noun and numeric coverage against the previous chapter's
documents. It reports; it never cuts and never decides.
"""
import argparse, glob, os, re, sys

ASIDE = re.compile(r"\*\(([^)]{12,})\)\*")
BULLET = re.compile(r"^-\s+(.*\S)\s*$", re.M)
# Proper nouns and numbers carry the identity of a beat; ordinary words do not.
TOKEN = re.compile(r"\b(?:[A-Z][a-z]{2,}|\d[\d,]*)\b")
STOP = {"The", "A", "An", "And", "But", "She", "He", "They", "It", "When",
        "After", "Before", "This", "That", "There", "Then", "His", "Her",
        "Their", "Zenvon", "Veyra", "Maela", "Pip", "Sister", "GM", "DM"}
BOOKKEEPING = re.compile(
    r"\b(?:reach(?:es|ed)?\s+\w+\s+level|level\s*\d|third level|second level|"
    r"archetype|subclass|long rest|short rest|gain(?:s|ed)?\s+(?:the\s+)?\w+\s+"
    r"(?:spell|cantrip)|hit dice|leveled|levelled)\b", re.I)


def prev_corpus(dirs):
    text = []
    for d in dirs:
        if os.path.isfile(d):
            text.append(open(d, encoding="utf-8", errors="ignore").read()); continue
        for pat in ("*.md", "narration/*.md", "scene_extractions/*.md",
                    "scene_extractions_smoothed/*.md"):
            for f in glob.glob(os.path.join(d, pat)):
                text.append(open(f, encoding="utf-8", errors="ignore").read())
    return "\n".join(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recap", required=True, help="the recap scene .md")
    ap.add_argument("--against", nargs="+", required=True, metavar="PATH",
                    help="previous chapter dir(s) and/or file(s) — its session "
                         "summary, narration, extractions")
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="flag a bullet when this fraction or less of its "
                         "distinctive tokens appear in the previous chapter "
                         "(default 0.5)")
    a = ap.parse_args()

    recap = open(a.recap, encoding="utf-8").read()
    summary = recap.split("## Voiced moments")[0]
    prev = prev_corpus(a.against)
    if not prev.strip():
        sys.exit("REFUSED: --against matched no text. Check the previous chapter path.")

    print(f"recap:   {os.path.basename(a.recap)}")
    print(f"against: {len(prev.split()):,} words of previous-chapter material\n")

    asides = ASIDE.findall(recap)
    print(f"--- GM asides / editorial annotations in the recap ({len(asides)}) ---")
    print("    Read every one. This is where new canon hides.")
    for s in asides:
        print(f"    * {s[:150]}")
    if not asides:
        print("    (none)")

    bullets = BULLET.findall(summary)
    book = [b for b in bullets if BOOKKEEPING.search(b)]
    print(f"\n--- THIS chapter's bookkeeping stated in the recap ({len(book)}) ---")
    print("    Belongs to this chapter, not the previous one. Rescue, never cut.")
    for b in book:
        print(f"    * {b[:150]}")
    if not book:
        print("    (none detected)")

    print(f"\n--- bullets poorly covered by the previous chapter ---")
    print("    Low coverage = possibly unique to the recap, OR a gap in the")
    print("    previous chapter's record. Both need a human. Proper-noun")
    print("    matching is crude: verify before believing.")
    flagged = 0
    for b in bullets:
        toks = {t for t in TOKEN.findall(b) if t not in STOP}
        if len(toks) < 2:
            continue
        found = {t for t in toks if re.search(r"\b" + re.escape(t) + r"\b", prev)}
        cov = len(found) / len(toks)
        if cov <= a.threshold:
            flagged += 1
            print(f"    [{cov:.0%}] {b[:130]}")
            print(f"           missing: {sorted(toks - found)[:8]}")
    if not flagged:
        print("    (none — every bullet is well covered upstream)")

    print("\nNothing was cut. Rescue what matters, then rule in SKILL.md Phase 2.")


if __name__ == "__main__":
    main()
