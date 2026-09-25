#!/usr/bin/env python3
"""Render a VTT spell-pass queue with the shared Codex review page."""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
from pathlib import Path


def escaped(value: object) -> str:
    return html.escape(str(value), quote=True)


def load_shared_builder():
    shared = Path(__file__).resolve().parents[1] / "_shared" / "review-page" / "build_review.py"
    spec = importlib.util.spec_from_file_location("codex_review_page", shared)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load shared review renderer: {shared}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rejected_text(item: dict, token: str, canonical: str | None) -> str:
    """Reject's consequence. Approve always means apply the correction, so a
    "real name, not a misspelling" ruling comes back as reject, and the card
    must say so in its `n` text."""
    reject_as = item.get("reject_as") or ("ignore" if canonical else "known")
    if reject_as == "known":
        return (
            f"Not a misspelling — add <code>{token}</code> to the known set "
            "(<code>notes/vtt_known_additions.md</code>); no glossary row, transcript unchanged."
        )
    if reject_as == "ignore":
        of = f" of <code>{canonical}</code>" if canonical else ""
        return (
            f"Not a garbling{of}. <code>{token}</code> is saved to "
            "<code>.vtt_spell_pass_state.json</code> as ignored and never asked again."
        )
    raise ValueError(f"item {item.get('id')!r}: reject_as must be 'known' or 'ignore', not {reject_as!r}")


def outcome(item: dict, target_vtt: str) -> tuple[str, str, str]:
    token = escaped(item.get("token", ""))
    canonical_value = item.get("canonical")
    target = escaped(target_vtt)

    if canonical_value:
        canonical = escaped(canonical_value)
        title = f"Correct <code>{token}</code> to <code>{canonical}</code>"
        if item.get("edit_mode") == "targeted":
            approved = (
                f"Apply the correction at the reviewed cue only: a cue-scoped entry "
                f"<code>{token}</code> → <code>{canonical}</code> in "
                "<code>transcript_corrections.yaml</code> (Phase 7); no glossary row."
            )
        else:
            approved = (
                f"Apply the correction: add <code>{token}</code> → <code>{canonical}</code> to "
                "<code>vtt_transcription_corrections.md</code>, lint, and record the substitutions "
                f"in <code>{target}</code> via <code>sd_corrections import</code> (Phase 7)."
            )
        return title, approved, rejected_text(item, token, canonical)

    title = f"Is <code>{token}</code> a misspelling?"
    approved = (
        "Misspelling — apply the correction: <b>name the right form in the note</b>; it becomes a "
        "glossary row and the substitutions are recorded via <code>sd_corrections import</code> "
        "(Phase 7). An approve with no canonical in the note comes back to chat."
    )
    return title, approved, rejected_text(item, token, None)


def evidence(item: dict) -> str:
    parts = [f"<b>VTT context:</b> {escaped(item.get('context', ''))}"]
    sibling = item.get("sibling") or {}
    if sibling.get("text"):
        line = f" line {escaped(sibling['line'])}" if sibling.get("line") is not None else ""
        score = f", score {float(sibling['score']):.3f}" if sibling.get("score") is not None else ""
        parts.append(f"<b>Sibling transcript{line}{score}:</b> {escaped(sibling['text'])}")
    if item.get("sibling_verdict"):
        parts.append(f"<b>Sibling verdict:</b> <code>{escaped(item['sibling_verdict'])}</code>")
    if item.get("evidence_note"):
        parts.append(f"<b>Note:</b> {escaped(item['evidence_note'])}")
    reason = item.get("reason")
    if isinstance(reason, list):
        reason = ",".join(str(r) for r in reason)
    chapters = f" across {escaped(item['chapters'])} chapter(s)" if item.get("chapters") else ""
    parts.append(
        f"<b>Classification:</b> {escaped(item.get('confidence', 'unknown'))} confidence"
        + (f" (<code>{escaped(reason)}</code>)" if reason else "")
        + f"; {escaped(item.get('count', 0))} occurrence(s){chapters}."
    )
    if item.get("recommended_decision"):
        parts.append(f"<b>Recommendation:</b> {escaped(item['recommended_decision'])}")
    return "<br>".join(parts)


def shared_spec(queue: dict) -> dict:
    target_vtt = str(queue.get("target_vtt", "transcript.vtt"))
    items = []

    for item in queue["items"]:
        title, approved, rejected = outcome(item, target_vtt)
        item_id = str(item["id"])
        ev = evidence(item)
        # A recorded decision or note is shown as text, never pre-marked: a
        # pre-set verdict would export as the GM's ruling on a single Save.
        recorded = []
        if item.get("decision"):
            recorded.append(f"Recorded earlier: <code>{escaped(item['decision'])}</code>")
        if item.get("note"):
            recorded.append(f"Note: {escaped(item['note'])}")
        if recorded:
            ev = ev + ("<br>" if ev else "") + " · ".join(recorded)
        items.append({"id": item_id, "t": title, "y": approved, "n": rejected, "ev": ev})

    session = str(queue.get("session_dir", Path(target_vtt).parent))
    footer = ["Nothing is written — glossary, state, record or transcript — until Codex "
              "receives the exported decisions."]
    summary = queue.get("summary") or {}
    for key, label in (("auto_dismissed", "Auto-dismissed (count 1, sibling shows ordinary words)"),
                       ("phase2_dropped", "Dropped as not a campaign name")):
        entries = summary.get(key) or []
        if entries:
            listed = "; ".join(
                f"<code>{escaped(e.get('token', ''))}</code> ×{escaped(e.get('count', '?'))}"
                + (f" — {escaped(e['reason'])}" if e.get("reason") else "")
                for e in entries
            )
            footer.append(f"<b>{label}, {len(entries)}:</b> {listed}")
    return {
        "title": "VTT Spell Pass Review",
        "reviewId": f"vtt-spell-pass:{target_vtt}",
        "outputName": "decisions.json",
        "eyebrow": f"{session} / VTT spell pass",
        "lede": (
            f"{len(items)} independent spelling decisions. Approve always applies the correction; "
            "Reject does what the card says (ignore, or keep it as a real name); Discuss returns the item to chat."
        ),
        "footer": "<br>".join(footer),
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    queue = json.loads(args.queue.read_text(encoding="utf-8"))
    items = queue.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("queue must contain a non-empty items array")
    ids = [item.get("id") for item in items]
    if any(not item_id for item_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("every review item must have a unique, non-empty id")

    output = args.output or args.queue.with_suffix(".html")
    builder = load_shared_builder()
    spec = shared_spec(queue)
    errors = builder.validate(spec)
    if errors:
        raise ValueError("invalid shared review data: " + "; ".join(errors))
    output.write_text(builder.build(spec), encoding="utf-8")
    print(f"Wrote {output} with {len(items)} review items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
