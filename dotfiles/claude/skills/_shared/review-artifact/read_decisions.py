#!/usr/bin/env python3
"""Read GM decisions back out of a saved review artifact.

The review page (see build_review.py) republishes ITSELF on save, embedding
the decisions in <script type="application/json" id="state">. Fetch the
artifact with WebFetch — which returns raw HTML for claude.ai/code/artifact
URLs, and for large pages also saves it to a local file whose path it
reports — then point this at that file.

Usage:
    read_decisions.py --html saved-artifact.html [--items review_items.json] [--out decisions.json]

Every decision and note must be keyed to an item the page actually asked
about (its embedded ITEMS). With --items, the page's item ids must also equal
the ids in the items file you built, which catches reading back a stale page
from an earlier run. Items with no decision are listed as "unmarked".

Exit codes:
    0  decisions read
    1  no state block, or the page was never saved (savedAt is null)
    2  malformed input, a decision for an id the page never asked about, or
       a page whose items do not match --items

Failing loudly on an unsaved page is the point: a silent empty result would
read as "the GM approved nothing" when it actually means "the GM has not
pressed Save yet."
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

STATE_RE = re.compile(
    r'<script[^>]*type=["\']application/json["\'][^>]*id=["\']state["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
# id before type — the shell may reorder attributes on republish
STATE_RE_ALT = re.compile(
    r'<script[^>]*id=["\']state["\'][^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)

VALID = {"approve", "reject", "discuss"}

ITEMS_RE = re.compile(r"var ITEMS = (\[.*?\]);\s*$", re.M | re.S)
EXTRA_RE = re.compile(r"var EXTRA = (\[.*?\]);\s*$", re.M | re.S)


def page_extra_keys(html: str) -> set[str]:
    """Verdicts the page declared beyond approve/reject/discuss (none on older pages)."""
    m = EXTRA_RE.search(html)
    if not m:
        return set()
    try:
        return {e["key"] for e in json.loads(m.group(1).replace("\\u003c", "<"))}
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"error: the page's EXTRA verdict list is not valid: {e}", file=sys.stderr)
        raise SystemExit(2)


def extract(html: str) -> dict:
    m = STATE_RE.search(html) or STATE_RE_ALT.search(html)
    if not m:
        print("error: no <script type=\"application/json\" id=\"state\"> block found.", file=sys.stderr)
        print("       Is this the review artifact's HTML? WebFetch returns raw HTML for", file=sys.stderr)
        print("       claude.ai/code/artifact URLs; a summarised fetch will not work.", file=sys.stderr)
        raise SystemExit(1)
    raw = m.group(1).strip().replace("\\u003c", "<")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"error: state block is not valid JSON: {e}", file=sys.stderr)
        raise SystemExit(2)


def page_item_ids(html: str) -> list[str]:
    m = ITEMS_RE.search(html)
    if not m:
        print("error: no ITEMS list found in the page source; cannot check decision ids.", file=sys.stderr)
        raise SystemExit(2)
    try:
        items = json.loads(m.group(1).replace("\\u003c", "<"))
    except json.JSONDecodeError as e:
        print(f"error: the page's ITEMS list is not valid JSON: {e}", file=sys.stderr)
        raise SystemExit(2)
    return [it["id"] for it in items]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--html", required=True, type=Path, help="saved artifact HTML")
    ap.add_argument("--items", type=Path,
                    help="the review_items JSON this page was built from; its ids must match the page's")
    ap.add_argument("--out", type=Path, help="write decisions JSON here (default: stdout)")
    ap.add_argument("--allow-unsaved", action="store_true",
                    help="do not fail when savedAt is null (inspecting a fresh page)")
    args = ap.parse_args()

    html = args.html.read_text(encoding="utf-8", errors="replace")
    state = extract(html)
    ids = page_item_ids(html)

    decisions = state.get("decisions") or {}
    notes = state.get("notes") or {}
    saved_at = state.get("savedAt")

    if not saved_at and not args.allow_unsaved:
        print("error: this page has never been saved (savedAt is null).", file=sys.stderr)
        print("       The GM has not pressed Save yet — do NOT treat this as 'no decisions'.", file=sys.stderr)
        raise SystemExit(1)

    valid = VALID | page_extra_keys(html)
    bad = {k: v for k, v in decisions.items() if v not in valid}
    if bad:
        print(f"error: unrecognised verdicts: {bad}", file=sys.stderr)
        raise SystemExit(2)

    known = set(ids)
    unknown = sorted((set(decisions) | set(notes)) - known)
    if unknown:
        print(f"error: decisions or notes for ids this page never asked about: {unknown}", file=sys.stderr)
        raise SystemExit(2)
    if args.items:
        spec = json.loads(args.items.read_text(encoding="utf-8"))
        if spec.get("reviewId") and spec["reviewId"] != state.get("reviewId"):
            print(f"error: this page's reviewId {state.get('reviewId')!r} is not "
                  f"--items' {spec['reviewId']!r}. Is it a page from another run?", file=sys.stderr)
            raise SystemExit(2)
        expected = {it["id"] for it in spec.get("items", [])}
        if expected != known:
            print("error: this page was not built from --items "
                  f"(only on page: {sorted(known - expected)}, only in items: {sorted(expected - known)}). "
                  "Is it a stale page from an earlier run?", file=sys.stderr)
            raise SystemExit(2)

    tally = {v: sum(1 for x in decisions.values() if x == v) for v in sorted(valid)}
    out = {
        "schemaVersion": 1,
        "reviewId": state.get("reviewId"),
        "savedAt": saved_at,
        "decided": len(decisions),
        "tally": tally,
        "decisions": decisions,
        "notes": notes,
        "discuss": sorted(k for k, v in decisions.items() if v == "discuss"),
        "unmarked": [i for i in ids if i not in decisions],
    }

    blob = json.dumps(out, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(blob + "\n", encoding="utf-8")
        print(f"{len(decisions)} decided  "
              f"({', '.join(f'{n} {v}' for v, n in tally.items())}, "
              f"{len(out['unmarked'])} unmarked)  "
              f"saved {saved_at}  ->  {args.out}")
    else:
        print(blob)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
