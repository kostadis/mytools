---
name: RLM → 5etools sideloading bridge
description: In-flight project to make 5etools (kostadis fork) read the per-PDF JSON sidecars produced by CampaignGenerator's convert_book pipeline, brokered via rpg-lib.
type: project
originSessionId: ca9406fb-4090-4f20-90a9-a6a34df43299
---
Goal: 5etools (`/home/kroussos/src/5etools-kostadis`) needs to load the
5etools-format JSON files that CampaignGenerator produces next to each
indexed PDF (e.g. `<library-root>/<title>/<id>.json` alongside the
`.pdf`). Bridge runs through rpg-lib (`/home/kroussos/src/mytools/rpg-lib`),
which already owns the index of "for each book, where does its PDF live."

**Why:** the converted JSONs are the load-bearing artifact for 5etools
sideloading; without a stable lookup path, every machine would need
bespoke symlink wiring. rpg-lib is the natural broker because it already
knows `relative_path` per book.

**How to apply:** when continuing this work, the architecture is
"rpg-lib resolves; 5etools homebrew loader consumes." Don't add a
parallel filesystem walker in CampaignGenerator — go through rpg-lib's
HTTP/MCP surfaces.

## Shipped (2026-05-03 / 2026-05-04)

- `library_api/sidecar.py` — `get_library_root()` reads
  `RPG_LIBRARY_ROOT` env var; `resolve_fivetools_json(book, root)`
  returns `<root>/<relative_path>.parent / <stem>.json` if present.
- `routes.py` — `GET /api/library/book/{id}/fivetools` streams the
  sibling JSON (503 if root unset, 404 if absent). `set_library_root()`
  setter added.
- `library_server.py` — reads env var at boot, prints in banner.
- `library_mcp.py` — `get_book_fivetools(book_id, include_content=False)`
  MCP tool returning `{configured, exists, path, content?}`.
- `ARCHITECTURE.md` — documented env var in §2, endpoint in §3.1, MCP
  tool in §4.
- **`fivetools_symlink_farm.py` (rpg-lib, 2026-05-04)** — CLI that
  reads the books table read-only, resolves each sidecar via
  `library_api.sidecar`, creates `rpglib_NNNNNNN__<stem>.json`
  symlinks in a target homebrew dir, and rewrites
  `homebrew/index.json#toImport` (preserves manual entries, replaces
  managed). Idempotent. Verified on a synthetic 2-book DB.
- **5etools self-host gate confirmed (2026-05-04):** kostadis fork has
  `globalThis.IS_DEPLOYED = undefined;` at `js/utils.js:4`, so the
  homebrew loader path is live.

## Pending

1. **User action — re-index the library.** `rpg_library.db` is not on
   disk (only `user_data.db`); a `restore_enrichment.sh` run (or
   `pdf_indexer.py` against `/mnt/g/My Drive/DriveThru` followed by
   importing `enrichment.json`) is required before either the
   `/fivetools` endpoint smoke test or the symlink-farm helper can
   produce real output.
2. **User action — smoke test.** With the DB rebuilt:
   `RPG_LIBRARY_ROOT="/mnt/g/My Drive/DriveThru" ./service.sh start`,
   then `curl -I http://localhost:8000/api/library/book/<id>/fivetools`
   for the Candlekeep "Inside the Great Library" entry — expect 200.
3. **User action — run the symlink farm.**
   `cd /home/kroussos/src/mytools/rpg-lib &&
    RPG_LIBRARY_ROOT="/mnt/g/My Drive/DriveThru"
    python3 fivetools_symlink_farm.py
    --db rpg_library.db
    --homebrew-dir /home/kroussos/src/5etools-kostadis/homebrew
    --dry-run`
   then re-run without `--dry-run`. Open 5etools and confirm
   sideloaded entries appear under Manage Homebrew.

## Architectural decisions made (don't relitigate)

- Library root is an **env var (`RPG_LIBRARY_ROOT`)**, not a config
  file or DB row — keeps the SQLite portable across machines.
- Single root, not a `{source → root}` map. If multi-source becomes
  real, swap the env var to a JSON map without changing call sites.
- Sidecar lookups gracefully return "not configured" when the env var
  is unset; existing endpoints unaffected.
- Resolution lives in **one** helper (`library_api/sidecar.py`) shared
  by HTTP route and MCP tool — keeps them in lockstep.
- Rejected: symlink farm built by CG walking the filesystem directly
  (would duplicate rpg-lib's index); patching 5etools JS to fetch
  arbitrary URLs (vendored-code conflict on upstream pulls).
