"""Move Drive files into a folder by ID, or create a folder path first.

Dry-run is the default — pass --execute to actually move.

Usage:
    python move.py --to FOLDER_ID FILE_ID [FILE_ID ...]
    python move.py --to RPG/Maps --create-folder FILE_ID [FILE_ID ...]
    python move.py --to FOLDER_ID --execute FILE_ID [FILE_ID ...]
"""
from __future__ import annotations

import argparse
import sys

from auth import WRITE_SCOPES, drive_service

FOLDER_MIME = "application/vnd.google-apps.folder"


def ensure_folder_path(svc, path: str, execute: bool) -> str | None:
    """Create nested folders from a slash-separated path. Returns leaf folder ID."""
    parts = [p for p in path.split("/") if p]
    parent_id = "root"
    for part in parts:
        query = (
            f"name = '{part}' and '{parent_id}' in parents "
            f"and mimeType = '{FOLDER_MIME}' and trashed = false"
        )
        resp = svc.files().list(q=query, fields="files(id,name)", pageSize=1).execute()
        existing = resp.get("files", [])
        if existing:
            parent_id = existing[0]["id"]
            print(f"FOLDER EXISTS  {part}/ (id: {parent_id})", file=sys.stderr)
        elif execute:
            body = {"name": part, "mimeType": FOLDER_MIME, "parents": [parent_id]}
            folder = svc.files().create(body=body, fields="id").execute()
            parent_id = folder["id"]
            print(f"FOLDER CREATED {part}/ (id: {parent_id})", file=sys.stderr)
        else:
            print(f"DRY-RUN would create folder {part}/ under {parent_id}", file=sys.stderr)
            return None
    return parent_id


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--to", required=True, help="destination folder ID, or path with --create-folder")
    p.add_argument("--create-folder", action="store_true", help="treat --to as a slash-separated path and create folders")
    p.add_argument("--execute", action="store_true", help="actually move (default is dry-run)")
    p.add_argument("file_ids", nargs="+", metavar="FILE_ID")
    args = p.parse_args()

    svc = drive_service(scopes=WRITE_SCOPES)

    if args.create_folder:
        dest_id = ensure_folder_path(svc, args.to, args.execute)
        if dest_id is None:
            print(f"\nDRY-RUN: would move {len(args.file_ids)} files into {args.to}/", file=sys.stderr)
            for fid in args.file_ids:
                try:
                    meta = svc.files().get(fileId=fid, fields="name,size").execute()
                    size = int(meta.get("size", 0))
                    print(f"  DRY-RUN would move  {size / 1e6:>8.1f} MB  {meta['name']}")
                except Exception as e:
                    print(f"  ERROR {fid}: {e}", file=sys.stderr)
            return
    else:
        dest_id = args.to

    root_id = svc.files().get(fileId="root", fields="id").execute()["id"]

    for fid in args.file_ids:
        try:
            meta = svc.files().get(
                fileId=fid,
                fields="id,name,size,parents,ownedByMe,capabilities",
                supportsAllDrives=True,
            ).execute()
        except Exception as e:
            print(f"ERROR {fid}: {e}", file=sys.stderr)
            continue

        name = meta.get("name", "?")
        size = int(meta.get("size", 0))
        owned = meta.get("ownedByMe", True)
        caps = meta.get("capabilities", {})
        current_parents = meta.get("parents", [])
        remove = ",".join(current_parents) if current_parents else root_id

        can_move = caps.get("canMoveItemWithinDrive", owned)
        need_copy = not can_move and caps.get("canCopy", False)

        if not args.execute:
            method = "copy+remove" if need_copy else "move"
            print(f"DRY-RUN would {method:12}  {size / 1e6:>8.1f} MB  {name}")
            continue

        if need_copy:
            try:
                copied = svc.files().copy(
                    fileId=fid,
                    body={"name": name, "parents": [dest_id]},
                    fields="id",
                ).execute()
                print(f"COPIED          {size / 1e6:>8.1f} MB  {name}  (new id: {copied['id']})")
                svc.files().update(
                    fileId=fid,
                    removeParents=remove,
                    fields="id",
                ).execute()
                print(f"REMOVED ORIGINAL from Drive view: {name}")
            except Exception as e:
                print(f"ERROR copy+remove {name}: {e}", file=sys.stderr)
        else:
            try:
                svc.files().update(
                    fileId=fid,
                    addParents=dest_id,
                    removeParents=remove,
                    fields="id,parents",
                ).execute()
                print(f"MOVED           {size / 1e6:>8.1f} MB  {name}")
            except Exception as e:
                print(f"ERROR moving {name}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
