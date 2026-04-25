"""Walk OneDrive metadata and emit one JSONL line per file.

Uses Microsoft Graph /me/drive/root/delta for a flat, paginated stream.
State (delta cursor + item store) is cached under ~/.config/onedrive-tools/
so repeat runs only fetch changes since the last scan. Output to --out is a
full snapshot of the current drive regardless of whether the run was cold
or incremental.

Usage:
    python onedrive_scan.py --out onedrive.jsonl                   # incremental if state exists
    python onedrive_scan.py --out onedrive.jsonl --full            # force cold scan, wipe state
    python onedrive_scan.py --out onedrive.jsonl --include-trashed
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from onedrive_auth import CONFIG_DIR, READ_SCOPES, get_token, graph_get

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

STORE_PATH = CONFIG_DIR / "onedrive-store.jsonl"
DELTA_PATH = CONFIG_DIR / "delta.json"

SELECT_FIELDS = ",".join([
    "id",
    "name",
    "size",
    "createdDateTime",
    "lastModifiedDateTime",
    "file",
    "folder",
    "parentReference",
    "shared",
    "deleted",
    "root",
    "webUrl",
])


class StaleDeltaLink(Exception):
    """Graph returned 410 Gone — cursor is too old, restart as cold scan."""


def normalize_item(item: dict) -> dict:
    """Flatten a Graph DriveItem into a consistent record."""
    parent = item.get("parentReference", {})
    rec = {
        "id": item["id"],
        "name": item.get("name", ""),
        "size": item.get("size", 0),
        "createdTime": item.get("createdDateTime", ""),
        "modifiedTime": item.get("lastModifiedDateTime", ""),
        "webViewLink": item.get("webUrl", ""),
        "parentId": parent.get("id", ""),
        "parentPath": parent.get("path", ""),
        "shared": "shared" in item,
        "trashed": "deleted" in item,
    }

    if "folder" in item:
        rec["mimeType"] = "folder"
        rec["childCount"] = item["folder"].get("childCount", 0)
    else:
        rec["mimeType"] = item.get("file", {}).get("mimeType", "")
        hashes = item.get("file", {}).get("hashes", {})
        if hashes.get("sha1Hash"):
            rec["sha1Hash"] = hashes["sha1Hash"]
        if hashes.get("quickXorHash"):
            rec["quickXorHash"] = hashes["quickXorHash"]

    return rec


def load_store() -> dict[str, dict]:
    if not STORE_PATH.exists():
        return {}
    store: dict[str, dict] = {}
    with STORE_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            store[rec["id"]] = rec
    return store


def save_store(store: dict[str, dict]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STORE_PATH.parent / (STORE_PATH.name + ".tmp")
    with tmp.open("w") as f:
        for rec in store.values():
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    os.replace(tmp, STORE_PATH)


def load_deltalink() -> str | None:
    if not DELTA_PATH.exists():
        return None
    return json.loads(DELTA_PATH.read_text()).get("deltaLink")


def save_deltalink(url: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DELTA_PATH.parent / (DELTA_PATH.name + ".tmp")
    tmp.write_text(json.dumps({"deltaLink": url}))
    os.replace(tmp, DELTA_PATH)


def reset_state() -> None:
    for p in (STORE_PATH, DELTA_PATH):
        p.unlink(missing_ok=True)


def cold_start_url() -> str:
    return f"{GRAPH_BASE}/me/drive/root/delta?$select={SELECT_FIELDS}&$top=200"


def walk_delta(token: str, start_url: str, store: dict[str, dict]) -> str:
    """Stream /delta pages into the store. Returns the final deltaLink."""
    url = start_url
    processed = 0
    t0 = time.time()

    while url:
        resp = graph_get(url, token)
        if resp.status_code == 401:
            raise SystemExit("Token expired — re-run to re-authenticate.")
        if resp.status_code == 410:
            raise StaleDeltaLink()
        if resp.status_code != 200:
            raise SystemExit(
                f"Graph error {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        for item in data.get("value", []):
            processed += 1
            if "deleted" in item:
                store.pop(item["id"], None)
            elif "root" in item:
                continue
            else:
                store[item["id"]] = normalize_item(item)

            if processed % 1000 == 0:
                print(
                    f"{processed} events, {len(store)} in store, "
                    f"{int(time.time() - t0)}s",
                    file=sys.stderr,
                )

        if "@odata.deltaLink" in data:
            return data["@odata.deltaLink"]
        url = data.get("@odata.nextLink")

    raise SystemExit("Delta stream ended without a deltaLink")


def emit_store(store: dict[str, dict], out, include_trashed: bool) -> int:
    count = 0
    for rec in store.values():
        if rec.get("trashed") and not include_trashed:
            continue
        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        count += 1
    return count


def scan(out, include_trashed: bool, full: bool) -> None:
    token = get_token(READ_SCOPES)

    if full:
        reset_state()
        store: dict[str, dict] = {}
        start_url = cold_start_url()
    else:
        store = load_store()
        saved = load_deltalink()
        if saved and store:
            start_url = saved
            print(
                f"resuming from saved delta cursor; {len(store)} items in store",
                file=sys.stderr,
            )
        else:
            store = {}
            start_url = cold_start_url()
            print("no usable state; starting cold scan", file=sys.stderr)

    t0 = time.time()
    try:
        delta_link = walk_delta(token, start_url, store)
    except StaleDeltaLink:
        print(
            "delta cursor stale (410); restarting as cold scan",
            file=sys.stderr,
        )
        reset_state()
        store = {}
        delta_link = walk_delta(token, cold_start_url(), store)

    save_store(store)
    save_deltalink(delta_link)

    emitted = emit_store(store, out, include_trashed)
    print(
        f"done: {emitted} records emitted ({len(store)} in store), "
        f"{int(time.time() - t0)}s",
        file=sys.stderr,
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=argparse.FileType("w"), default=sys.stdout)
    p.add_argument("--include-trashed", action="store_true")
    p.add_argument(
        "--full",
        action="store_true",
        help="force cold scan and wipe cached delta state",
    )
    args = p.parse_args()
    scan(args.out, include_trashed=args.include_trashed, full=args.full)


if __name__ == "__main__":
    main()
