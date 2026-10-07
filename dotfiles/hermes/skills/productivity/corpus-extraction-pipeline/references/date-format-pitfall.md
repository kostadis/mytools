# Date-format drift: preserve raw, normalize at merge

## The problem (observed in a 47-chapter campaign extraction)
Source headers used the stamp `DD-MM-Taraskh 1495` where the **middle number is the month** and "Taraskh" is the in-world year label. Example: `01-02-Taraskh 1495` = day 1, month 2.

When subagents were told to also produce a `sort_date`, they disagreed on interpretation:
- Some read "Taraskh" as month 01 → `1495-01-02`.
- Some used the literal middle number as month → `1495-02-01`.
- Some preserved the variant spelling `01-03 Taraskh 1495` (space) → fell into the "undated/null" bucket.

Result: ordering was corrupted and a few events were mis-sorted or dropped to an undated group.

## The fix
- Instruct subagents to record `date_label` **verbatim** (the raw string) and set `sort_date` as best-effort only.
- Do ALL normalization at the merge step with a single parser:

```python
import re, glob, json

def parse_sort(dl):
    if not dl:
        return None
    m = re.search(r'(\d{1,2})-(\d{1,2})\s*-?\s*([A-Za-z]+)\s*(\d{4})', dl)
    if not m:
        return None
    day, month = int(m.group(1)), int(m.group(2))   # middle number IS the month
    return f"1495-{month:02d}-{day:02d}"

# normalize the space-variant too: '01-03 Taraskh 1495' -> '01-03-Taraskh 1495'
def normalize(dl):
    if not dl:
        return None
    m = re.search(r'(\d{1,2})-(\d{1,2})\s*-?\s*([A-Za-z]+)\s*(\d{4})', dl)
    if not m:
        return dl
    return f"{int(m.group(1)):02d}-{int(m.group(2)):02d}-{m.group(3)} {m.group(4)}"
```

## Lesson
Centralize any value that different agents could parse differently. The merge step owns normalization; subagents only preserve raw text. Verify with `json.load` and assert file existence after every wave — async batch-complete messages can arrive before the agent's final write executes (one 72KB chapter's file was reported done but never written; re-dispatch fixed it).
