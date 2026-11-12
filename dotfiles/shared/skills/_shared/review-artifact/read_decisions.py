#!/usr/bin/env python3
"""Read GM decisions back out of a saved review artifact.

The review page (see build_review.py) republishes ITSELF on save, embedding
the decisions in <script type="application/json" id="state">. Fetch the
artifact with WebFetch — which returns raw HTML for claude.ai/code/artifact
URLs, and for large pages also saves it to a local file whose path it
reports — then point this at that file.

Usage:
    read_decisions.py --html saved-artifact.html [--items review_items.json] [--out decisions.json]
    read_decisions.py --in decisions.json [--items review_items.json] [--out normalized.json]

--html reads a page saved with `build_review.py --save artifact` (the page
republished itself). --in validates the decisions.json export of a page built
with `--save local` (Copy output / Save output / Save to VM): every item is
either in `decisions` or in `unmarked`, notes must belong to one of those, and
with --items the exported ids and reviewId must match the items file the page
was built from, which catches a stale export. `normalize()` is the single
validator the serve_review.py save endpoint also calls.

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


def page_picks(html: str) -> dict[str, list[str]]:
    """Per-card clickable word choices (items[].picks); empty on older pages."""
    m = ITEMS_RE.search(html)
    items = json.loads(m.group(1).replace("\\u003c", "<")) if m else []
    return {it["id"]: it["picks"] for it in items if it.get("picks")}


def page_members(html: str) -> dict[str, list[str]]:
    """Per-card member item ids (items[].members): a card that stands for several items. Empty on older pages."""
    m = ITEMS_RE.search(html)
    items = json.loads(m.group(1).replace("\\u003c", "<")) if m else []
    return {it["id"]: it["members"] for it in items if it.get("members")}


class DecisionError(ValueError):
    """A decision export cannot be trusted or does not match its items file."""

    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.exit_code = exit_code


def expected_review_id(spec: dict) -> str:
    review_id = spec.get("reviewId")
    if review_id is not None:
        if not isinstance(review_id, str) or not review_id:
            raise DecisionError("items file has an invalid reviewId")
        return review_id
    title = spec.get("title")
    if not isinstance(title, str) or not title:
        raise DecisionError("items file has no title or reviewId")
    return re.sub(r"[^A-Za-z0-9_.:-]+", "-", title).strip("-")


def expected_item_ids(spec: object) -> set[str]:
    if not isinstance(spec, dict) or not isinstance(spec.get("items"), list):
        raise DecisionError("items file does not contain an items list")
    ids: list[str] = []
    for item in spec["items"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise DecisionError("items file contains an item without a string id")
        ids.append(item["id"])
    if not ids or len(ids) != len(set(ids)):
        raise DecisionError("items file must contain unique item ids")
    return set(ids)


def normalize(payload: object, spec: dict | None = None) -> dict:
    """Validate and normalize one browser export.

    Both the CLI and the HTTP save endpoint call this function. Keeping the
    trust boundary here prevents a served page from acquiring a second, looser
    interpretation of the decision format.
    """
    if not isinstance(payload, dict):
        raise DecisionError("input is not a JSON object")
    if payload.get("schemaVersion", 1) != 1:
        raise DecisionError(f"unsupported schemaVersion: {payload.get('schemaVersion')!r}")
    decisions = payload.get("decisions")
    if not isinstance(payload.get("savedAt"), str) or not payload["savedAt"].strip():
        raise DecisionError("input is not a saved review decision file", 1)
    if not isinstance(decisions, dict):
        raise DecisionError("input is not a saved review decision file", 1)

    bad = {
        key: value for key, value in decisions.items()
        if not isinstance(value, str) or value not in VALID
    }
    if bad:
        raise DecisionError(f"unrecognised verdicts: {bad}")

    notes = payload.get("notes", {})
    if not isinstance(notes, dict):
        raise DecisionError("'notes' is not an object")
    unmarked = payload.get("unmarked", [])
    if not isinstance(unmarked, list):
        raise DecisionError("'unmarked' is not a list")
    if not all(isinstance(item, str) for item in unmarked):
        raise DecisionError("'unmarked' ids must be strings")
    if len(unmarked) != len(set(unmarked)):
        raise DecisionError("'unmarked' contains duplicate ids")
    both = sorted(set(decisions) & set(unmarked))
    if both:
        raise DecisionError(f"ids both decided and unmarked: {both}")
    asked = set(decisions) | set(unmarked)
    stray = sorted(set(notes) - asked)
    if stray:
        raise DecisionError(f"notes for ids the page never asked about: {stray}")

    if spec is not None:
        expected = expected_item_ids(spec)
        if expected != asked:
            raise DecisionError(
                "this export was not made from --items "
                f"(only in export: {sorted(asked - expected)}, "
                f"only in items: {sorted(expected - asked)}). "
                "Is it a stale export from an earlier run?"
            )
        expected_id = expected_review_id(spec)
        if payload.get("reviewId") != expected_id:
            raise DecisionError(
                "this export has the wrong reviewId "
                f"({payload.get('reviewId')!r}; expected {expected_id!r}). "
                "Is it from another review page?"
            )

    tally = {
        value: sum(1 for choice in decisions.values() if choice == value)
        for value in sorted(VALID)
    }
    return {
        "schemaVersion": payload.get("schemaVersion", 1),
        "reviewId": payload.get("reviewId"),
        "savedAt": payload["savedAt"],
        "decided": len(decisions),
        "tally": tally,
        "decisions": decisions,
        "notes": notes,
        "discuss": sorted(key for key, value in decisions.items() if value == "discuss"),
        "unmarked": unmarked,
    }


def main_html(args: argparse.Namespace) -> int:
    html = args.html.read_text(encoding="utf-8", errors="replace")
    state = extract(html)
    ids = page_item_ids(html)

    decisions = state.get("decisions") or {}
    raw_decisions = dict(decisions)
    notes = state.get("notes") or {}
    saved_at = state.get("savedAt")

    if not saved_at and not args.allow_unsaved:
        print("error: this page has never been saved (savedAt is null).", file=sys.stderr)
        print("       The GM has not pressed Save yet — do NOT treat this as 'no decisions'.", file=sys.stderr)
        raise SystemExit(1)

    picks = state.get("picks") or {}
    offered = page_picks(html)
    valid = VALID | page_extra_keys(html) | ({"pick"} if offered else set())
    bad = {k: v for k, v in decisions.items() if v not in valid}
    if bad:
        print(f"error: unrecognised verdicts: {bad}", file=sys.stderr)
        raise SystemExit(2)

    for iid, v in decisions.items():
        if v == "pick" and picks.get(iid) not in offered.get(iid, []):
            print(f"error: {iid} is marked 'pick' but its picked word {picks.get(iid)!r} "
                  f"is not one the card offered {offered.get(iid)}", file=sys.stderr)
            raise SystemExit(2)
    picks = {k: w for k, w in picks.items() if decisions.get(k) == "pick"}

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

    # A card with `members` is a class card: one verdict stands for each member item. The members come from
    # the items file (the page must agree with it), and only an explicit non-discuss verdict is expanded.
    # Discuss and unmarked class cards yield no decision for any member.
    page_mem = page_members(html)
    members = page_mem
    if args.items:
        file_mem = {it["id"]: it["members"] for it in spec.get("items", []) if it.get("members")}
        if file_mem != page_mem:
            diff = sorted(k for k in set(file_mem) | set(page_mem) if file_mem.get(k) != page_mem.get(k))
            print(f"error: class-card membership on the page differs from --items for {diff}. "
                  "Is it a stale page from an earlier run?", file=sys.stderr)
            raise SystemExit(2)
        members = file_mem
    classes: dict[str, dict] = {}
    if members:
        expanded: dict[str, str] = {}
        enotes: dict[str, str] = {}
        for k, v in decisions.items():
            if k not in members:
                expanded[k] = v
                continue
            if v == "discuss":
                continue
            classes[k] = {"verdict": v, "members": members[k]}
            # Every member's note says it came from one class-card verdict, so the decision history
            # downstream (CG `review decide`) shows provenance, not an apparently individual ruling.
            provenance = f"GM class verdict on batch card [{k}] ({len(members[k])} occurrences)"
            for mid in members[k]:
                expanded[mid] = v
                enotes[mid] = f"{provenance}: {notes[k]}" if notes.get(k) else provenance
        for k, n in notes.items():
            if k not in members:
                enotes[k] = n
        if set(expanded) & set(members):
            print(f"error: a member item id collides with a class-card id: {sorted(set(expanded) & set(members))}",
                  file=sys.stderr)
            raise SystemExit(2)
        decisions, notes = expanded, enotes

    tally = {v: sum(1 for x in decisions.values() if x == v) for v in sorted(valid)}
    out = {
        "schemaVersion": 1,
        "reviewId": state.get("reviewId"),
        "savedAt": saved_at,
        "decided": len(decisions),
        "tally": tally,
        "decisions": decisions,
        "notes": notes,
        "picks": picks,
        "discuss": sorted(k for k, v in decisions.items() if v == "discuss"),
        "unmarked": [i for i in ids if i not in decisions and i not in raw_decisions],
    }
    if members:
        out["classes"] = classes  # class card id -> {verdict, members}; absent for pages with no class card
        out["discuss"] = sorted(set(out["discuss"]) | {k for k in members if raw_decisions.get(k) == "discuss"})

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


def main_in(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(args.inp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read decisions: {exc}", file=sys.stderr)
        return 2

    spec = None
    if args.items:
        try:
            spec = json.loads(args.items.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: cannot read items: {exc}", file=sys.stderr)
            return 2
    try:
        normalized = normalize(payload, spec)
    except DecisionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code

    blob = json.dumps(normalized, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(blob + "\n", encoding="utf-8")
        print(f"{normalized['decided']} decided -> {args.out}")
    else:
        print(blob)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--html", type=Path, help="saved artifact HTML (page built with --save artifact)")
    src.add_argument("--in", dest="inp", type=Path, help="decisions.json exported by a page built with --save local")
    ap.add_argument("--items", type=Path,
                    help="the review_items JSON the page was built from; its ids must match the page's")
    ap.add_argument("--out", type=Path, help="write decisions JSON here (default: stdout)")
    ap.add_argument("--allow-unsaved", action="store_true",
                    help="--html only: do not fail when savedAt is null (inspecting a fresh page)")
    args = ap.parse_args()
    return main_in(args) if args.inp else main_html(args)


if __name__ == "__main__":
    raise SystemExit(main())
