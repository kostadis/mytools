"""
wiki_setup.py — One-time DB migrations for the RPG Library Wiki features.

Creates:
  - books_fts    : FTS5 virtual table for full-text search
  - topic_overviews : LLM-generated overviews for tags/systems/series
  - book_relations  : pairwise tag-similarity scores between books

Usage:
  python wiki_setup.py rpg_library.db
  python wiki_setup.py rpg_library.db --rebuild-fts
"""

import argparse
import sqlite3
import sys


def setup_fts(conn: sqlite3.Connection, rebuild: bool = False) -> None:
    """Create (or rebuild) the FTS5 virtual table."""
    if rebuild:
        print("Dropping existing books_fts...")
        conn.execute("DROP TABLE IF EXISTS books_fts")

    existing = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='books_fts'"
    ).fetchone()
    if existing and not rebuild:
        print("books_fts already exists. Use --rebuild-fts to recreate.")
        return

    print("Creating books_fts FTS5 table...")
    conn.execute("""
        CREATE VIRTUAL TABLE books_fts USING fts5(
            display_title,
            description,
            tags,
            series,
            game_system,
            content='books',
            content_rowid='id'
        )
    """)

    print("Populating books_fts from books...")
    conn.execute("""
        INSERT INTO books_fts(rowid, display_title, description, tags, series, game_system)
        SELECT
            id,
            COALESCE(display_title, ''),
            COALESCE(description, ''),
            COALESCE(tags, ''),
            COALESCE(series, ''),
            COALESCE(game_system, '')
        FROM books
        WHERE is_old_version = 0 AND is_draft = 0 AND is_duplicate = 0
    """)
    count = conn.execute("SELECT COUNT(*) FROM books_fts").fetchone()[0]
    print(f"  Indexed {count} books.")


def setup_topic_overviews(conn: sqlite3.Connection) -> None:
    """Create the topic_overviews table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS topic_overviews (
            id           INTEGER PRIMARY KEY,
            topic_type   TEXT NOT NULL,
            topic_name   TEXT NOT NULL,
            overview_text TEXT,
            book_count   INTEGER,
            date_generated TEXT,
            UNIQUE(topic_type, topic_name)
        )
    """)
    print("topic_overviews table ready.")


def setup_book_relations(conn: sqlite3.Connection) -> None:
    """Create the book_relations table and index if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS book_relations (
            book_id_a       INTEGER NOT NULL,
            book_id_b       INTEGER NOT NULL,
            score           REAL NOT NULL,
            shared_tags_count INTEGER,
            PRIMARY KEY (book_id_a, book_id_b)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_relations_a
        ON book_relations(book_id_a, score DESC)
    """)
    print("book_relations table and index ready.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Set up wiki DB tables for the RPG library.")
    parser.add_argument("db", help="Path to rpg_library.db")
    parser.add_argument("--rebuild-fts", action="store_true",
                        help="Drop and recreate the FTS5 table")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    try:
        setup_fts(conn, rebuild=args.rebuild_fts)
        setup_topic_overviews(conn)
        setup_book_relations(conn)
        conn.commit()
        print("\nDone. Wiki DB setup complete.")
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
