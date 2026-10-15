#!/usr/bin/env python3
"""Turn a summary_native NPC review into a review_items.json for build_review.py.

A summary_native review lives at <campaign>/docs/reviews/<review-id>/:
manifest.json names each item and its current revision, items/<id>/<rev>.json
holds it, and events/*.json holds the decisions recorded so far. This reads
those files (read-only) and writes contract-shaped cards (CONTRACT.md), one per
item, so an NPC review page never has to be hand-written again.

    npc_review_items.py <review-dir> --out <file>.json [--undecided]
        [--ids ID,ID,... | --ids-file FILE] [--action ACTION ...]
        [--title T] [--eyebrow E] [--lede L] [--footer F] [--review-id ID]
    build_review.py --in <file>.json --out <page>.html

Card ids are the review's own item ids, so decisions.json comes back keyed by
the ids `summary_native review decide` and `review npc sign` take. This script
records nothing in the review: the page only collects the GM's rulings.

Every card carries a keep-as-is outcome. For a finding, Approve keeps the
draft line as written (accept_no_change). For a sign-off, Reject keeps the
draft exactly as it is, unpublished.

Filters:
    --undecided   only items with no current decision: never decided, decided
                  on an older item revision, withdrawn, or left at discuss
    --ids/--ids-file   only these item ids (a JSON list, or one id per line);
                  an id the review does not have is an error
    --action      only items whose proposed action is this (repeatable):
                  signoff_npc_draft, review_claim_against_evidence,
                  review_presentation, ...

A sign-off card shows the draft's full text and its sha256. If the draft on
disk no longer has the bytes the item asks to sign, the script stops (exit 2):
signing would fail, and the card would show the GM the wrong text.
--allow-stale builds anyway and marks those cards STALE (for inspecting an old
review, not for collecting sign-offs).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path

E = html.escape
EXCERPT = 600  # chars of each evidence excerpt shown before the <details> fold


def load_review(rdir: Path) -> tuple[str, list[dict], list[dict]]:
    """(review_id, current items in manifest order, events)."""
    man = json.loads((rdir / "manifest.json").read_text(encoding="utf-8"))
    items = []
    for ref in man.get("items", []):
        f = rdir / "items" / ref["item_id"] / f"{ref.get('revision', 1)}.json"
        if not f.exists():
            raise SystemExit(f"{f}: listed in manifest.json but missing")
        items.append(json.loads(f.read_text(encoding="utf-8")))
    events = [json.loads(f.read_text(encoding="utf-8")) for f in sorted((rdir / "events").glob("*.json"))] \
        if (rdir / "events").is_dir() else []
    return man.get("review_id") or rdir.name, items, events


def current_decisions(items: list[dict], events: list[dict]) -> dict[str, dict]:
    """item_id -> the event that currently decides it (approve/reject on the current revision)."""
    rev = {i["item_id"]: i.get("revision", 1) for i in items}
    latest: dict[str, dict] = {}
    for e in events:
        iid = e.get("item_id")
        if iid not in rev or e.get("decision_revision") is None:
            continue  # rebind/stage events and decisions for items no longer in the review
        if iid not in latest or e["decision_revision"] > latest[iid]["decision_revision"]:
            latest[iid] = e
    return {iid: e for iid, e in latest.items()
            if e.get("kind") != "withdrawal"
            and e.get("item_revision", rev[iid]) == rev[iid]
            and e.get("verdict") in ("approve", "reject")}


def subject_name(item: dict, root: Path) -> str:
    d = item.get("proposed_action", {}).get("details", {})
    if d.get("npc"):
        return d["npc"]
    paths = [b.get("path", "") for b in item.get("input_bindings", [])] + \
            [e.get("source_path", "") for e in item.get("evidence", [])]
    for p in paths:  # an evidence file states its subject in its front matter
        if "/evidence/" in p and (root / p).is_file():
            m = re.search(r"^subject: (.+)$", (root / p).read_text(encoding="utf-8"), re.M)
            if m:
                return m.group(1).strip()
    src = item.get("locator", {}).get("source_path") or (paths[0] if paths else item["item_id"])
    stem = Path(src).stem
    return (stem[4:] if stem.startswith("npc_") else stem).replace("_", " ").title()


def diag_html(item: dict) -> str:
    msgs = sorted({d.get("message", "") for d in item.get("diagnostics", []) if d.get("message")})
    return "".join(f"<br>Checker: <i>{E(m)}</i>" for m in msgs)


def evidence_html(item: dict) -> str:
    out = []
    for ev in item.get("evidence", []):
        x = ev.get("exact_excerpt")
        if not x:
            if ev.get("missing_reason"):
                out.append(f"<br><code>{E(ev.get('source_path', ''))}</code>: {E(ev['missing_reason'])}")
            continue
        head = f"<br><code>{E(ev.get('source_path', ''))}</code> ({E(ev.get('anchor', ''))}):"
        if len(x) <= EXCERPT:
            out.append(f"{head}<br><i>{E(x)}</i>")
        else:
            out.append(f"{head}<br><i>{E(x[:EXCERPT])}…</i><details><summary>Full excerpt "
                       f"({len(x)} chars)</summary><pre style=\"white-space:pre-wrap\">{E(x)}</pre></details>")
    return "".join(out)


def card(item: dict, root: Path, decided: dict | None, stale: str = "") -> dict:
    act = item.get("proposed_action", {}).get("action", "")
    d = item.get("proposed_action", {}).get("details", {})
    who = E(subject_name(item, root))
    loc = item.get("locator", {})
    where = E(loc.get("source_path", ""))
    line = loc.get("display_line")
    prior = (f"<br><b>Already decided:</b> {E(decided['verdict'])} ({E(decided.get('disposition', ''))}) "
             f"by {E(decided.get('reviewer', '?'))}" + (f": <i>{E(decided['note'])}</i>" if decided.get("note") else "")
             ) if decided else ""
    if act == "signoff_npc_draft":
        p = root / d["draft_path"]
        body = p.read_bytes().decode("utf-8") if p.is_file() else "(draft file missing)"
        warn = (f"<b>STALE: {E(stale)}. Signing these bytes would fail; refresh the review.</b><br>"
                if stale else "")
        return {
            "id": item["item_id"],
            "t": f"Sign off <b>{who}</b>'s draft for publication",
            "y": f"Record a GM sign-off for these exact bytes (<code>review npc sign</code>, sha256 "
                 f"<code>{E(d['draft_sha256'][:16])}…</code>); publish can then proceed.",
            "n": "Keep the draft as it is, unsigned and unpublished. Say what to change in a note; "
                 "the fix goes in the draft and comes back for a new sign-off.",
            "ev": f"{warn}<code>{where}</code>. Mechanical verdict: {E(str(d.get('mechanical_verdict', '?')))}."
                  f"{diag_html(item)}{prior}"
                  f"<details><summary>Full draft text</summary><pre style=\"white-space:pre-wrap\">{E(body)}</pre></details>",
        }
    at = f" L{line}" if line else ""
    kind = {"review_claim_against_evidence": "claim vs evidence",
            "review_presentation": "presentation"}.get(act, act or "finding")
    return {
        "id": item["item_id"],
        "t": f"<b>{who}</b>{at} ({E(kind)}): {E(item.get('rationale', ''))}",
        "y": f"Keep as-is: the draft line stands as written (records <code>accept_no_change</code>). "
             f"No edit to <code>{where}</code>.",
        "n": f"The line is wrong: no sign-off for this draft until it is corrected in <code>{where}</code> "
             f"(the draft is the origin). Say the fix in a note.",
        "ev": f"<code>{where}{':' + str(line) if line else ''}</code><br>Claim: <i>{E(item.get('claim_text', ''))}</i>"
              f"{diag_html(item)}{evidence_html(item)}{prior}",
    }


def read_ids(a) -> list[str] | None:
    if a.ids:
        return [x.strip() for x in a.ids.split(",") if x.strip()]
    if a.ids_file:
        t = Path(a.ids_file).read_text(encoding="utf-8").strip()
        return json.loads(t) if t.startswith("[") else [x.strip() for x in t.splitlines() if x.strip()]
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("review_dir", type=Path, help="<campaign>/docs/reviews/<review-id>")
    ap.add_argument("--out", required=True, type=Path, help="items JSON to write (build_review.py --in)")
    ap.add_argument("--campaign", type=Path, help="campaign root (default: three levels above review_dir)")
    ap.add_argument("--undecided", action="store_true", help="only items with no current approve/reject")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--ids", help="comma-separated item ids")
    g.add_argument("--ids-file", help="JSON list or one id per line")
    ap.add_argument("--action", action="append", help="only this proposed action (repeatable)")
    ap.add_argument("--allow-stale", action="store_true",
                    help="build even if a sign-off's draft bytes changed; those cards are marked STALE")
    ap.add_argument("--title"); ap.add_argument("--eyebrow"); ap.add_argument("--lede"); ap.add_argument("--footer")
    ap.add_argument("--review-id", help="page reviewId (default: <review-id>:<hash of the selected ids>)")
    a = ap.parse_args(argv)

    rdir = a.review_dir.resolve()
    root = (a.campaign or rdir.parent.parent.parent).resolve()
    rid, items, events = load_review(rdir)
    decided = current_decisions(items, events)
    ids = read_ids(a)
    if ids is not None:
        known = {i["item_id"] for i in items}
        unknown = [x for x in ids if x not in known]
        if unknown:
            print(f"error: not items of {rid}: {unknown}", file=sys.stderr); return 2
        want = set(ids); items = [i for i in items if i["item_id"] in want]
    if a.action:
        items = [i for i in items if i.get("proposed_action", {}).get("action") in a.action]
    if a.undecided:
        items = [i for i in items if i["item_id"] not in decided]
    if not items:
        print("error: no items left after filtering; nothing to review", file=sys.stderr); return 1

    stale: dict[str, str] = {}
    for i in items:
        d = i.get("proposed_action", {}).get("details", {})
        if i.get("proposed_action", {}).get("action") == "signoff_npc_draft":
            p = root / d.get("draft_path", "")
            got = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "missing"
            if got != d.get("draft_sha256"):
                stale[i["item_id"]] = f"{d.get('draft_path')} is {got[:16]} on disk, the item signs {str(d.get('draft_sha256'))[:16]}"
    if stale and not a.allow_stale:
        print("error: drafts changed since the review was created; refresh the review first "
              "(or --allow-stale to build anyway, with the cards marked STALE):", file=sys.stderr)
        for k, v in stale.items(): print(f"   {k}: {v}", file=sys.stderr)
        return 2

    def draft_of(i):  # group by the draft file: sign-off and findings may name the NPC differently
        return Path(i.get("locator", {}).get("source_path") or i["item_id"]).stem.casefold()

    def key(i):
        so = i.get("proposed_action", {}).get("action") == "signoff_npc_draft"
        return (draft_of(i), so, i.get("locator", {}).get("display_line") or 0, i["item_id"])
    items.sort(key=key)
    cards = [card(i, root, decided.get(i["item_id"]), stale.get(i["item_id"], "")) for i in items]
    n_sign = sum(i.get("proposed_action", {}).get("action") == "signoff_npc_draft" for i in items)
    n_subj = len({draft_of(i) for i in items})
    digest = hashlib.sha256(",".join(sorted(c["id"] for c in cards)).encode()).hexdigest()[:8]
    doc = {
        "title": a.title or f"NPC review {rid}: {len(cards)} rulings",
        "reviewId": a.review_id or f"{rid}:{digest}",
        "eyebrow": a.eyebrow or f"{root.name} / summary-native NPC review / {rid}",
        "lede": a.lede or (f"{len(cards)} cards across {n_subj} NPCs: {n_sign} draft sign-offs and "
                           f"{len(cards) - n_sign} checker findings, grouped by NPC. Each card says what Approve "
                           f"and Reject do; one of the two always keeps the text as it is. Nothing is pre-selected."),
        "footer": a.footer or ("This page records nothing in the review. Your rulings are entered with "
                               "<code>summary_native review decide</code> (findings) and <code>review npc sign</code> "
                               "(sign-offs), keyed by these same item ids."),
        "items": cards,
    }
    a.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {a.out}  ({len(cards)} cards: {n_sign} sign-offs, {len(cards) - n_sign} findings; "
          f"{sum(c['id'] in decided for c in cards)} already decided)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
