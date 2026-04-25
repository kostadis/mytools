"""Folder-structure overview for a onedrive.jsonl dump.

Aggregates file counts, folder counts, byte totals, and subtree depth by
folder path, up to a configurable depth. Gives an at-a-glance map of where
the drive's mass lives before you pick a cleanup target.

Usage:
    python onedrive_folders.py onedrive.jsonl
    python onedrive_folders.py onedrive.jsonl --depth 2
    python onedrive_folders.py onedrive.jsonl --exclude DriveThru Kickstarter
    python onedrive_folders.py onedrive.jsonl --top 20
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from collections import defaultdict

GRAPH_PATH_PREFIX = "/drive/root:"


def full_path(rec: dict) -> str:
    """Reconstruct a human-readable path from a OneDrive record.

    parentPath is Graph-style and may be URL-encoded; strip the prefix and
    unquote before joining with the item's name.
    """
    parent = rec.get("parentPath", "")
    if parent.startswith(GRAPH_PATH_PREFIX):
        parent = parent[len(GRAPH_PATH_PREFIX):]
    parent = urllib.parse.unquote(parent)
    name = rec.get("name", "")
    if parent:
        return f"{parent}/{name}"
    return f"/{name}"


def bucket_for(rec: dict, path: str, depth: int) -> tuple[str, int]:
    """Return (bucket_key, bucket_key_depth) for this record.

    Folders bucket at their own path; files bucket at their container's
    path. Buckets deeper than the requested depth are clamped.
    """
    parts = [p for p in path.split("/") if p]
    is_folder = rec.get("mimeType") == "folder"
    container = parts if is_folder else parts[:-1]
    taken = container[:depth]
    key = "/" + "/".join(taken) if taken else "/"
    return key, len(taken)


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("input", help="onedrive.jsonl file")
    p.add_argument(
        "--depth",
        type=int,
        default=1,
        help="aggregation depth (1 = top-level folders, default)",
    )
    p.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        metavar="NAME",
        help="skip any item whose top-level folder matches one of these names",
    )
    p.add_argument(
        "--top",
        type=int,
        default=None,
        help="show only the N largest buckets by bytes",
    )
    p.add_argument(
        "--under",
        default=None,
        metavar="PATH",
        help="only include items under this path; depth is measured from here",
    )
    args = p.parse_args()

    under = args.under.rstrip("/") if args.under else None
    under_parts = [p for p in under.split("/") if p] if under else []

    buckets: dict[str, dict] = defaultdict(
        lambda: {"files": 0, "folders": 0, "bytes": 0, "max_depth": 0}
    )
    total_files = 0
    total_folders = 0
    total_bytes = 0
    skipped = 0

    with open(args.input) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            path = full_path(rec)
            parts = [p for p in path.split("/") if p]

            if parts and parts[0] in args.exclude:
                skipped += 1
                continue

            if under_parts:
                if parts[: len(under_parts)] != under_parts:
                    continue
                # Re-scope: remove the prefix so depth is measured from `under`.
                rel_parts = parts[len(under_parts):]
                rel_path = "/" + "/".join(rel_parts) if rel_parts else "/"
                key, key_depth = bucket_for(rec, rel_path, args.depth)
                key = under + key if key != "/" else under
            else:
                key, key_depth = bucket_for(rec, path, args.depth)
            b = buckets[key]
            is_folder = rec.get("mimeType") == "folder"
            if is_folder:
                b["folders"] += 1
                total_folders += 1
            else:
                b["files"] += 1
                total_files += 1
                size = rec.get("size", 0) or 0
                b["bytes"] += size
                total_bytes += size
            depth_below = max(0, len(parts) - key_depth)
            if depth_below > b["max_depth"]:
                b["max_depth"] = depth_below

    ordered = sorted(buckets.items(), key=lambda kv: kv[1]["bytes"], reverse=True)
    if args.top:
        ordered = ordered[: args.top]

    path_w = max(40, min(70, max((len(k) for k, _ in ordered), default=40)))
    header = (
        f"{'Path':<{path_w}} {'Files':>10} {'Folders':>10} "
        f"{'Size':>12} {'Depth':>6}"
    )
    print(header)
    print("-" * len(header))
    for key, b in ordered:
        disp = key if len(key) <= path_w else "…" + key[-(path_w - 1):]
        print(
            f"{disp:<{path_w}} {b['files']:>10,} {b['folders']:>10,} "
            f"{human_bytes(b['bytes']):>12} {b['max_depth']:>6}"
        )
    print("-" * len(header))
    print(
        f"{'TOTAL':<{path_w}} {total_files:>10,} {total_folders:>10,} "
        f"{human_bytes(total_bytes):>12}"
    )
    if skipped:
        print(f"(skipped {skipped:,} records via --exclude)", file=sys.stderr)


if __name__ == "__main__":
    main()
