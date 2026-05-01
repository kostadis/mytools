#!/usr/bin/env python3
"""Backfill `source_extracts:` frontmatter on every NPC dossier.

After a sidecar merge, every dossier in <npc_dir> has absorbed all the
content that exists for it across the current extract set. Recording that
fact in the dossier's frontmatter will let a future planning.py change skip
re-sidecaring extracts that are already in the canonical.

Usage:
    python backfill_source_extracts.py <npc_dir> <extract_dir>
    python backfill_source_extracts.py <npc_dir> <extract_dir> --dry-run

What it writes:
    source_extracts: [1, 2, 3, ..., 38]   # union over the extract dir

Conservative: it overclaims (assigns the full extract range to every
dossier) rather than computing per-NPC presence. Safe because (a) any
extract that mentions an NPC already contributed to the canonical, and
(b) extracts are deterministic — re-running --build-dossiers won't
discover new facts within the same extract set.

Skips sidecars (`.new_notes.NNN.md`) and anything in subdirectories.
"""
import argparse
import re
import sys
from pathlib import Path

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n+(.*)\Z", re.DOTALL)
SIDECAR_RE = re.compile(r"^.+\.new_notes\.\d+\.md$")
EXTRACT_RE = re.compile(r"dossier_extract_(\d+)\.md$")


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return ({line: line, ...}, body) preserving frontmatter line order via dict insertion."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_lines = m.group(1).splitlines()
    body = m.group(2)
    return fm_lines, body


def write_frontmatter(fm_lines: list[str], body: str) -> str:
    return "---\n" + "\n".join(fm_lines) + "\n---\n\n" + body.lstrip()


def upsert_source_extracts(fm_lines: list[str], extract_nums: list[int]) -> list[str]:
    """Add or replace the source_extracts: line. Place after aliases: block if present, else after name:."""
    nums_str = "[" + ", ".join(str(n) for n in extract_nums) + "]"
    new_line = f"source_extracts: {nums_str}"

    # Find any existing source_extracts line (could be flow or block style — replace whole-line for flow)
    existing_idx = next((i for i, ln in enumerate(fm_lines)
                         if re.match(r"^source_extracts:", ln)), None)
    if existing_idx is not None:
        fm_lines[existing_idx] = new_line
        return fm_lines

    # Insert after the aliases: block (whether flow `aliases: []` or block `aliases:\n  - ...`)
    insert_at = len(fm_lines)
    for i, ln in enumerate(fm_lines):
        if re.match(r"^aliases:\s*\[", ln):
            insert_at = i + 1
            break
        if re.match(r"^aliases:\s*$", ln):
            j = i + 1
            while j < len(fm_lines) and (fm_lines[j].startswith("  -") or fm_lines[j].startswith(" -")):
                j += 1
            insert_at = j
            break
    else:
        # No aliases — try to insert after name:
        for i, ln in enumerate(fm_lines):
            if re.match(r"^name:", ln):
                insert_at = i + 1
                break

    fm_lines.insert(insert_at, new_line)
    return fm_lines


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("npc_dir", type=Path)
    ap.add_argument("extract_dir", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.npc_dir.is_dir():
        sys.exit(f"Not a directory: {args.npc_dir}")
    if not args.extract_dir.is_dir():
        sys.exit(f"Not a directory: {args.extract_dir}")

    extract_nums = sorted({int(m.group(1))
                           for p in args.extract_dir.glob("dossier_extract_*.md")
                           if (m := EXTRACT_RE.search(p.name))})
    if not extract_nums:
        sys.exit(f"No dossier_extract_*.md files in {args.extract_dir}")
    print(f"Extract numbers found: {extract_nums[0]}..{extract_nums[-1]} ({len(extract_nums)} files)")

    dossiers = [p for p in args.npc_dir.glob("*.md") if not SIDECAR_RE.match(p.name)]
    print(f"Dossiers to update: {len(dossiers)}")

    n_added = n_updated = n_no_fm = 0
    for p in dossiers:
        text = p.read_text()
        m = FRONTMATTER_RE.match(text)
        if not m:
            n_no_fm += 1
            print(f"  ⚠  no frontmatter: {p.name} — adding")
            fm_lines = [f"name: {p.stem}", "aliases: []"]
            body = text
        else:
            fm_lines = m.group(1).splitlines()
            body = m.group(2)

        already = any(re.match(r"^source_extracts:", ln) for ln in fm_lines)
        fm_lines = upsert_source_extracts(fm_lines, extract_nums)
        new_text = write_frontmatter(fm_lines, body)

        if new_text == text:
            continue

        if already:
            n_updated += 1
        else:
            n_added += 1

        if not args.dry_run:
            p.write_text(new_text)

    print(f"\nAdded source_extracts to:   {n_added} dossier(s)")
    print(f"Updated existing line on:   {n_updated} dossier(s)")
    print(f"Created frontmatter on:     {n_no_fm} dossier(s)")
    if args.dry_run:
        print("(dry-run — no files written)")


if __name__ == "__main__":
    main()
