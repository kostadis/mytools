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


def outcome(item: dict, target_vtt: str) -> tuple[str, str, str]:
    token = escaped(item.get("token", ""))
    canonical_value = item.get("canonical")
    target = escaped(target_vtt)

    if canonical_value:
        canonical = escaped(canonical_value)
        title = f"Correct <code>{token}</code> to <code>{canonical}</code>"
        if item.get("edit_mode") == "targeted":
            approved = (
                f"Apply <code>{token}</code> to <code>{canonical}</code> only at the reviewed "
                f"location in <code>{target}</code>; do not add a global glossary rule."
            )
        else:
            approved = (
                f"Add <code>{token}</code> to <code>{canonical}</code> to the campaign glossary, "
                f"then apply that pair to <code>{target}</code>."
            )
        rejected = f"Leave <code>{token}</code> unchanged in <code>{target}</code> and ignore this pair."
        return title, approved, rejected

    title = f"Treat <code>{token}</code> as a new campaign term"
    approved = (
        f"Keep <code>{token}</code> unchanged in <code>{target}</code> and add the confirmed spelling "
        "to the campaign's canonical-name source. Include a note if the spelling should change."
    )
    rejected = f"Treat <code>{token}</code> as non-campaign speech and leave <code>{target}</code> unchanged."
    return title, approved, rejected


def evidence(item: dict) -> str:
    parts = [f"<b>VTT context:</b> {escaped(item.get('context', ''))}"]
    sibling = item.get("sibling") or {}
    if sibling.get("text"):
        line = f" line {escaped(sibling['line'])}" if sibling.get("line") is not None else ""
        score = f", score {float(sibling['score']):.3f}" if sibling.get("score") is not None else ""
        parts.append(f"<b>Sibling transcript{line}{score}:</b> {escaped(sibling['text'])}")
    if item.get("evidence_note"):
        parts.append(f"<b>Note:</b> {escaped(item['evidence_note'])}")
    parts.append(
        f"<b>Classification:</b> {escaped(item.get('confidence', 'unknown'))} confidence; "
        f"{escaped(item.get('count', 0))} occurrence(s); {escaped(item.get('edit_mode', 'unknown'))} edit."
    )
    return "<br>".join(parts)


def shared_spec(queue: dict) -> dict:
    target_vtt = str(queue.get("target_vtt", "transcript.vtt"))
    items = []
    decisions: dict[str, str] = {}
    notes: dict[str, str] = {}
    choice_map = {
        "approve_correction": "approve",
        "new_canon": "approve",
        "ignore": "reject",
        "discuss": "discuss",
    }

    for item in queue["items"]:
        title, approved, rejected = outcome(item, target_vtt)
        item_id = str(item["id"])
        items.append({"id": item_id, "t": title, "y": approved, "n": rejected, "ev": evidence(item)})
        if item.get("decision") in choice_map:
            decisions[item_id] = choice_map[item["decision"]]
        if item.get("note"):
            notes[item_id] = str(item["note"])

    session = str(queue.get("session_dir", Path(target_vtt).parent))
    return {
        "title": "VTT Spell Pass Review",
        "reviewId": f"vtt-spell-pass:{target_vtt}",
        "outputName": "vtt_spell_pass_decisions.json",
        "eyebrow": f"{session} / VTT spell pass",
        "lede": (
            f"{len(items)} independent spelling decisions. Approve applies the consequence shown on the card; "
            "Reject leaves the transcript unchanged; Discuss returns the item to chat."
        ),
        "footer": "The source VTT, glossary, and saved review state remain unchanged until Codex receives the exported decisions.",
        "state": {"decisions": decisions, "notes": notes, "savedAt": None},
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
