"""LLM-drafted description backfill for empty-description categories
(issue #98; `reports/consolidation/DEDUP_BLIND_SPOTS.md` failure mode 1).

Two entry points, mirroring `consolidate.py`'s `collect()`/`apply()` split —
driven from the CLI (`drive-tagger consolidate backfill ...`):

  draft()              - read-only against the store. For every empty-
                          description multi-word category (`consolidate.
                          _backfill_targets`), gathers grounding context
                          (sample member doc names + a few body-text
                          snippets), asks the DGX chat endpoint for a
                          concise on-topic description, and writes
                          reports/consolidation/description_backfill.json
                          for HUMAN REVIEW. Never calls create_category or
                          any other store-mutating method.
  apply_descriptions()  - reads the (human-reviewed) artifact written by
                          draft() and writes each drafted description into
                          the store via store.create_category.

Unlike consolidate.py ("nothing here talks to Drive, the DGX judge, or an
LLM API"), draft() DOES talk to the DGX chat endpoint — that's exactly why
this backfill logic lives in its own module rather than folded into
consolidate.py.

The draft/apply split is the human checkpoint, not an implementation detail:
draft() only ever produces a reviewable JSON file; nothing touches the store
until a human has read that file and a separate `apply-descriptions` command
is run. Applying the drafted text automatically inside draft() would remove
exactly the review step this two-command design exists to enforce.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .config import CONFIG
from .consolidate import _backfill_targets
from .store import Store

SAMPLE_DOCS_PER_TARGET = 5  # member doc names shown in the prompt + written to the artifact
SNIPPET_DOCS = 3  # how many of those sample docs get a body-text snippet pulled
SNIPPET_CHARS = 300  # per-doc body-text truncation for the prompt

_SYSTEM_PROMPT = (
    "You write short, factual descriptions for document categories in a "
    "personal RPG/TTRPG file archive. Given a category name and a sample of "
    "its member documents, respond with ONLY a concise 1-2 sentence "
    "description of what belongs in this category, grounded in the sample "
    "documents shown. No preamble, no markdown, no surrounding quotation "
    "marks — just the description text."
)


def _members_by_cat_with_ids(docs: list[dict]) -> dict[str, list[tuple[str, str]]]:
    """category name -> list of (doc_id, doc_name), inverted from
    all_documents() (same inversion pattern consolidate.collect() uses for
    `members_by_cat`, but keeping ids alongside names — ids are needed to
    call get_document() for body-text snippets; names are needed for the
    prompt and the human-reviewable artifact)."""
    out: dict[str, list[tuple[str, str]]] = {}
    for d in docs:
        for cname in d.get("categories", []) or []:
            out.setdefault(cname, []).append((d["id"], d.get("name", d["id"])))
    return out


def _gather_context(store: Store, target: dict, members_by_cat: dict) -> dict:
    """All store reads for one target, done up front (while the Store is
    still open) so the network chat call below never needs it. Returns a
    working dict — not the final artifact shape, see draft()."""
    members = sorted(members_by_cat.get(target["name"], []), key=lambda t: t[1])
    sample = members[:SAMPLE_DOCS_PER_TARGET]
    sample_names = [name for _, name in sample]

    snippets = []
    for doc_id, name in sample[:SNIPPET_DOCS]:
        doc = store.get_document(doc_id)
        text = (doc or {}).get("document") or ""
        if text:
            snippets.append({"name": name, "snippet": text[:SNIPPET_CHARS]})

    return {
        "name": target["name"],
        "member_count": target["member_count"],
        "sample_docs": sample_names,
        "snippets": snippets,
    }


def _build_messages(ctx: dict) -> list[dict]:
    lines = [
        f'Category name: "{ctx["name"]}"',
        f"Number of member documents: {ctx['member_count']}",
    ]
    if ctx["sample_docs"]:
        lines.append("")
        lines.append("Sample member document names:")
        lines.extend(f"- {name}" for name in ctx["sample_docs"])
    if ctx["snippets"]:
        lines.append("")
        lines.append("Sample document content excerpts:")
        lines.extend(f"- {s['name']}: {s['snippet']}" for s in ctx["snippets"])
    lines.append("")
    lines.append(
        "Write a concise, on-topic 1-2 sentence description of what this "
        "category is for, grounded in the sample documents above."
    )
    return [
        {"role": "system", "content": "/no_think\n\n" + _SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(lines)},
    ]


def draft(*, client=None, out_path: Optional[Path] = None) -> dict:
    """Draft descriptions for every empty-description multi-word category.
    Read-only against the store: must never call create_category, merge_
    categories, or any other mutating Store method. Writes a reviewable
    artifact and returns a summary; nothing is applied to the store here."""
    CONFIG.ensure_dirs()
    path = out_path or (CONFIG.consolidation_dir / "description_backfill.json")

    # All store I/O happens up front, store closed before any network call.
    store = Store()
    try:
        targets = _backfill_targets(store.list_categories())
        members_by_cat = _members_by_cat_with_ids(store.all_documents())
        contexts = [_gather_context(store, t, members_by_cat) for t in targets]
    finally:
        store.close()

    if client is None:
        from openai import OpenAI

        client = OpenAI(base_url=CONFIG.dgx_endpoint, api_key="unused", timeout=120.0)

    drafted = []
    for ctx in contexts:
        response = client.chat.completions.create(
            model=CONFIG.dgx_model,
            messages=_build_messages(ctx),
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        content = response.choices[0].message.content or ""
        drafted.append(
            {
                "name": ctx["name"],
                "member_count": ctx["member_count"],
                "sample_docs": ctx["sample_docs"],
                "drafted_description": content.strip(),
            }
        )

    path.write_text(json.dumps(drafted, indent=2), encoding="utf-8")
    return {"drafted": drafted, "path": path}


def apply_descriptions(*, descriptions_path: Optional[Path] = None) -> dict:
    """Write the (human-reviewed) descriptions drafted by draft() into the
    store via store.create_category. No automatic backup here — same
    convention as consolidate.apply(): backing up data/db before a mutating
    run is a manual step done by the human/skill outside this function."""
    path = descriptions_path or (CONFIG.consolidation_dir / "description_backfill.json")
    entries = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError(f"{path} must contain a JSON array of entries")

    applied, skipped = [], []
    store = Store()
    try:
        for entry in entries:
            if not isinstance(entry, dict):
                skipped.append({"entry": entry, "reason": "not a JSON object"})
                continue
            name = (entry.get("name") or "").strip()
            description = (entry.get("drafted_description") or "").strip()
            if not name:
                skipped.append({"name": None, "reason": "missing name"})
                continue
            if not description:
                # Never write an empty description — that's re-introducing
                # failure mode 1, the exact bug this backfill exists to fix.
                skipped.append({"name": name, "reason": "empty drafted_description"})
                continue
            store.create_category(name, description)
            applied.append({"name": name, "description": description})
    finally:
        store.close()

    return {"applied": applied, "skipped": skipped}
