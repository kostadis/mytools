#!/usr/bin/env python3
"""Deterministic recap detector for a session's scene extractions.

A recorded session almost always opens with the GM recapping the previous
chapter. That material belongs to the PREVIOUS chapter's document, not this
one, and narrating it again duplicates a chapter the campaign already has.

This script LOCATES the recap and proposes where it ends. It never cuts, and
it never decides the boundary -- that is a scope decision (SKILL.md Phase 2).

No LLM, no network. Regex and counting over text already on disk.
"""
import argparse, glob, json, os, re, sys

# Things a GM says out loud when starting a recap. High precision, low recall:
# a hit is strong evidence, a miss means nothing.
OPEN = [
    r"let me read you what happened", r"\blast time\b", r"\blast session\b",
    r"\blast week\b", r"where we left off", r"catch (?:you|us) up",
    r"\brecap\b", r"previously[, ]", r"to remind you", r"so far,? ",
    r"quick(?:ly)? (?:recap|summar)", r"what happened (?:last|previously)",
]
# Real-world scheduling talk clusters at the very top of a recording and is
# never in-fiction: "after, like, three weeks - or a month".
SCHED = [r"\b(?:three|two|four|a few|several)\s+weeks?\b", r"\ba month\b",
         r"\bit'?s been\b.{0,24}\b(?:weeks?|months?)\b", r"\bwe last played\b"]
# A GM's verbal sting closing the recap before live play begins.
CLOSE = [r"\bbum,? bum,? bum\b", r"\band that'?s where we (?:left|stopped)\b",
         r"\bthat'?s the recap\b", r"\bso[,.]? here we are\b",
         r"\bnow[,.]? (?:back to|we (?:are|start))\b"]

PAST = re.compile(r"\b(?:was|were|had|did|went|came|took|gave|told|found|"
                  r"escaped|managed|realized|realised|decided|arrived|"
                  r"[a-z]{3,}ed)\b", re.I)
PRESENT2P = re.compile(r"\b(?:you see|you notice|you hear|you arrive|roll a|"
                       r"roll your|what do you|do you want|you can attempt)\b", re.I)

LABEL = re.compile(r'^\*\*\[?([^*\]]+?)\]?\*\*')
QUOTE = re.compile(r'^>\s*"')


def hits(text, pats):
    return [p for p in pats if re.search(p, text, re.I)]


def scan(path):
    text = open(path, encoding="utf-8").read()
    name = os.path.basename(path)
    heading = ""
    m = re.search(r"^####\s*(.+)$", text, re.M)
    if m:
        heading = m.group(1).strip()

    if "## Voiced moments" not in text:
        return {"file": name, "error": "no '## Voiced moments' section"}
    head, body = text.split("## Voiced moments", 1)
    offset = head.count("\n") + 1

    quotes, speaker = [], None
    for i, line in enumerate(body.split("\n"), start=offset):
        lm = LABEL.match(line)
        if lm:
            speaker = lm.group(1).strip(); continue
        if QUOTE.match(line):
            quotes.append({"line": i, "speaker": speaker, "text": line})

    n = len(quotes)
    joined = " ".join(q["text"] for q in quotes)
    gm = sum(1 for q in quotes if (q["speaker"] or "") == "GM")

    # Longest run of consecutive GM-only quotes anywhere: a recap is a
    # monologue. NOT anchored at quote 0 -- the recording usually opens with a
    # player on scheduling talk ("after, like, three weeks"), so an
    # opening-anchored run reads 0 on a scene that is 91% GM monologue.
    run = best = 0
    for q in quotes:
        run = run + 1 if (q["speaker"] or "") == "GM" else 0
        best = max(best, run)
    run = best

    past = len(PAST.findall(joined))
    pres = len(PRESENT2P.findall(joined))

    # Boundary candidates: the LAST closing-sting hit, and the FIRST quote that
    # reads like live play (second person / a call for a roll).
    close_at = None
    for q in quotes:
        if hits(q["text"], CLOSE):
            close_at = q["line"]
    live_at = next((q["line"] for q in quotes if PRESENT2P.search(q["text"])), None)

    ev = {
        "opening_markers": hits(joined, OPEN),
        "scheduling_talk": hits(joined, SCHED),
        "closing_sting": hits(joined, CLOSE),
    }
    # Max 6. Each term is independent evidence; none is sufficient alone.
    score = (2 * bool(ev["opening_markers"])
             + bool(ev["scheduling_talk"])
             + bool(ev["closing_sting"])
             + bool(re.search(r"recap", name + " " + heading, re.I))
             + (1 if n and gm / n >= 0.80 else 0))
    score = min(score, 6)

    return {
        "file": name, "heading": heading, "quotes": n,
        "gm_share": round(gm / n, 2) if n else 0.0,
        "longest_gm_run": run,
        "past_markers": past, "live_play_markers": pres,
        "evidence": {k: v for k, v in ev.items() if v},
        "score": score,
        "verdict": ("RECAP — strong" if score >= 4 else
                    "recap — possible" if score >= 2 else "not a recap"),
        "boundary_candidates": {
            "last_closing_sting_line": close_at,
            "first_live_play_line": live_at,
        },
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="a scene .md, or a directory of scene extractions")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--all-scenes", action="store_true",
                    help="scan every scene. Default is the FIRST scene only: the "
                         "recap is the opening of the recording, so that is where "
                         "it lives. Use this to audit the assumption, not to hunt "
                         "for a recap in the middle of a session.")
    a = ap.parse_args()

    files = (sorted(f for f in glob.glob(os.path.join(a.target, "*.md"))
                    if not f.endswith(".prev"))
             if os.path.isdir(a.target) else [a.target])
    if os.path.isdir(a.target) and not a.all_scenes:
        files = files[:1]
    out = [scan(f) for f in files]
    if a.json:
        json.dump(out, sys.stdout, indent=2, ensure_ascii=False); print(); return

    for r in out:
        if "error" in r:
            print(f"{r['file']:44} -- {r['error']}"); continue
        print(f"\n=== {r['file']}   [{r['verdict']}]  score {r['score']}/6")
        if r["heading"]:
            print(f"    heading: {r['heading'][:100]}")
        print(f"    {r['quotes']} quotes, GM share {r['gm_share']}, "
              f"longest GM-only run {r['longest_gm_run']}")
        print(f"    past-tense markers {r['past_markers']} vs live-play markers "
              f"{r['live_play_markers']}")
        for k, v in r["evidence"].items():
            print(f"    {k}: {v}")
        b = r["boundary_candidates"]
        if b["last_closing_sting_line"] or b["first_live_play_line"]:
            print(f"    boundary candidates -> closing sting at line "
                  f"{b['last_closing_sting_line']}, first live play at line "
                  f"{b['first_live_play_line']}")
    print("\nThis LOCATES the recap. It does not decide where it ends -- "
          "see SKILL.md Phase 2.")


if __name__ == "__main__":
    main()
