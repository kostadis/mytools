#!/usr/bin/env python3
"""Turn a summary_native NPC review into a review_items.json for build_review.py.

This is a shim. CampaignGenerator owns the cards: it runs

    summary_native review cards export REVIEW --campaign-dir DIR --out TMP --json

and this script maps each card of that packet to a kit item (CONTRACT.md). It
reads no review-store file; the packet copy in TMP is a CLI output.

    npc_review_items.py <review-dir> --out <file>.json
        [--campaign DIR] [--ids ID,ID,... | --ids-file FILE] [--action ACTION ...]
        [--title T] [--eyebrow E] [--lede L] [--footer F]
    build_review.py --in <file>.json --out <page>.html

<review-dir> names the review (its last path component is the review id);
without --campaign the campaign root is taken to be three levels above it.

Mapping: id = card id, t = title, y = approveMeans, n = rejectMeans, ev = the
card body plus its evidence and any previousDiscussion. EVERY packet string is
plain text and goes through html.escape. `members` and `draftSha256` pass
through (the page echoes them back), `group` is set for noise class cards, and
`reviewId` is the packet id. --ids/--ids-file map to export --item.

--allow-stale and --undecided are gone: a stale sign-off is never carded
(export reports it) and only undecided items are ever carded. --review-id is
gone too, because the page's reviewId must be the packet id.

Exit codes follow the CLI that refused (2 refusal, 3 stale, 5 conflict).
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

E = html.escape
EXCERPT = 600  # chars of each evidence excerpt shown before the <details> fold
NOISE_GROUP = "Classified noise"


def die(msg: str, code: int = 2) -> "int":
    print(f"error: {msg}", file=sys.stderr)
    return code


def run_export(review_id: str, campaign: Path, items: list[str] | None, actions: list[str] | None,
               tmp: Path) -> tuple[int, dict, str]:
    exe = shutil.which("summary_native")
    if not exe:
        raise SystemExit("error: `summary_native` is not on PATH; install CampaignGenerator "
                         "(uv pip install -e .) so its console script exists")
    out = tmp / "packet.json"
    cmd = [exe, "review", "cards", "export", review_id, "--campaign-dir", str(campaign),
           "--out", str(out), "--json"]
    for i in items or []:
        cmd += ["--item", i]
    for a in actions or []:
        cmd += ["--action", a]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        env = json.loads(r.stdout)
    except json.JSONDecodeError:
        env = {}
    return r.returncode, env, r.stderr


def evidence_html(rows: list[dict]) -> str:
    out = []
    for ev in rows:
        x = ev.get("excerpt")
        src = E(ev.get("source") or "")
        if not x:
            if ev.get("missingReason"):
                out.append(f"<br><code>{src}</code>: {E(ev['missingReason'])}")
            continue
        head = f"<br><code>{src}</code> ({E(ev.get('anchor') or '')}):"
        if len(x) <= EXCERPT:
            out.append(f"{head}<br><i>{E(x)}</i>")
        else:
            out.append(f"{head}<br><i>{E(x[:EXCERPT])}…</i><details><summary>Full excerpt "
                       f"({len(x)} chars)</summary><pre style=\"white-space:pre-wrap\">{E(x)}</pre></details>")
    return "".join(out)


def to_item(card: dict) -> dict:
    prev = card.get("previousDiscussion")
    ev = ""
    if prev:
        ev += f"<b>{E(prev)}</b><br>"
    ev += f"<pre style=\"white-space:pre-wrap\">{E(card['body'])}</pre>" if card.get("body") else ""
    ev += evidence_html(card.get("evidence") or [])
    item = {
        "id": card["id"],
        "t": E(card["title"]),
        "y": E(card["approveMeans"]),
        "n": E(card["rejectMeans"]),
        "ev": ev or E(card["title"]),
        "members": [m["itemId"] for m in card["members"]],
    }
    if card.get("draftSha256"):
        item["draftSha256"] = card["draftSha256"]
    if card["kind"] == "noise_class":
        item["group"] = NOISE_GROUP
    return item


def read_ids(a) -> list[str] | None:
    if a.ids:
        return [x.strip() for x in a.ids.split(",") if x.strip()]
    if a.ids_file:
        t = Path(a.ids_file).read_text(encoding="utf-8").strip()
        return json.loads(t) if t.startswith("[") else [x.strip() for x in t.splitlines() if x.strip()]
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("review_dir", type=Path, help="the review directory; its last component is the review id")
    ap.add_argument("--out", required=True, type=Path, help="items JSON to write (build_review.py --in)")
    ap.add_argument("--campaign", type=Path, help="campaign root (default: three levels above review_dir)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--ids", help="comma-separated item ids (export --item)")
    g.add_argument("--ids-file", help="JSON list or one id per line")
    ap.add_argument("--action", action="append", help="only this proposed action (repeatable)")
    ap.add_argument("--title"); ap.add_argument("--eyebrow"); ap.add_argument("--lede"); ap.add_argument("--footer")
    # Dropped flags: accepted by the parser only to refuse them with a reason.
    ap.add_argument("--allow-stale", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--undecided", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--review-id", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)

    if a.allow_stale:
        return die("--allow-stale was removed: a sign-off whose draft changed is never carded "
                   "(the export lists it as skipped); refresh the review instead")
    if a.undecided:
        return die("--undecided was removed: only undecided items are ever carded now")
    if a.review_id:
        return die("--review-id was removed: the page's reviewId is the packet id")

    rdir = a.review_dir.resolve()
    campaign = (a.campaign or rdir.parent.parent.parent).resolve()
    ids = read_ids(a)
    with tempfile.TemporaryDirectory() as t:
        rc, env, err = run_export(rdir.name, campaign, ids, a.action, Path(t))
        if rc != 0 or not env.get("ok"):
            msg = f"{env.get('code', 'summary_native failed')}: {env.get('message', err.strip())}"
            skipped = (env.get("data") or {}).get("skippedSignoffs") or []
            for s in skipped:
                msg += f"\n   skipped sign-off {s.get('npc')}: {s.get('code')}"
            return die(msg, rc or 2)
        packet = json.loads((Path(t) / "packet.json").read_text(encoding="utf-8"))

    cards = [to_item(c) for c in packet["cards"]]
    n_sign = sum(c["kind"] == "signoff" for c in packet["cards"])
    n_noise = sum(c["kind"] == "noise_class" for c in packet["cards"])
    n_subj = len({c.get("npc") for c in packet["cards"] if c.get("npc")})
    skipped = (env.get("data") or {}).get("skippedSignoffs") or []
    lede = (f"{len(cards)} cards: {n_sign} draft sign-offs, {len(cards) - n_sign - n_noise} checker findings"
            + (f" and {n_noise} classified-noise class cards" if n_noise else "")
            + f" across {n_subj} NPCs. Each card says what Approve and Reject do. Nothing is pre-selected.")
    if skipped:
        lede += f" {len(skipped)} stale sign-off(s) are not shown."
    doc = {
        "title": a.title or f"NPC review {packet['reviewId']}: {len(cards)} rulings",
        "reviewId": packet["packetId"],
        "eyebrow": a.eyebrow or f"summary-native NPC review / {packet['reviewId']}",
        "lede": a.lede or lede,
        "footer": a.footer or ("This page records nothing in the review. Your rulings are applied with "
                               "read_decisions.py --npc, then `summary_native review cards decide`."),
        "items": cards,
    }
    a.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {a.out}  ({len(cards)} cards: {n_sign} sign-offs, {len(cards) - n_sign} findings "
          f"incl. {n_noise} noise-class cards; packet {packet['packetId']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
