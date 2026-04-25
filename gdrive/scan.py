"""Walk Drive metadata and emit one JSONL line per file.

JSONL is the interface: downstream tools (dedup, staleness, oversharing
reports) consume this file rather than re-hitting the API.

Usage:
    python scan.py --out drive.jsonl
    python scan.py --out drive.jsonl --all-drives
    python scan.py --out drive.jsonl --include-trashed
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from auth import drive_service

FIELDS = ",".join([
    "id",
    "name",
    "mimeType",
    "parents",
    "owners(displayName,emailAddress)",
    "ownedByMe",
    "size",
    "quotaBytesUsed",
    "createdTime",
    "modifiedTime",
    "viewedByMeTime",
    "sharedWithMeTime",
    "shared",
    "trashed",
    "webViewLink",
    "md5Checksum",
    "driveId",
    "permissions(emailAddress,role,type,domain)",
])


def scan(out, include_trashed: bool, all_drives: bool) -> None:
    svc = drive_service()
    kwargs: dict = {
        "q": None if include_trashed else "trashed=false",
        "fields": f"nextPageToken,files({FIELDS})",
        "pageSize": 1000,
        "orderBy": "createdTime",
    }
    if all_drives:
        kwargs.update(
            corpora="allDrives",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        )
    token = None
    total = 0
    pages = 0
    t0 = time.time()
    while True:
        if token:
            kwargs["pageToken"] = token
        resp = svc.files().list(**kwargs).execute()
        batch = resp.get("files", [])
        for f in batch:
            out.write(json.dumps(f, ensure_ascii=False) + "\n")
        total += len(batch)
        pages += 1
        if pages % 10 == 0:
            print(
                f"{pages} pages, {total} files, {int(time.time() - t0)}s",
                file=sys.stderr,
            )
        token = resp.get("nextPageToken")
        if not token:
            break
    print(
        f"done: {total} files in {pages} pages, {int(time.time() - t0)}s",
        file=sys.stderr,
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=argparse.FileType("w"), default=sys.stdout)
    p.add_argument("--include-trashed", action="store_true")
    p.add_argument("--all-drives", action="store_true", help="include shared drives")
    args = p.parse_args()
    scan(args.out, include_trashed=args.include_trashed, all_drives=args.all_drives)


if __name__ == "__main__":
    main()
