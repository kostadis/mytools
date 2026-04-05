# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A full-stack RPG PDF library: Python scripts index PDFs from disk into SQLite, the Claude API enriches them with metadata (game system, tags, description), and a FastAPI + Vue 3 web UI lets you search and browse them.

**Three-phase pipeline:**
1. `pdf_indexer.py` — scans folders, extracts PDF metadata and bookmarks → SQLite
2. `pdf_enricher.py` — calls Claude API to classify each book with game_system, product_type, tags, description, display_title
3. `library_server.py` — serves the REST API and Vue SPA

## Commands

### Backend
```bash
# Start server (from rpg-lib/)
python library_server.py --db rpg_library.db --port 8000
./start_library.sh                          # same, with defaults

# Index PDFs
./index_rpgs.sh /path/to/pdfs rpg_library.db drivethrurpg

# Enrich with Claude API
./enrich_rpgs.sh rpg_library.db
python pdf_enricher.py rpg_library.db --dry-run --limit 10  # preview only
python pdf_enricher.py rpg_library.db --series-pass         # detect series groupings
python pdf_enricher.py rpg_library.db --normalize-tags      # normalize tag vocabulary
```

### Frontend
```bash
cd frontend
npm run build      # type-check + production build → frontend/dist/
npm run dev        # Vite dev server on :5173 (proxies /api to :8000)
```

**Important:** After any frontend change, run `npm run build` — the backend serves `frontend/dist/` as the SPA. Check for stale compiled files with `find src -name "*.js"` before debugging build issues; a `.js` file next to a `.ts` file will shadow it silently.

## Architecture

```
library_server.py          # FastAPI app; mounts /assets from frontend/dist/;
                           # catch-all serves index.html (no-cache headers)
library_api/
  routes.py                # All API endpoints, grouped under /api/library/
  db.py                    # All DB queries; search_books() builds WHERE clauses
                           # dynamically and groups results by collection
  models.py                # Pydantic models (BookSummary has variant_count/variant_ids)
frontend/src/
  stores/library.ts        # Pinia store — single source of truth for search state,
                           # filters, pagination, expanded variant groups
  views/LibraryBrowse.vue  # Sidebar filters + table/card results; variant expansion
  views/BookDetail.vue     # Full book detail, bookmarks, PDF open/preview
```

### Key design decisions

**Grouping:** Search results are grouped by `(publisher, normalized_collection)` in Python after fetching all matching IDs sorted. Each group returns one representative row plus `variant_count` and `variant_ids`. The frontend can expand a group by fetching `GET /api/library/books?ids=1,2,3`.

**Tags:** Stored as JSON arrays in the `books.tags` column. The enricher uses a fixed canonical vocabulary (~80 tags) with aliases. `--normalize-tags` applies aliases and drops tags below a frequency threshold. Tag filters in the UI use `LIKE '%"tag"%'` queries.

**PDF access:** Two modes — `POST /book/{id}/open` launches the file in the desktop app (uses `wslpath -w` + `explorer.exe` on WSL; `xdg-open` on Linux), `GET /book/{id}/pdf` streams the file inline for browser preview.

**Store actions vs. direct assignment:** Always use store actions (`setFilter`, `setQuery`, `toggleGroup`) to mutate state — direct assignment to store properties from components can silently fail to update the ref inside the closure.

**`lib/claudelib.py`** lives in the parent `mytools/lib/` directory (shared across projects). `pdf_enricher.py` adds `..` to `sys.path` to import it.

## Database

SQLite (`rpg_library.db`), opened **read-only** by the API (`?mode=ro`). The indexer and enricher open it read-write directly.

Key columns: `is_old_version`, `is_draft`, `is_duplicate` (all filtered out by default in search). `tags` is a JSON array string. `collection` is the folder name from disk — used as the grouping key for deduplication.

The `tsconfig.app.json` uses `"moduleResolution": "bundler"` — required for Vite to prefer `.ts` over `.js` source files.
