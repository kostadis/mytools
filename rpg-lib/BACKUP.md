# Enrichment Backup & Restore

The SQLite database (`rpg_library.db`) is not checked into git. The raw PDF metadata can be re-indexed from disk for free, but the Claude API enrichment (game_system, product_type, tags, description, display_title, series, level ranges) is expensive to regenerate.

These scripts export the enrichment data to a git-tracked JSON file so it survives a database loss.

## How It Works

Each book gets a stable fingerprint derived from its content — not its file path — so the key survives directory reorganizations:

| Priority | Key source | Coverage |
|----------|-----------|----------|
| 1 | SHA256 of ordered bookmarks (level, title, page) | 56% of enriched books |
| 2 | SHA256 of first page text | 39% |
| 3 | SHA256 of filename | 5% |

Version collisions (e.g. v1.23 and v1.29 of the same PDF with identical TOC) are harmless — all versions of the same book share identical enrichment data.

## Backup

Run after any enrichment session (`enrich_rpgs.sh`, `--series-pass`, `--normalize-tags`):

```bash
./backup_enrichment.sh
```

This exports enrichment to `enrichment.json` and commits it to git.

## Restore

Run after a database loss or on a new machine:

```bash
./restore_enrichment.sh
```

This will:
1. Confirm before overwriting any existing database
2. Re-index PDFs from disk (DriveThruRPG + Kickstarter)
3. Import enrichment from `enrichment.json` — no API calls needed

### Scan roots

The restore script expects PDFs at these paths (edit lines 19–20 if they change):

```
/mnt/g/My Drive/DriveThru      → source: drivethrurpg
/mnt/g/My Drive/Kickstarter    → source: kickstarter
```

## Manual usage

```bash
# Export only (no git commit)
python export_enrichment.py rpg_library.db --output enrichment.json

# Import with preview
python import_enrichment.py rpg_library.db --input enrichment.json --dry-run

# Import for real
python import_enrichment.py rpg_library.db --input enrichment.json
```

The importer skips books that already have enrichment, so it's safe to run multiple times.

## Files

| File | Purpose |
|------|---------|
| `backup_enrichment.sh` | Export + git commit |
| `restore_enrichment.sh` | Full rebuild: index from disk + import enrichment |
| `export_enrichment.py` | Export enrichment data to JSON |
| `import_enrichment.py` | Import enrichment data from JSON |
| `enrichment.json` | The snapshot (git-tracked) |
