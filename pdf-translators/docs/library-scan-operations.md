# Run and resume the library scan

Run `scripts/run_library_scan.sh` from any directory. Its defaults are the mounted `/mnt/g/My Drive/DriveThru` library and a private `source-selection-data` directory in this project. Optional arguments override the source and working directories. Never put the working directory inside the library.

The script appends timestamped progress to `source-selection-data/scan-progress.log` every 100 inventoried sources and every 100 checked duplicate-hash candidates. It uses a lock to prevent concurrent runs through the script. A final successful summary is saved as `scan.json`; failed runs do not overwrite that summary.

Inventory discoveries are flushed and synchronized to `inventory-progress.jsonl` every 100 sources, including a final partial batch. This is a diagnostic journal, not an authoritative completed inventory. A restart re-walks filesystem metadata and replaces this journal. Inventory traversal order is not stable, so partial inventory entries are not used to skip files.

Each successful SHA-256 cache entry commits to `selection.db` independently before the inventory publication transaction. A restart reuses a completed hash only when the source path and observed fingerprint still match; changed sources are rehashed. An in-flight file's hash may need to be repeated after a crash. Inventory and grouping publication remain transactional, preserving the last completed state when interrupted. Do not delete `selection.db`, its SQLite journals, or the work directory to resume.

The scan identifies exact byte matches and broader filename candidates. It does not prove semantic equivalence or revision chronology, run OCR, delete duplicates, or convert PDFs. Existing Dungeon Masters Guild artifacts remain protected by the full library hierarchy. Further content inspection and review are needed for versions whose bytes differ.

Verification for the checkpoint change: tests cover an interrupted inventory walk, persistent completed hashes across a rolled-back inventory publication, progress at 100/200 files, complete inventory journaling, and cached hash reuse on the next run. Existing Rust tests and Clippy also pass.
