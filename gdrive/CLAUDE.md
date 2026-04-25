# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Personal tools against cloud-drive APIs. Two parallel stacks live side by side in this directory:

- **Google Drive** — `auth.py`, `scan.py`, `dupes.py`, `move.py`, `trash.py`. Entry point is `scan.py`, which dumps Drive metadata to `drive.jsonl`.
- **OneDrive** (personal Microsoft account) — `onedrive_auth.py`, `onedrive_scan.py`. Entry point is `onedrive_scan.py`, which dumps OneDrive metadata to `onedrive.jsonl` via Microsoft Graph.

Despite the directory name, this is no longer Google-only. New OneDrive tools should follow the `onedrive_*.py` prefix convention to keep the namespaces separate.

## Why APIs and not filesystem mounts

Google Drive is mirrored at `/mnt/g` via VirtualBox shared folder; OneDrive has analogous sync clients. Neither is a substitute for the API:

- `.gdoc` / `.gsheet` / `.gslides` files on disk are tiny JSON stubs, not real content — `stat().st_size` tells you nothing about native Google Docs.
- Filesystems have no sharing, ownership, `viewedByMeTime`, or Graph `shared`/`deleted` facets — the fields that make sprawl actionable.
- `vboxsf` walks are slow; a single API walk is faster and richer.

Use filesystem mounts only as cross-checks.

## Setup

### Google Drive

1. GCP project → enable the Drive API → create an **OAuth 2.0 Client ID** of type **Desktop app** → download JSON.
2. Save as `~/.config/gdrive-tools/credentials.json`.
3. First run opens a browser; token cached at `~/.config/gdrive-tools/token.json` (read) or `token-write.json` (write).

Default scope is `drive.readonly`. Write-scope clients (`move.py`, `trash.py`) request `drive` via `WRITE_SCOPES` in `auth.py`. Do not widen the default read scope — give new write tools their own scope import.

### OneDrive (personal)

1. Azure portal → **App registrations** → **New registration** → name it (e.g. `onedrive-tools`), choose **Personal Microsoft accounts only**, redirect URI **Public client/native**. Copy the Application (client) ID.
2. In **Authentication**, enable **Allow public client flows** (required for device flow).
3. In **API permissions**, add Microsoft Graph delegated permissions: `Files.Read` (and `Files.ReadWrite` if you plan to add a write tool).
4. Save the client_id at `~/.config/onedrive-tools/app.json` as `{"client_id": "YOUR_APP_CLIENT_ID"}`.
5. First run prints a device-code URL; token cached at `~/.config/onedrive-tools/token.json` (shared across scopes — MSAL handles incremental consent).
6. `onedrive_scan.py` additionally caches `delta.json` (Graph delta cursor) and `onedrive-store.jsonl` (accumulated item snapshot) in the same dir — these are the source of truth between runs; `--out` is re-derived from the store each run.

Authority is hard-coded to `login.microsoftonline.com/consumers` (personal accounts). A work/school tenant would need a different authority URL; add a separate helper rather than switching the consumer path.

### Python env

Use the shared venv at `~/src` (not a per-project `.venv`):

```bash
source ~/src/bin/activate
pip install -r requirements.txt
```

`requirements.txt` covers both stacks: `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2`, `msal`, `requests`.

## Running

### Google Drive

```bash
python scan.py --out drive.jsonl                  # My Drive + Shared with me
python scan.py --out drive.jsonl --all-drives     # also shared drives
python scan.py --out drive.jsonl --include-trashed
```

Single paginated `files.list` call (1000/page); progress every 10 pages.

### OneDrive

```bash
python onedrive_scan.py --out onedrive.jsonl                   # incremental if state exists, cold otherwise
python onedrive_scan.py --out onedrive.jsonl --full            # force cold scan, wipe cached state
python onedrive_scan.py --out onedrive.jsonl --include-trashed
```

Flat `/me/drive/root/delta` stream (200/page — Graph caps lower than Drive); progress every 1000 delta events. The final page yields an `@odata.deltaLink` cursor cached in `~/.config/onedrive-tools/delta.json`; subsequent runs reuse it to fetch only changes, making repeat scans near-instant. A stale cursor returns 410 Gone, which auto-falls-back to a cold scan.

`--include-trashed` is retained but near-no-op: neither `/children` nor `/delta` returns recycle-bin items. Delta tombstones (items deleted since the last cursor) are applied to the internal store as removals, not emitted as trashed records.

### Copying between drives

```bash
python onedrive_to_gdrive.py --source "/Dungeons and Dragons/KickStarter" --target "/Kickstarter"
python onedrive_to_gdrive.py --source "..." --target "..." --limit 5 --execute
python onedrive_to_gdrive.py --source "..." --target "..." --execute
```

Dry-run by default. Reads `onedrive.jsonl` for the source enumeration (no Graph folder walks), then for each file checks the target folder on Drive — same (name, size) → skip; else download via Graph to a tempfile and upload via a resumable Drive media request. Name collisions with different size are uploaded as duplicates (Drive allows two files of the same name in a folder). Resumes from `~/.config/gdrive-tools/copy-state.sqlite` (stdlib sqlite3, WAL mode — per-row atomic writes, no lock in the worker hot path). On first run with this tool, rows from the legacy `copy-state.json` are imported once; the JSON is then left in place but ignored. Failures are also logged (`action='failed'` with `error_kind` + `error_msg`) and are retried on the next run.

## JSONL shapes differ between providers

Both scanners emit JSONL, but the schemas are not identical — a downstream tool that wants to handle both needs to branch on which file it reads.

Shared fields: `id`, `name`, `size`, `createdTime`, `modifiedTime`, `webViewLink`, `shared`, `trashed`.

Differences:

| Concept | `drive.jsonl` | `onedrive.jsonl` |
|---|---|---|
| Parent | `parents` (list of IDs) | `parentId` + `parentPath` (Graph-style path string) |
| Folder type | `mimeType == "application/vnd.google-apps.folder"` | `mimeType == "folder"` (our own label) + `childCount` |
| Ownership | `owners`, `ownedByMe` | — |
| Permissions | `permissions[]` with role/type/domain | — (would require a second Graph call per item) |
| Checksums | `md5Checksum` for binary uploads | `sha1Hash` / `quickXorHash` |
| Last viewed | `viewedByMeTime`, `sharedWithMeTime` | — |
| Shared-drive membership | `driveId` | — |

If you extend `dupes.py` (or any analyzer) to consume OneDrive output, write a small adapter rather than sprinkling `if "parents" in e` branches through the analysis code.

## Conventions for new tools

- **JSONL is the interface.** New analysis tools read `drive.jsonl` / `onedrive.jsonl` — they do not re-hit the API. Only `scan.py` and `onedrive_scan.py` talk to their respective services.
- **One file per tool.** Share auth through `auth.py` (Google) or `onedrive_auth.py` (Microsoft); otherwise keep tools self-contained.
- **stdlib-first for analyzers.** Only the scan tools need their SDKs; downstream report tools should not import `googleapiclient` or `msal`.
- **Path reconstruction** (parent IDs → human path) is a downstream concern. For Drive, folders are in the JSONL dump; build a lookup as `dupes.py` does. For OneDrive, `parentPath` is already Graph-style (`/drive/root:/Foo/Bar`) — strip the prefix rather than reconstructing from IDs.
- **Dry-run by default** for any write tool. See `move.py` / `trash.py` on the Drive side; a OneDrive equivalent should follow the same `--execute` gate.
- **New OneDrive tools:** prefix filenames with `onedrive_` so auth and data paths stay unambiguous.
