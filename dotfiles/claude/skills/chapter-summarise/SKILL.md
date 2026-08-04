---
name: chapter-summarise
description: >
  Generate structured session-summary.md files from campaign chapter PROSE, for
  chapters that have no session recording behind them — the case where the
  extraction ladder would otherwise be stuck on raw prose and the event spine
  has no scene key. Opus orchestrates, one Haiku subagent per chapter, writing
  to summaries/haiku/<NNN>-<slug>/. Generation is constrained (no invented
  dialogue, no module-canon backfill, no silent typo fixes, must compress) and
  every output is then checked by a deterministic verifier that the GM reviews —
  the model's self-report is never the gate. Surfaces chapter typos and name
  drift as a fix-at-source queue rather than papering over them. Invoke as
  /chapter-summarise [campaign-dir] [chapter-range].
tools: Read, Bash, Write, Edit, Glob, Grep, Agent, AskUserQuestion
---

# chapter-summarise

Build `session-summary.md` files from chapter prose so that chapters with **no
transcript** can still feed the summary rung of the extraction ladder and give
the event spine a real scene key.

## Read this first: when NOT to run

**If a chapter has a session workspace with a VTT, do not generate a summary for
it.** That workspace's `session-summary.md` came from `enhance_summary` reading
the actual transcript; it sits *upstream* of the chapter prose. A generated
summary sits *downstream* — it can only ever lose or invent information relative
to its source. Generating one would be
`LLM extracts → LLM structures → LLM renders`, the compounding pattern the
project rule prohibits.

Check before you start:

```bash
cd <campaign-dir>
find summaries -name '*.vtt' | sed 's|/[^/]*$||' | sort -u
```

Any chapter covered by one of those directories is out of scope. This skill is
only for the chapters left over — typically the early campaign, before recording
started.

Be honest with the GM about what this buys: the chapter prose remains the most
upstream artifact available. A generated summary does not add information. What
it adds is **structure** — explicit scene boundaries, which the prose lacks and
which the spine needs.

## What the structure is worth

`event_spine` rows key on `(chapter, scene, seq)`. `scene` is `scene_index`,
stamped by `ensemble_merge.stamp_scene_index` from `campaignlib.textproc.
chunk_by_scenes` — **header-driven**. So the source document's headings literally
become the scene key.

Early-campaign chapters are usually organised by in-world date (`## 8/1 of
Taraksh 1495`) with POV names beneath (`### Soma`), or have no `##` heading at
all. Either way `scene` ends up meaning "which day" or "which POV block", or
nothing. A generated summary's `### <Scene title>` list gives real scenes.

**The catch, and it is easy to miss:** `chunk_by_scenes` splits on `##` and only
consults `###` when there are **no** `##` headings anywhere. The summary's own
`## Summary` / `## Scenes` / `## NPCs` are H2s, so feeding the whole file yields
three or four chunks and collapses every scene into one. Slicing to the `##
Scenes` section alone does not help either — `## Scenes` is still an H2.

Per-scene chunking requires the section body with the `## Scenes` wrapper line
stripped, leaving `###` titles as the only headings:

```python
sec  = re.search(r'(?ms)^##\s+Scenes\b.*?(?=^##\s+(?!#)|\Z)', text).group(0)
body = re.sub(r'(?m)^##\s+Scenes\b.*\n', '', sec)     # -> convention='h3'
```

And note the tension: `campaignlib.lineage._summary_is_structured` *requires* a
literal `## Scenes` and `## NPCs` to admit the file to the summary rung at all.
The ladder gate demands the wrapper; the chunker is defeated by it. One document
cannot satisfy both — this needs a slicing pre-pass at extraction time, not a
format change. Tell the GM this rather than quietly picking one.

## Procedure

### 1. Scope and confirm

Resolve the campaign dir and the chapter range. Establish which chapters have no
VTT (above). Report the count and the total word volume before spending tokens.

Check for **duplicate chapter indices** — a re-split after a spelling fix leaves
orphans behind:

```bash
python3 -c "
import re,glob
from collections import Counter
c=Counter(int(re.match(r'.*chapter_(\d+)_',f).group(1)) for f in glob.glob('docs/chapters/chapter_*.md'))
print([k for k,v in c.items() if v>1] or 'no duplicates')"
```

If there are duplicates, resolve them with the GM **before** generating — pick
the newest file per index, and list the strays for the GM to delete. Do not
delete chapter files yourself. Confirm which spelling is canonical by counting
both against the bible, not by guessing.

### 2. Build the plan

One JSON entry per chapter: `ch`, `chapter` (input path), `out` (output path),
`words`. Output layout, zero-padded so lexical sort matches chapter order:

```
summaries/haiku/<NNN>-<chapter-slug>/session-summary.md
   e.g. summaries/haiku/002-arrival_in_phandalin/session-summary.md
```

Reuse the chapter filename's own slug. Create the directories up front.

### 3. Generate — one Haiku subagent per chapter

Copy `summary_spec.md` (bundled with this skill) somewhere the subagents can
read, or point them at it in place. Launch subagents in **batches of about 10**,
in a single message each so they run concurrently. Each prompt gives:

- the campaign root, the spec path, and the plan path
- its chapter number, and an instruction to take input/output paths from the plan
- a warning that a deterministic verifier will check quotes, proper nouns and
  word count, and that self-reports are not accepted
- for short chapters (< ~900 words), an explicit "do not pad" note
- for chapters where a previous pass is known to have fabricated, a specific
  heads-up about what it invented

Use `model: haiku`. Ask each agent to reply with only three numbers: words
written, chapter words, quoted strings. **These are for triage, not truth.**

### 4. Verify — this is the gate

```bash
python3 ~/.claude/skills/chapter-summarise/verify_summaries.py \
    --campaign-dir <campaign-dir> --summaries-dir summaries/haiku
```

Exit 2 on a setup problem (no summaries, or two directories claiming the same
chapter index — it refuses rather than verifying the wrong file). Exit 1 on a
content failure: missing file, gate fail, ratio >= 1.0, or a flagged quote.

Regenerate on gate/ratio failures — those are unambiguous. **A flagged quote is
not automatically a regenerate**; adjudicate it first (see below), because an
innocent flag will otherwise loop forever.

Read the output honestly rather than reporting the headline:

- **`order` = `unverif`** means no scene in that chapter could be anchored to a
  traceable string. That is *unverified ordering*, not verified — say so. A
  chapter whose bullets are all heavy paraphrase will read as `unverif`.
- **Flagged quotes are candidates, not verdicts.** Check each by hand. In the
  reference run both flags were innocent: one stitched two real fragments into
  one quote, and one silently corrected a **typo in the chapter**
  (`lightbrining` → `lightbringing`). The second is a finding about the source,
  not the summary.
- **Novel proper nouns leak ordinary words** (sentence-initial `Throughout`,
  `Compelled`). Skim for real names. Genuine hits are usually module-canon bleed
  — a name from the published adventure that is not in the chapter.

### 5. Hand back a fix-at-source queue

Do not suppress what the verifier finds. Chapter typos, name drift, and lore
bleed should be reported to the GM as a list to fix **in the bible and the
chapters**, because that is where the next re-split will read from. Patching a
generated summary fixes nothing; the defect regenerates.

Check the bible directly:

```bash
grep -oci 'Axelholm\|Axeholm' docs/<bible>.md
```

## Reference run (Phandalin, chapters 2-30, 2026-08-02)

29 chapters, 55k words of prose, one Haiku agent each, three batches.

| check | this skill | prior unconstrained pass |
|---|---|---|
| gate pass | 29/29 | 29/29 |
| no `## Memorable Moments` | 29/29 | 0/29 |
| shorter than source | 29/29 | 11/28 |
| dialogue quotes | 73 | 87 |
| — with no trace in chapter | 2 (both innocent) | 14 |
| novel proper nouns | 18 (mostly artifacts) | 434 |
| scenes produced | 148, all h3-chunking cleanly | 164 |

The prior pass's failure modes, all of which the constraints above target:
invented attributed dialogue; expansion to as much as 2.9x the source;
module-canon backfill (`Toblen`, `Harbin`, `Menzoberranzan` in chapters that
never mention them); and silently changed roles and pronouns (a "wererat miner"
with *his* became "the wererat leader" with *She*).

Known residual weaknesses:

- A `## NPCs` section will balloon a short chapter past 100% if it writes an
  entry per proper noun — rule 9 in the spec exists for this, and chapter 1 of
  the pilot still failed it at 1.50x before the rule was added.
- The verifier catches invented *names* and invented *quotes*. It does **not**
  catch invented *claims about real entities*. A paragraph elaborating on a real
  NPC from model knowledge passes every check. Chapters that are mostly `##
  NPCs` prose deserve a human read.
- Compression near 0.95 (chapter 14 hit 0.94) passes the rule but is not really
  a summary. Consider flagging anything above ~0.85 for the GM.
