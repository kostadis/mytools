"""Copy a OneDrive subtree into Google Drive, preserving folder structure.

Reads onedrive.jsonl to enumerate source files. Mirrors the source folder
structure under --target on Google Drive. Skips files whose (name, size)
already exist at the exact target path (target-local dedup). Name collisions
where the size differs are uploaded as duplicates — Drive allows two files
of the same name in a folder.

State is logged per-file to ~/.config/gdrive-tools/copy-state.sqlite
(WAL mode, autocommit). A rerun skips any onedrive_id already recorded
with action='uploaded' or 'skipped_existing'; failed rows are retried.

Usage:
    python onedrive_to_gdrive.py --source "/Dungeons and Dragons/KickStarter" --target "/Kickstarter"
    python onedrive_to_gdrive.py --source "..." --target "..." --execute
    python onedrive_to_gdrive.py --source "..." --target "..." --limit 5 --execute
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from googleapiclient.http import MediaFileUpload

from auth import WRITE_SCOPES, drive_service
from onedrive_auth import READ_SCOPES, get_token

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
CONFIG_DIR = Path.home() / ".config" / "gdrive-tools"
DB_PATH = CONFIG_DIR / "copy-state.sqlite"
LEGACY_JSON_PATH = CONFIG_DIR / "copy-state.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS copied (
    onedrive_id TEXT PRIMARY KEY,
    gdrive_id   TEXT,
    rel_path    TEXT NOT NULL,
    size        INTEGER,
    action      TEXT NOT NULL CHECK (action IN ('uploaded','skipped_existing','failed')),
    error_kind  TEXT,
    error_msg   TEXT,
    ts          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS copied_action_ix ON copied(action);
"""

DONE_ACTIONS = ("uploaded", "skipped_existing")

_tls = threading.local()


def tls_drive_service():
    if not hasattr(_tls, "svc"):
        _tls.svc = drive_service(WRITE_SCOPES)
    return _tls.svc


def _tls_conn() -> sqlite3.Connection:
    conn = getattr(_tls, "conn", None)
    if conn is None:
        conn = sqlite3.connect(
            DB_PATH, isolation_level=None, check_same_thread=False,
        )
        conn.execute("PRAGMA busy_timeout = 5000")
        _tls.conn = conn
    return conn


def onedrive_full_path(rec: dict) -> str:
    parent = rec.get("parentPath", "")
    prefix = "/drive/root:"
    if parent.startswith(prefix):
        parent = parent[len(prefix):]
    parent = urllib.parse.unquote(parent)
    name = rec.get("name", "")
    return f"{parent}/{name}" if parent else f"/{name}"


def load_source_files(jsonl: str, source: str) -> list[dict]:
    """Non-folder records whose path sits under `source`, with `_relpath` attached."""
    source_parts = [p for p in source.strip("/").split("/") if p]
    out: list[dict] = []
    with open(jsonl) as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("mimeType") == "folder":
                continue
            parts = [p for p in onedrive_full_path(rec).split("/") if p]
            if parts[: len(source_parts)] != source_parts:
                continue
            rec["_relpath"] = "/".join(parts[len(source_parts):])
            out.append(rec)
    out.sort(key=lambda r: r["_relpath"])
    return out


def escape_q(s: str) -> str:
    """Escape a string for use inside a Drive API q= expression."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def find_folder(svc, parent_id: str, name: str) -> str | None:
    q = (
        f"'{parent_id}' in parents and name = '{escape_q(name)}' "
        f"and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    files = (
        svc.files()
        .list(q=q, fields="files(id,name)", pageSize=10)
        .execute(num_retries=5)
        .get("files", [])
    )
    return files[0]["id"] if files else None


def create_folder(svc, parent_id: str, name: str) -> str:
    body = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    return svc.files().create(body=body, fields="id").execute(num_retries=5)["id"]


def ensure_folder_path(svc, root_id: str, rel_parts: list[str],
                       cache: dict[str, str]) -> str:
    """Return the folder id for root_id + rel_parts, creating missing levels."""
    path_so_far: list[str] = []
    parent_id = root_id
    for segment in rel_parts:
        path_so_far.append(segment)
        key = "/".join(path_so_far)
        if key in cache:
            parent_id = cache[key]
            continue
        found = find_folder(svc, parent_id, segment) or create_folder(svc, parent_id, segment)
        cache[key] = found
        parent_id = found
    return parent_id


def find_existing_files(svc, parent_id: str, name: str) -> list[dict]:
    q = (
        f"'{parent_id}' in parents and name = '{escape_q(name)}' "
        f"and trashed = false"
    )
    return (
        svc.files()
        .list(q=q, fields="files(id,name,size)", pageSize=10)
        .execute(num_retries=5)
        .get("files", [])
    )


def download_onedrive(item_id: str, token: str, out_path: str) -> None:
    url = f"{GRAPH_BASE}/me/drive/items/{item_id}/content"
    headers = {"Authorization": f"Bearer {token}"}
    with requests.get(url, headers=headers, stream=True, timeout=(30, 600)) as resp:
        if resp.status_code != 200:
            raise RuntimeError(
                f"download failed: {resp.status_code} {resp.text[:200]}"
            )
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)


def upload_gdrive(svc, parent_id: str, name: str, local_path: str, mime: str) -> str:
    media = MediaFileUpload(
        local_path,
        mimetype=mime or "application/octet-stream",
        resumable=True,
        chunksize=8 * 1024 * 1024,
    )
    req = svc.files().create(
        body={"name": name, "parents": [parent_id]},
        media_body=media,
        fields="id",
    )
    resp = None
    while resp is None:
        _, resp = req.next_chunk(num_retries=5)
    return resp["id"]


def open_db() -> sqlite3.Connection:
    """Bootstrap the state DB: create parent dir, enable WAL, run schema."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.executescript(SCHEMA)
    return conn


def maybe_migrate_from_json(conn: sqlite3.Connection) -> int:
    """Import rows from the legacy JSON iff the copied table is empty.

    Returns the number of rows imported (0 if migration was skipped).
    The JSON file is left on disk — SQLite becomes the source of truth.
    """
    if not LEGACY_JSON_PATH.exists():
        return 0
    (row_count,) = conn.execute("SELECT COUNT(*) FROM copied").fetchone()
    if row_count > 0:
        return 0
    data = json.loads(LEGACY_JSON_PATH.read_text())
    rows = data.get("copied", {})
    if not rows:
        return 0
    to_insert = [
        (
            oid,
            v.get("gdrive_id"),
            v.get("rel_path", ""),
            v.get("size"),
            v.get("action", "uploaded"),
            None,
            None,
            v.get("ts", time.strftime("%Y-%m-%dT%H:%M:%S")),
        )
        for oid, v in rows.items()
    ]
    conn.execute("BEGIN")
    conn.executemany(
        "INSERT OR REPLACE INTO copied "
        "(onedrive_id, gdrive_id, rel_path, size, action, error_kind, error_msg, ts) "
        "VALUES (?,?,?,?,?,?,?,?)",
        to_insert,
    )
    conn.execute("COMMIT")
    return len(to_insert)


def record(onedrive_id: str, gdrive_id: str | None, rel_path: str,
           size: int, action: str,
           error_kind: str | None = None, error_msg: str | None = None) -> None:
    _tls_conn().execute(
        "INSERT OR REPLACE INTO copied "
        "(onedrive_id, gdrive_id, rel_path, size, action, error_kind, error_msg, ts) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            onedrive_id, gdrive_id, rel_path, size, action,
            error_kind, error_msg,
            time.strftime("%Y-%m-%dT%H:%M:%S"),
        ),
    )


def already_done_ids(conn: sqlite3.Connection) -> set[str]:
    placeholders = ",".join("?" * len(DONE_ACTIONS))
    rows = conn.execute(
        f"SELECT onedrive_id FROM copied WHERE action IN ({placeholders})",
        DONE_ACTIONS,
    ).fetchall()
    return {r[0] for r in rows}


def human_bytes(n: float) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}PB"


def process_one(rec, idx, total, target_root, folder_cache, folder_lock,
                onedrive_token, counters, counters_lock, t0):
    svc = tls_drive_service()
    rel = rec["_relpath"]
    name = rec["name"]
    size = int(rec.get("size", 0) or 0)
    mime = rec.get("mimeType", "") or "application/octet-stream"

    rel_folders = rel.split("/")[:-1]
    with folder_lock:
        parent_id = ensure_folder_path(svc, target_root, rel_folders, folder_cache)

    existing = find_existing_files(svc, parent_id, name)
    same_size = [e for e in existing if int(e.get("size", 0) or 0) == size]
    if same_size:
        record(rec["id"], same_size[0]["id"], rel, size, "skipped_existing")
        with counters_lock:
            counters["skipped"] += 1
        print(
            f"[{idx:>4}/{total}] skip {rel} ({human_bytes(size)})",
            file=sys.stderr,
        )
        return

    tmp_path = None
    try:
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=".onedrive",
            dir=tempfile.gettempdir(),
        )
        tmp.close()
        tmp_path = tmp.name
        download_onedrive(rec["id"], onedrive_token, tmp_path)
        gdrive_id = upload_gdrive(svc, parent_id, name, tmp_path, mime)
    except Exception as e:
        record(
            rec["id"], None, rel, size, "failed",
            error_kind=type(e).__name__, error_msg=str(e)[:500],
        )
        with counters_lock:
            counters["failed"] += 1
        print(
            f"[{idx:>4}/{total}] FAIL {rel}: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    record(rec["id"], gdrive_id, rel, size, "uploaded")
    with counters_lock:
        counters["uploaded"] += 1
    print(
        f"[{idx:>4}/{total}] up   {rel} ({human_bytes(size)}) "
        f"{int(time.time() - t0)}s",
        file=sys.stderr,
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--source", required=True,
                   help="OneDrive subtree path to copy, e.g. '/Dungeons and Dragons/KickStarter'")
    p.add_argument("--target", required=True,
                   help="GDrive target folder path, e.g. '/Kickstarter'")
    p.add_argument("--onedrive-jsonl", default="onedrive.jsonl")
    p.add_argument("--limit", type=int, default=None,
                   help="cap the run to the first N pending files (for testing)")
    p.add_argument("--workers", type=int, default=6,
                   help="concurrent download+upload workers (default 6)")
    p.add_argument("--execute", action="store_true",
                   help="actually transfer files (default: dry-run)")
    args = p.parse_args()

    files = load_source_files(args.onedrive_jsonl, args.source)
    total_bytes = sum(int(r.get("size", 0) or 0) for r in files)

    bootstrap_conn = open_db()
    migrated = maybe_migrate_from_json(bootstrap_conn)
    if migrated:
        print(
            f"migrated {migrated:,} rows from {LEGACY_JSON_PATH.name} "
            f"into {DB_PATH.name}",
            file=sys.stderr,
        )
    already = already_done_ids(bootstrap_conn)
    pending = [r for r in files if r["id"] not in already]
    pending_bytes = sum(int(r.get("size", 0) or 0) for r in pending)

    print(f"source:           {args.source}")
    print(f"target:           {args.target}")
    print(f"files under src:  {len(files):,} ({human_bytes(total_bytes)})")
    print(f"already in state: {len(files) - len(pending):,}")
    print(f"pending:          {len(pending):,} ({human_bytes(pending_bytes)})")

    if args.limit:
        pending = pending[: args.limit]
        pending_bytes = sum(int(r.get("size", 0) or 0) for r in pending)
        print(f"limited to:       {len(pending):,} ({human_bytes(pending_bytes)})")

    if not args.execute:
        print("\ndry-run; pass --execute to transfer", file=sys.stderr)
        return

    print("\nauthenticating…", file=sys.stderr)
    onedrive_token = get_token(READ_SCOPES)
    bootstrap_svc = drive_service(WRITE_SCOPES)
    folder_cache: dict[str, str] = {"": None}  # type: ignore[dict-item]
    target_parts = [p for p in args.target.strip("/").split("/") if p]
    target_root = ensure_folder_path(bootstrap_svc, "root", target_parts, {})
    folder_cache[""] = target_root
    print(f"target root id: {target_root}", file=sys.stderr)

    counters = {"uploaded": 0, "skipped": 0, "failed": 0}
    folder_lock = threading.Lock()
    counters_lock = threading.Lock()
    t0 = time.time()
    total = len(pending)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [
            ex.submit(
                process_one, rec, i, total, target_root, folder_cache,
                folder_lock, onedrive_token,
                counters, counters_lock, t0,
            )
            for i, rec in enumerate(pending, 1)
        ]
        for _ in as_completed(futures):
            pass

    uploaded = counters["uploaded"]
    skipped = counters["skipped"]
    failed = counters["failed"]

    print(
        f"\ndone: uploaded {uploaded:,}, skipped {skipped:,}, failed {failed:,}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
