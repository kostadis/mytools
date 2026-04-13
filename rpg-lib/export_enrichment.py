#!/usr/bin/env python3
"""
Export enrichment data from rpg_library.db to a JSON file for safe-keeping in git.

The key for each record is a SHA256 fingerprint derived from:
  1. Bookmarks (level|title|page joined, ordered by rowid) — most books
  2. first_page_text                                        — no-bookmark fallback
  3. filename                                               — last resort

Usage:
    python export_enrichment.py rpg_library.db [--output enrichment.json]
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
                     filename: str, conn: sqlite3.Connection) -> tuple[str, str]:
    """Return (fingerprint_hex, method) for a book."""
    if has_bookmarks:
        rows = conn.execute(
            "SELECT level, title, page_number FROM bookmarks WHERE book_id = ? ORDER BY rowid",
            (book_id,),
        ).fetchall()
        if rows:
            raw = "\n".join(f"{r[0]}|{r[1]}|{r[2]}" for r in rows)
            return hashlib.sha256(raw.encode()).hexdigest(), "bookmarks"

    if first_page_text:
        return hashlib.sha256(first_page_text.encode()).hexdigest(), "first_page_text"

    return hashlib.sha256(filename.encode()).hexdigest(), "filename"


def export_enrichment(db_path: str, output_path: str) -> None:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    # Only export rows that have been enriched
    columns = ", ".join(["id", "filename", "has_bookmarks", "first_page_text"] + ENRICHMENT_COLUMNS)
    rows = conn.execute(
        f"SELECT {columns} FROM books WHERE date_enriched IS NOT NULL ORDER BY id"
    ).fetchall()

    records = []
    method_counts: dict[str, int] = {}
    seen_keys: dict[str, int] = {}  # key -> book_id, for collision detection

    for row in rows:
        book_id = row["id"]
        key, method = book_fingerprint(
            book_id, row["has_bookmarks"], row["first_page_text"], row["filename"], conn
        )

        method_counts[method] = method_counts.get(method, 0) + 1

        if key in seen_keys:
            # Collision — same fingerprint, presumably same content/enrichment.
            # Store anyway; import will apply the same enrichment to all matches.
            pass
        seen_keys[key] = book_id

        record: dict = {"_key": key, "_key_method": method}
        for col in ENRICHMENT_COLUMNS:
            record[col] = row[col]
        records.append(record)

    conn.close()

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    total = len(records)
    unique = len(seen_keys)
    collisions = total - unique
    print(f"Exported {total} enriched records → {output_path}")
    print(f"  Unique keys: {unique}  Collisions (same content): {collisions}")
    for method, count in sorted(method_counts.items(), key=lambda x: -x[1]):
        print(f"  Key method '{method}': {count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export RPG library enrichment to JSON")
    parser.add_argument("db", help="Path to rpg_library.db")
    parser.add_argument("--output", default="enrichment.json", help="Output JSON file (default: enrichment.json)")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"Error: database not found: {args.db}", file=sys.stderr)
        sys.exit(1)

    export_enrichment(args.db, args.output)


if __name__ == "__main__":
    main()
