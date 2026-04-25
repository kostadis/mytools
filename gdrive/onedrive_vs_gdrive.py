"""Report OneDrive files under a given path that have no counterpart on Google Drive.

Matches by (name, size) — case-insensitive name, exact byte size. Folders
are ignored. Google Docs/Sheets/Slides on the Drive side have no real byte
size and are excluded from the match set.

Summary mode (default) aggregates unmatched files by OneDrive subfolder.
--list emits individual unmatched files, largest first.

Usage:
    python onedrive_vs_gdrive.py --under "/Dungeons and Dragons"
    python onedrive_vs_gdrive.py --under "/Dungeons and Dragons" --depth 2
    python onedrive_vs_gdrive.py --under "/Dungeons and Dragons" --list --limit 50
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from collections import defaultdict

GRAPH_PATH_PREFIX = "/drive/root:"
GOOGLE_APPS_PREFIX = "application/vnd.google-apps."


def full_path(rec: dict) -> str:
    parent = rec.get("parentPath", "")
    if parent.startswith(GRAPH_PATH_PREFIX):
        parent = parent[len(GRAPH_PATH_PREFIX):]
    parent = urllib.parse.unquote(parent)
    name = rec.get("name", "")
    return f"{parent}/{name}" if parent else f"/{name}"


def load_gdrive_keys(path: str) -> set[tuple[str, int]]:
    """Set of (name_lower, size) for every non-folder, non-native-Google file on Drive."""
    keys: set[tuple[str, int]] = set()
    with open(path) as f:
        for line in f:
            rec = json.loads(line)
            mt = rec.get("mimeType", "")
            if mt.startswith(GOOGLE_APPS_PREFIX):
                continue
            try:
                size = int(rec.get("size", 0) or 0)
            except (TypeError, ValueError):
                size = 0
            name = rec.get("name", "").lower()
            keys.add((name, size))
    return keys


def human_bytes(n: float) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}PB"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--under", required=True,
                   help="OneDrive path to inspect, e.g. '/Dungeons and Dragons'")
    p.add_argument("--onedrive", default="onedrive.jsonl")
    p.add_argument("--gdrive", default="drive.jsonl")
    p.add_argument("--depth", type=int, default=1,
                   help="rollup depth for the summary (default 1)")
    p.add_argument("--list", action="store_true",
                   help="print unmatched files individually, largest first")
    p.add_argument("--limit", type=int, default=None,
                   help="cap --list output to N rows")
    args = p.parse_args()

    print(f"loading Google Drive keys from {args.gdrive} …", file=sys.stderr)
    gdrive = load_gdrive_keys(args.gdrive)
    print(f"  {len(gdrive):,} (name,size) keys", file=sys.stderr)

    under = args.under.rstrip("/")
    under_parts = [p for p in under.split("/") if p]

    unmatched: list[tuple[str, str, int]] = []
    matched = 0
    scanned = 0

    with open(args.onedrive) as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("mimeType") == "folder":
                continue
            path = full_path(rec)
            parts = [p for p in path.split("/") if p]
            if parts[: len(under_parts)] != under_parts:
                continue
            scanned += 1
            size = int(rec.get("size", 0) or 0)
            name = rec.get("name", "")
            if (name.lower(), size) in gdrive:
                matched += 1
            else:
                unmatched.append((path, name, size))

    unmatched_bytes = sum(s for _, _, s in unmatched)

    print(f"\nscope:     {under}", file=sys.stderr)
    print(f"scanned:   {scanned:,} files under scope", file=sys.stderr)
    print(f"matched:   {matched:,} also on Google Drive", file=sys.stderr)
    print(
        f"unmatched: {len(unmatched):,} "
        f"({human_bytes(unmatched_bytes)}) OneDrive-only",
        file=sys.stderr,
    )

    if args.list:
        rows = sorted(unmatched, key=lambda r: r[2], reverse=True)
        if args.limit:
            rows = rows[: args.limit]
        print()
        for path, _name, size in rows:
            print(f"{human_bytes(size):>10}  {path}")
        return

    buckets: dict[str, dict] = defaultdict(lambda: {"files": 0, "bytes": 0})
    for path, _name, size in unmatched:
        parts = [p for p in path.split("/") if p]
        rel = parts[len(under_parts):]
        container = rel[:-1]
        taken = container[: args.depth]
        key = under + ("/" + "/".join(taken) if taken else "")
        b = buckets[key]
        b["files"] += 1
        b["bytes"] += size

    ordered = sorted(buckets.items(), key=lambda kv: kv[1]["bytes"], reverse=True)

    path_w = max(40, min(80, max((len(k) for k, _ in ordered), default=40)))
    header = f"{'Path':<{path_w}} {'Unmatched':>11} {'Size':>12}"
    print()
    print(header)
    print("-" * len(header))
    for key, b in ordered:
        disp = key if len(key) <= path_w else "…" + key[-(path_w - 1):]
        print(f"{disp:<{path_w}} {b['files']:>11,} {human_bytes(b['bytes']):>12}")
    print("-" * len(header))
    print(
        f"{'TOTAL':<{path_w}} {len(unmatched):>11,} "
        f"{human_bytes(unmatched_bytes):>12}"
    )


if __name__ == "__main__":
    main()
