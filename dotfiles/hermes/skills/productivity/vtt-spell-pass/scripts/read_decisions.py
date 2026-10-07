#!/usr/bin/env python3
"""Read GM decisions back out of a saved review artifact.

The review page (see build_review.py) republishes ITSELF on save, embedding
the decisions in <script type="application/json" id="state">. Fetch the
artifact with WebFetch — which returns raw HTML for claude.ai/code/artifact
URLs, and for large pages also saves it to a local file whose path it
reports — then point this at that file.

Usage:
    read_decisions.py --html saved-artifact.html [--out decisions.json]

Exit codes:
    0  decisions read
    1  no state block, or the page was never saved (savedAt is null)
    2  malformed input

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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--html", required=True, type=Path, help="saved artifact HTML")
    ap.add_argument("--out", type=Path, help="write decisions JSON here (default: stdout)")
    ap.add_argument("--allow-unsaved", action="store_true",
                    help="do not fail when savedAt is null (inspecting a fresh page)")
    args = ap.parse_args()

    state = extract(args.html.read_text(encoding="utf-8", errors="replace"))

    decisions = state.get("decisions") or {}
    notes = state.get("notes") or {}
    saved_at = state.get("savedAt")

    if not saved_at and not args.allow_unsaved:
        print("error: this page has never been saved (savedAt is null).", file=sys.stderr)
        print("       The GM has not pressed Save yet — do NOT treat this as 'no decisions'.", file=sys.stderr)
        raise SystemExit(1)

    bad = {k: v for k, v in decisions.items() if v not in VALID}
    if bad:
        print(f"error: unrecognised verdicts: {bad}", file=sys.stderr)
        raise SystemExit(2)

    tally = {v: sum(1 for x in decisions.values() if x == v) for v in sorted(VALID)}
    out = {
        "savedAt": saved_at,
        "decided": len(decisions),
        "tally": tally,
        "decisions": decisions,
        "notes": notes,
        "discuss": sorted(k for k, v in decisions.items() if v == "discuss"),
    }

    blob = json.dumps(out, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(blob + "\n", encoding="utf-8")
        print(f"{len(decisions)} decided  "
              f"({tally['approve']} approve, {tally['reject']} reject, {tally['discuss']} discuss)  "
              f"saved {saved_at}  ->  {args.out}")
    else:
        print(blob)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
