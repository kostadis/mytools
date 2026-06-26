"""Generate human- and machine-readable reports from turbovecdb + the graph DB.

Outputs (under ``reports/``):
  * ``DRIVE-TAGS.md``   - categories with their files, the connection list, and a
    mermaid diagram of file-to-file links.
  * ``categories.json`` - categories with members.
  * ``graph.json``      - nodes (files) + typed edges (links).
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

from .config import CONFIG
from .graph import Graph
from .store import Store


def _mermaid_label(text: str) -> str:
    safe = text.replace('"', "'").replace("\n", " ").strip()
    return safe[:40] if safe else "(untitled)"


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
    link_by_id = {d.get("web_view_link", "") or "" for d in docs}  # noqa: F841 (kept for clarity)

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

    # --- DRIVE-TAGS.md -------------------------------------------------------
    lines: list[str] = []
    lines.append("# Drive Tags")
    lines.append("")
    lines.append(f"Generated {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append(
        f"{len(docs)} documents - {len(all_cat_names)} categories - {len(links)} links"
    )
    lines.append("")

    lines.append("## Categories")
    lines.append("")
    for name in all_cat_names:
        mem = members.get(name, [])
        lines.append(f"### {name} ({len(mem)})")
        desc = cat_desc.get(name, "")
        if desc:
            lines.append("")
            lines.append(desc)
        lines.append("")
        for m in sorted(mem, key=lambda d: d.get("name", "").lower()):
            link = m.get("web_view_link", "") or ""
            others = [c for c in (m.get("categories", []) or []) if c != name]
            suffix = f" - also: {', '.join(others)}" if others else ""
            if link:
                lines.append(f"- [{m.get('name', '(untitled)')}]({link}){suffix}")
            else:
                lines.append(f"- {m.get('name', '(untitled)')}{suffix}")
        lines.append("")

    lines.append("## Connections")
    lines.append("")
    if links:
        for ln in links:
            src = name_by_id.get(ln["src_id"], ln["src_id"])
            dst = name_by_id.get(ln["dst_id"], ln["dst_id"])
            note = f" ({ln['note']})" if ln.get("note") else ""
            lines.append(f"- {src} --{ln['relation']}--> {dst}{note}")
        lines.append("")

        # mermaid diagram of the link graph
        node_ids: dict[str, str] = {}
        for ln in links:
            for fid in (ln["src_id"], ln["dst_id"]):
                if fid not in node_ids:
                    node_ids[fid] = f"n{len(node_ids)}"
        lines.append("```mermaid")
        lines.append("graph LR")
        for fid, nid in node_ids.items():
            lines.append(f'  {nid}["{_mermaid_label(name_by_id.get(fid, fid))}"]')
        for ln in links:
            s = node_ids[ln["src_id"]]
            d = node_ids[ln["dst_id"]]
            lines.append(f'  {s} -->|"{_mermaid_label(ln["relation"])}"| {d}')
        lines.append("```")
        lines.append("")
    else:
        lines.append("_No file-to-file links recorded yet._")
        lines.append("")

    md_path = CONFIG.reports_dir / "DRIVE-TAGS.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return {"markdown": md_path, "categories": categories_path, "graph": graph_path}
