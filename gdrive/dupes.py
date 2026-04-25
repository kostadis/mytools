"""Find files with very similar names in a Drive JSONL dump.

Normalizes names (strips "Copy of", trailing "(1)", etc.) and groups
files that collapse to the same key. Reconstructs folder paths from
parent IDs so directories can be excluded.

Usage:
    python dupes.py drive.jsonl
    python dupes.py drive.jsonl --exclude DriveThru kickstarter
    python dupes.py drive.jsonl --exclude DriveThru kickstarter --min-group 3
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys


def load_jsonl(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def build_path_lookup(entries: list[dict]) -> dict[str, str]:
    """Map file/folder ID → full path string."""
    folders: dict[str, dict] = {}
    for e in entries:
        if e.get("mimeType") == "application/vnd.google-apps.folder":
            folders[e["id"]] = e

    cache: dict[str, str] = {}

    def resolve(fid: str) -> str:
        if fid in cache:
            return cache[fid]
        folder = folders.get(fid)
        if not folder:
            cache[fid] = ""
            return ""
        parents = folder.get("parents", [])
        if parents:
            parent_path = resolve(parents[0])
            path = os.path.join(parent_path, folder["name"]) if parent_path else folder["name"]
        else:
            path = folder["name"]
        cache[fid] = path
        return path

    for fid in folders:
        resolve(fid)
    return cache


def file_path(entry: dict, path_lookup: dict[str, str]) -> str:
    parents = entry.get("parents", [])
    if parents:
        parent_path = path_lookup.get(parents[0], "")
        return os.path.join(parent_path, entry["name"]) if parent_path else entry["name"]
    return entry["name"]


def normalize(name: str) -> str:
    """Collapse similar names to a canonical key."""
    n = name.lower()
    root, ext = os.path.splitext(n)
    root = re.sub(r"^copy of\s+", "", root)
    root = re.sub(r"\s*\(\d+\)$", "", root)
    root = re.sub(r"\s*-\s*copy$", "", root)
    root = re.sub(r"\s+", " ", root).strip()
    return root + ext


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("jsonl", help="path to drive.jsonl")
    p.add_argument("--exclude", nargs="+", default=[], help="directory names to exclude (case-insensitive substring match on path)")
    p.add_argument("--min-group", type=int, default=2, help="minimum group size to report (default: 2)")
    args = p.parse_args()

    entries = load_jsonl(args.jsonl)
    path_lookup = build_path_lookup(entries)
    exclude_lower = [x.lower() for x in args.exclude]

    files: list[tuple[str, str, dict]] = []
    for e in entries:
        if e.get("mimeType") == "application/vnd.google-apps.folder":
            continue
        fp = file_path(e, path_lookup)
        if any(ex in fp.lower() for ex in exclude_lower):
            continue
        files.append((fp, normalize(e["name"]), e))

    groups: dict[str, list[tuple[str, dict]]] = {}
    for fp, key, entry in files:
        groups.setdefault(key, []).append((fp, entry))

    dupes = {k: v for k, v in groups.items() if len(v) >= args.min_group}
    by_size = sorted(dupes.items(), key=lambda kv: -len(kv[1]))

    print(f"{len(dupes)} groups with {args.min_group}+ similar files\n", file=sys.stderr)

    for key, members in by_size:
        print(f"--- {key} ({len(members)} files) ---")
        for fp, entry in sorted(members, key=lambda x: x[0]):
            size = entry.get("size")
            size_str = f"{int(size) / 1e6:.1f}MB" if size else "native"
            modified = entry.get("modifiedTime", "")[:10]
            print(f"  {modified}  {size_str:>10}  {fp}")
        print()


if __name__ == "__main__":
    main()
