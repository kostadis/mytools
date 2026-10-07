# Bounded Chapter Extraction Technique

Source chapters in the Phandalin campaign are 10–60 KB each. Dumping them into
`execute_code` to read inline, or pulling every matching line for broad keywords,
blows past the ~50 KB `execute_code` stdout cap and truncates (head+tail),
losing the middle. Use a narrow, bounded pass.

## Pattern (copy and adapt per batch)

```python
import glob, os
base = "/home/kostadis/src/campaigns/Phandalin/docs/chapters/"

def chap(n):
    fs = glob.glob(f"{base}chapter_{n:02d}_*.md")
    return fs[0] if fs else None

def text(n):
    p = chap(n); return open(p).read() if p else ""

def chrange(s):
    out = []
    for part in s.split(','):
        if '-' in part:
            a, b = part.split('-'); out += list(range(int(a), int(b)+1))
        else:
            out.append(int(part))
    return out

def hits(nums, keywords, ctx=1, maxper=8):
    """Return {chapter: [snippet, ...]} for paragraphs containing any keyword.
    snippet = (ctx±) context lines joined, truncated by caller."""
    res = {}
    for n in nums:
        t = text(n); paras = t.split('\n'); found = []
        for i, para in enumerate(paras):
            low = para.lower()
            if any(k in low for k in keywords):
                lo = max(0, i-ctx); hi = min(len(paras), i+ctx+1)
                found.append(" / ".join(paras[lo:hi]).strip())
        if found:
            res[n] = found[:maxper]
    return res

# Example query block: one entry per dossier, entity-specific keywords.
queries = {
    "audit_drone": (chrange("29-29"), ["drone", "vukradin", "valphine", "captured"]),
    "blights": (chrange("41-41"), ["twig blight", "killed", "missed"]),
}
for name, (nums, kw) in queries.items():
    print("#####", name)
    r = hits(nums, kw)
    for n in nums:
        if n in r:
            for s in r[n]:
                print(f"[ch{n}] {s[:350]}")
    print()
```

## Tuning rules

- **Keywords**: 3–8 per dossier, specific to the entity (e.g. `"boar mask"`,
  `"grey rags"`, `"dragonslayer"/"dragon slayer"`, `"rule-breaking boars"`) not
  generic nouns like `"boar"` alone (too many hits).
- **ctx=1–2**: ±1 line is usually enough; use 2 when a fact spans two sentences.
- **maxper=6–12**: caps hits per chapter so a heavily-mentioned chapter can't
  dominate stdout.
- **snippet cap `s[:350]`**: keeps total output bounded when many dossiers are
  processed. Increase only when a single passage is long and central.
- **Process in chunks**: with 25–30 dossiers, run the dict in 2–3 batches rather
  than all at once, or the aggregated stdout truncates.
- **When a needed passage is omitted** (truncation warning), re-run that single
  dossier's query with tighter keywords / smaller `maxper`.
