"""chunk_cache.py — persist the *structural extraction* of a PDF so the chunking
and LLM/encode passes can run without re-opening it.

The v2 batch pipeline is a sequence of passes with very different resource
profiles, each reading the previous pass's output from disk:

  * **Fast extract** (PyMuPDF) / **Marker extract** (GPU/ML) — open the source
    once, produce a ``TocNode`` tree plus the raw text. CPU/RAM- or GPU-heavy,
    local. Marker runs as its own standalone tool (``batch_marker.py``).
  * **Split** — a pure function of (tree, text, cap): walk the tree and emit the
    ``ChunkSpec`` list, subdividing oversized nodes by their children. No PDF, no
    Marker, so it can be re-run with a tighter cap (e.g. per endpoint) for free.
  * **Encode** — send each chunk to the LLM, assemble + write the JSON.

This module owns the on-disk *extract* artifact (``<stem>-extract.json``): the
tree plus the **granular text units** the split pass slices to reconstruct any
node's body.

**Why a stable key is required.** ``assemble_adventure`` reassembles the document
using Python object identity — it groups chunks with ``id(spec.root)`` and maps
entries onto the tree with ``id(spec.target_node)`` / ``id(node)``. That identity
does not survive JSON. So every ``TocNode`` gets a stable integer ``key`` on
serialize; on load the tree is rebuilt and the split pass produces ``ChunkSpec``
objects that reference the *reloaded* nodes, so identity is internally consistent
within the encode process and assembly works unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path

from pdf_utils import TocNode

# Bump when the on-disk shape changes incompatibly.
FORMAT_VERSION = 1

# Valid ``kind`` values for the ``units`` list. "pages" = one entry per PDF page
# (fast path); "lines" = one entry per Marker markdown line.
KINDS = ("pages", "lines")


def _assign_keys(roots: list[TocNode]) -> dict[int, int]:
    """Map ``id(node) -> stable int key`` over every node reachable from
    ``roots`` (pre-order). Used only within the serializing process."""
    keys: dict[int, int] = {}
    counter = 0
    for root in roots:
        for node in root.walk():
            if id(node) not in keys:
                keys[id(node)] = counter
                counter += 1
    return keys


def tocnode_to_dict(node: TocNode, keys: dict[int, int]) -> dict:
    """Serialize a ``TocNode`` subtree, tagging each node with its stable key."""
    return {
        "key": keys[id(node)],
        "level": node.level,
        "title": node.title,
        "start_page": node.start_page,
        "end_page": node.end_page,
        "children": [tocnode_to_dict(c, keys) for c in node.children],
    }


def tocnode_from_dict(d: dict, key_map: dict[int, TocNode]) -> TocNode:
    """Rebuild a ``TocNode`` subtree and register each node in ``key_map`` by its
    stable key. Registration happens before recursing so all keys resolve."""
    node = TocNode(
        level=d["level"],
        title=d["title"],
        start_page=d["start_page"],
        end_page=d["end_page"],
        children=[],
    )
    key_map[d["key"]] = node
    node.children = [tocnode_from_dict(c, key_map) for c in d["children"]]
    return node


def serialize_extract(path: Path, roots: list[TocNode], units: list[str],
                      kind: str, meta: dict) -> None:
    """Write the structural extraction to ``path`` as JSON.

    ``roots`` is the TocNode tree, ``units`` the flat text list (``kind="pages"``
    → ``units[p-1]`` is page p's text; ``kind="lines"`` → Marker markdown lines),
    and ``meta`` a JSON-serializable dict (``short_id``, ``name``,
    ``output_type``, ``page_count``, ``source_kind``).
    """
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
    keys = _assign_keys(roots)
    data = {
        "version": FORMAT_VERSION,
        "kind": kind,
        "meta": meta,
        "roots": [tocnode_to_dict(r, keys) for r in roots],
        "units": units,
    }
    Path(path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def load_extract(path: Path) -> tuple[list[TocNode], list[str], str, dict]:
    """Inverse of :func:`serialize_extract`. Returns ``(roots, units, kind,
    meta)`` with a freshly-rebuilt TocNode tree (so a subsequent split produces
    chunks whose ``id()`` identity is internally consistent for assembly).

    Raises ``ValueError`` on an unknown format version or kind (a corrupt/stale
    cache file — re-extract with ``--force``).
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    version = data.get("version")
    if version != FORMAT_VERSION:
        raise ValueError(
            f"{path}: unsupported extract-cache version {version!r} "
            f"(expected {FORMAT_VERSION}); re-extract with --force"
        )
    kind = data.get("kind")
    if kind not in KINDS:
        raise ValueError(f"{path}: bad kind {kind!r}; re-extract with --force")

    key_map: dict[int, TocNode] = {}
    roots = [tocnode_from_dict(r, key_map) for r in data["roots"]]
    return roots, data["units"], kind, data["meta"]
