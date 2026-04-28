#!/usr/bin/env python3
"""
validate_adventure.py — Validate 5etools adventure JSON structure.

Checks structural correctness against the patterns used in official 5etools
adventure data files (data/adventure/*.json). Can validate both official format
({"data": [...]}) and homebrew format ({"_meta":..., "adventure":..., "adventureData":...}).

Usage:
    python3 validate_adventure.py adventure.json           # validate one file
    python3 validate_adventure.py *.json                   # validate multiple
    python3 validate_adventure.py --official-dir ../data/adventure/  # validate official files

As a library:
    from validate_adventure import validate
    errors, warnings = validate(json_data)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Valid values (derived from official 5etools adventure files)
# ---------------------------------------------------------------------------

VALID_ENTRY_TYPES = {
    # Container types
    "section", "entries", "inset", "insetReadaloud", "quote",
    "variantInner",
    # Data types
    "list", "table", "tableGroup",
    # Inline/leaf types
    "item", "itemSub", "cell", "cellHeader", "row",
    "image", "gallery", "statblock", "statblockInline",
    "spellcasting", "flowchart", "flowBlock",
    # Structural
    "hr", "inline", "inlineBlock",
    # Href/grid types (nested inside image objects)
    "internal", "external", "square", "none",
    "hexColsOdd", "hexColsEven", "hexRowsOdd", "hexRowsEven",
}

# Tags recognised by the 5etools renderer (from validate_tags.py / render.js)
KNOWN_TAGS = {
    "5etools", "5etoolsImg", "ability", "actResponse", "actSave",
    "actSaveFail", "actSaveFailBy", "actSaveSuccess", "actSaveSuccessOrFail",
    "actTrigger", "action", "adventure", "area", "atk", "atkr",
    "autodice", "b", "background", "bold", "book", "boon", "card",
    "chance", "charoption", "cite", "class", "classFeature", "code",
    "coinflip", "color", "comic", "comicH1", "comicH2", "comicH3",
    "comicH4", "comicNote", "condition", "creature", "creatureFluff",
    "cult", "d20", "damage", "dc", "dcYourSpellSave", "deck", "deity",
    "dice", "disease", "facility", "feat", "filter", "font", "footnote",
    "h", "hazard", "help", "highlight", "hit", "hitYourSpellAttack",
    "hom", "homebrew", "i", "initiative", "italic", "item",
    "itemMastery", "itemProperty", "kbd", "language", "legroup", "link",
    "loader", "m", "note", "object", "optfeature", "psionic",
    "quickref", "race", "raceFluff", "recharge", "recipe", "reward",
    "s", "s2", "savingThrow", "scaledamage", "scaledice", "sense",
    "skill", "skillCheck", "spell", "status", "strike", "strikeDouble",
    "style", "sub", "subclass", "subclassFeature", "sup", "table",
    "tip", "trap", "u", "u2", "underline", "underlineDouble", "unit",
    "variantrule", "vehicle", "vehupgrade",
}

TAG_RE = re.compile(r"\{@(\w+)([^}]*)\}")


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

class ValidationResult:
    """Collects errors (must fix) and warnings (should review)."""

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        parts = []
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s)")
        return ", ".join(parts) if parts else "OK"


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------

def validate(data: Any, *, filename: str = "") -> ValidationResult:
    """Validate a parsed adventure JSON object. Returns ValidationResult."""
    r = ValidationResult()
    prefix = f"{filename}: " if filename else ""

    if not isinstance(data, dict):
        r.error(f"{prefix}Top level must be a JSON object")
        return r

    # Determine format
    if "data" in data and "adventure" not in data:
        # Official format: {"data": [...]}
        entries = data["data"]
        _validate_data_array(r, entries, prefix, strict_top_level=False)
    elif "adventure" in data and "adventureData" in data:
        # Homebrew format
        _validate_homebrew(r, data, prefix)
    elif "book" in data and "bookData" in data:
        # Book homebrew format
        _validate_homebrew(r, data, prefix, book=True)
    else:
        r.error(f"{prefix}Unrecognised top-level structure. Expected 'data' (official), "
                "'adventure'+'adventureData' (homebrew), or 'book'+'bookData'")
        return r

    return r


def _validate_homebrew(r: ValidationResult, data: dict, prefix: str, *, book: bool = False) -> None:
    """Validate homebrew adventure/book format."""
    idx_key = "book" if book else "adventure"
    data_key = "bookData" if book else "adventureData"

    # _meta
    meta = data.get("_meta")
    if meta is None:
        r.warn(f"{prefix}Missing _meta section")
    elif not isinstance(meta, dict):
        r.error(f"{prefix}_meta must be an object")
    else:
        sources = meta.get("sources", [])
        if not sources:
            r.warn(f"{prefix}_meta.sources is empty")
        for i, src in enumerate(sources):
            if not isinstance(src, dict):
                r.error(f"{prefix}_meta.sources[{i}] must be an object")
            elif not src.get("json"):
                r.error(f"{prefix}_meta.sources[{i}].json is required")

    # Index array
    idx_arr = data.get(idx_key)
    if not isinstance(idx_arr, list) or len(idx_arr) == 0:
        r.error(f"{prefix}{idx_key} must be a non-empty array")
        return

    adv = idx_arr[0]
    if not isinstance(adv, dict):
        r.error(f"{prefix}{idx_key}[0] must be an object")
        return

    if not adv.get("name"):
        r.warn(f"{prefix}{idx_key}[0].name is missing")
    if not adv.get("id"):
        r.warn(f"{prefix}{idx_key}[0].id is missing")

    contents = adv.get("contents", [])

    # Data array
    data_arr = data.get(data_key)
    if not isinstance(data_arr, list) or len(data_arr) == 0:
        r.error(f"{prefix}{data_key} must be a non-empty array")
        return

    adv_data = data_arr[0]
    if not isinstance(adv_data, dict):
        r.error(f"{prefix}{data_key}[0] must be an object")
        return

    entries = adv_data.get("data", [])

    # Contents/data alignment
    _validate_contents_alignment(r, contents, entries, prefix)

    # Validate data entries
    _validate_data_array(r, entries, prefix)


def _validate_contents_alignment(r: ValidationResult, contents: list, entries: list, prefix: str) -> None:
    """Check that contents[] and data[] are aligned."""
    section_count = sum(1 for e in entries if isinstance(e, dict) and e.get("type") == "section")

    if len(contents) != section_count:
        r.warn(f"{prefix}contents has {len(contents)} entries but data has {section_count} sections")

    for i, entry in enumerate(entries):
        if isinstance(entry, dict) and entry.get("type") != "section":
            r.error(f"{prefix}data[{i}] is type '{entry.get('type')}', must be 'section' "
                    "(non-section top-level entries break TOC/data index alignment)")

    # Check names match
    section_idx = 0
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict) or entry.get("type") != "section":
            continue
        if section_idx < len(contents):
            toc_name = contents[section_idx].get("name", "")
            data_name = entry.get("name", "")
            if toc_name and data_name and toc_name != data_name:
                r.warn(f"{prefix}contents[{section_idx}].name '{toc_name}' != data[{i}].name '{data_name}'")
        section_idx += 1


def _validate_data_array(r: ValidationResult, entries: list, prefix: str,
                         *, strict_top_level: bool = True) -> None:
    """Validate the data[] array of entries.

    strict_top_level: if True (homebrew), non-section top-level entries are errors
    (they break TOC/data alignment). If False (official), they are warnings.
    """
    if not isinstance(entries, list):
        r.error(f"{prefix}data must be an array")
        return

    if len(entries) == 0:
        r.warn(f"{prefix}data is empty")
        return

    # Check top-level entries are sections
    report = r.error if strict_top_level else r.warn
    for i, entry in enumerate(entries):
        if isinstance(entry, str):
            report(f"{prefix}data[{i}] is a bare string (must be wrapped in a section)")
        elif isinstance(entry, dict) and entry.get("type") != "section":
            report(f"{prefix}data[{i}] is type '{entry.get('type')}', expected 'section'")

    # Walk all entries
    ids_seen: dict[str, str] = {}
    _walk_entries(r, entries, "data", prefix, ids_seen)


def _walk_entries(r: ValidationResult, entries: list, path: str, prefix: str,
                  ids_seen: dict[str, str]) -> None:
    """Recursively validate all entries."""
    for i, entry in enumerate(entries):
        entry_path = f"{path}[{i}]"
        if isinstance(entry, str):
            _check_tags_in_string(r, entry, entry_path, prefix)
        elif isinstance(entry, dict):
            _validate_entry(r, entry, entry_path, prefix, ids_seen)
        elif entry is None:
            r.error(f"{prefix}{entry_path}: null entry")
        elif not isinstance(entry, (int, float, bool)):
            r.warn(f"{prefix}{entry_path}: unexpected type {type(entry).__name__}")


def _validate_entry(r: ValidationResult, entry: dict, path: str, prefix: str,
                    ids_seen: dict[str, str]) -> None:
    """Validate a single entry object."""
    etype = entry.get("type")

    # Type check
    if etype is None:
        r.warn(f"{prefix}{path}: entry has no 'type' field")
    elif etype not in VALID_ENTRY_TYPES:
        r.warn(f"{prefix}{path}: unknown entry type '{etype}'")

    # ID uniqueness (skip mapParent duplicates which are normal)
    eid = entry.get("id")
    if eid is not None:
        if not isinstance(eid, str):
            r.error(f"{prefix}{path}: id must be a string, got {type(eid).__name__}")
        elif "mapParent" not in path:
            if eid in ids_seen:
                r.warn(f"{prefix}{path}: duplicate id '{eid}' (first at {ids_seen[eid]})")
            ids_seen[eid] = path

    # Type-specific validation
    if etype == "table":
        _validate_table(r, entry, path, prefix)
    elif etype == "list":
        _validate_list(r, entry, path, prefix, ids_seen)
    elif etype == "image":
        _validate_image(r, entry, path, prefix)
    elif etype in ("section", "entries", "inset", "insetReadaloud", "quote", "variantInner"):
        if etype in ("section", "entries") and not entry.get("name"):
            r.warn(f"{prefix}{path}: {etype} has no name")
        sub = entry.get("entries", [])
        if not isinstance(sub, list):
            r.error(f"{prefix}{path}.entries must be an array")
        else:
            _walk_entries(r, sub, f"{path}.entries", prefix, ids_seen)

    # Check all string fields for tags
    for key in ("name", "caption", "by", "from"):
        val = entry.get(key)
        if isinstance(val, str):
            _check_tags_in_string(r, val, f"{path}.{key}", prefix)

    # Recurse into known child arrays (skip "rows" — handled by _validate_table)
    for key in ("entries", "items", "images", "tables",
                "headerEntries", "footerEntries"):
        val = entry.get(key)
        if isinstance(val, list):
            if key != "entries":  # entries already handled above for section/entries types
                _walk_entries(r, val, f"{path}.{key}", prefix, ids_seen)
            elif etype not in ("section", "entries", "inset", "insetReadaloud",
                               "quote", "variantInner"):
                _walk_entries(r, val, f"{path}.{key}", prefix, ids_seen)


def _validate_table(r: ValidationResult, entry: dict, path: str, prefix: str) -> None:
    """Validate a table entry."""
    col_labels = entry.get("colLabels", [])
    rows = entry.get("rows", [])

    if not isinstance(col_labels, list):
        r.error(f"{prefix}{path}.colLabels must be an array")
        return
    if not isinstance(rows, list):
        r.error(f"{prefix}{path}.rows must be an array")
        return

    if len(col_labels) == 0 and len(rows) > 0:
        r.warn(f"{prefix}{path}: table has rows but no colLabels")

    for ri, row in enumerate(rows):
        if isinstance(row, list):
            for ci, cell in enumerate(row):
                if isinstance(cell, str):
                    _check_tags_in_string(r, cell, f"{path}.rows[{ri}][{ci}]", prefix)
        elif isinstance(row, dict):
            pass  # Row objects (e.g. with "type": "row") are valid
        else:
            r.warn(f"{prefix}{path}.rows[{ri}]: unexpected type {type(row).__name__}")


def _validate_list(r: ValidationResult, entry: dict, path: str, prefix: str,
                   ids_seen: dict[str, str]) -> None:
    """Validate a list entry."""
    items = entry.get("items", [])
    if not isinstance(items, list):
        r.error(f"{prefix}{path}.items must be an array")
        return

    for i, item in enumerate(items):
        item_path = f"{path}.items[{i}]"
        if isinstance(item, str):
            _check_tags_in_string(r, item, item_path, prefix)
        elif isinstance(item, dict):
            itype = item.get("type")
            if itype == "item":
                name = item.get("name")
                if name and isinstance(name, str):
                    _check_tags_in_string(r, name, f"{item_path}.name", prefix)
                entry_val = item.get("entry")
                if entry_val and isinstance(entry_val, str):
                    _check_tags_in_string(r, entry_val, f"{item_path}.entry", prefix)
                entries = item.get("entries")
                if isinstance(entries, list):
                    _walk_entries(r, entries, f"{item_path}.entries", prefix, ids_seen)
            else:
                _validate_entry(r, item, item_path, prefix, ids_seen)


def _validate_image(r: ValidationResult, entry: dict, path: str, prefix: str) -> None:
    """Validate an image entry."""
    href = entry.get("href")
    if href is None:
        r.error(f"{prefix}{path}: image has no href")
    elif isinstance(href, dict):
        if not href.get("path") and not href.get("url"):
            r.warn(f"{prefix}{path}: image href has no path or url")


def _check_tags_in_string(r: ValidationResult, text: str, path: str, prefix: str) -> None:
    """Check all {@tag} references in a string."""
    for m in TAG_RE.finditer(text):
        tag = m.group(1)
        if tag not in KNOWN_TAGS:
            r.error(f"{prefix}{path}: unknown tag '{{@{tag}}}' in: ...{m.group(0)}...")

    # Check for unbalanced braces (common LLM error)
    depth = 0
    for ch in text:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                r.warn(f"{prefix}{path}: unbalanced closing brace")
                break
    if depth > 0:
        r.warn(f"{prefix}{path}: unbalanced opening brace ({depth} unclosed)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Validate 5etools adventure JSON")
    parser.add_argument("files", nargs="*", type=Path, help="JSON files to validate")
    parser.add_argument("--official-dir", type=Path, default=None,
                        help="Validate all JSON files in an official adventure directory")
    args = parser.parse_args()

    files = list(args.files or [])
    if args.official_dir:
        files.extend(sorted(args.official_dir.glob("*.json")))

    if not files:
        parser.error("No files specified")

    total_errors = 0
    total_warnings = 0

    for fpath in files:
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"FAIL {fpath}: {e}")
            total_errors += 1
            continue

        result = validate(data, filename=fpath.name)

        status = "OK" if result.ok else "FAIL"
        print(f"{status} {fpath}: {result.summary()}")

        for msg in result.errors:
            print(f"  ERROR: {msg}")
        for msg in result.warnings:
            print(f"  WARN:  {msg}")

        total_errors += len(result.errors)
        total_warnings += len(result.warnings)

    print(f"\nTotal: {len(files)} file(s), {total_errors} error(s), {total_warnings} warning(s)")
    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    main()
