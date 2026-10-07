# Lower-case / non-capitalized semantic pass

The Capitalized-token scan and the word-pair scan (in
`entity_registry_scan.md`) only see Capitalized names. A garble rendered as a
common lowercase word or a multi-word module term is **invisible** to those
scans — it never appears as an unrecognized Capitalized token. This pass closes
that gap. It is MANDATORY (workflow step 8), not optional.

## Why it's needed

The user explicitly asks for it ("what about lower case typos? Probably needs a
semantic pass?"). In the obelisk campaign these lower-case garbles were MISSED
by the Capitalized hunt and only caught by this pass:

| Garble (lower-case / phrase) | Right | Note |
|---|---|---|
| `notar` | **dwarf** | ASR of "dwarf" |
| `red brand`, `Red Brand` | **Redbrand** | bandit gang (singular) |
| `red brands`, `Red Brands` | **Redbrands** | bandit gang (plural) |
| `Red Browns` | **Redbrands** | 'w' ASR slip |
| `Forward Giants` | **Redbrands** | player garbled the gang name twice |
| `frock-seeker`, `frock seeker` | **Rockseeker** | "old frock-seeker" |
| `Gundren Roxiga` | **Gundren Rockseeker** | Roxiga = Rockseeker |
| `Glass Staff`, `Glassdaff`, `Glass Tap` | **Glasstaff** | two-word / variant of the villain alias |
| `Weiwe Vekov Cave`, `wake of Evoko Cave` | **Wave Echo Cave** | cave name (NOT the Iarno character) |
| `Fandele Verpakt`, `Phandalin Verpakt` | **Phandelver Pact** | pact name |
| `Tribor Trail`, `Tribor Trails` | **Triboar Trail** | trail name (incl. plural) |

## Recipe

After the Capitalized pass has produced the (partially) cleaned file, run this
on it. It greps for any surviving lower-case garble form and for frail phonetic
tokens:

```python
import os, re
p = "GMT...transcript.cleaned.vtt"   # the just-cleaned file
# known lower-case garble forms to hunt (extend from the glossary as you find more)
CHECK = {
  "redbrand":   ["red brand", "red brands", "redbrown", "red browns"],
  "cragmaw":    ["crag maw", "krag maw"],
  "wave echo":  ["wave echo", "wake of", "weiwe", "evoko", "glass tap"],
  "phandelver": ["phandelver", "fandele", "fandalin", "verpakt"],
  "rockseeker": ["rock seeker", "frock", "roxiga", "roxica"],
  "neverwinter":["neverwinter", "neverwin", "nevermember"],
  "phandalin":  ["phandalin", "fandalin", "fandele"],
  "tresendar":  ["tresender", "tressander"],
  "triboar":    ["tribor", "tribo"],
  "zhentarim":  ["zentarim", "zent"],
  "dwarf":      ["notar"],
  "redbrands":  ["forward giants", "red brows"],
}
for stem, variants in CHECK.items():
    for v in variants:
        rx = re.compile(r"\b" + re.escape(v) + r"\b", re.I)
        n = sum(1 for ln in open(p, encoding="utf-8") if rx.search(ln))
        if n:
            print(f"  FOUND  {stem} <- '{v}': {n}")
# heuristic frail lowercase tokens (confirm IN CONTEXT before fixing)
for s in [r"\b(notar)\b", r"\b(red browns?)\b", r"\b(forward giants?)\b",
          r"\b(glass tap)\b", r"\b(glass staff)\b"]:
    rx = re.compile(s, re.I)
    n = sum(1 for ln in open(p, encoding="utf-8") if rx.search(ln))
    if n:
        print(f"  suspect  {s}: {n}")
```

Any hit means a garble the Capitalized pass missed. Confirm IN CONTEXT, add the
wrong→right row to the glossary (source of truth), then re-run the FULL pass
from the pristine `.bak` so all fixes apply together (CRLF-preserving).

## Pitfall

This pass is easy to skip because the Capitalized scan "came back clean." Never
skip it — lower-case module-term garbles are the most common misses and the
user specifically asks for them.
