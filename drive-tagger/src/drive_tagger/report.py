"""Generate human- and machine-readable reports from turbovecdb + the graph DB.

Outputs (under ``reports/``):
  * ``DRIVE-TAGS.md``       - index: totals + one line per category linking to its page.
  * ``categories/<slug>.md`` - one page per category: description, member files,
    and the links that touch those files (with a mermaid diagram when small
    enough to render usefully).
  * ``categories.json``     - categories with members (machine-readable).
  * ``graph.json``          - nodes (files) + typed edges (links) (machine-readable).
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

from .config import CONFIG
from .graph import Graph
from .store import Store

# Above this many links touching a category, skip the mermaid diagram (unreadable
# past this size) and truncate the textual connection list.
MAX_MERMAID_EDGES = 150
MAX_CONNECTIONS_LISTED = 300


def _mermaid_label(text: str) -> str:
    safe = text.replace('"', "'").replace("\n", " ").strip()
    return safe[:40] if safe else "(untitled)"


def _slugify(name: str, used: dict[str, int]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "untitled"
    count = used.get(slug, 0)
    used[slug] = count + 1
    return slug if count == 0 else f"{slug}-{count + 1}"


def _category_page(
    name: str,
    slug: str,
    desc: str,
    mem: list[dict],
    local_links: list[dict],
    name_by_id: dict[str, str],
    slug_by_name: dict[str, str],
) -> str:
    lines: list[str] = []
    lines.append(f"# {name}")
    lines.append("")
    lines.append("[← All categories](../DRIVE-TAGS.md)")
    lines.append("")
    if desc:
        lines.append(desc)
        lines.append("")

    lines.append(f"## Files ({len(mem)})")
    lines.append("")
    for m in sorted(mem, key=lambda d: d.get("name", "").lower()):
        link = m.get("web_view_link", "") or ""
        others = [c for c in (m.get("categories", []) or []) if c != name]
        also = ", ".join(f"[{c}]({slug_by_name[c]}.md)" for c in others if c in slug_by_name)
        title = m.get("name", "(untitled)")
        entry = f"[{title}]({link})" if link else title
        lines.append(f"- {entry}")
        if also:
            lines.append(f"  - Also in: {also}")
    lines.append("")

    lines.append(f"## Connections ({len(local_links)})")
    lines.append("")
    if local_links:
        shown = local_links[:MAX_CONNECTIONS_LISTED]
        for ln in shown:
            src = name_by_id.get(ln["src_id"], ln["src_id"])
            dst = name_by_id.get(ln["dst_id"], ln["dst_id"])
            note = f" ({ln['note']})" if ln.get("note") else ""
            lines.append(f"- {src} --{ln['relation']}--> {dst}{note}")
        if len(local_links) > MAX_CONNECTIONS_LISTED:
            remaining = len(local_links) - MAX_CONNECTIONS_LISTED
            lines.append("")
            lines.append(f"_...and {remaining} more. See `graph.json` for the full link list._")
        lines.append("")

        if len(local_links) <= MAX_MERMAID_EDGES:
            node_ids: dict[str, str] = {}
            for ln in local_links:
                for fid in (ln["src_id"], ln["dst_id"]):
                    if fid not in node_ids:
                        node_ids[fid] = f"n{len(node_ids)}"
            lines.append("```mermaid")
            lines.append("graph LR")
            for fid, nid in node_ids.items():
                lines.append(f'  {nid}["{_mermaid_label(name_by_id.get(fid, fid))}"]')
            for ln in local_links:
                s = node_ids[ln["src_id"]]
                d = node_ids[ln["dst_id"]]
                lines.append(f'  {s} -->|"{_mermaid_label(ln["relation"])}"| {d}')
            lines.append("```")
            lines.append("")
    else:
        lines.append("_No file-to-file links recorded yet._")
        lines.append("")

    return "\n".join(lines)


def generate() -> dict[str, Path]:
    CONFIG.ensure_dirs()
    store = Store()
    graph = Graph()
    try:
        docs = store.all_documents()
        categories = store.list_categories()
        links = graph.all_links()
    finally:
        store.close()
        graph.close()

    name_by_id = {d["id"]: d.get("name", "") for d in docs}

    # category -> [docs]
    members: dict[str, list[dict]] = defaultdict(list)
    for d in docs:
        for cat in d.get("categories", []) or []:
            members[cat].append(d)

    cat_desc = {c["name"]: c.get("description", "") for c in categories}
    all_cat_names = sorted(set(list(cat_desc.keys()) + list(members.keys())), key=str.lower)

    # --- categories.json -----------------------------------------------------
    categories_json = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "categories": [
            {
                "name": name,
                "description": cat_desc.get(name, ""),
                "member_count": len(members.get(name, [])),
                "members": [
                    {"id": m["id"], "name": m.get("name", "")} for m in members.get(name, [])
                ],
            }
            for name in all_cat_names
        ],
    }
    categories_path = CONFIG.reports_dir / "categories.json"
    categories_path.write_text(json.dumps(categories_json, indent=2), encoding="utf-8")

    # --- graph.json ----------------------------------------------------------
    graph_json = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "nodes": [
            {
                "id": d["id"],
                "name": d.get("name", ""),
                "categories": d.get("categories", []) or [],
                "web_view_link": d.get("web_view_link", "") or "",
            }
            for d in docs
        ],
        "links": links,
    }
    graph_path = CONFIG.reports_dir / "graph.json"
    graph_path.write_text(json.dumps(graph_json, indent=2), encoding="utf-8")

    # --- category pages -------------------------------------------------------
    pages_dir = CONFIG.reports_dir / "categories"
    pages_dir.mkdir(parents=True, exist_ok=True)
    for stale in pages_dir.glob("*.md"):
        stale.unlink()

    used_slugs: dict[str, int] = {}
    slug_by_name = {name: _slugify(name, used_slugs) for name in all_cat_names}

    for name in all_cat_names:
        mem = members.get(name, [])
        local_ids = {m["id"] for m in mem}
        local_links = sorted(
            (
                ln
                for ln in links
                if ln["src_id"] in local_ids or ln["dst_id"] in local_ids
            ),
            key=lambda ln: (
                name_by_id.get(ln["src_id"], ""),
                name_by_id.get(ln["dst_id"], ""),
            ),
        )
        page = _category_page(
            name, slug_by_name[name], cat_desc.get(name, ""), mem, local_links, name_by_id, slug_by_name
        )
        (pages_dir / f"{slug_by_name[name]}.md").write_text(page, encoding="utf-8")

    # --- DRIVE-TAGS.md (index) -------------------------------------------------
    lines: list[str] = []
    lines.append("# Drive Tags")
    lines.append("")
    lines.append(f"Generated {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append(
        f"{len(docs)} documents - {len(all_cat_names)} categories - {len(links)} links"
    )
    lines.append("")
    lines.append(
        "Each category has its own page under `categories/` with its files and the "
        "links that touch them. The full link list is in `graph.json`."
    )
    lines.append("")

    # Relation breakdown — the verification surface for link consolidation.
    if links:
        rel_counts = Counter(ln["relation"] for ln in links)
        lines.append(f"## Relations ({len(rel_counts)} types)")
        lines.append("")
        for rel, n in sorted(rel_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- `{rel}` — {n}")
        lines.append("")

    lines.append("## Categories")
    lines.append("")
    for name in all_cat_names:
        mem = members.get(name, [])
        slug = slug_by_name[name]
        desc = cat_desc.get(name, "").strip().splitlines()[0] if cat_desc.get(name, "").strip() else ""
        if len(desc) > 100:
            desc = desc[:99].rstrip() + "…"
        suffix = f" — {desc}" if desc else ""
        lines.append(f"- [{name}](categories/{slug}.md) ({len(mem)}){suffix}")
    lines.append("")

    md_path = CONFIG.reports_dir / "DRIVE-TAGS.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "index": md_path,
        "categories_dir": pages_dir,
        "categories_json": categories_path,
        "graph": graph_path,
    }
