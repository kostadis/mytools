#!/usr/bin/env python3
"""
toc_fixer.py — Heuristic-guided TOC & nesting repair for 5etools adventure JSON.

Presents a three-panel UI (PDF TOC | Current TOC | Proposed TOC) plus an
editable flat heading table.  Two heuristics are available:

  • PDF Anchor  — PDF bookmark names define authoritative level-1 sections.
  • Keyed Room  — Headings like "A.", "B.", "A1.", "A2." within a section
                   are levelled relative to their enclosing PDF anchor.

Usage:
    python3 toc_fixer.py [file.json] [--pdf file.pdf] [--port N]
    # http://localhost:5102
"""

from __future__ import annotations

import copy
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).parent))
from fix_adventure_json import assign_ids, build_toc, reset_ids  # type: ignore
from pdf_utils import _decode_pdf_string  # type: ignore
from toc_editor import list_json_files  # type: ignore

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("PyMuPDF required: pip install pymupdf")

app = Flask(__name__)

_preload_json: str = ""
_preload_pdf: str = ""

# Server-side session state keyed by json_path
_sessions: dict[str, dict] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Heading:
    id: int
    name: str
    entry_type: str           # "section" | "entries"
    original_path: list[int]  # indices to navigate original data[] tree
    current_depth: int        # 0 = top-level section
    proposed_level: int       # 1–4; 1 = top-level section
    pdf_section: str = ""     # name of enclosing PDF level-1 bookmark
    pattern: str = ""         # "pdf-anchor:<level>" | "keyed-room:X" | "manual" | ""


# ─────────────────────────────────────────────────────────────────────────────
# PDF helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_pdf_toc(pdf_path: str) -> list[dict]:
    """Return PDF bookmarks as [{level, title, page}, ...] using raw PDF levels.

    Levels are kept exactly as defined in the PDF — a level-2 bookmark in the
    PDF becomes level 2 in the proposed TOC.  No normalisation is applied.
    """
    doc = fitz.open(pdf_path)
    try:
        raw: list[list] = doc.get_toc(simple=True)
    finally:
        doc.close()

    return [{"level": lvl, "title": _decode_pdf_string(title), "page": page}
            for lvl, title, page in raw]


# ─────────────────────────────────────────────────────────────────────────────
# Flat heading extraction
# ─────────────────────────────────────────────────────────────────────────────

def _dfs_headings(
    entries: list,
    depth: int,
    path: list[int],
    result: list[Heading],
) -> None:
    for j, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        current_path = path + [j]
        if entry.get("type") in ("section", "entries") and entry.get("name", "").strip():
            result.append(Heading(
                id=len(result),
                name=entry["name"],
                entry_type=entry["type"],
                original_path=current_path,
                current_depth=depth,
                proposed_level=min(depth + 1, 4),
            ))
        if "entries" in entry:
            _dfs_headings(entry["entries"], depth + 1, current_path, result)


def extract_headings(data: list) -> list[Heading]:
    """DFS traversal of data[], returning all named section/entries nodes."""
    result: list[Heading] = []
    _dfs_headings(data, 0, [], result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Heuristics
# ─────────────────────────────────────────────────────────────────────────────

_STOPWORDS = {"a", "an", "the", "of", "in", "to", "and", "or", "for", "with",
              "at", "by", "from", "on", "is", "it", "as", "be", "this"}


def _token_overlap(a: str, b: str) -> float:
    """Token overlap similarity between two strings, case-insensitive.

    Stopwords are excluded so that common function words (of, the, to…) do not
    create false matches between unrelated headings.
    """
    ta = set(re.split(r"\W+", a.lower())) - {""} - _STOPWORDS
    tb = set(re.split(r"\W+", b.lower())) - {""} - _STOPWORDS
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def _pdf_parent_map(pdf_toc: list[dict]) -> dict[str, str | None]:
    """Return {bookmark_title: parent_title | None} from the raw PDF TOC list.

    Used to restrict same-level boundary pairs to anchors that share the same
    PDF parent, preventing cross-chapter false promotions when parent bookmarks
    are unmatched in the JSON headings.
    """
    parent: dict[str, str | None] = {}
    stack: list[dict] = []
    for bm in pdf_toc:
        while stack and stack[-1]["level"] >= bm["level"]:
            stack.pop()
        parent[bm["title"]] = stack[-1]["title"] if stack else None
        stack.append(bm)
    return parent


def _promote_same_level_pairs(
    anchor_by_id: dict[int, tuple[int, str]],
    pdf_toc: list[dict],
) -> dict[int, tuple[int, str]]:
    """Iteratively promote anchors sandwiched between two same-level, same-parent anchors.

    Rule: If anchor_i and anchor_j both have the same effective_level L AND the
    same PDF bookmark parent, and no anchor with effective_level < L appears
    strictly between them (in heading-id / document order), then every anchor
    strictly between them that also has the same parent and level >= L is promoted
    to max(its_level, L + 1).

    The same-PDF-parent guard prevents cross-chapter false promotions when a
    parent bookmark (e.g. "To Worlds Unknown" L1) is absent from the JSON headings
    and two L2 anchors from different chapters would otherwise appear to be peers.

    Levels ≤ 1 are skipped (top-level anchors are always siblings; there is
    nothing above them to distinguish containment).

    Repeats until stable (levels only ever increase → convergence guaranteed).
    """
    parent_map = _pdf_parent_map(pdf_toc)
    bm_title: dict[int, str] = {hid: title for hid, (_, title) in anchor_by_id.items()}
    effective: dict[int, int] = {hid: lvl for hid, (lvl, _) in anchor_by_id.items()}

    changed = True
    while changed:
        changed = False
        sorted_ids = sorted(effective.keys())
        n = len(sorted_ids)
        promotions: dict[int, int] = {}

        for i in range(n):
            for j in range(i + 1, n):
                id_i, id_j = sorted_ids[i], sorted_ids[j]
                L = effective[id_i]
                if effective[id_j] != L:
                    continue
                if L <= 1:
                    continue

                # Only pair anchors that share the same PDF parent bookmark.
                # Without this guard, unmatched parent anchors cause cross-chapter
                # cascades (e.g. "What You Find" L2 under "Welcome" incorrectly
                # boundaries "Part 1" L2 under an unmatched L1 chapter title).
                if parent_map.get(bm_title[id_i]) != parent_map.get(bm_title[id_j]):
                    continue

                between = [sorted_ids[k] for k in range(i + 1, j)]

                # Not a boundary pair if a shallower anchor already separates them.
                if any(effective[mid] < L for mid in between):
                    continue

                for mid in between:
                    if effective[mid] >= L:
                        # Only promote the "between" anchor if it also shares the
                        # same PDF parent — don't promote anchors from unrelated
                        # bookmark subtrees that happen to fall in this id range.
                        if parent_map.get(bm_title.get(mid)) == parent_map.get(bm_title[id_i]):
                            new_lvl = max(promotions.get(mid, effective[mid]), L + 1)
                            promotions[mid] = new_lvl

        for hid, new_lvl in promotions.items():
            if effective[hid] != new_lvl:
                effective[hid] = new_lvl
                changed = True

    return {hid: (effective[hid], title) for hid, (_, title) in anchor_by_id.items()}


def apply_pdf_anchor(headings: list[Heading], pdf_toc: list[dict]) -> list[Heading]:
    """
    The PDF TOC is authoritative across all bookmark levels (1–4).

    Steps:
    1. Match every PDF bookmark (any level) to the best-scoring unmatched
       heading by name.  Each heading can match at most one bookmark.
       Stopwords are excluded from the token overlap score to prevent false
       matches on common function words (of, the, to, …).
    2. After matching, apply the "same-level boundary pair" promotion:
       if two anchors sit at the same effective level L and no anchor with
       level < L lies strictly between them, then any matched anchor strictly
       between them that is also at level L is promoted to L+1.  This is
       iterated until stable and covers only levels > 1 (L1 anchors are always
       siblings so no promotion is meaningful there).
       NOTE: the promotion only affects matched PDF anchor headings.  Non-anchor
       JSON headings are rebased by the sequential scan in step 4.
    3. Set matched headings: proposed_level = effective_level,
       pattern = "pdf-anchor:<level>".
    4. Sequential scan in document order.  Track:
       - current_enclosing_level: the effective bookmark level of the last anchor.
       - current_section: name of the last anchor at any level (used as
         pdf_section for grouping non-anchor headings in the keyed-room
         heuristic, so letter_level is relative to the most-specific enclosing
         anchor rather than the outermost L1 chapter).
    5. For every non-anchor heading inside a PDF section, rebase proposed_level
       so the internal hierarchy sits below the anchor:
           proposed_level = min(current_depth + current_enclosing_level + 1, 4)
       Headings before the first anchor keep their depth-derived level.
    """
    if not pdf_toc:
        return headings

    headings = [copy.copy(h) for h in headings]

    # ── Step 1: match each bookmark to the best unmatched heading ──────────────
    anchor_by_id: dict[int, tuple[int, str]] = {}
    used_ids: set[int] = set()

    for bm in pdf_toc:
        best_id: int | None = None
        best_score = 0.0
        for h in headings:
            if h.id in used_ids:
                continue
            score = _token_overlap(h.name, bm["title"])
            if score > best_score:
                best_score = score
                best_id = h.id
        if best_score >= 0.3 and best_id is not None:
            anchor_by_id[best_id] = (bm["level"], bm["title"])
            used_ids.add(best_id)

    if not anchor_by_id:
        return headings

    # ── Step 2: (optional) promote sandwiched anchors ──────────────────────────
    # _promote_same_level_pairs() can promote a PDF anchor that is genuinely at
    # the wrong level — sandwiched between two real siblings in the PDF.
    # However, with three or more genuine same-level siblings the outermost pair
    # incorrectly treats the middle ones as "sandwiched" and demotes them.
    # Because non-anchor JSON headings are correctly rebased by the sequential
    # scan (step 4) relative to the enclosing anchor level, the promotion is not
    # needed for the common case and is intentionally not called here.
    # Uncomment the line below only when the PDF has explicit level errors:
    # anchor_by_id = _promote_same_level_pairs(anchor_by_id, pdf_toc)

    # ── Step 3: mark anchor headings with their (possibly promoted) level ──────
    for h in headings:
        if h.id in anchor_by_id:
            lvl, _title = anchor_by_id[h.id]
            h.proposed_level = lvl
            h.pattern = f"pdf-anchor:{lvl}"

    # ── Steps 4–5: assign pdf_section and rebase non-anchor levels ─────────────
    # pdf_section tracks the LAST SEEN ANCHOR at any level so that the
    # keyed-room heuristic can use the correct enclosing anchor level.
    # Example: headings inside Part 1 (L2) get pdf_section = "PART 1: PRISON
    # BREAK" and anchor_level = 2, giving letter_level = 3.  If we only tracked
    # L1 anchors, they would inherit the Welcome (L1) anchor and get letter_level = 2.
    current_enclosing_level = 0   # 0 = before any anchor
    current_section = ""          # name of the last seen anchor (any level)

    for h in sorted(headings, key=lambda x: x.id):
        if h.id in anchor_by_id:
            lvl, _title = anchor_by_id[h.id]
            current_enclosing_level = lvl
            current_section = h.name  # use JSON heading name so anchor_levels lookup matches
        else:
            h.pdf_section = current_section
            if current_enclosing_level > 0:
                h.proposed_level = min(
                    h.current_depth + current_enclosing_level + 1, 4
                )

    return headings


# Keyed-room regex patterns (checked in priority order)
# "A1 Name" or "A1. Name"  — letter immediately followed by digit
_LETTER_NUM_RE       = re.compile(r"^([A-Z])(\d+)(?:[.\-)\s]|$)")
# "C 1. Name" or "GT 1. Name"  — letter(s), spaces, then a digit
_LETTER_SPACE_NUM_RE = re.compile(r"^([A-Z]+)\s+(\d+)(?:[.\-)\s]|$)")
# "A. Name" or "B Name"  — bare single letter
_SINGLE_LETTER_RE    = re.compile(r"^([A-Z])(?:[.\-)\s]|$)")


def apply_keyed_room(headings: list[Heading]) -> list[Heading]:
    """
    Within each pdf_section group, detect D&D keyed-room heading patterns:
      • Single letter  (A, B, C  /  A. Name  /  A Name)  → area headings, same level
      • Letter+number  (A1, A2, B3  /  A1. Name)         → sub-rooms under their letter

    Single-letter headings become level (anchor_level + 1),
    letter+number headings become level (anchor_level + 2).
    """
    headings = [copy.copy(h) for h in headings]

    # Build lookup: section_name → proposed_level of its anchor heading
    anchor_levels: dict[str, int] = {}
    for h in headings:
        if h.pattern.startswith("pdf-anchor"):
            anchor_levels[h.name] = h.proposed_level

    # Group non-anchor headings by pdf_section
    groups: dict[str, list[Heading]] = defaultdict(list)
    for h in headings:
        if not h.pattern.startswith("pdf-anchor"):
            groups[h.pdf_section].append(h)

    for section_name, group in groups.items():
        # anchor_level for this group's enclosing section (usually 1)
        anchor_level = anchor_levels.get(section_name, 1)
        letter_level = min(anchor_level + 1, 4)
        room_level   = min(anchor_level + 2, 4)

        for h in group:
            name = h.name.strip()
            if len(name) >= 40:
                continue

            m_room       = _LETTER_NUM_RE.match(name)
            m_space_room = _LETTER_SPACE_NUM_RE.match(name)
            m_letter     = _SINGLE_LETTER_RE.match(name)

            if m_room:
                # "A1 Name" — letter directly adjacent to digit
                letter = m_room.group(1)
                num    = m_room.group(2)
                h.proposed_level = room_level
                h.pattern = f"keyed-room:{letter}{num}"
            elif m_space_room:
                # "C 1. Name" or "GT 1. Name" — letter prefix, space, then digit
                prefix = m_space_room.group(1)
                num    = m_space_room.group(2)
                h.proposed_level = room_level
                h.pattern = f"keyed-room:{prefix}{num}"
            elif m_letter:
                # "A. Name" or "B Name" — bare single letter
                letter = m_letter.group(1)
                h.proposed_level = letter_level
                h.pattern = f"keyed-room:{letter}"

        # Post-pass: deduplicate — for headings sharing the same keyed-room pattern,
        # keep only the one with the longest name (e.g. "A15" vs "A15. Lab" → keep latter).
        _dedup_keyed_room(headings)

        # Post-pass: if a numbered series (A1..An) is interrupted by a heading
        # at a level shallower than room_level between consecutive members,
        # promote all numbered members of that series to letter_level.
        _promote_interrupted_series(group, letter_level, room_level)

    return headings


def _dedup_keyed_room(headings: list[Heading]) -> None:
    """Remove shorter-named duplicates that share the same keyed-room pattern.

    Example: "A15" (pattern keyed-room:A15) and "A15. Microbiology Lab" (same
    pattern) → remove "A15", keep "A15. Microbiology Lab".  Modifies in place.
    """
    from itertools import groupby

    keyed = [h for h in headings if h.pattern.startswith("keyed-room:")]
    keyed.sort(key=lambda h: h.pattern)

    to_remove: set[int] = set()
    for _pat, grp in groupby(keyed, key=lambda h: h.pattern):
        group_list = list(grp)
        if len(group_list) < 2:
            continue
        best = max(group_list, key=lambda h: len(h.name))
        for h in group_list:
            if h is not best:
                to_remove.add(h.id)

    # Remove in-place (list is already a copy from the outer function)
    i = 0
    while i < len(headings):
        if headings[i].id in to_remove:
            headings.pop(i)
        else:
            i += 1


def _promote_interrupted_series(
    group: list[Heading],
    letter_level: int,
    room_level: int,
) -> None:
    """Promote a numbered keyed-room series (A1..An) to letter_level when any
    heading at level < room_level appears between two consecutive members.

    Example: A4 … [level-2 heading] … A5  →  all A-numbered headings → level_level.
    This prevents numbered rooms from being nested under unrelated headings that
    appear between them in the document.
    """
    # Collect numbered members per letter prefix, sorted by document order
    by_prefix: dict[str, list[Heading]] = defaultdict(list)
    for h in group:
        if h.proposed_level == room_level and h.pattern.startswith("keyed-room:"):
            suffix = h.pattern[len("keyed-room:"):]
            letter = "".join(c for c in suffix if c.isalpha())
            if letter and any(c.isdigit() for c in suffix):
                by_prefix[letter].append(h)

    sorted_group = sorted(group, key=lambda h: h.id)

    for prefix, numbered in by_prefix.items():
        if len(numbered) < 2:
            continue
        numbered.sort(key=lambda h: h.id)

        # Check each consecutive pair for an intervening shallower heading
        interrupted = False
        numbered_ids = {h.id for h in numbered}
        for i in range(len(numbered) - 1):
            h_prev, h_next = numbered[i], numbered[i + 1]
            for h in sorted_group:
                if h_prev.id < h.id < h_next.id and h.id not in numbered_ids:
                    if h.proposed_level < room_level:
                        interrupted = True
                        break
            if interrupted:
                break

        if interrupted:
            for h in numbered:
                h.proposed_level = letter_level


def reset_headings(headings: list[Heading]) -> list[Heading]:
    """Reset all headings to their original depth-derived proposed levels."""
    return [
        Heading(
            id=h.id,
            name=h.name,
            entry_type=h.entry_type,
            original_path=h.original_path,
            current_depth=h.current_depth,
            proposed_level=min(h.current_depth + 1, 4),
        )
        for h in headings
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Tree reconstruction
# ─────────────────────────────────────────────────────────────────────────────

def get_node_by_path(data: list, path: list[int]) -> dict:
    """Navigate the original data[] tree using a list of integer indices."""
    node = data[path[0]]
    for idx in path[1:]:
        node = node["entries"][idx]
    return node


def split_node_content(
    node: dict,
    node_path: list[int],
    heading_paths: set[tuple],
) -> list:
    """Return the non-heading direct children of node['entries'].

    Heading children (those whose computed path is in heading_paths) are
    excluded because the rebuild loop will place them at their new position.
    """
    result = []
    for j, child in enumerate(node.get("entries", [])):
        if tuple(node_path + [j]) not in heading_paths:
            result.append(child)
    return result


def rebuild_tree(original_data: list, headings: list[Heading]) -> list[dict]:
    """Reconstruct data[] from the headings list with proposed_level assignments.

    Algorithm (stack-based, Markdown-heading style):
    - Process headings in document order (by id).
    - Pop stack until the top has level < current heading's proposed_level.
    - Append new node to stack top's entries; push new node.
    - Non-heading leaf content of each node is preserved at that node.
    - Top-level data[] items not represented by any heading are folded into
      the last section (same strategy as fix_adventure_json.normalize_chapters).
    """
    heading_paths = {tuple(h.original_path) for h in headings}
    sorted_headings = sorted(headings, key=lambda h: h.id)

    output: list[dict] = []
    sentinel: dict[str, Any] = {"entries": output}
    stack: list[tuple[int, dict]] = [(0, sentinel)]

    for h in sorted_headings:
        node = get_node_by_path(original_data, h.original_path)
        leaf_content = split_node_content(node, h.original_path, heading_paths)

        new_node: dict[str, Any] = {
            "type": "section" if h.proposed_level == 1 else "entries",
            "name": h.name,
            "entries": list(leaf_content),
        }
        # Carry forward any extra fields (e.g. custom metadata)
        for k, v in node.items():
            if k not in ("type", "name", "entries", "id"):
                new_node[k] = v

        L = h.proposed_level
        while len(stack) > 1 and stack[-1][0] >= L:
            stack.pop()
        stack[-1][1]["entries"].append(new_node)
        stack.append((L, new_node))

    # Force every top-level item to be type "section"
    for item in output:
        if isinstance(item, dict) and item.get("type") != "section":
            item["type"] = "section"

    # Fold any top-level original items that have no heading representation.
    # Skip items whose sub-headings are already placed by the rebuild loop
    # (e.g. a bare "A14" wrapper whose only child is "A14. Observation Deck").
    top_heading_indices = {
        h.original_path[0] for h in headings if len(h.original_path) == 1
    }
    container_indices = {
        h.original_path[0] for h in headings if len(h.original_path) > 1
    }
    for i, item in enumerate(original_data):
        if i not in top_heading_indices and i not in container_indices:
            if output:
                output[-1].setdefault("entries", []).append(item)
            else:
                output.append({"type": "section", "name": "Preamble", "entries": [item]})

    # Reassign sequential IDs
    reset_ids()
    assign_ids(output)

    return output


def headings_to_proposed_toc(headings: list[Heading]) -> list[dict]:
    """Compute a 2-level contents[] preview from the current proposed_levels."""
    toc: list[dict] = []
    current: dict | None = None
    for h in headings:
        if h.proposed_level == 1:
            current = {"name": h.name, "headers": []}
            toc.append(current)
        elif h.proposed_level == 2 and current is not None:
            current["headers"].append(h.name)
    return toc


# ─────────────────────────────────────────────────────────────────────────────
# Flask routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return (
        HTML
        .replace('"__PRELOAD_JSON__"', json.dumps(_preload_json))
        .replace('"__PRELOAD_PDF__"', json.dumps(_preload_pdf))
    )


@app.route("/api/files")
def api_files():
    return jsonify(list_json_files())


@app.route("/api/load", methods=["POST"])
def api_load():
    body = request.json or {}
    json_path = body.get("json_path", "").strip()
    pdf_path  = body.get("pdf_path",  "").strip()

    if not json_path:
        return jsonify({"error": "json_path required"}), 400

    try:
        with open(json_path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    if "adventure" in raw:
        index_key, data_key = "adventure", "adventureData"
    elif "book" in raw:
        index_key, data_key = "book", "bookData"
    else:
        return jsonify({"error": "Not a valid 5etools adventure/book JSON"}), 400

    data        = raw[data_key][0].get("data", [])
    current_toc = raw[index_key][0].get("contents", [])

    headings = extract_headings(data)

    pdf_toc: list[dict] = []
    if pdf_path:
        try:
            pdf_toc = get_pdf_toc(pdf_path)
        except Exception as exc:
            return jsonify({"error": f"PDF error: {exc}"}), 500

        # Auto-apply PDF anchor on load so headings start at levels derived
        # from the authoritative PDF bookmark outline rather than from the
        # (potentially broken) JSON nesting depth.  This avoids confusing
        # initial states where sibling entries appear at different levels.
        headings = apply_pdf_anchor(headings, pdf_toc)

    _sessions[json_path] = {
        "raw":           raw,
        "index_key":     index_key,
        "data_key":      data_key,
        "pdf_toc":       pdf_toc,
        "headings":      headings,
        "original_data": copy.deepcopy(data),
    }

    return jsonify({
        "pdf_toc":      pdf_toc,
        "current_toc":  current_toc,
        "headings":     [asdict(h) for h in headings],
        "proposed_toc": headings_to_proposed_toc(headings),
    })


@app.route("/api/apply_heuristic", methods=["POST"])
def api_apply_heuristic():
    body      = request.json or {}
    json_path = body.get("json_path", "").strip()
    heuristic = body.get("heuristic", "")

    sess = _sessions.get(json_path)
    if not sess:
        return jsonify({"error": "File not loaded — call /api/load first"}), 400

    headings = sess["headings"]

    if heuristic == "pdf_anchor":
        headings = apply_pdf_anchor(headings, sess["pdf_toc"])
    elif heuristic == "keyed_room":
        headings = apply_keyed_room(headings)
    elif heuristic == "reset":
        headings = reset_headings(headings)
    else:
        return jsonify({"error": f"Unknown heuristic: {heuristic!r}"}), 400

    sess["headings"] = headings
    return jsonify({
        "headings":     [asdict(h) for h in headings],
        "proposed_toc": headings_to_proposed_toc(headings),
    })


@app.route("/api/update_level", methods=["POST"])
def api_update_level():
    body       = request.json or {}
    json_path  = body.get("json_path", "").strip()
    heading_id = body.get("heading_id")
    new_level  = body.get("proposed_level")

    sess = _sessions.get(json_path)
    if not sess:
        return jsonify({"error": "File not loaded — call /api/load first"}), 400

    headings = sess["headings"]
    for h in headings:
        if h.id == heading_id:
            h.proposed_level = max(1, min(4, int(new_level)))
            h.pattern = "manual"
            break
    else:
        return jsonify({"error": f"Heading id {heading_id} not found"}), 404

    return jsonify({
        "headings":     [asdict(h) for h in headings],
        "proposed_toc": headings_to_proposed_toc(headings),
    })


@app.route("/api/shift_section", methods=["POST"])
def api_shift_section():
    """Shift a heading AND all its proposed-tree children up or down one level.

    "Children" = every heading after it (in document / id order) whose
    proposed_level is strictly greater than the heading's own proposed_level,
    stopping as soon as a heading at the same level or shallower is encountered.

    delta = -1  →  promote (decrease level, min 1)
    delta = +1  →  demote  (increase level, max 4)

    All shifted headings get pattern = "manual".
    """
    body       = request.json or {}
    json_path  = body.get("json_path", "").strip()
    heading_id = body.get("heading_id")
    delta      = body.get("delta")

    sess = _sessions.get(json_path)
    if not sess:
        return jsonify({"error": "File not loaded — call /api/load first"}), 400
    if delta not in (-1, 1):
        return jsonify({"error": "delta must be -1 or 1"}), 400

    headings = sess["headings"]
    sorted_hs = sorted(headings, key=lambda h: h.id)

    # Find the target heading and its index in document order
    try:
        idx = next(i for i, h in enumerate(sorted_hs) if h.id == heading_id)
    except StopIteration:
        return jsonify({"error": f"Heading id {heading_id} not found"}), 404

    root = sorted_hs[idx]
    base_level = root.proposed_level

    # Collect root + all children
    to_shift = [root]
    for h in sorted_hs[idx + 1:]:
        if h.proposed_level <= base_level:
            break
        to_shift.append(h)

    for h in to_shift:
        h.proposed_level = max(1, min(4, h.proposed_level + delta))
        h.pattern = "manual"

    return jsonify({
        "headings":     [asdict(h) for h in headings],
        "proposed_toc": headings_to_proposed_toc(headings),
    })


@app.route("/api/save", methods=["POST"])
def api_save():
    body      = request.json or {}
    json_path = body.get("json_path", "").strip()

    sess = _sessions.get(json_path)
    if not sess:
        return jsonify({"error": "File not loaded — call /api/load first"}), 400

    try:
        path          = Path(json_path)
        raw           = sess["raw"]
        index_key     = sess["index_key"]
        data_key      = sess["data_key"]
        headings      = sess["headings"]
        original_data = sess["original_data"]

        # Rebuild data[] tree
        new_data = rebuild_tree(original_data, headings)

        # Rebuild contents[] from corrected tree
        new_contents = build_toc(new_data)

        raw[data_key][0]["data"]          = new_data
        raw[index_key][0]["contents"]     = new_contents

        # Backup then overwrite
        bak_path = path.with_suffix(".bak")
        bak_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent="\t", ensure_ascii=False)
            f.write("\n")

        # Refresh session raw so subsequent saves are idempotent
        sess["raw"] = raw

        return jsonify({"ok": True, "backup": str(bak_path)})
    except Exception as exc:
        import traceback
        return jsonify({"error": str(exc), "trace": traceback.format_exc()}), 500


# ─────────────────────────────────────────────────────────────────────────────
# HTML / JS UI
# ─────────────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TOC Fixer</title>
<link rel="stylesheet"
  href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
<style>
  body { font-size: 0.875rem; }
  .toc-panel { height: 300px; overflow-y: auto; }
  .toc-l1 { font-weight: 600; margin-top: 0.2rem; }
  .toc-l2 { padding-left: 1rem; color: #444; }
  .toc-l3 { padding-left: 2rem; color: #888; }
  .row-changed { background: #fff3cd !important; }
  .row-manual  { background: #cfe2ff !important; }
  .row-l1 > td:nth-child(2) { font-weight: 600; }
  .name-indent { display: inline-block; }
  #headingTable tbody tr:hover { filter: brightness(0.96); }
  #status { font-size: 0.8rem; }
  .badge-pat { font-size: 0.68rem; }
</style>
</head>
<body class="p-3">

<h5 class="mb-3">TOC Fixer</h5>

<!-- Toolbar -->
<div class="row g-2 mb-3 align-items-end">
  <div class="col-auto">
    <label class="form-label mb-1 small">Adventure JSON</label>
    <select id="jsonSel" class="form-select form-select-sm" style="max-width:340px"></select>
  </div>
  <div class="col-auto">
    <label class="form-label mb-1 small">PDF (optional)</label>
    <input id="pdfInput" type="text" class="form-control form-control-sm"
      style="max-width:300px" placeholder="path/to/module.pdf">
  </div>
  <div class="col-auto">
    <button class="btn btn-primary btn-sm" onclick="doLoad()">Load</button>
  </div>
  <div class="col-auto">
    <span id="status" class="text-muted"></span>
  </div>
</div>

<!-- Three TOC panels -->
<div class="row g-2 mb-2">
  <div class="col-4">
    <div class="card h-100">
      <div class="card-header py-1 fw-semibold small">
        PDF TOC <span class="text-muted fw-normal">(authoritative)</span>
      </div>
      <div class="card-body p-2 toc-panel" id="pdfTocPanel">
        <span class="text-muted">No file loaded.</span>
      </div>
    </div>
  </div>
  <div class="col-4">
    <div class="card h-100">
      <div class="card-header py-1 fw-semibold small">Current JSON TOC</div>
      <div class="card-body p-2 toc-panel" id="currentTocPanel">
        <span class="text-muted">No file loaded.</span>
      </div>
    </div>
  </div>
  <div class="col-4">
    <div class="card h-100">
      <div class="card-header py-1 fw-semibold small">
        Proposed TOC <span class="text-muted fw-normal">(live preview)</span>
      </div>
      <div class="card-body p-2 toc-panel" id="proposedTocPanel">
        <span class="text-muted">No file loaded.</span>
      </div>
    </div>
  </div>
</div>

<!-- Heuristic buttons -->
<div class="d-flex gap-2 mb-2 align-items-center flex-wrap">
  <button id="btnPdfAnchor" class="btn btn-outline-secondary btn-sm"
    onclick="applyHeuristic('pdf_anchor')" disabled>
    Apply PDF Anchor
  </button>
  <button id="btnKeyedRoom" class="btn btn-outline-secondary btn-sm"
    onclick="applyHeuristic('keyed_room')" disabled>
    Apply Keyed Room
  </button>
  <button id="btnReset" class="btn btn-outline-danger btn-sm"
    onclick="applyHeuristic('reset')" disabled>
    Reset
  </button>
  <div class="ms-auto">
    <button id="btnSave" class="btn btn-success btn-sm"
      onclick="doSave()" disabled>
      Save JSON
    </button>
  </div>
</div>

<!-- Heading table -->
<div style="max-height:50vh;overflow-y:auto">
  <table class="table table-sm table-bordered table-hover mb-0" id="headingTable">
    <thead class="table-light sticky-top">
      <tr>
        <th style="width:2.5rem">#</th>
        <th>Name</th>
        <th style="width:3rem" class="text-center">Cur</th>
        <th style="width:7rem">Proposed</th>
        <th style="width:4rem" class="text-center" title="Shift whole section up/down one level">Section</th>
        <th style="width:14rem">PDF Section</th>
        <th style="width:11rem">Pattern</th>
      </tr>
    </thead>
    <tbody id="headingTbody"></tbody>
  </table>
</div>

<script>
const PRELOAD_JSON = "__PRELOAD_JSON__";
const PRELOAD_PDF  = "__PRELOAD_PDF__";

let state = {
  jsonPath:    null,
  pdfPath:     null,
  hasPdf:      false,
  pdfToc:      [],
  currentToc:  [],
  headings:    [],
  proposedToc: [],
};

// ── Init ──────────────────────────────────────────────────────────────────

async function init() {
  const resp  = await fetch("/api/files");
  const files = await resp.json();
  const sel   = document.getElementById("jsonSel");
  sel.innerHTML = files.map(f =>
    `<option value="${esc(f)}">${esc(f)}</option>`
  ).join("");
  if (PRELOAD_JSON) {
    sel.value = PRELOAD_JSON;
    document.getElementById("pdfInput").value = PRELOAD_PDF || "";
  }
}

// ── Load ──────────────────────────────────────────────────────────────────

async function doLoad() {
  const jsonPath = document.getElementById("jsonSel").value;
  const pdfPath  = document.getElementById("pdfInput").value.trim();
  setStatus("Loading…", "text-muted");
  try {
    const resp = await fetch("/api/load", {
      method:  "POST",
      headers: {"Content-Type": "application/json"},
      body:    JSON.stringify({json_path: jsonPath, pdf_path: pdfPath}),
    });
    const data = await resp.json();
    if (data.error) { setStatus(data.error, "text-danger"); return; }
    state.jsonPath   = jsonPath;
    state.pdfPath    = pdfPath;
    state.hasPdf     = pdfPath !== "" && data.pdf_toc && data.pdf_toc.length > 0;
    state.currentToc = data.current_toc;
    applyResponse(data);
    enableButtons();
    setStatus(
      `Loaded ${data.headings.length} headings` +
      (state.hasPdf ? `, ${data.pdf_toc.length} PDF bookmarks.` : ". (No PDF bookmarks.)"),
      "text-success"
    );
  } catch (e) {
    setStatus(String(e), "text-danger");
  }
}

function applyResponse(data) {
  if (data.pdf_toc      !== undefined) state.pdfToc      = data.pdf_toc;
  if (data.headings     !== undefined) state.headings    = data.headings;
  if (data.proposed_toc !== undefined) state.proposedToc = data.proposed_toc;
  render();
}

// ── Heuristics ────────────────────────────────────────────────────────────

async function applyHeuristic(name) {
  setStatus("Applying…", "text-muted");
  try {
    const resp = await fetch("/api/apply_heuristic", {
      method:  "POST",
      headers: {"Content-Type": "application/json"},
      body:    JSON.stringify({json_path: state.jsonPath, heuristic: name}),
    });
    const data = await resp.json();
    if (data.error) { setStatus(data.error, "text-danger"); return; }
    applyResponse(data);
    setStatus("Done.", "text-success");
  } catch (e) {
    setStatus(String(e), "text-danger");
  }
}

// ── Manual level update ───────────────────────────────────────────────────

async function shiftSection(headingId, delta) {
  try {
    const resp = await fetch("/api/shift_section", {
      method:  "POST",
      headers: {"Content-Type": "application/json"},
      body:    JSON.stringify({
        json_path:  state.jsonPath,
        heading_id: headingId,
        delta:      delta,
      }),
    });
    const data = await resp.json();
    if (data.error) { setStatus(data.error, "text-danger"); return; }
    applyResponse(data);
  } catch (e) {
    setStatus(String(e), "text-danger");
  }
}

async function updateLevel(headingId, newLevel) {
  try {
    const resp = await fetch("/api/update_level", {
      method:  "POST",
      headers: {"Content-Type": "application/json"},
      body:    JSON.stringify({
        json_path: state.jsonPath,
        heading_id: headingId,
        proposed_level: newLevel,
      }),
    });
    const data = await resp.json();
    if (data.error) { setStatus(data.error, "text-danger"); return; }
    applyResponse(data);
  } catch (e) {
    setStatus(String(e), "text-danger");
  }
}

// ── Save ──────────────────────────────────────────────────────────────────

async function doSave() {
  setStatus("Saving…", "text-muted");
  try {
    const resp = await fetch("/api/save", {
      method:  "POST",
      headers: {"Content-Type": "application/json"},
      body:    JSON.stringify({json_path: state.jsonPath}),
    });
    const data = await resp.json();
    if (data.error) {
      setStatus("Error: " + data.error, "text-danger");
      console.error(data.trace);
      return;
    }
    setStatus(`Saved. Backup: ${data.backup}`, "text-success");
  } catch (e) {
    setStatus(String(e), "text-danger");
  }
}

// ── Rendering ─────────────────────────────────────────────────────────────

function render() {
  renderPdfToc();
  renderCurrentToc();
  renderProposedToc();
  renderTable();
}

function renderPdfToc() {
  const el = document.getElementById("pdfTocPanel");
  if (!state.pdfToc.length) {
    el.innerHTML = '<span class="text-muted small">No bookmarks found.</span>';
    return;
  }
  el.innerHTML = state.pdfToc.map(e => {
    const pad  = (e.level - 1) * 16;
    const cls  = e.level === 1 ? "toc-l1" : e.level === 2 ? "toc-l2" : "toc-l3";
    return `<div class="${cls}" style="padding-left:${pad}px">p${e.page}: ${esc(e.title)}</div>`;
  }).join("");
}

function renderTocList(toc, el) {
  if (!toc.length) {
    el.innerHTML = '<span class="text-muted small">Empty.</span>';
    return;
  }
  el.innerHTML = toc.map(ch => {
    const hdrs = (ch.headers || [])
      .map(h => `<div class="toc-l2">${esc(h)}</div>`)
      .join("");
    return `<div class="toc-l1">${esc(ch.name)}</div>${hdrs}`;
  }).join("");
}

function renderCurrentToc()  {
  renderTocList(state.currentToc,  document.getElementById("currentTocPanel"));
}
function renderProposedToc() {
  renderTocList(state.proposedToc, document.getElementById("proposedTocPanel"));
}

function renderTable() {
  const tbody = document.getElementById("headingTbody");
  if (!state.headings.length) { tbody.innerHTML = ""; return; }

  tbody.innerHTML = state.headings.map(h => {
    const origLevel = h.current_depth + 1;
    const changed   = h.proposed_level !== origLevel;
    const manual    = h.pattern === "manual";
    const rowCls    = manual ? "row-manual" : changed ? "row-changed" : "";
    const l1Cls     = h.proposed_level === 1 ? "row-l1" : "";
    const indent    = h.current_depth * 12;

    const opts = [1, 2, 3, 4].map(l =>
      `<option value="${l}"${l === h.proposed_level ? " selected" : ""}>${l}</option>`
    ).join("");

    const patternHtml = h.pattern
      ? `<span class="badge bg-light text-dark border badge-pat">${esc(h.pattern)}</span>`
      : "";

    const depthWarn = origLevel > 4
      ? `<span class="text-warning ms-1" title="Original depth ${origLevel} exceeds cap">⚠</span>`
      : "";

    return `<tr class="${rowCls} ${l1Cls}" data-id="${h.id}">
      <td class="text-muted small">${h.id}</td>
      <td>
        <span class="name-indent" style="padding-left:${indent}px">${esc(h.name)}</span>
      </td>
      <td class="text-center text-muted">${origLevel}</td>
      <td>
        <select class="form-select form-select-sm py-0"
          onchange="updateLevel(${h.id}, +this.value)">
          ${opts}
        </select>${depthWarn}
      </td>
      <td class="text-center">
        <button class="btn btn-outline-secondary btn-sm py-0 px-1 lh-1"
          title="Promote section (shift this heading + children up one level)"
          onclick="shiftSection(${h.id}, -1)">▲</button>
        <button class="btn btn-outline-secondary btn-sm py-0 px-1 lh-1"
          title="Demote section (shift this heading + children down one level)"
          onclick="shiftSection(${h.id}, +1)">▼</button>
      </td>
      <td class="text-muted small">${esc(h.pdf_section)}</td>
      <td>${patternHtml}</td>
    </tr>`;
  }).join("");
}

// ── Helpers ───────────────────────────────────────────────────────────────

function setStatus(msg, cls) {
  const el = document.getElementById("status");
  el.textContent = msg;
  el.className   = cls;
}

function enableButtons() {
  document.getElementById("btnPdfAnchor").disabled = !state.hasPdf;
  document.getElementById("btnKeyedRoom").disabled = false;
  document.getElementById("btnReset").disabled     = false;
  document.getElementById("btnSave").disabled      = false;
}

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

init();
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="TOC fixer for 5etools adventure/book JSON"
    )
    parser.add_argument("file",  nargs="?", default="", help="JSON file to pre-load")
    parser.add_argument("--pdf", default="",            help="PDF file to pre-load")
    parser.add_argument(
        "--port", type=int,
        default=int(os.environ.get("PORT", 5102)),
    )
    args = parser.parse_args()

    _preload_json = args.file
    _preload_pdf  = args.pdf

    print(f"TOC Fixer running at http://localhost:{args.port}")
    app.run(port=args.port, debug=False)
