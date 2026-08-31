#!/usr/bin/env python3
"""Extract monster stat blocks from a parsed adventure JSON and convert them
to 5etools bestiary format using Claude.

Usage:
    python3 converters/extract_monsters.py adventure-toworlds.json
    python3 converters/extract_monsters.py adventure-toworlds.json --dry-run
    python3 converters/extract_monsters.py adventure-toworlds.json --model claude-sonnet-4-6
    python3 converters/extract_monsters.py adventure-toworlds.json --out bestiary-toworlds.json
"""

import argparse
import json
import re
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lib.claude_api as _api
import lib.llm_backend as _lb

# ---------------------------------------------------------------------------
# System prompt for monster conversion
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = textwrap.dedent("""\
You are an expert at converting D&D 5e monster stat blocks into the 5etools
bestiary JSON format.

You will receive one or more stat blocks that have been extracted from an
adventure JSON file. They are represented as tables (key-value rows or
multi-column) plus trait/action entries. Convert each into a proper 5etools
monster object.

Return ONLY a valid JSON array of monster objects. Return [] if the input does
not contain a real stat block. No markdown fences, no explanation.

Each monster object must include these fields (omit optional ones if not present):

REQUIRED:
  name        string   -- creature name (strip parenthetical counts like "(2)")
  source      string   -- use "PLACEHOLDER" (script fills in the real source)
  size        array    -- ["M"] for Medium, ["S"] for Small, etc.
  type        string or {{"type":"humanoid","tags":["human"]}}
  alignment   array    -- ["L","G"] / ["N","E"] / ["U"] for unaligned etc.
  ac          array    -- [15] or [{{"ac":15,"from":["chain mail"]}}]
  hp          object   -- {{"average":22,"formula":"3d8+9"}}
  speed       object   -- {{"walk":30}} or {{"walk":30,"fly":60}}
  str,dex,con,int,wis,cha  integers (just the score, not the modifier)
  passive     integer  -- passive Perception
  cr          string   -- "1/4","1/2","1","2" etc.

OPTIONAL (include if present):
  save        object   -- {{"str":"+4","con":"+6"}}
  skill       object   -- {{"perception":"+5","stealth":"+4"}}
  senses      array    -- ["darkvision 60 ft.","tremorsense 30 ft."]
  languages   array    -- ["Common","Elvish"] or ["\\u2014"] if none
  immune      array    -- damage types: ["fire","poison"]
  resist      array    -- damage types
  vulnerable  array    -- damage types
  conditionImmune array -- ["charmed","frightened"]
  trait       array    -- [{{"name":"Trait Name","entries":["Description."]}}]
  action      array    -- [{{"name":"Multiattack","entries":["The creature makes two attacks."]}}]
               For attacks use: "{{@atk mw}} {{@hit 5}} to hit, reach 5 ft., one target. {{@h}}{{@damage 2d6+3}} slashing damage."
  bonus       array    -- bonus actions, same format as action
  reaction    array    -- reactions, same format as action
  legendary   array    -- legendary actions
  legendaryActions  number -- number of legendary actions per round (default 3)
  spellcasting array   -- see format below
  isNamedCreature bool -- see NPC classification rules below
  isNpc       bool     -- see NPC classification rules below

NPC classification (IMPORTANT — many adventure-module stat blocks are NPCs
rather than monsters; classifying them correctly keeps the default
5etools bestiary filter clean):

  Set `isNpc: true` when the stat block represents a PERSON filling a
  human role or trade, rather than a creature type. This applies whether
  the entry is singular or a group.
    - Singular named person:      Ostler the Innkeeper, Rannos Davl,
                                  Elmo, Hedrack -> isNpc: true
    - Singular role / title:      Farmer, Smith, Woodcutter, Tailor,
                                  Manservant, Groom -> isNpc: true
    - Plural group of people:     Sons (2), Apprentices (4), Stablemen (2),
                                  Guards (6), Men-at-Arms (8) -> isNpc: true

  Set `isNamedCreature: true` (IN ADDITION to `isNpc: true`) when the
  name is a unique proper noun for a specific individual rather than a
  generic role:
    - Ostler the Innkeeper  -> isNpc: true, isNamedCreature: true
    - Rannos Davl           -> isNpc: true, isNamedCreature: true
    - Farmer                -> isNpc: true  (no isNamedCreature — it's a role)
    - Sons (2)              -> isNpc: true  (no isNamedCreature — group)

  Do NOT set `isNpc` when the stat block is a CREATURE TYPE, even if it
  appears in a group or keeps company with humans:
    - Farm dogs (2), Cart horses, Rats (giant) -> regular monster, no isNpc
    - Ghouls, Gnolls, Orcs, Goblins, Dragons   -> regular monster, no isNpc
    - Demons, Undead, Elementals               -> regular monster, no isNpc

  Rule of thumb: if a five-year-old would say "that's a person" -> isNpc.
  If they'd say "that's an animal / a monster" -> leave isNpc unset.

Spellcasting format:
{{
  "name": "Spellcasting",
  "type": "spellcasting",
  "headerEntries": ["The mage is a 5th-level spellcaster...spell save {{@dc 13}}; {{@hit 5}} to hit..."],
  "spells": {{
    "0": {{"spells": ["{{@spell mage hand}}","{{@spell prestidigitation}}"]}},
    "1": {{"slots": 4, "spells": ["{{@spell magic missile}}","{{@spell shield}}"]}},
    "2": {{"slots": 3, "spells": ["{{@spell misty step}}"]}}
  }},
  "footerEntries": []
}}

For innate spellcasting use:
{{
  "name": "Innate Spellcasting",
  "type": "spellcasting",
  "headerEntries": ["The creature's innate spellcasting ability is Charisma (spell save DC 13). It can innately cast the following spells, requiring no material components:"],
  "will": ["{{@spell light}}"],
  "daily": {{
    "1e": ["{{@spell lesser restoration}}"],
    "3e": ["{{@spell cure wounds}}"]
  }},
  "footerEntries": []
}}

IMPORTANT formatting rules:
- Spell names must be wrapped in {{@spell name}} tags
- Attack entries must use {{@atk mw}} (melee weapon), {{@atk rw}} (ranged weapon), {{@atk ms}} (melee spell), {{@atk rs}} (ranged spell)
- Hit bonuses: {{@hit N}}
- Damage: {{@damage XdY+Z}}
- DCs: {{@dc N}}
- Hit shorthand: {{@h}} (expands to "Hit: ")
- Conditions: {{@condition poisoned}}, {{@condition frightened}}, etc.
- Strip count suffixes from names: "Klaven Void Zombie (2)" -> "Klaven Void Zombie"
- For named NPCs set isNamedCreature: true and isNpc: true

Alignment abbreviations: L=Lawful, N=Neutral, C=Chaotic, G=Good, E=Evil, U=Unaligned, A=Any
""")

# ---------------------------------------------------------------------------
# Extract stat block entries from adventure JSON
# ---------------------------------------------------------------------------

def _has_ac_table(entry):
    """Check if an entries dict directly contains an AC stat-block table."""
    for child in entry.get("entries", []):
        if isinstance(child, dict) and child.get("type") == "table":
            rows = child.get("rows", [])
            cols = child.get("colLabels", [])
            has_ac = any(
                isinstance(r, list) and len(r) > 0 and r[0] == "Armor Class"
                for r in rows
            )
            if has_ac or "Armor Class" in cols:
                return True
    return False


def extract_statblock_entries(obj, parent_name=""):
    """Walk the adventure JSON tree and return all entries containing stat-block tables.

    For unnamed entries, inherits the name from the nearest named ancestor.
    """
    results = []
    if isinstance(obj, dict):
        name = obj.get("name", "") or parent_name
        if obj.get("type") == "entries" and "entries" in obj:
            if _has_ac_table(obj):
                # If this entry has no name, inherit from parent
                if not obj.get("name") and parent_name:
                    obj = {**obj, "name": parent_name}
                results.append(obj)
                return results
            # No stat table found directly — recurse into children
            for child in obj["entries"]:
                results.extend(extract_statblock_entries(child, name))
            return results
        for k, v in obj.items():
            results.extend(extract_statblock_entries(v, name))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(extract_statblock_entries(item, parent_name))
    return results


# ---------------------------------------------------------------------------
# Italic-string stat blocks (v2 adventure format)
# ---------------------------------------------------------------------------
# v2's adventure prompt emits 1e/2e stat blocks as italic strings of the form
# `{@i Name: AC X, MV Y, HD Z, ...}`. We detect these by matching the {@i ...}
# envelope, then checking that the body starts with a name followed by an AC
# token. The approach also works for 5e-shape stat lines where AC appears
# early in the body.

# A stat line starts with a monster name, a colon, then "AC <digit>" within
# the first ~40 chars of the body. The name may contain commas, parens, or
# numbers but never `{`, `}`, or a leading digit (which would indicate a
# numbered room heading like "101. Armory", not a monster).
_ITALIC_STATBLOCK_RE = re.compile(
    r"\{@i\s+(?P<name>(?!\d)[^:{}\n]{2,120}?)\s*[:;]\s*(?P<body>AC\b[^{}]{10,2000})\}",
    re.DOTALL,
)


def iter_strings(obj):
    """Yield every string value found in a nested JSON structure."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from iter_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_strings(v)


def extract_italic_statblocks(obj):
    """Find italic-string stat blocks in a parsed adventure tree.

    Returns a list of ``{"name": str, "text": str}`` dicts where ``text``
    is the full stat line (without the surrounding ``{@i ...}`` markers),
    ready to be concatenated into a Claude prompt.

    Deduplicates by name + first 60 chars of body (handles the common
    case where the same stat line appears verbatim in multiple rooms).
    """
    seen: dict[tuple[str, str], dict] = {}
    for s in iter_strings(obj):
        for m in _ITALIC_STATBLOCK_RE.finditer(s):
            name = m.group("name").strip()
            body = m.group("body").strip()
            key = (name.lower(), body[:60])
            if key not in seen:
                seen[key] = {"name": name, "text": f"{name}: {body}"}
    return list(seen.values())


def italic_statblock_to_text(block):
    """Match the shape of statblock_to_text() for consistency."""
    name = block["name"]
    return f"=== {name} ===\n{block['text']}"


# ---------------------------------------------------------------------------
# Label-line stat blocks (5e format inside a converted adventure/book JSON)
# ---------------------------------------------------------------------------
# The v2 adventure prompt renders a modern 5e stat block as plain entry
# strings carrying markdown-bold labels:
#
#     "{@b Armor Class} 13 (natural armor)"
#     "**Hit Points** 45 (6d10 + 12)"
#     "**Speed** 30 ft."
#     ...
#     "**Challenge** 3 (700 XP)"
#
# None of the detectors above see these: `_has_ac_table` needs a real
# `table` child, and `_ITALIC_STATBLOCK_RE` needs the 1e-style
# `{@i Name: AC 7, MV 12", ...}` envelope. On a modern bestiary PDF that
# made `--extract-monsters` report "0 stat blocks" and write nothing —
# silently, because zero blocks is a legitimate result for an adventure
# with no monsters.
#
# Detection is deliberately conservative. A node qualifies only if at
# least `_MIN_STATBLOCK_LABELS` of the four canonical labels appear, each
# at the start of a line and each followed by a number. Requiring three
# of four is what separates a stat block from prose or a player option
# that merely mentions AC (e.g. a druid Wild Shape "Bear Form" entry, or
# a barding item with an AC bonus).

_STATBLOCK_LABEL_RES = {
    "ac":        re.compile(r"^armor\s+class\b\D{0,24}\d", re.I),
    "hp":        re.compile(r"^hit\s+points\b\D{0,24}\d", re.I),
    "speed":     re.compile(r"^speed\b\D{0,24}\d", re.I),
    "challenge": re.compile(r"^challenge\b\D{0,24}\d", re.I),
}

# How many of the four labels a node must carry to count as a stat block.
_MIN_STATBLOCK_LABELS = 3

# Sub-headings a converter emits *inside* a stat block. A node whose
# children are all named from this set is a single monster split across
# sub-entries, not a chapter holding several monsters — so it is kept
# whole rather than descended into.
_GENERIC_STATBLOCK_HEADINGS = {
    "description", "defenses", "ability scores", "abilities", "statistics",
    "stats", "attributes", "traits", "trait", "special abilities",
    "actions", "reactions", "bonus actions", "legendary actions",
    "lair actions", "regional effects", "spellcasting",
}

# Keys under which an entry node holds its children. `entries` is the
# usual one; `data` is the top level of adventureData/bookData. Walking
# only `entries` is what makes a naive scan of a *book* find nothing.
_ENTRY_CHILD_KEYS = ("entries", "data")

_MARKUP_TAG_RE = re.compile(r"\{@[bi]\s+([^{}]*)\}")


def _demark(text: str) -> str:
    """Strip the bold/italic wrappers a label may arrive in.

    Handles all four shapes seen in practice: ``**Armor Class** 13``,
    ``{@b Armor Class} 13``, ``**Armor Class 13**`` and bare
    ``Armor Class 13``.
    """
    return _MARKUP_TAG_RE.sub(r"\1", text).replace("*", "").strip()


def _labels_in_string(text: str) -> set[str]:
    """Return the canonical stat labels that start a line of *text*."""
    found: set[str] = set()
    for line in text.splitlines():
        line = _demark(line)
        if not line:
            continue
        for key, pat in _STATBLOCK_LABEL_RES.items():
            if key not in found and pat.match(line):
                found.add(key)
    return found


def _direct_labels(node: dict) -> set[str]:
    """Stat labels on *node*'s own string children (one level deep).

    Looks at bare strings under `entries`/`data` and at the items of a
    directly-nested `list`, which is how some chunks render the stat
    lines. Does not descend into child entry nodes — that is what keeps a
    chapter from matching on the strength of the monsters inside it.
    """
    found: set[str] = set()
    for key in _ENTRY_CHILD_KEYS:
        for child in node.get(key, []) or []:
            if isinstance(child, str):
                found |= _labels_in_string(child)
            elif isinstance(child, dict) and child.get("type") == "list":
                for item in child.get("items", []) or []:
                    if isinstance(item, str):
                        found |= _labels_in_string(item)
    return found


def _subtree_labels(node: Any) -> set[str]:
    """Stat labels anywhere beneath *node*, at any depth."""
    found: set[str] = set()
    if isinstance(node, str):
        return _labels_in_string(node)
    if isinstance(node, list):
        for item in node:
            found |= _subtree_labels(item)
        return found
    if isinstance(node, dict):
        for key in ("entries", "data", "items", "rows"):
            found |= _subtree_labels(node.get(key, []) or [])
    return found


def _entry_children(node: dict) -> list[dict]:
    """Immediate child entry *dicts* of *node*, across both child keys."""
    kids: list[dict] = []
    for key in _ENTRY_CHILD_KEYS:
        for child in node.get(key, []) or []:
            if isinstance(child, dict) and child.get("type") != "list":
                kids.append(child)
    return kids


def _is_generic_heading(node: dict) -> bool:
    """True if *node* is an unnamed wrapper or a stat-block sub-heading."""
    name = (node.get("name") or "").strip().lower().rstrip(".")
    return not name or name in _GENERIC_STATBLOCK_HEADINGS


def _flatten_node_text(node: Any, out: list[str], depth: int = 0) -> None:
    """Append a readable flattening of *node* to *out*."""
    if isinstance(node, str):
        out.append(node)
        return
    if isinstance(node, list):
        for item in node:
            _flatten_node_text(item, out, depth)
        return
    if not isinstance(node, dict):
        return
    ntype = node.get("type", "")
    if ntype == "table":
        cols = node.get("colLabels") or []
        if cols:
            out.append("  ".join(str(c) for c in cols))
        for row in node.get("rows", []) or []:
            if isinstance(row, list):
                out.append("  ".join(str(c) for c in row))
        return
    if ntype == "list":
        for item in node.get("items", []) or []:
            if isinstance(item, str):
                out.append(f"- {item}")
            else:
                _flatten_node_text(item, out, depth)
        return
    name = node.get("name")
    if name and depth:
        out.append(f"\n{name}")
    for key in _ENTRY_CHILD_KEYS:
        _flatten_node_text(node.get(key, []) or [], out, depth + 1)


def labeled_statblock_to_text(name: str, node: dict) -> str:
    """Format one detected node as prompt content for the monster pass."""
    lines: list[str] = []
    _flatten_node_text(node, lines)
    body = "\n".join(line for line in lines).strip()
    return f"=== {name} ===\n{body}"


def extract_labeled_statblocks(obj: Any) -> list[dict]:
    """Find label-line 5e stat blocks in a parsed adventure/book tree.

    Returns ``{"name": str, "text": str}`` dicts where ``text`` is already
    prompt-ready (same contract as :func:`statblock_to_text`'s output),
    deduplicated by name plus the head of the block.

    The walk keeps the *innermost* node that owns the stat lines: a node
    matches either because its own string children carry the labels, or
    because it carries them across sub-entries that are all generic
    stat-block headings (``Defenses``, ``Ability Scores``, ``Actions``…),
    which is how a handful of blocks come back shaped per conversion run.
    A node whose children are named something else is treated as a
    container and descended into instead.
    """
    results: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def keep(node: dict, name: str) -> None:
        label = name or node.get("name") or "Unknown"
        text = labeled_statblock_to_text(label, node)
        key = (label.strip().lower(), text[:120])
        if key in seen:
            return
        seen.add(key)
        results.append({"name": label.strip(), "text": text})

    def visit(node: Any, inherited: str) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item, inherited)
            return
        if not isinstance(node, dict):
            return

        own = (node.get("name") or "").strip()
        # A generic sub-heading is never the monster's name — keep looking
        # up the tree for the nearest real one.
        effective = own if own and not _is_generic_heading(node) else inherited

        if len(_direct_labels(node)) >= _MIN_STATBLOCK_LABELS:
            keep(node, effective)
            return

        kids = _entry_children(node)
        if (kids
                and len(_subtree_labels(node)) >= _MIN_STATBLOCK_LABELS
                and all(_is_generic_heading(k) for k in kids)):
            keep(node, effective)
            return

        if kids:
            for kid in kids:
                visit(kid, effective)
        else:
            for value in node.values():
                visit(value, effective)

    visit(obj, "")
    return results


# ---------------------------------------------------------------------------
# Marker-markdown stat block detection (for --monsters-only)
# ---------------------------------------------------------------------------
# Adventure modules interleave stat blocks with room descriptions, so a
# heading-based section scan is too loose — a farmhouse room that happens
# to contain a "Farm dogs: AC 7" line would be classified as a monster.
#
# Instead we find STAT LINES directly and emit one entry per line. A stat
# line matches ``NAME (optional count): AC N, ...`` or ``NAME AC N`` where:
#   - NAME is 2–80 chars, starts with a letter (not a digit, to reject
#     numbered room headings like "101. Armory"), contains no colon
#   - AC is immediately followed by a digit
#   - Additional stat tokens (MV / HD / #AT / D / hp) appear nearby
#
# Bestiary-style PDFs (one monster per `##` section) are handled as a
# fallback: if a section's FIRST non-empty body line is itself a stat
# line, we keep the whole section as context for that monster.

_MD_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")

# Tokens that distinguish a 1e stat line from prose with "AC" in it.
_STAT_TOKEN_RE = re.compile(
    r"\b(?:MV\s+\d|HD\s+\d|#AT\b|hp\s+\d|THAC0\b|Hit\s*Points|"
    r"Speed\s+\d|passive\s+Perception)",
    re.IGNORECASE,
)

# 5e-style stat-block header markers. A section whose first few body
# lines contain any of these is treated as a bestiary entry and kept
# wholesale. Strip markdown bold (`**`) before matching.
_5E_HEADER_RE = re.compile(
    r"\b(?:Armor\s+Class\s+\d|Hit\s+Points\s+\d|Speed\s+\d+\s*ft\.?|"
    r"Challenge\s+\d|Proficiency\s+Bonus\s+[+−-]?\d)",
    re.IGNORECASE,
)


def _is_1e_stat_line(line: str) -> bool:
    """True if `line` matches the 1e-style NAME: AC N, MV ..., HD ..., ... shape."""
    m = _INLINE_STAT_RE.match(line)
    return bool(m and _STAT_TOKEN_RE.search(m.group("body")))


def _is_5e_statblock_start(lines: list[str], start_of_body: int, end: int,
                          scan: int = 4) -> bool:
    """True if any of the first `scan` non-empty body lines look like a 5e
    stat-block header (Armor Class / Hit Points / Speed / Challenge)."""
    seen = 0
    for j in range(start_of_body, end):
        stripped = re.sub(r"\*+", "", lines[j]).strip()
        if not stripped:
            continue
        if _MD_HEADING_RE.match(lines[j]):
            continue
        if _5E_HEADER_RE.search(stripped):
            return True
        seen += 1
        if seen >= scan:
            break
    return False

# Per-line stat line: NAME: AC <digit>, ...
# The name must start with a letter (rejects "101. Armory: AC ...")
# and not contain { } : (so `{@i ...}` envelopes don't match here).
_INLINE_STAT_RE = re.compile(
    r"""
    ^\s*(?:[-*]\s+)?          # optional leading bullet
    (?:\*\*)?                 # optional leading bold
    (?P<name>
        (?![0-9])[^:{}\n]{2,80}?
    )
    (?:\*\*)?                 # optional trailing bold on name
    \s*[:;]\s*
    (?:\*\*)?                 # optional leading bold on body
    (?P<body>
        AC\s+\d[^{}\n]{10,800}
    )
    $
    """,
    re.MULTILINE | re.VERBOSE,
)


def _gather_context(lines: list[str], line_idx: int,
                    back: int = 3, forward: int = 3) -> str:
    """Grab ``back`` preceding non-empty lines, the stat line, and up to
    ``forward`` following stat-continuation lines (they often wrap)."""
    start = line_idx
    collected_back = 0
    for j in range(line_idx - 1, -1, -1):
        if lines[j].strip():
            start = j
            collected_back += 1
            if collected_back >= back:
                break
        elif collected_back:
            break

    end = line_idx + 1
    for j in range(line_idx + 1, min(len(lines), line_idx + 1 + forward)):
        stripped = lines[j].strip()
        if not stripped:
            break
        if _MD_HEADING_RE.match(stripped):
            break
        end = j + 1

    return "\n".join(lines[start:end]).strip()


def extract_markdown_statblocks(md_text: str, header_scan_lines: int = 2):
    """Find stat-line-shaped paragraphs in Marker markdown output.

    For each match, returns ``{"name": creature_name, "text": context}``
    where the context is the stat line plus a few surrounding lines to
    anchor the creature for Claude.

    ``header_scan_lines`` is kept as a (narrower now) window for the
    legacy "whole section is a stat block" detection path, still useful
    for proper bestiary PDFs where each monster has its own heading.
    """
    lines = md_text.splitlines()

    # Per-section fallback: if the FIRST non-empty body line after a
    # heading is itself a stat line, keep the whole section.
    heading_indices: list[tuple[str, int, int]] = []
    current_heading = None
    current_start = 0
    for i, line in enumerate(lines):
        m = _MD_HEADING_RE.match(line)
        if m:
            if current_heading is not None:
                heading_indices.append((current_heading, current_start, i))
            current_heading = re.sub(r"\*+", "", m.group(1)).strip()
            current_start = i
    if current_heading is not None:
        heading_indices.append((current_heading, current_start, len(lines)))

    # Section fallback is ONLY for 5e-style stat blocks (one monster per
    # heading, with "Armor Class"/"Hit Points"/"Speed N ft." labels).
    # For 1e content we never keep whole sections because Marker groups
    # "Statistics" / "Details" sections that contain a bulleted list of
    # stat lines — line-level extraction produces cleaner per-monster
    # entries than the section wrapper would.
    section_blocks: list[dict] = []
    keep_lines_as_covered: set[int] = set()
    for heading, start, end in heading_indices:
        if _is_5e_statblock_start(lines, start + 1, end):
            body = "\n".join(lines[start:end]).strip()
            section_blocks.append({"name": heading, "text": body})
            for j in range(start, end):
                keep_lines_as_covered.add(j)

    # Line-level: find every stat line not already covered by a section.
    line_blocks: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()
    for i, line in enumerate(lines):
        if i in keep_lines_as_covered:
            continue
        m = _INLINE_STAT_RE.match(line)
        if not m:
            continue
        # Reject prose "AC" matches by requiring another stat token nearby
        body = m.group("body")
        if not _STAT_TOKEN_RE.search(body):
            continue
        name = re.sub(r"\*+", "", m.group("name")).strip()
        key = (name.lower(), body[:60])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        line_blocks.append({
            "name": name,
            "text": _gather_context(lines, i),
        })

    return section_blocks + line_blocks


# ---------------------------------------------------------------------------
# Shared monster-pass driver: batches text → Claude → bestiary JSON
# ---------------------------------------------------------------------------

def build_bestiary(
    backend: "_lb.Backend",
    statblocks: list[dict],
    *,
    source_id: str,
    source_meta: dict,
    model: str,
    use_batch: bool = False,
    batch_size: int = 5,
    debug_dir: Path | None = None,
    verbose: bool = False,
) -> dict:
    """Run the monster-extraction Claude pass over a list of stat blocks.

    Each ``statblocks`` entry is ``{"name": str, "text": str}`` where
    ``text`` is the pre-formatted Claude prompt content (typically the
    output of :func:`italic_statblock_to_text` or a full markdown section
    from :func:`extract_markdown_statblocks`).

    Returns a bestiary homebrew dict with ``{"_meta": ..., "monster": [...]}``.
    Caller is responsible for writing the file.
    """
    if not statblocks:
        return {
            "_meta": {
                "sources": [source_meta],
                "dateAdded": int(time.time()),
                "dateLastModified": int(time.time()),
            },
            "monster": [],
        }

    texts = [sb["text"] for sb in statblocks]
    batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]
    all_monsters: list = []

    if use_batch:
        # Each Batch API item is one Claude call; we still group statblocks
        # into batches of `batch_size` per call for context efficiency.
        prompts = ["\n\n---\n\n".join(b) for b in batches]
        per_batch_results = _api.call_claude_batch(
            backend, prompts, model, SYSTEM_PROMPT, verbose, debug_dir=debug_dir,
            validate=False,
        )
        for monsters in per_batch_results:
            if monsters:
                all_monsters.extend(monsters)
    else:
        for batch_idx, batch in enumerate(batches):
            combined = "\n\n---\n\n".join(batch)
            if verbose:
                print(f"  monster batch {batch_idx + 1}/{len(batches)} "
                      f"({len(batch)} stat blocks)...", flush=True)
            monsters = _api.call_claude(
                backend, combined, model, SYSTEM_PROMPT,
                verbose, debug_dir, f"monsters-{batch_idx:04d}",
                validate=False,
            )
            if monsters:
                all_monsters.extend(monsters)

    # Set source on every monster
    for m in all_monsters:
        if isinstance(m, dict):
            m["source"] = source_id

    # Deduplicate by name; keep last occurrence (usually the best)
    seen: dict[str, dict] = {}
    for m in all_monsters:
        if isinstance(m, dict):
            seen[m.get("name", "")] = m

    return {
        "_meta": {
            "sources": [source_meta],
            "dateAdded": int(time.time()),
            "dateLastModified": int(time.time()),
        },
        "monster": list(seen.values()),
    }


def make_bestiary_source_meta(
    adventure_source: str,
    adventure_name: str,
    author: str = "Unknown",
) -> tuple[str, dict]:
    """Return ``(bestiary_source_id, source_meta_dict)`` following the
    ``{SOURCE}b`` convention used by ``monster_editor.py``.

    The separate ID prevents 5etools from conflating the adventure and
    bestiary homebrews when both are loaded."""
    bestiary_id = f"{adventure_source}b"
    meta = {
        "json": bestiary_id,
        "abbreviation": bestiary_id[:8],
        "full": f"{adventure_name} (Bestiary)",
        "version": "1.0.0",
        "authors": [author] if author else [],
        "convertedBy": ["pdf_to_5etools_v2"],
    }
    return bestiary_id, meta


def statblock_to_text(entry):
    """Convert a stat block entry dict to a readable text representation for Claude."""
    lines = []
    name = entry.get("name", "Unknown")
    lines.append(f"=== {name} ===")

    for child in entry.get("entries", []):
        if isinstance(child, str):
            lines.append(child)
        elif isinstance(child, dict):
            ctype = child.get("type", "")
            if ctype == "table":
                cols = child.get("colLabels", [])
                if cols:
                    lines.append("  ".join(cols))
                    lines.append("-" * 40)
                for row in child.get("rows", []):
                    if isinstance(row, list):
                        lines.append("  ".join(str(c) for c in row))
            elif ctype == "entries":
                cname = child.get("name", "")
                if cname:
                    lines.append(f"\n{cname}")
                for e in child.get("entries", []):
                    if isinstance(e, str):
                        lines.append(f"  {e}")
                    elif isinstance(e, dict) and e.get("type") == "list":
                        for item in e.get("items", []):
                            lines.append(f"  - {item}")
                    elif isinstance(e, dict) and e.get("type") == "table":
                        for row in e.get("rows", []):
                            if isinstance(row, list):
                                lines.append("  " + "  ".join(str(c) for c in row))
            elif ctype == "list":
                for item in child.get("items", []):
                    lines.append(f"  - {item}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract monsters from adventure JSON into 5etools bestiary format"
    )
    parser.add_argument("input", type=Path, help="Adventure JSON file")
    parser.add_argument("--out", "-o", type=Path, default=None,
                        help="Output bestiary JSON file (default: bestiary-<input>.json)")
    parser.add_argument("--provider", choices=["claude", "dgx"], default="claude",
                        help="LLM backend (default: claude). 'dgx' calls the "
                             "OpenAI-compatible vLLM endpoint on the DGX Spark.")
    parser.add_argument("--endpoint", default=None,
                        help="DGX base URL (dgx provider only). "
                             "Default: http://192.168.1.147:8001/v1")
    parser.add_argument("--model", default=None,
                        help="Model id. For claude, defaults to claude-sonnet-4-6. "
                             "For dgx, auto-discovered from /v1/models if omitted.")
    parser.add_argument("--api-key", default=None,
                        help="Anthropic API key (claude provider only)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Just list found stat blocks, don't call Claude")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--batch-size", type=int, default=5,
                        help="Number of stat blocks to send per Claude call (default: 5)")
    args = parser.parse_args()

    # Load adventure JSON
    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    # Determine source ID
    source_id = "HOMEBREW"
    sources = data.get("_meta", {}).get("sources", [])
    if sources:
        source_id = sources[0].get("json", source_id)
    source_meta = sources[0] if sources else {
        "json": source_id,
        "abbreviation": source_id[:8],
        "full": args.input.stem,
        "version": "1.0.0",
        "authors": ["Unknown"],
        "convertedBy": ["extract_monsters"],
    }

    # Extract stat blocks
    statblocks = extract_statblock_entries(data)
    print(f"Found {len(statblocks)} stat blocks:")
    for sb in statblocks:
        print(f"  - {sb.get('name', '?')}")

    if args.dry_run:
        print("\n[dry-run] Would send these to Claude for conversion.")
        for sb in statblocks:
            print(f"\n{'='*60}")
            print(statblock_to_text(sb))
        return

    if not statblocks:
        print("No stat blocks found — nothing to do.")
        return

    # Set up the LLM backend and resolve the model id
    if args.provider == "dgx":
        endpoint = args.endpoint or _lb.DEFAULT_ENDPOINT
        model = args.model or _lb.discover_model(endpoint)
        if not args.model:
            print(f"[dgx] auto-discovered model: {model}")
        backend = _lb.dgx_backend(endpoint)
    else:
        model = args.model or "claude-sonnet-4-6"
        backend = _lb.anthropic_backend(args.api_key)

    # Convert stat blocks to text and batch them
    texts = [statblock_to_text(sb) for sb in statblocks]
    all_monsters = []

    batch_size = args.batch_size
    batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]

    print(f"\nSending {len(batches)} batch(es) to {backend.kind} ({model})...")

    for batch_idx, batch in enumerate(batches):
        combined = "\n\n---\n\n".join(batch)
        print(f"  Batch {batch_idx + 1}/{len(batches)} ({len(batch)} stat blocks)...",
              flush=True)

        monsters = _api.call_claude(
            backend, combined, model, SYSTEM_PROMPT,
            args.verbose, None, f"monsters-{batch_idx:04d}"
        )

        for m in monsters:
            if isinstance(m, dict):
                m["source"] = source_id

        all_monsters.extend(monsters)
        print(f"    Got {len(monsters)} monsters", flush=True)

    # Deduplicate by name (keep last occurrence which is usually better)
    seen = {}
    for m in all_monsters:
        if isinstance(m, dict):
            seen[m.get("name", "")] = m
    all_monsters = list(seen.values())

    print(f"\nTotal unique monsters: {len(all_monsters)}")

    # Build output
    out_path = args.out or Path(f"bestiary-{args.input.stem}.json")
    homebrew_obj = {
        "_meta": {
            "sources": [source_meta],
            "dateAdded": int(time.time()),
            "dateLastModified": int(time.time()),
        },
        "monster": all_monsters,
    }

    out_path.write_text(
        json.dumps(homebrew_obj, indent="\t", ensure_ascii=False), encoding="utf-8"
    )

    print(f"\nWrote {out_path} ({len(all_monsters)} monsters)")
    print(f"\nTo load in 5etools:")
    print(f"  1. Open bestiary.html → Manage Homebrew")
    print(f"  2. Load from File → select {out_path.name}")


if __name__ == "__main__":
    main()
