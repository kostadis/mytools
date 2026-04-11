"""
relation_builder.py — Build book_relations from tag Jaccard similarity.

For each pair of enriched books that share at least one tag, computes:
  Jaccard(A, B) = |tags_A ∩ tags_B| / |tags_A ∪ tags_B|

Keeps the top 10 relations per book where score >= MIN_SCORE.
Stores both directions (A→B and B→A) for fast lookup.

Run wiki_setup.py first to create the book_relations table.

Usage:
  python relation_builder.py rpg_library.db
  python relation_builder.py rpg_library.db --min-score 0.15 --top-k 15
"""

import argparse
import json
import sqlite3
import sys
from collections import defaultdict

MIN_SCORE = 0.1
TOP_K = 10
# Skip tags shared by more than this many books (too common to discriminate)
MAX_TAG_BOOKS = 500


def load_books(conn: sqlite3.Connection) -> dict[int, set[str]]:
    """Load all enriched books with their tag sets."""
    rows = conn.execute(
        """SELECT id, tags FROM books
           WHERE tags IS NOT NULL AND tags != '[]' AND tags != ''
             AND is_old_version = 0 AND is_draft = 0 AND is_duplicate = 0"""
    ).fetchall()
    books: dict[int, set[str]] = {}
    for row in rows:
        try:
            tags = json.loads(row["tags"])
            if tags:
                books[row["id"]] = set(tags)
        except (json.JSONDecodeError, TypeError):
            pass
    return books


def build_relations(
    books: dict[int, set[str]],
    min_score: float,
    top_k: int,
) -> list[tuple[int, int, float, int]]:
    """
    Compute pairwise Jaccard similarity using an inverted index.
    Returns list of (book_id_a, book_id_b, score, shared_count).
    Both directions (a→b and b→a) are included.
    """
    # Build inverted index: tag → [book_id, ...]
    tag_index: dict[str, list[int]] = defaultdict(list)
    for book_id, tags in books.items():
        for tag in tags:
            tag_index[tag].append(book_id)

    # Count shared tags between pairs (using only discriminative tags)
    pair_shared: dict[tuple[int, int], int] = defaultdict(int)
    skipped_tags = 0
    for tag, book_ids in tag_index.items():
        if len(book_ids) > MAX_TAG_BOOKS:
            skipped_tags += 1
            continue
        for i in range(len(book_ids)):
            for j in range(i + 1, len(book_ids)):
                a, b = book_ids[i], book_ids[j]
                if a > b:
                    a, b = b, a
                pair_shared[(a, b)] += 1

    if skipped_tags:
        print(f"  Skipped {skipped_tags} high-frequency tags (>{MAX_TAG_BOOKS} books each).")

    # Compute Jaccard and filter
    print(f"  Scoring {len(pair_shared):,} candidate pairs...")
    results: list[tuple[int, int, float, int]] = []
    for (a, b), shared in pair_shared.items():
        union = len(books[a]) + len(books[b]) - shared
        if union <= 0:
            continue
        score = shared / union
        if score >= min_score:
            results.append((a, b, score, shared))

    # Keep top_k per book (both directions)
    book_top: dict[int, list[tuple[int, float, int]]] = defaultdict(list)
    for a, b, score, shared in results:
        book_top[a].append((b, score, shared))
        book_top[b].append((a, score, shared))

    final: list[tuple[int, int, float, int]] = []
    for book_id, rels in book_top.items():
        rels.sort(key=lambda x: -x[1])
        for other_id, score, shared in rels[:top_k]:
            final.append((book_id, other_id, score, shared))

    return final


def save_relations(
    conn: sqlite3.Connection,
    relations: list[tuple[int, int, float, int]],
) -> None:
    """Replace all book_relations with the new data."""
    conn.execute("DELETE FROM book_relations")
    conn.executemany(
        "INSERT OR REPLACE INTO book_relations(book_id_a, book_id_b, score, shared_tags_count)"
        " VALUES (?, ?, ?, ?)",
        relations,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build book_relations from tag similarity.")
    parser.add_argument("db", help="Path to rpg_library.db")
    parser.add_argument("--min-score", type=float, default=MIN_SCORE,
                        help=f"Minimum Jaccard score to keep (default: {MIN_SCORE})")
    parser.add_argument("--top-k", type=int, default=TOP_K,
                        help=f"Max relations per book to store (default: {TOP_K})")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    try:
        print("Loading books with tags...")
        books = load_books(conn)
        print(f"  Found {len(books):,} books with tags.")

        if not books:
            print("No enriched books with tags found. Run pdf_enricher.py first.")
            sys.exit(1)

        print("Building tag inverted index and scoring pairs...")
        relations = build_relations(books, args.min_score, args.top_k)
        print(f"  Found {len(relations):,} relations (both directions).")

        print("Saving to book_relations...")
        save_relations(conn, relations)
        conn.commit()
        print(f"Done. {len(relations):,} relations stored.")

    except Exception as e:
        conn.rollback()
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
