#!/usr/bin/env python3
"""Refactor session summaries: move ## Summary narrative paragraphs into scenes.

Final form per scene: '### Title' + narrative paragraph(s) + existing #### / bullets.
No content changes: every non-blank line is preserved verbatim; only ordering and
the removal of the '## Summary' heading change.

Usage:
    python3 refactor_summaries.py               # dry-run: JSON mapping + flags
    python3 refactor_summaries.py --apply       # write files (refuses on verify fail)
    python3 refactor_summaries.py f1.md f2.md   # subset, with or without --apply

See references/summary_narrative_refactor.md for the alignment algorithm,
pitfalls, and the verification gate that must pass after --apply.
"""
import sys, os, re, json, difflib

DIR = "/home/kostadis/phandalin/Phandalin/docs/summaries"
STOP = set("the a an and or but if of to in on at by for with from she he they them his her their it its was were is are be been had have has not no that this as what when where how why you your we our us i me my so all out more than then there here these those would could will just".split())

def norm_words(s):
    return set(w for w in re.findall(r"[a-z']+", s.lower()) if w not in STOP and len(w) > 1)

def section_range(lines, header_re):
    start = None
    for i, l in enumerate(lines):
        if re.match(header_re, l):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return (start, end)

def paragraphs_in(lines, lo, hi):
    """Return list of (block_lines) in chronological order."""
    blocks, cur = [], []
    for l in lines[lo:hi]:
        if l.strip() == "":
            if cur:
                blocks.append(cur); cur = []
        else:
            if l.startswith("#"):
                continue
            cur.append(l)
    if cur:
        blocks.append(cur)
    return blocks

def scenes_in(lines, lo, hi):
    """Return list of dicts: start, end, lines (lines of scene incl title)."""
    idxs = [i for i in range(lo, hi) if lines[i].startswith("### ")]
    scenes = []
    for n, s in enumerate(idxs):
        e = idxs[n + 1] if n + 1 < len(idxs) else hi
        scenes.append({"start": s, "end": e, "lines": lines[s:e]})
    return scenes

def scene_blob(sc):
    return "\n".join(sc["lines"])

def align(paras, scenes):
    """DP: assign paragraphs in order to scenes in order (contiguous blocks).
    Score = sum of para-scene similarity; EMPTY_PEN makes the DP itself cover
    every scene when there are at least as many paragraphs as scenes."""
    n, m = len(paras), len(scenes)
    pw = [norm_words(" ".join(p)) for p in paras]
    sw = [norm_words(scene_blob(s)) for s in scenes]
    sim = [[0.0] * m for _ in range(n)]
    for i in range(n):
        for j in range(m):
            a, b = pw[i], sw[j]
            if not a or not b:
                sim[i][j] = 0.0
            else:
                inter = len(a & b)
                jac = inter / len(a | b)
                seq = difflib.SequenceMatcher(None, " ".join(sorted(a)), " ".join(sorted(b))).ratio()
                sim[i][j] = 0.7 * jac + 0.3 * seq
    NEG = float("-inf")
    EMPTY_PEN = 1.0 if n >= m else 0.0  # penalty per empty scene, only when coverable
    # dp[i][j] = best score assigning first i paras to first j scenes (monotonic)
    dp = [[NEG] * (m + 1) for _ in range(n + 1)]
    choice = [[0] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for j in range(1, m + 1):
        for i in range(n + 1):
            run = 0.0
            best, bk = NEG, i
            if dp[i][j - 1] != NEG:
                best, bk = dp[i][j - 1] - EMPTY_PEN, i
            for k in range(i - 1, -1, -1):
                run += sim[k][j - 1]
                if dp[k][j - 1] != NEG:
                    tot = dp[k][j - 1] + run
                    if tot > best:
                        best, bk = tot, k
            dp[i][j], choice[i][j] = best, bk
    # traceback
    assign = [[] for _ in range(m)]
    i, j = n, m
    while j > 0:
        k = choice[i][j]
        for p in range(k, i):
            assign[j - 1].append(p)
        i = k
        j -= 1
    for lst in assign:
        lst.sort()
    # invariant: contiguity + monotonic order
    flat = [p for lst in assign for p in lst]
    assert flat == list(range(n)), "assignment broke contiguity"
    return assign, sim

def process(path, apply=False):
    text = open(path, encoding="utf-8").read()
    if "## Summary" not in text or "## Scenes" not in text:
        return {"file": os.path.basename(path), "skip": True, "mapping": [], "flags": ["no Summary/Scenes section"]}
    lines = text.split("\n")
    sr = section_range(lines, r"^## Summary\b")
    cr = section_range(lines, r"^## Scenes\b")
    paras = paragraphs_in(lines, sr[0] + 1, sr[1])
    scenes = scenes_in(lines, cr[0] + 1, cr[1])
    assign, sim = align(paras, scenes)
    flags = []
    for j, lst in enumerate(assign):
        title = scenes[j]["lines"][0].lstrip("# ").strip()
        for p in lst:
            s = sim[p][j]
            if s < 0.10:
                flags.append(f"LOW {p}->{j} '{title[:40]}' score={s:.3f} para='{paras[p][0][:60]}...'")
        if not lst:
            flags.append(f"EMPTY scene {j} '{title[:50]}'")
    report = {"file": os.path.basename(path), "n_paras": len(paras), "n_scenes": len(scenes),
              "mapping": [[scenes[j]["lines"][0].lstrip("# ").strip(), [paras[p][0][:50] for p in assign[j]]] for j in range(len(scenes))],
              "flags": flags}
    if apply:
        new_lines = []
        # everything before Summary section
        new_lines.extend(lines[:sr[0]])
        # between Summary end and FIRST SCENE: includes '## Scenes' header
        # and any intro text before the first '###' (dropping it = verify fail)
        between = lines[sr[1]:scenes[0]["start"]]
        new_lines.extend(between)
        # rebuild scenes with narrative inserted after title
        for j, sc in enumerate(scenes):
            new_lines.append(sc["lines"][0])  # ### Title
            for p in assign[j]:
                new_lines.append("")
                new_lines.extend(paras[p])
            rest = sc["lines"][1:]
            # drop leading blank lines to avoid doubles, we added our own
            while rest and rest[0].strip() == "":
                rest = rest[1:]
            new_lines.append("")
            new_lines.extend(rest)
        new_lines.extend(lines[cr[1]:])
        new_text = "\n".join(new_lines)
        # collapse runs of 3+ newlines to 2 (spacing cleanup only)
        new_text = re.sub(r"\n{3,}", "\n\n", new_text)
        # verify: multiset of non-blank lines preserved (minus removed heading)
        from collections import Counter
        old_nb = sorted(l for l in text.split("\n") if l.strip() and l.strip() != "## Summary")
        new_nb = sorted(l for l in new_text.split("\n") if l.strip())
        co, cn = Counter(old_nb), Counter(new_nb)
        if co != cn:
            diff_o = list((co - cn).elements()); diff_n = list((cn - co).elements())
            report["verify"] = "FAIL"
            report["missing"] = diff_o[:5]; report["extra"] = diff_n[:5]
            print(f"VERIFY FAIL {path}", file=sys.stderr)
            return report
        open(path, "w", encoding="utf-8").write(new_text)
        report["verify"] = "OK"
    return report

if __name__ == "__main__":
    apply = "--apply" in sys.argv
    files = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not files:
        files = sorted(os.path.join(DIR, f) for f in os.listdir(DIR) if f.endswith(".md"))
    for f in files:
        r = process(f, apply)
        print(json.dumps(r, indent=1))
