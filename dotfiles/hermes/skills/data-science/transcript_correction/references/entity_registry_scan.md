# Entity-registry-driven garble hunt

When the curated glossary / `name_glossary.md` phonetic scan isn't enough —
typically when the user asks "did you use the entity inventory / registry as the
source of truth?" or "proper nouns get turned into word pairs" — drive the hunt
from the AUTHORITATIVE entity registry instead of a curated subset.

This campaign's registry: `docs/entity_registry.yaml` (GENERATED from
`docs/entity_inventory.md`; 374 entities). It lists canonical spellings only —
no garbles — so it can't supply the fixes, but it IS the complete enumerative
list of "what exists", which lets you flag ANY unrecognized name in the
transcripts.

## 1. Build the known-name set

Fold in: every `name:` + `aliases:` entry (lowercased), plus each word (>=3
chars) of multiword names; the glossary's right-hand sides; and any
campaign-original names.

No PyYAML in this env — parse the YAML with regex:

```python
import re
known = set()
reg_txt = open("docs/entity_registry.yaml").read()
cur = None
for line in reg_txt.splitlines():
    m = re.match(r"^- name:\s*(.+)$", line)
    if m:
        cur = m.group(1).strip()
        known.add(cur.lower())
        for w in cur.split():
            if len(w) >= 3: known.add(w.lower())
        continue
    if cur is not None:
        ma = re.match(r"^\s+- (.+)$", line)
        if ma and "aliases:" not in line:
            known.add(ma.group(1).strip().lower())
```

## 2. Unrecognized-Capitalized-token scan

For each transcript: strip the speaker prefix
(`re.sub(r"^[A-Z][a-z]+ [A-Z][a-z]+:?", "", line)`), then collect every
`\b([A-Z][a-z]{2,})\b` token NOT in `known` and NOT in a common-English stopword
set. Anything remaining is a candidate missed garble.

Sort by frequency (`sort | uniq -c`). In session 004 this surfaced a SECOND
WAVE the `name_glossary.md` grep missed: Iarno (Yarno/Jarno/Albrecht...),
Cragmaw (Kragmaw), Zhentarim (Zentarim), Phandalin (Fandelin/Fandale...),
Neverwinter (Nevermember...), Tharden (Thardin), plus more Toblen/Gundren
variants.

## 3. Word-pair / split-garble scan (the user-called-out pitfall)

ASR breaks names into two words or renders them as phrases. Single-token scans
MISS these. Scan for a Capitalized word immediately followed by a short (2-4
char) lowercase word, and treat multi-word phrases as single garble units.

```python
SPLIT = re.compile(r"\b([A-Z][a-z]{2,})\b\s+([a-z]{2,4})\b")
```

Session-004 catches:
- `Weiwe Vekov Cave` / `Evoko Cave` -> **Wave Echo Cave**
- `Fandele Verpakt` -> **Phandelver Pact**
- `Linene Lanain` -> **Linene Graywind** (double-garbled surname)
- `Jarno Albrecht` / `Larno Albrecht` -> **Iarno Albrek**
- "Gun dren" style splits -> treat the two tokens as one name.

In the corrections list, write the phrase as one entry so it substitutes
atomically, e.g. `(r"\bWeiwe Vekov Cave\b", "Wave Echo Cave")`.

## 4. Verify each candidate IN CONTEXT before adding a row

Print the matching line. Real other words (Linux, link, half, hardware, line)
are NOT garbles. When confident, add wrong->right rows to the glossary (source
of truth), then re-run the FULL pass from the pristine `.bak` so old + new
fixes apply together.
