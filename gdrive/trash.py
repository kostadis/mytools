"""Trash Drive files by ID. Moves to Drive trash (recoverable for 30 days).

Dry-run is the default — pass --execute to actually trash.

Usage:
    python trash.py FILE_ID [FILE_ID ...]
    python trash.py --execute FILE_ID [FILE_ID ...]
"""
from __future__ import annotations

import argparse
import sys

from auth import WRITE_SCOPES, drive_service


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("file_ids", nargs="+", metavar="FILE_ID")
    p.add_argument("--execute", action="store_true", help="actually trash (default is dry-run)")
    args = p.parse_args()

    svc = drive_service(scopes=WRITE_SCOPES)

    for fid in args.file_ids:
        try:
            meta = svc.files().get(fileId=fid, fields="id,name,size,trashed").execute()
        except Exception as e:
            print(f"ERROR {fid}: {e}", file=sys.stderr)
            continue

        name = meta.get("name", "?")
        size = int(meta.get("size", 0))
        if meta.get("trashed"):
            print(f"SKIP (already trashed)  {size / 1e6:.1f} MB  {name}")
            continue

        if not args.execute:
            print(f"DRY-RUN would trash     {size / 1e6:.1f} MB  {name}")
            continue

        try:
            svc.files().update(fileId=fid, body={"trashed": True}).execute()
            print(f"TRASHED                 {size / 1e6:.1f} MB  {name}")
        except Exception as e:
            print(f"ERROR trashing {name}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
