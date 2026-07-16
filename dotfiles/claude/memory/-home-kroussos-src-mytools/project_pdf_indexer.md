---
name: PDF Library Indexer
description: RPG PDF indexer — Phase 1 complete (SQLite + PyMuPDF), Phase 2 is Claude API enrichment + series detection
type: project
---

Building a PDF library indexer for ~5000+ RPG PDFs across two sources:
- **Kickstarter**: `/mnt/g/My Drive/Kickstarter` — publisher/collection/file hierarchy
- **DriveThruRPG**: `/mnt/g/My Drive/DriveThru` — publisher/title/file hierarchy, filenames often have product IDs (`1549348-...`) and versions (`(v1.4)`), old versions as `.old-NNN.pdf`

**Phase 1 (complete)**: `pdf_indexer.py` + `index_rpgs.sh` — extracts metadata, bookmarks, folder hierarchy into SQLite. Parallel processing with `--workers`. Schema has `source`, `publisher`, `collection`, `product_id`, `product_version`, `is_old_version`, `version_generation`.

**Phase 2 (next)**: Claude API enrichment to populate `game_system`, `product_type`, `description`, and a new `series` column. Key challenge: some publishers (e.g. Raging Swan Press) put all files flat in one directory with series as a filename prefix (`Dungeon Dressing_`, `Village Backdrop_`, etc.) instead of subdirectories.

**Why:** User has a massive RPG collection and wants to build a searchable web UI on top of the indexed data.
