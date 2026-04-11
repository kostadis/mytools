"""
topic_generator.py — Generate LLM overviews for topic hub pages.

For each topic (game_system, tag, series, or publisher), fetches the top books
and asks Claude to write a 2-3 paragraph wiki-style overview. Overviews are
cached in the topic_overviews table.

Run wiki_setup.py first to create the topic_overviews table.

Usage:
  python topic_generator.py rpg_library.db --type game_system --limit 10
  python topic_generator.py rpg_library.db --type tag --limit 20
  python topic_generator.py rpg_library.db --type series --name "Waterdeep"
  python topic_generator.py rpg_library.db --type game_system --force  # regen existing
"""

import argparse
import json
import sqlite3
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from lib.claudelib import make_client, call_api

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are an expert RPG librarian writing wiki-style articles for a personal PDF library.
Write concise, informative overviews in an encyclopedic style. Be specific about what kinds of products exist.
No headers or bullet points — flowing prose only. 2-3 paragraphs maximum."""

TYPE_LABELS = {
    "game_system": "game system",
    "tag": "content category",
    "series": "product series",
    "publisher": "publisher",
}


def get_top_topics(conn: sqlite3.Connection, topic_type: str, limit: int,
                   force: bool) -> list[tuple[str, int]]:
    """Return (name, book_count) for the top topics by book count."""
    if topic_type == "tag":
        # Tags are stored as JSON arrays
        rows = conn.execute(
            """SELECT tags FROM books
               WHERE tags IS NOT NULL AND is_old_version = 0
                 AND is_draft = 0 AND is_duplicate = 0"""
        ).fetchall()
        counts: dict[str, int] = {}
        for (raw,) in rows:
            try:
                for t in json.loads(raw):
                    counts[t] = counts.get(t, 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass
        topics = sorted(counts.items(), key=lambda x: -x[1])[:limit]
    else:
        col = topic_type
        rows = conn.execute(
            f"""SELECT {col}, COUNT(*) as cnt FROM books
                WHERE {col} IS NOT NULL AND {col} != ''
                  AND is_old_version = 0 AND is_draft = 0 AND is_duplicate = 0
                GROUP BY {col}
                ORDER BY cnt DESC
                LIMIT ?""",
            (limit,),
        ).fetchall()
        topics = [(r[0], r[1]) for r in rows]

    if not force:
        existing = set(
            r[0] for r in conn.execute(
                "SELECT topic_name FROM topic_overviews WHERE topic_type = ?",
                (topic_type,),
            ).fetchall()
        )
        topics = [(name, cnt) for name, cnt in topics if name not in existing]

    return topics


def get_topic_books(conn: sqlite3.Connection, topic_type: str, topic_name: str,
                    sample: int = 20) -> list[dict]:
    """Get a sample of books for the topic."""
    if topic_type == "tag":
        rows = conn.execute(
            """SELECT display_title, filename, description, page_count, publisher
               FROM books
               WHERE tags LIKE ? AND is_old_version = 0
                 AND is_draft = 0 AND is_duplicate = 0
               ORDER BY page_count DESC NULLS LAST
               LIMIT ?""",
            (f'%"{topic_name}"%', sample),
        ).fetchall()
    elif topic_type == "game_system":
        rows = conn.execute(
            """SELECT display_title, filename, description, page_count, publisher
               FROM books
               WHERE game_system = ? AND is_old_version = 0
                 AND is_draft = 0 AND is_duplicate = 0
               ORDER BY page_count DESC NULLS LAST
               LIMIT ?""",
            (topic_name, sample),
        ).fetchall()
    elif topic_type == "series":
        rows = conn.execute(
            """SELECT display_title, filename, description, page_count, publisher
               FROM books
               WHERE series = ? AND is_old_version = 0
                 AND is_draft = 0 AND is_duplicate = 0
               ORDER BY filename
               LIMIT ?""",
            (topic_name, sample),
        ).fetchall()
    else:  # publisher
        rows = conn.execute(
            """SELECT display_title, filename, description, page_count, publisher
               FROM books
               WHERE publisher = ? AND is_old_version = 0
                 AND is_draft = 0 AND is_duplicate = 0
               ORDER BY page_count DESC NULLS LAST
               LIMIT ?""",
            (topic_name, sample),
        ).fetchall()

    return [dict(r) for r in rows]


def build_prompt(topic_type: str, topic_name: str, book_count: int,
                 books: list[dict]) -> str:
    label = TYPE_LABELS.get(topic_type, topic_type)
    book_lines = []
    for b in books:
        title = b["display_title"] or b["filename"]
        desc = b["description"] or ""
        if desc:
            desc = desc[:120] + "..." if len(desc) > 120 else desc
        book_lines.append(f"- {title}: {desc}" if desc else f"- {title}")

    book_list = "\n".join(book_lines)

    return f"""Write a wiki-style overview for this {label} in a personal RPG PDF library.

{label.title()}: "{topic_name}"
Total books in collection: {book_count}

Representative books ({len(books)} of {book_count}):
{book_list}

Write 2-3 paragraphs covering:
1. What this {label} is and what it offers players/GMs
2. The range and style of products in this collection
3. Any notable titles, series, or themes visible in the list

Be specific and use examples from the book list. Write in encyclopedic style."""


def generate_overview(client, topic_type: str, topic_name: str,
                      book_count: int, books: list[dict]) -> str:
    prompt = build_prompt(topic_type, topic_name, book_count, books)
    return call_api(client, SYSTEM_PROMPT, prompt, model=MODEL, max_tokens=600)


def save_overview(conn: sqlite3.Connection, topic_type: str, topic_name: str,
                  overview_text: str, book_count: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO topic_overviews(topic_type, topic_name, overview_text, book_count, date_generated)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(topic_type, topic_name) DO UPDATE SET
             overview_text = excluded.overview_text,
             book_count = excluded.book_count,
             date_generated = excluded.date_generated""",
        (topic_type, topic_name, overview_text, book_count, now),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate LLM overviews for topic hub pages.")
    parser.add_argument("db", help="Path to rpg_library.db")
    parser.add_argument("--type", dest="topic_type", default="game_system",
                        choices=["game_system", "tag", "series", "publisher"],
                        help="Topic type to generate (default: game_system)")
    parser.add_argument("--name", help="Generate for a specific topic name only")
    parser.add_argument("--limit", type=int, default=10,
                        help="Max number of topics to generate (default: 10)")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate overviews that already exist")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    try:
        client = make_client()

        if args.name:
            # Single topic mode
            book_count = conn.execute(
                "SELECT COUNT(*) FROM books WHERE is_old_version=0",
            ).fetchone()[0]
            topics = [(args.name, book_count)]
        else:
            print(f"Finding top {args.limit} {args.topic_type} topics...")
            topics = get_top_topics(conn, args.topic_type, args.limit, args.force)
            print(f"  {len(topics)} topics to generate (skipping existing).")

        for i, (name, count) in enumerate(topics, 1):
            print(f"[{i}/{len(topics)}] Generating overview for {args.topic_type}: {name!r} ({count} books)...")
            books = get_topic_books(conn, args.topic_type, name)
            if not books:
                print(f"  No books found, skipping.")
                continue
            try:
                overview = generate_overview(client, args.topic_type, name, count, books)
                save_overview(conn, args.topic_type, name, overview, count)
                conn.commit()
                print(f"  Done ({len(overview)} chars).")
            except Exception as e:
                print(f"  Error: {e}", file=sys.stderr)
                conn.rollback()

        print("\nAll done.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
