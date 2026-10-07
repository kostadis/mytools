#!/usr/bin/env python3
"""Append a new misspelling row to the corrections glossary.

Inserts under the section header that matches --section. If the section
doesn't exist yet, appends a new section at the end. If the canonical
already has a row, appends the new wrong-form to that row's wrong-list
rather than duplicating.

Usage:
  add_to_glossary.py \
      --glossary notes/vtt_transcription_corrections.md \
      --section "NPCs and creatures" \
      --wrong "Elvara,elvara" \
      --right "Ilvara"
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


SECTION_HEADERS = {
    "pcs": "## PCs",
    "npcs": "## NPCs and creatures",
    "items": "## Items / artifacts",
    "factions": "## Houses / factions",
    "locations": "## Locations",
    "table": "## Real-world / table",
}


def normalise_section(name: str) -> str:
    key = name.strip().lower()
    if key in SECTION_HEADERS:
        return SECTION_HEADERS[key]
    if name.startswith("##"):
        return name.strip()
    return f"## {name.strip()}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glossary", required=True, type=Path)
    ap.add_argument("--section", required=True,
                    help="Section name or shortcut (pcs/npcs/items/factions/locations/table)")
    ap.add_argument("--wrong", required=True,
                    help="Comma-separated wrong forms")
    ap.add_argument("--right", required=True,
                    help="Canonical form (will be **bolded**)")
    ap.add_argument("--note", default="",
                    help="Optional parenthetical note appended after the canonical")
    args = ap.parse_args()

    section = normalise_section(args.section)
    text = args.glossary.read_text(encoding="utf-8")
    lines = text.splitlines()

    canonical_cell = f"**{args.right}**"
    if args.note:
        canonical_cell += f" ({args.note})"

    # Find section
    sec_idx = None
    for i, line in enumerate(lines):
        if line.strip() == section:
            sec_idx = i
            break

    if sec_idx is None:
        # Append new section at end
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([
            section,
            "",
            "| Wrong | Right |",
            "|---|---|",
            f"| {args.wrong} | {canonical_cell} |",
        ])
        args.glossary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Created new section {section!r} and added row.")
        return

    # Find next section header (or EOF) to bound the table
    end_idx = len(lines)
    for j in range(sec_idx + 1, len(lines)):
        if lines[j].startswith("## "):
            end_idx = j
            break

    # Look for an existing row with same canonical (right column)
    bold_re = re.compile(r"\*\*(.+?)\*\*")
    for k in range(sec_idx, end_idx):
        line = lines[k]
        if not line.startswith("|") or line.startswith("|---") or "Wrong" in line:
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 2:
            continue
        m = bold_re.search(cols[1])
        existing_right = m.group(1).strip() if m else cols[1].strip()
        if existing_right.lower() == args.right.strip().lower():
            existing_wrongs = [w.strip() for w in cols[0].split(",") if w.strip()]
            new_wrongs = [w.strip() for w in args.wrong.split(",") if w.strip()]
            merged: list[str] = []
            seen_lc: set[str] = set()
            for w in existing_wrongs + new_wrongs:
                if w.lower() not in seen_lc:
                    merged.append(w)
                    seen_lc.add(w.lower())
            new_line = f"| {', '.join(merged)} | {cols[1]} |"
            lines[k] = new_line
            args.glossary.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"Appended {args.wrong!r} to existing row for {args.right!r}.")
            return

    # No existing row — find the last table row in the section, insert after
    last_row = sec_idx
    for k in range(sec_idx, end_idx):
        if lines[k].startswith("|") and not lines[k].startswith("|---") and "Wrong" not in lines[k]:
            last_row = k
    new_row = f"| {args.wrong} | {canonical_cell} |"
    lines.insert(last_row + 1, new_row)
    args.glossary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Added new row to section {section!r}: {new_row}")


if __name__ == "__main__":
    main()
