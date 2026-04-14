#!/usr/bin/env python3
"""
Import enrichment data from a JSON snapshot back into rpg_library.db.

Run this after a fresh pdf_indexer.py pass to restore Claude API enrichment
without making any API calls. Each record is matched by its fingerprint key.

Usage:
    python import_enrichment.py rpg_library.db [--input enrichment.json] [--dry-run]
"""

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path


ENRICHMENT_COLUMNS = [
    "game_system",
    "product_type",
    "description",
    "date_enriched",
    "tags",
    "series",
    "display_title",
    "min_level",
    "max_level",
]


def book_fingerprint(book_id: int, has_bookmarks: int, first_page_text: str | None,
                     filename: str, conn: sqlite3.Connection) -> str:
    """Compute fingerprint for a book — must match export_enrichment.py exactly."""
    if has_bookmarks:
        rows = conn.execute(
            "SELECT level, title, page_number FROM bookmarks WHERE book_id = ? ORDER BY rowid",
            (book_id,),
        ).fetchall()
        if rows:
            raw = "\n".join(f"{r[0]}|{r[1]}|{r[2]}" for r in rows)
            return hashlib.sha256(raw.encode()).hexdigest()

    if first_page_text:
        return hashlib.sha256(first_page_text.encode()).hexdigest()

    return hashlib.sha256(filename.encode()).hexdigest()


def import_enrichment(db_path: str, input_path: str, dry_run: bool) -> None:
    with open(input_path, encoding="utf-8") as f:
        records = json.load(f)

    key_to_record: dict[str, dict] = {r["_key"]: r for r in records}
    print(f"Loaded {len(records)} records from {input_path} ({len(key_to_record)} unique keys)")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    books = conn.execute(
        "SELECT id, filename, has_bookmarks, first_page_text FROM books"
    ).fetchall()

    matched = 0
    skipped_already_enriched = 0
    unmatched = 0

    updates: list[tuple] = []

    for book in books:
        book_id = book["id"]
        key = book_fingerprint(
            book_id, book["has_bookmarks"], book["first_page_text"], book["filename"], conn
        )

        record = key_to_record.get(key)
        if record is None:
            unmatched += 1
            continue

        # Check if already enriched — skip to avoid overwriting newer data
        existing = conn.execute(
            "SELECT date_enriched FROM books WHERE id = ?", (book_id,)
        ).fetchone()
        if existing["date_enriched"] is not None:
            skipped_already_enriched += 1
            continue

        values = [record.get(col) for col in ENRICHMENT_COLUMNS]
        values.append(book_id)
        updates.append(tuple(values))
        matched += 1

    set_clause = ", ".join(f"{col} = ?" for col in ENRICHMENT_COLUMNS)
    sql = f"UPDATE books SET {set_clause} WHERE id = ?"

    if not dry_run:
        conn.executemany(sql, updates)
        conn.commit()

    conn.close()

    action = "Would update" if dry_run else "Updated"
    print(f"{action} {matched} books with enrichment data")
    print(f"  Skipped (already enriched): {skipped_already_enriched}")
    print(f"  No match in snapshot:       {unmatched}")
    if dry_run:
        print("Dry run — no changes written.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import RPG library enrichment from JSON snapshot")
    parser.add_argument("db", help="Path to rpg_library.db")
    parser.add_argument("--input", default="enrichment.json", help="Input JSON file (default: enrichment.json)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be imported without writing")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"Error: database not found: {args.db}", file=sys.stderr)
        sys.exit(1)

    if not Path(args.input).exists():
        print(f"Error: enrichment file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    import_enrichment(args.db, args.input, args.dry_run)


if __name__ == "__main__":
    main()
