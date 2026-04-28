#!/usr/bin/env python3
"""
merge_patch.py — Insert sections from a partial conversion into an existing
5etools adventure/book JSON.

Workflow for missing/bad pages:

    # 1. Re-convert only the missing pages (smaller chunk to reduce drop risk):
    python3 pdf_to_5etools.py INPUT.pdf --pages 14-22 --pages-per-chunk 2 \\
        --out patch.json --debug-dir debug-patch/

    # 2. Preview what will be inserted and where:
    python3 merge_patch.py adventure.json patch.json --at 13 --dry-run

    # 3. Merge (creates a .bak backup first):
    python3 merge_patch.py adventure.json patch.json --at 13

The --at index is the data[] position BEFORE which the new sections are
inserted.  Run `python3 merge_patch.py adventure.json --list` to print the
current section list with indices so you can find the right insertion point.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fix_adventure_json import assign_ids, reset_ids


# ---------------------------------------------------------------------------

def _keys(raw: dict) -> tuple[str, str]:
    if "adventure" in raw:
        return "adventure", "adventureData"
    if "book" in raw:
        return "book", "bookData"
    sys.exit("Not a valid 5etools adventure/book JSON.")


def _load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_sections(base_path: Path) -> None:
    raw = _load(base_path)
    idx_key, data_key = _keys(raw)
    data = raw[data_key][0]["data"]
    toc  = raw[idx_key][0].get("contents", [])
    print(f"{base_path}  —  {len(data)} data sections, {len(toc)} TOC entries\n")
    for i, s in enumerate(data):
        name = s.get("name", "?") if isinstance(s, dict) else str(s)[:60]
        typ  = s.get("type", "?") if isinstance(s, dict) else "string"
        toc_name = toc[i]["name"] if i < len(toc) else "—"
        match = "✓" if toc_name == name else "✗"
        print(f"  [{i:3d}] {match} {typ:10s} {name!r}")


def merge(base_path: Path, patch_path: Path, at: int, dry_run: bool) -> None:
    raw  = _load(base_path)
    ridx, rdata = _keys(raw)
    base_data: list = raw[rdata][0]["data"]
    base_toc:  list = raw[ridx][0].get("contents", [])

    patch_raw = _load(patch_path)
    pidx, pdata = _keys(patch_raw)
    patch_data: list = patch_raw[pdata][0]["data"]
    patch_toc:  list = patch_raw[pidx][0].get("contents", [])

    if at < 0 or at > len(base_data):
        sys.exit(f"--at {at} is out of range (base has {len(base_data)} sections, "
                 f"valid range is 0–{len(base_data)}).")

    print(f"Inserting {len(patch_data)} section(s) at data[{at}]:")
    for i, s in enumerate(patch_data):
        name = s.get("name", "?") if isinstance(s, dict) else str(s)[:60]
        print(f"  +[{at + i:3d}] {name!r}")

    base_data[at:at] = patch_data
    base_toc[at:at]  = patch_toc

    # Verify alignment after merge
    mismatches = sum(
        1 for i, (t, d) in enumerate(zip(base_toc, base_data))
        if isinstance(d, dict) and t["name"] != d.get("name", "")
    )
    print(f"\nAfter merge: {len(base_data)} sections, {len(base_toc)} TOC entries"
          f"  ({mismatches} name mismatches)")
    if mismatches:
        print("  Run toc_editor.py to review and correct the TOC.")

    # Reassign IDs sequentially so they stay consistent
    reset_ids()
    assign_ids(base_data)

    if dry_run:
        print("\n(dry run — nothing written)")
        return

    bak = base_path.with_suffix(".json.bak")
    shutil.copy2(base_path, bak)
    print(f"\nBackup : {bak}")

    with open(base_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent="\t", ensure_ascii=False)
    print(f"Saved  : {base_path}")


# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge a partial conversion into an existing adventure JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("base", type=Path, help="Existing adventure JSON to patch")
    parser.add_argument("patch", type=Path, nargs="?",
                        help="Partial conversion JSON to insert")
    parser.add_argument("--at", type=int,
                        help="data[] index to insert before (use --list to find it)")
    parser.add_argument("--list", action="store_true",
                        help="Print current section list with indices, then exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would change without writing")
    args = parser.parse_args()

    if args.list:
        list_sections(args.base)
        return

    if not args.patch:
        parser.error("patch JSON is required (or use --list to inspect the base file)")
    if args.at is None:
        parser.error("--at INDEX is required")

    merge(args.base, args.patch, args.at, args.dry_run)


if __name__ == "__main__":
    main()
