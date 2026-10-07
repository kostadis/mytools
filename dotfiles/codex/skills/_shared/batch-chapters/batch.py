#!/usr/bin/env python3
"""Plumbing for running one review stage across several chapters. See BATCH.md.

One config file (batch.json) names the chapters; every subcommand reads it.

  batch.py validate --config batch.json --stage stage1
      Per chapter: check that findings_<stage>.json and review_items_<stage>.json
      agree, that every edit's `old` occurs exactly `count` times in the target,
      then build review_<stage>.html. Writes nothing else.

  batch.py read --config batch.json --stage stage1 [--review-dir D --plain-names]
      Per chapter: validate decisions_<stage>.json against the items used to
      build the local review page, then print savedAt, the tally, unmarked and
      discuss ids. A missing or unsaved export is reported, not read.
      Works for ANY stage's pages, including speaker_review/ and spell_review/
      (--review-dir speaker_review --plain-names); validate/apply/manifest
      are for stages whose output is edits to a document.

  batch.py apply --config batch.json --stage stage1 [--rulings r.json] [--propagate-stage0] [--dry-run]
      Apply autos plus approved cards to the target file. ALL-OR-NOTHING across
      every chapter: nothing is written unless every chapter resolves and every
      count matches. Refuses while any card is unmarked, on an unsaved page, or
      in discuss, unless --rulings carries the GM's chat ruling for it.

  batch.py manifest --config batch.json --stage stage1 [--out-name NAME]
      Print (or write per chapter) a Markdown "Rulings" section: every finding,
      its verdict, where the verdict came from (page / chat), and what applied.

batch.json:
  {"campaign": "/abs/path/to/campaign",
   "summaries": "summaries",                  # relative to campaign
   "target": "session-summary.md",            # file the edits land in
   "chapters": [
     {"dir": "2025-01-06-chapter_015",
      "stage0": "gm-assist.md"}]}                 # optional; names vary per chapter

rulings.json (chat rulings; the GM's own words go in "said"):
  {"2025-01-13-chapter_016": {
     "rr-04": {"verdict": "approve", "said": "Approve"},
     "s1-04": {"verdict": "approve", "said": "Use that wording",
               "edits": [{"old": "...", "new": "...", "count": 1}]}}}
  "edits" replaces the card's own edits (a discuss note resolved to new wording).
"""
import argparse, json, os, pathlib, subprocess, sys

RP = pathlib.Path(os.environ.get("CODEX_HOME", pathlib.Path.home() / ".codex")) / "skills/_shared/review-page"


CARD = ("card", "tape")  # "tape": a transcript garble; its writes go to transcript_corrections.yaml, not the target


def load_cfg(p):
    c = json.load(open(p))
    base = pathlib.Path(c["campaign"]) / c.get("summaries", "summaries")
    return c, base


def findings(R, stage):
    f = json.load(open(R / f"findings_{stage}.json"))
    return f.get("findings", f) if isinstance(f, dict) else f


def target_of(c, ch, a):
    """File the edits land in: --target stage0 -> the chapter's Stage 0 source; --target NAME -> NAME; else batch.json target."""
    t = getattr(a, "target", None)
    if t == "stage0":
        if not ch.get("stage0"): raise SystemExit(f"{ch['dir']}: --target stage0 but batch.json has no stage0 for it")
        return ch["stage0"]
    return t or c.get("target", "session-summary.md")


def cmd_validate(a):
    c, base = load_cfg(a.config); bad = 0
    for ch in c["chapters"]:
        sd = base / ch["dir"]; R = sd / "staged_review"
        if not (R / f"review_items_{a.stage}.json").exists():
            print(f"== {ch['dir']}  not built yet (no review_items_{a.stage}.json)"); bad += 1; continue
        items = json.load(open(R / f"review_items_{a.stage}.json"))
        L = findings(R, a.stage); t = (sd / target_of(c, ch, a)).read_text()
        cards = {x["id"] for x in L if x.get("disposition") in CARD}
        iids = {i["id"] for i in items["items"]}
        mism = []  # simulate in file order, every auto and card approved -- the order apply uses
        for x in L:
            if x.get("disposition") not in ("auto",) + CARD: continue
            for e in x.get("edits", []):
                n = t.count(e["old"])
                if n != e.get("count"): mism.append((x["id"], e["old"][:60], e.get("count"), n))
                else: t = t.replace(e["old"], e["new"])
        lit = [i["id"] for i in items["items"] if any("\\n" in str(i.get(k, "")) for k in ("t", "y", "n"))]
        ok = not (mism or cards ^ iids or lit)
        bad += not ok
        print(f"== {ch['dir']}  items={len(iids)}  {'OK' if ok else 'PROBLEMS'}")
        if mism: print("   count mismatches:", mism)
        if cards - iids: print("   cards with no item:", sorted(cards - iids))
        if iids - cards: print("   items with no card:", sorted(iids - cards))
        if lit: print("   literal \\n in card text:", lit)
        if items["items"]:
            r = subprocess.run([sys.executable, str(RP / "build_review.py"), "--in", str(R / f"review_items_{a.stage}.json"),
                                "--out", str(R / f"review_{a.stage}.html")], capture_output=True, text=True)
            if r.returncode: bad += 1; print("   build failed:", r.stderr.strip()[-300:])
    sys.exit(1 if bad else 0)


def cmd_read(a):
    c, base = load_cfg(a.config); bad = 0
    # staged_review/ uses stage-suffixed names; speaker_review/ and spell_review/ use plain ones
    sfx = "" if a.plain_names else f"_{a.stage}"
    for ch in c["chapters"]:
        R = base / ch["dir"] / a.review_dir
        out = R / f"decisions{sfx}.json"
        items = R / f"review_items{sfx}.json"
        if not out.exists():
            print(f"== {ch['dir']}  NOT EXPORTED: {out}")
            bad += 1
            continue
        r = subprocess.run([sys.executable, str(RP / "read_decisions.py"), "--in", str(out),
                            "--items", str(items)],
                           capture_output=True, text=True)
        if r.returncode == 1:
            print(f"== {ch['dir']}  UNSAVED (savedAt missing) — not a decision"); bad += 1; continue
        if r.returncode:
            print(f"== {ch['dir']}  READ FAILED rc={r.returncode}: {r.stderr.strip()[-300:]}"); bad += 1; continue
        d = json.loads(r.stdout)
        print(f"== {ch['dir']}  savedAt={d.get('savedAt')}  tally={d.get('tally')}")
        if d.get("unmarked"): print("   UNMARKED (re-ask):", d["unmarked"])
        for i in d.get("discuss", []): print(f"   DISCUSS {i}: {d.get('notes', {}).get(i, '')!r}")
    sys.exit(1 if bad else 0)


def resolve(ch, a, base, rulings):
    """Return (plan, problems). plan: list of (id, source, verdict, edits)."""
    R = base / ch["dir"] / "staged_review"; df = R / f"decisions_{a.stage}.json"
    d = json.load(open(df)) if df.exists() else {"savedAt": None, "decisions": {}}
    page = d.get("decisions", {}) if d.get("savedAt") else {}
    chat = rulings.get(ch["dir"], {}); plan, probs = [], []
    for x in findings(R, a.stage):
        disp, i = x.get("disposition"), x["id"]
        if disp == "auto": plan.append((i, "auto", "approve", x.get("edits", []))); continue
        if disp not in CARD: continue
        if i in chat:
            r = chat[i]; plan.append((i, "chat", r["verdict"], r.get("edits", x.get("edits", [])))); continue
        v = page.get(i)
        if v is None: probs.append(f"{i}: {'page unsaved' if not d.get('savedAt') else 'unmarked'} — re-ask")
        elif v == "discuss": probs.append(f"{i}: discuss ({d.get('notes', {}).get(i, '')!r}) — needs a chat ruling")
        else: plan.append((i, "page", v, x.get("edits", [])))
    for i in chat:
        if i not in {p[0] for p in plan}: probs.append(f"{i}: chat ruling for an id that is not a card")
    return plan, probs, d


def cmd_apply(a):
    c, base = load_cfg(a.config); rulings = json.load(open(a.rulings)) if a.rulings else {}
    staged, probs = [], []
    for ch in c["chapters"]:  # pass 1: resolve and count, write nothing
        plan, p, d = resolve(ch, a, base, rulings); probs += [f"{ch['dir']} {x}" for x in p]
        target = target_of(c, ch, a)
        sd = base / ch["dir"]; t = (sd / target).read_text()
        s0p = sd / ch["stage0"] if a.propagate_stage0 and ch.get("stage0") else None
        s0 = s0p.read_text() if s0p else None; prop = []
        for i, src, v, edits in plan:
            if v != "approve": continue
            for e in edits:
                n = t.count(e["old"])
                if n != e["count"]: probs.append(f"{ch['dir']} {i}: expected {e['count']} of {e['old'][:60]!r}, found {n}"); continue
                t = t.replace(e["old"], e["new"])
                if s0 is not None and e["old"].strip() and s0.count(e["old"]):
                    prop.append((i, s0.count(e["old"]), e["old"][:60])); s0 = s0.replace(e["old"], e["new"])
        staged.append((ch, sd, target, t, s0p, s0, plan, prop, d))
    if probs:
        print("NOTHING WRITTEN. Resolve these first:"); [print("  ", p) for p in probs]; sys.exit(1)
    for ch, sd, target, t, s0p, s0, plan, prop, d in staged:  # pass 2: write
        tally = {}
        for _, src, v, _ in plan: tally[f"{src}:{v}"] = tally.get(f"{src}:{v}", 0) + 1
        print(f"== {ch['dir']}  {tally}  propagated into stage0: {len(prop)}")
        for i, src, v, _ in plan:
            x = next((f for f in findings(sd / "staged_review", a.stage) if f["id"] == i), {})
            tp = x.get("tape") or x.get("tape_cues")
            if v == "approve" and tp:
                print(f"    TAPE {i}: write these to transcript_corrections.yaml by hand, then sd_corrections apply/check:")
                for tc in tp: print(f"       cue {tc.get('cue')}: {str(tc.get('was'))[:70]!r} -> {str(tc.get('now'))[:70]!r}")
        for p in prop: print("    ->", p)
        if a.dry_run: continue
        (sd / target).write_text(t)
        if s0p: s0p.write_text(s0)
        R = sd / "staged_review"
        chat = rulings.get(ch["dir"], {})
        if chat:
            d.setdefault("decisions", {}); d["rulings_in_chat"] = {i: {"verdict": r["verdict"], "said": r.get("said", "")} for i, r in chat.items()}
            json.dump(d, open(R / f"decisions_{a.stage}.json", "w"), indent=1)
        json.dump({"plan": [{"id": i, "source": s, "verdict": v, "edits": len(e)} for i, s, v, e in plan],
                   "stage0_propagated": prop}, open(R / f"apply_{a.stage}_log.json", "w"), indent=1)
    if a.dry_run: print("(dry run: nothing written)")


def cmd_manifest(a):
    c, base = load_cfg(a.config); rulings = json.load(open(a.rulings)) if a.rulings else {}
    for ch in c["chapters"]:
        R = base / ch["dir"] / "staged_review"; plan, probs, d = resolve(ch, a, base, rulings)
        items = {i["id"]: i for i in json.load(open(R / f"review_items_{a.stage}.json"))["items"]}
        got = {p[0]: p for p in plan}; chat = rulings.get(ch["dir"], {})
        out = [f"## Rulings — {a.stage}", "",
               f"Page saved at {d.get('savedAt') or 'NEVER (ruled in chat)'}. "
               f"{len([p for p in plan if p[1] == 'page'])} from the page, {len(chat)} in chat, "
               f"{len([p for p in plan if p[1] == 'auto'])} auto. Unresolved: {len(probs)}.", ""]
        for x in findings(R, a.stage):
            i = x["id"]; txt = items.get(i, {}).get("t") or x.get("summary") or x.get("issue") or ""
            if i in got: _, src, v, _ = got[i]; tag = f"**{v}** ({src}" + (f": “{chat[i].get('said', '')}”" if src == "chat" else "") + ")"
            elif x.get("disposition") in ("card",): tag = "**UNRESOLVED**"
            else: tag = f"_{x.get('disposition')}_"
            out.append(f"- **{i}** — {tag}: {' '.join(str(txt).split())}")
        if probs: out += ["", "Unresolved:"] + [f"- {p}" for p in probs]
        md = "\n".join(out) + "\n"
        if a.out_name: (base / ch["dir"] / a.out_name).write_text(md); print("wrote", base / ch["dir"] / a.out_name)
        else: print(f"# {ch['dir']}\n\n{md}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in [("validate", cmd_validate), ("read", cmd_read), ("apply", cmd_apply), ("manifest", cmd_manifest)]:
        p = sp.add_parser(name); p.set_defaults(fn=fn)
        p.add_argument("--config", required=True); p.add_argument("--stage", required=True,
                       help="file-name stem: enhance | stage1 | recap | ...")
        if name in ("validate", "apply"):
            p.add_argument("--target", help="file the edits land in: 'stage0' = each chapter's Stage 0 source, or a file name (default: batch.json target)")
        if name == "read":
            p.add_argument("--review-dir", default="staged_review",
                           help="per-chapter folder holding the page files (speaker_review, spell_review, ...)")
            p.add_argument("--plain-names", action="store_true",
                           help="review_items.json / decisions.json, no _<stage> suffix (speaker and spell pages)")
        if name in ("apply", "manifest"): p.add_argument("--rulings")
        if name == "apply":
            p.add_argument("--propagate-stage0", action="store_true"); p.add_argument("--dry-run", action="store_true")
        if name == "manifest": p.add_argument("--out-name", help="write <chapter>/<NAME> instead of printing")
    a = ap.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
