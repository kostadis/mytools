"""Move a OneDrive item to the recycle bin.

Dry-run by default; pass --execute to actually delete. Matches the pattern
of the Google trash.py sibling.

Usage:
    python onedrive_trash.py --path "/ODocuments/Virtual Machines/Windows 11 Work/Windows 11 Work.vmdk"
    python onedrive_trash.py --path "..." --execute
    python onedrive_trash.py --id 01ABCDEF --execute
"""
from __future__ import annotations

import argparse
import sys
import urllib.parse

import requests

from onedrive_auth import WRITE_SCOPES, get_token, graph_get

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def resolve_path(path: str, token: str) -> dict:
    """Fetch current metadata for a drive item by path."""
    clean = path.lstrip("/")
    encoded = urllib.parse.quote(clean, safe="/")
    url = f"{GRAPH_BASE}/me/drive/root:/{encoded}"
    resp = graph_get(url, token)
    if resp.status_code == 404:
        raise SystemExit(f"not found: {path}")
    if resp.status_code != 200:
        raise SystemExit(f"Graph error {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def resolve_id(item_id: str, token: str) -> dict:
    url = f"{GRAPH_BASE}/me/drive/items/{item_id}"
    resp = graph_get(url, token)
    if resp.status_code == 404:
        raise SystemExit(f"not found: id={item_id}")
    if resp.status_code != 200:
        raise SystemExit(f"Graph error {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def human_bytes(n: float) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}PB"


def trash_item(item_id: str, token: str) -> None:
    url = f"{GRAPH_BASE}/me/drive/items/{item_id}"
    resp = requests.delete(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    if resp.status_code not in (204, 200):
        raise SystemExit(
            f"delete failed: {resp.status_code}: {resp.text[:200]}"
        )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--path", help="item path, e.g. /Foo/Bar/baz.pdf")
    group.add_argument("--id", help="item id")
    p.add_argument(
        "--execute",
        action="store_true",
        help="actually delete (default is dry-run)",
    )
    args = p.parse_args()

    token = get_token(WRITE_SCOPES)

    item = resolve_path(args.path, token) if args.path else resolve_id(args.id, token)

    size = item.get("size", 0) or 0
    parent = item.get("parentReference", {}).get("path", "")
    is_folder = "folder" in item
    child_count = item.get("folder", {}).get("childCount", 0) if is_folder else 0

    print(f"target:    {parent}/{item.get('name', '')}")
    print(f"id:        {item['id']}")
    print(f"kind:      {'folder' if is_folder else 'file'}")
    if is_folder:
        print(f"children:  {child_count:,} (all will be trashed with the folder)")
    print(f"size:      {human_bytes(size)}")
    print(f"modified:  {item.get('lastModifiedDateTime', '')}")

    if not args.execute:
        print("\ndry-run; pass --execute to move to recycle bin", file=sys.stderr)
        return

    trash_item(item["id"], token)
    print(
        "\nmoved to OneDrive recycle bin (recoverable ~30 days via web UI)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
