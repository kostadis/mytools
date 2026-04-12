"""Database access layer for the RPG Library API."""

import json
import sqlite3
from pathlib import Path


def init_user_db(user_db_path: str) -> None:
    """Create the user-data database and schema if it doesn't exist."""
    conn = sqlite3.connect(user_db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            book_id    INTEGER PRIMARY KEY,
            date_added TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def get_db(db_path: str, user_db_path: str | None = None) -> sqlite3.Connection:
    """Open a read-only connection to the library database.

    If *user_db_path* is provided, the user-data DB is ATTACHed as
    ``user_data`` so queries can JOIN against ``user_data.favorites``.
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    if user_db_path:
        conn.execute("ATTACH DATABASE ? AS user_data", (user_db_path,))
    return conn


def _parse_tags(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _row_to_summary(row: sqlite3.Row) -> dict:
    keys = row.keys()
    return {
        "id": row["id"],
        "display_title": row["display_title"],
        "filename": row["filename"],
        "publisher": row["publisher"],
        "collection": row["collection"],
        "game_system": row["game_system"],
        "product_type": row["product_type"],
        "tags": _parse_tags(row["tags"]),
        "series": row["series"],
        "source": row["source"],
        "page_count": row["page_count"],
        "has_bookmarks": bool(row["has_bookmarks"]),
        "description": row["description"],
        "min_level": row["min_level"],
        "max_level": row["max_level"],
        "is_favorite": bool(row["is_favorite"]) if "is_favorite" in keys else False,
    }


SORTABLE_COLUMNS = {
    "title", "filename", "publisher", "game_system", "product_type",
    "series", "source", "page_count", "collection",
}


def _collection_group_key(publisher: str | None, collection: str | None, book_id: int) -> str:
    """Normalize publisher+collection into a stable group key."""
    if not collection:
        return f"id:{book_id}"
    norm = (collection
            .replace('\u2013', '-').replace('\u2014', '-')  # en/em dash
            .replace('  ', ' ').strip().lower())
    pub = (publisher or '').strip().lower()
    return f"{pub}||{norm}"


def _build_search_where(
    q: str | None = None,
    q_name: str | None = None,
    game_system: str | None = None,
    product_type: str | None = None,
    publisher: str | None = None,
    series: str | None = None,
    source: str | None = None,
    tags: str | None = None,
    level_min: int | None = None,
    level_max: int | None = None,
    include_old: bool = False,
    include_drafts: bool = False,
    include_duplicates: bool = False,
    favorites_only: bool = False,
) -> tuple[str, list]:
    """Build the WHERE clause + parameter list shared by search_books and
    search_facets, so a faceted search reflects exactly the same set of books
    that the regular search would return."""
    conditions: list[str] = []
    params: list = []

    if not include_old:
        conditions.append("is_old_version = 0")
    if not include_drafts:
        conditions.append("is_draft = 0")
    if not include_duplicates:
        conditions.append("is_duplicate = 0")

    if q:
        conditions.append(
            "(display_title LIKE ? OR filename LIKE ? OR pdf_title LIKE ? "
            "OR publisher LIKE ? OR collection LIKE ? OR series LIKE ? "
            "OR description LIKE ? OR tags LIKE ?)"
        )
        like = f"%{q}%"
        params.extend([like] * 8)
    if q_name:
        conditions.append(
            "(display_title LIKE ? OR filename LIKE ? OR pdf_title LIKE ? OR collection LIKE ?)"
        )
        like = f"%{q_name}%"
        params.extend([like] * 4)

    if game_system:
        conditions.append("game_system = ?")
        params.append(game_system)
    if product_type:
        conditions.append("product_type = ?")
        params.append(product_type)
    if publisher:
        conditions.append("publisher = ?")
        params.append(publisher)
    if series:
        conditions.append("series = ?")
        params.append(series)
    if source:
        conditions.append("source = ?")
        params.append(source)
    if tags:
        for tag in tags.split(","):
            tag = tag.strip()
            if tag:
                conditions.append("tags LIKE ?")
                params.append(f'%"{tag}"%')
    if level_min is not None or level_max is not None:
        conditions.append(
            "min_level IS NOT NULL AND max_level IS NOT NULL "
            "AND min_level <= ? AND max_level >= ?"
        )
        params.extend([
            level_max if level_max is not None else level_min,
            level_min if level_min is not None else level_max,
        ])
    if favorites_only:
        conditions.append("id IN (SELECT book_id FROM user_data.favorites)")

    where = " AND ".join(conditions) if conditions else "1=1"
    return where, params


def search_books(conn: sqlite3.Connection, q: str | None = None,
                 q_name: str | None = None,
                 game_system: str | None = None,
                 product_type: str | None = None,
                 publisher: str | None = None,
                 series: str | None = None,
                 source: str | None = None,
                 tags: str | None = None,
                 level_min: int | None = None,
                 level_max: int | None = None,
                 sort: str | None = None,
                 sort_dir: str | None = None,
                 include_old: bool = False,
                 include_drafts: bool = False,
                 include_duplicates: bool = False,
                 favorites_only: bool = False,
                 grouped: bool = True,
                 page: int = 1, per_page: int = 50) -> dict:
    """Search and filter books. Returns dict with results, total, pagination info."""
    where, params = _build_search_where(
        q=q, q_name=q_name,
        game_system=game_system, product_type=product_type,
        publisher=publisher, series=series, source=source, tags=tags,
        level_min=level_min, level_max=level_max,
        include_old=include_old, include_drafts=include_drafts,
        include_duplicates=include_duplicates,
        favorites_only=favorites_only,
    )

    # Sort
    direction = "DESC" if sort_dir == "desc" else "ASC"
    if sort == "title":
        order_by = f"COALESCE(display_title, filename) {direction}"
    elif sort and sort in SORTABLE_COLUMNS:
        order_by = f"{sort} {direction}"
    else:
        order_by = "COALESCE(display_title, filename) ASC"

    offset = (page - 1) * per_page

    if grouped:
        # Fetch id+publisher+collection in sorted order, group in Python
        id_rows = conn.execute(
            f"SELECT id, publisher, collection FROM books WHERE {where} ORDER BY {order_by}",
            params,
        ).fetchall()

        # Group preserving sort order; first occurrence is the representative
        seen: dict[str, dict] = {}
        group_order: list[str] = []
        for row in id_rows:
            key = _collection_group_key(row["publisher"], row["collection"], row["id"])
            if key not in seen:
                seen[key] = {"rep_id": row["id"], "ids": [row["id"]]}
                group_order.append(key)
            else:
                seen[key]["ids"].append(row["id"])

        total = len(group_order)
        total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0

        page_keys = group_order[offset: offset + per_page]
        if not page_keys:
            return {"results": [], "total": total, "page": page,
                    "per_page": per_page, "total_pages": total_pages}

        rep_ids = [seen[k]["rep_id"] for k in page_keys]
        placeholders = ",".join("?" * len(rep_ids))
        rep_rows = conn.execute(
            f"""SELECT b.id, b.display_title, b.filename, b.publisher, b.collection,
                       b.game_system, b.product_type, b.tags, b.series, b.source,
                       b.page_count, b.has_bookmarks, b.description, b.min_level, b.max_level,
                       (f.book_id IS NOT NULL) AS is_favorite
                FROM books b
                LEFT JOIN user_data.favorites f ON f.book_id = b.id
                WHERE b.id IN ({placeholders})""",
            rep_ids,
        ).fetchall()
        id_to_row = {r["id"]: r for r in rep_rows}

        results = []
        for key in page_keys:
            g = seen[key]
            row = id_to_row.get(g["rep_id"])
            if row:
                summary = _row_to_summary(row)
                summary["variant_count"] = len(g["ids"])
                summary["variant_ids"] = g["ids"]
                results.append(summary)

        return {"results": results, "total": total, "page": page,
                "per_page": per_page, "total_pages": total_pages}

    # Ungrouped path
    count_row = conn.execute(
        f"SELECT COUNT(*) FROM books WHERE {where}", params
    ).fetchone()
    total = count_row[0]
    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0

    rows = conn.execute(
        f"""SELECT b.id, b.display_title, b.filename, b.publisher, b.collection,
                   b.game_system, b.product_type, b.tags, b.series, b.source,
                   b.page_count, b.has_bookmarks, b.description, b.min_level, b.max_level,
                   (f.book_id IS NOT NULL) AS is_favorite
            FROM books b
            LEFT JOIN user_data.favorites f ON f.book_id = b.id
            WHERE {where}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()

    return {
        "results": [_row_to_summary(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }


def search_facets(
    conn: sqlite3.Connection,
    q: str | None = None,
    q_name: str | None = None,
    game_system: str | None = None,
    product_type: str | None = None,
    publisher: str | None = None,
    series: str | None = None,
    source: str | None = None,
    tags: str | None = None,
    level_min: int | None = None,
    level_max: int | None = None,
    include_old: bool = False,
    include_drafts: bool = False,
    include_duplicates: bool = False,
    favorites_only: bool = False,
) -> dict:
    """Aggregate the books matching a search by series / publisher / game_system / tag.

    Uses exactly the same WHERE clause as ``search_books``, so the counts here
    sum to the same set of books that the regular search would return. The
    return shape is::

        {
            "total": <int>,
            "series":      [{"value": "Ravenloft", "count": 8}, ...],
            "publisher":   [{"value": "WotC",      "count": 24}, ...],
            "game_system": [{"value": "D&D 5e",    "count": 87}, ...],
            "tag":         [{"value": "horror",    "count": 14}, ...],
        }

    Each list is sorted by descending count. Tags are decoded from the JSON
    array column. Empty/NULL values are excluded from the buckets.
    """
    where, params = _build_search_where(
        q=q, q_name=q_name,
        game_system=game_system, product_type=product_type,
        publisher=publisher, series=series, source=source, tags=tags,
        level_min=level_min, level_max=level_max,
        include_old=include_old, include_drafts=include_drafts,
        include_duplicates=include_duplicates,
        favorites_only=favorites_only,
    )

    total = conn.execute(
        f"SELECT COUNT(*) FROM books WHERE {where}", params
    ).fetchone()[0]

    def _column_facet(col: str) -> list[dict]:
        rows = conn.execute(
            f"""SELECT {col} AS value, COUNT(*) AS count
                FROM books
                WHERE {where} AND {col} IS NOT NULL AND {col} != ''
                GROUP BY {col}
                ORDER BY count DESC, {col} ASC""",
            params,
        ).fetchall()
        return [{"value": r["value"], "count": r["count"]} for r in rows]

    series_facet = _column_facet("series")
    publisher_facet = _column_facet("publisher")
    game_system_facet = _column_facet("game_system")

    # Tags live in a JSON-array column — decode in Python.
    tag_rows = conn.execute(
        f"SELECT tags FROM books WHERE {where} AND tags IS NOT NULL",
        params,
    ).fetchall()
    tag_counts: dict[str, int] = {}
    for (raw,) in tag_rows:
        try:
            for t in json.loads(raw):
                if t:
                    tag_counts[t] = tag_counts.get(t, 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass
    tag_facet = sorted(
        [{"value": t, "count": c} for t, c in tag_counts.items()],
        key=lambda x: (-x["count"], x["value"]),
    )

    return {
        "total": total,
        "series": series_facet,
        "publisher": publisher_facet,
        "game_system": game_system_facet,
        "tag": tag_facet,
    }


def get_books_by_ids(conn: sqlite3.Connection, book_ids: list[int]) -> list[dict]:
    """Fetch multiple books by ID, ordered by filename."""
    if not book_ids:
        return []
    placeholders = ",".join("?" * len(book_ids))
    rows = conn.execute(
        f"""SELECT b.id, b.display_title, b.filename, b.publisher, b.collection,
                   b.game_system, b.product_type, b.tags, b.series, b.source,
                   b.page_count, b.has_bookmarks, b.description, b.min_level, b.max_level,
                   (f.book_id IS NOT NULL) AS is_favorite
            FROM books b
            LEFT JOIN user_data.favorites f ON f.book_id = b.id
            WHERE b.id IN ({placeholders})
            ORDER BY b.filename""",
        book_ids,
    ).fetchall()
    return [_row_to_summary(r) for r in rows]


def get_book(conn: sqlite3.Connection, book_id: int) -> dict | None:
    """Get full book detail including bookmarks."""
    row = conn.execute(
        """SELECT b.*, (f.book_id IS NOT NULL) AS is_favorite
           FROM books b
           LEFT JOIN user_data.favorites f ON f.book_id = b.id
           WHERE b.id = ?""",
        (book_id,),
    ).fetchone()
    if not row:
        return None

    bookmarks = conn.execute(
        "SELECT level, title, page_number FROM bookmarks WHERE book_id = ? ORDER BY id",
        (book_id,),
    ).fetchall()

    return {
        **_row_to_summary(row),
        "filepath": row["filepath"],
        "relative_path": row["relative_path"],
        "pdf_title": row["pdf_title"],
        "pdf_author": row["pdf_author"],
        "pdf_creator": row["pdf_creator"],
        "first_page_text": row["first_page_text"],
        "is_old_version": bool(row["is_old_version"]),
        "version_generation": row["version_generation"],
        "product_id": row["product_id"],
        "product_version": row["product_version"],
        "date_indexed": row["date_indexed"],
        "date_enriched": row["date_enriched"],
        "bookmarks": [
            {"level": b["level"], "title": b["title"], "page_number": b["page_number"]}
            for b in bookmarks
        ],
    }


def set_favorite(conn: sqlite3.Connection, book_id: int) -> None:
    """Mark a book as a favorite."""
    conn.execute(
        "INSERT OR IGNORE INTO user_data.favorites (book_id) VALUES (?)",
        (book_id,),
    )
    conn.commit()


def unset_favorite(conn: sqlite3.Connection, book_id: int) -> None:
    """Remove a book from favorites."""
    conn.execute(
        "DELETE FROM user_data.favorites WHERE book_id = ?",
        (book_id,),
    )
    conn.commit()


def get_bookmarks(conn: sqlite3.Connection, book_id: int) -> list[dict]:
    """Get bookmark tree for a book."""
    rows = conn.execute(
        "SELECT level, title, page_number FROM bookmarks WHERE book_id = ? ORDER BY id",
        (book_id,),
    ).fetchall()
    return [{"level": r["level"], "title": r["title"], "page_number": r["page_number"]}
            for r in rows]


def get_book_text(conn: sqlite3.Connection, book_id: int) -> dict | None:
    """Get text content for a book (for pipeline consumption)."""
    row = conn.execute(
        "SELECT id, display_title, filename, first_page_text FROM books WHERE id = ?",
        (book_id,),
    ).fetchone()
    if not row:
        return None

    bm_rows = conn.execute(
        "SELECT title FROM bookmarks WHERE book_id = ? ORDER BY id",
        (book_id,),
    ).fetchall()

    return {
        "id": row["id"],
        "display_title": row["display_title"],
        "filename": row["filename"],
        "first_page_text": row["first_page_text"],
        "bookmark_titles": [r["title"] for r in bm_rows],
    }


def get_filters(conn: sqlite3.Connection) -> dict:
    """Get distinct filter values with counts."""
    result = {}
    for field in ["game_system", "product_type", "publisher", "series", "source"]:
        rows = conn.execute(
            f"""SELECT {field} as value, COUNT(*) as count
                FROM books
                WHERE is_old_version = 0 AND {field} IS NOT NULL
                GROUP BY {field}
                ORDER BY count DESC""",
        ).fetchall()
        result[field] = [{"value": r["value"], "count": r["count"]} for r in rows]

    # Tags need special handling — stored as JSON arrays
    tag_rows = conn.execute(
        "SELECT tags FROM books WHERE tags IS NOT NULL AND is_old_version = 0"
    ).fetchall()
    tag_counts: dict[str, int] = {}
    for (raw,) in tag_rows:
        try:
            for t in json.loads(raw):
                tag_counts[t] = tag_counts.get(t, 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass
    result["tags"] = sorted(
        [{"value": t, "count": c} for t, c in tag_counts.items()],
        key=lambda x: -x["count"],
    )

    return result


def nlq_search(
    conn: sqlite3.Connection,
    keywords: str,
    game_system: str | None = None,
    product_type: str | None = None,
    tags: list[str] | None = None,
    level_min: int | None = None,
    level_max: int | None = None,
    limit: int = 30,
) -> list[dict]:
    """
    Full-text search using the books_fts FTS5 table, plus optional structured filters.
    Falls back to LIKE-based search if books_fts doesn't exist.
    """
    conditions = [
        "b.is_old_version = 0",
        "b.is_draft = 0",
        "b.is_duplicate = 0",
    ]
    params: list = []

    if game_system:
        conditions.append("b.game_system = ?")
        params.append(game_system)
    if product_type:
        conditions.append("b.product_type = ?")
        params.append(product_type)
    for tag in (tags or []):
        conditions.append("b.tags LIKE ?")
        params.append(f'%"{tag}"%')
    if level_min is not None or level_max is not None:
        conditions.append(
            "b.min_level IS NOT NULL AND b.max_level IS NOT NULL "
            "AND b.min_level <= ? AND b.max_level >= ?"
        )
        params.extend([level_max if level_max is not None else level_min,
                        level_min if level_min is not None else level_max])

    where = " AND ".join(conditions)

    # Try FTS5 first
    try:
        fts_params = [keywords] + params
        rows = conn.execute(
            f"""SELECT b.id, b.display_title, b.filename, b.publisher, b.collection,
                       b.game_system, b.product_type, b.tags, b.series, b.source,
                       b.page_count, b.has_bookmarks, b.description, b.min_level, b.max_level,
                       (fav.book_id IS NOT NULL) AS is_favorite
                FROM books_fts
                JOIN books b ON books_fts.rowid = b.id
                LEFT JOIN user_data.favorites fav ON fav.book_id = b.id
                WHERE books_fts MATCH ? AND {where}
                ORDER BY bm25(books_fts)
                LIMIT ?""",
            fts_params + [limit],
        ).fetchall()
        return [_row_to_summary(r) for r in rows]
    except Exception:
        pass

    # Fallback: LIKE search on display_title and description
    kw_like = f"%{keywords}%"
    conditions.append("(b.display_title LIKE ? OR b.description LIKE ? OR b.tags LIKE ?)")
    params.extend([kw_like, kw_like, kw_like])
    where = " AND ".join(conditions)
    rows = conn.execute(
        f"""SELECT b.id, b.display_title, b.filename, b.publisher, b.collection,
                   b.game_system, b.product_type, b.tags, b.series, b.source,
                   b.page_count, b.has_bookmarks, b.description, b.min_level, b.max_level,
                   (fav.book_id IS NOT NULL) AS is_favorite
            FROM books b
            LEFT JOIN user_data.favorites fav ON fav.book_id = b.id
            WHERE {where}
            ORDER BY COALESCE(b.display_title, b.filename)
            LIMIT ?""",
        params + [limit],
    ).fetchall()
    return [_row_to_summary(r) for r in rows]


def _topic_where(topic_type: str, topic_name: str) -> tuple[str, list]:
    """Return (WHERE clause, params) for a given topic type/name."""
    base = "is_old_version = 0 AND is_draft = 0 AND is_duplicate = 0"
    if topic_type == "tag":
        return f"{base} AND tags LIKE ?", [f'%"{topic_name}"%']
    elif topic_type == "game_system":
        return f"{base} AND game_system = ?", [topic_name]
    elif topic_type == "series":
        return f"{base} AND series = ?", [topic_name]
    elif topic_type == "publisher":
        return f"{base} AND publisher = ?", [topic_name]
    return base, []


def _topic_stats(conn: sqlite3.Connection, topic_type: str, where: str,
                 params: list) -> dict:
    """Compute stats for a topic: counts, breakdowns by type/publisher/tags/series."""
    total = conn.execute(f"SELECT COUNT(*) FROM books WHERE {where}", params).fetchone()[0]
    enriched = conn.execute(
        f"SELECT COUNT(*) FROM books WHERE {where} AND date_enriched IS NOT NULL", params
    ).fetchone()[0]

    def breakdown(col: str, limit: int = 10) -> list[dict]:
        rows = conn.execute(
            f"""SELECT {col} as value, COUNT(*) as count FROM books
                WHERE {where} AND {col} IS NOT NULL AND {col} != ''
                GROUP BY {col} ORDER BY count DESC LIMIT {limit}""",
            params,
        ).fetchall()
        return [{"value": r["value"], "count": r["count"]} for r in rows]

    # Tags need JSON parsing
    def tag_breakdown(limit: int = 15) -> list[dict]:
        tag_rows = conn.execute(
            f"SELECT tags FROM books WHERE {where} AND tags IS NOT NULL", params
        ).fetchall()
        counts: dict[str, int] = {}
        for (raw,) in tag_rows:
            try:
                for t in json.loads(raw):
                    counts[t] = counts.get(t, 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass
        return sorted(
            [{"value": t, "count": c} for t, c in counts.items()],
            key=lambda x: -x["count"],
        )[:limit]

    return {
        "total": total,
        "enriched": enriched,
        "by_product_type": breakdown("product_type"),
        "top_publishers": [] if topic_type == "publisher" else breakdown("publisher"),
        "top_tags": [] if topic_type == "tag" else tag_breakdown(),
        "top_series": [] if topic_type == "series" else breakdown("series"),
        "top_game_systems": [] if topic_type == "game_system" else breakdown("game_system"),
    }


def get_topic(conn: sqlite3.Connection, topic_type: str, topic_name: str) -> dict | None:
    """Get topic stats and books for a topic hub page."""
    if topic_type not in {"tag", "game_system", "series", "publisher"}:
        return None

    where, params = _topic_where(topic_type, topic_name)
    stats = _topic_stats(conn, topic_type, where, params)

    if stats["total"] == 0:
        return None

    rows = conn.execute(
        f"""SELECT b.id, b.display_title, b.filename, b.publisher, b.collection,
                   b.game_system, b.product_type, b.tags, b.series, b.source,
                   b.page_count, b.has_bookmarks, b.description, b.min_level, b.max_level,
                   (f.book_id IS NOT NULL) AS is_favorite
            FROM books b
            LEFT JOIN user_data.favorites f ON f.book_id = b.id
            WHERE {where}
            ORDER BY COALESCE(b.display_title, b.filename)""",
        params,
    ).fetchall()

    return {
        "topic_type": topic_type,
        "topic_name": topic_name,
        "stats": stats,
        "books": [_row_to_summary(r) for r in rows],
    }


def generate_topic_overview(conn: sqlite3.Connection, topic_type: str, topic_name: str) -> str:
    """
    Generate and store a topic overview via Claude. Returns the overview text.
    Imports topic_generator lazily to avoid circular imports.
    """
    import sys
    import os
    # topic_generator is at rpg-lib/ level; db.py is at rpg-lib/library_api/
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    import topic_generator as tg

    client = tg.make_client()
    books = tg.get_topic_books(conn, topic_type, topic_name)
    book_count = len(conn.execute(
        "SELECT COUNT(*) FROM books WHERE is_old_version=0 AND is_draft=0 AND is_duplicate=0"
    ).fetchone())
    overview = tg.generate_overview(client, topic_type, topic_name, book_count, books)
    tg.save_overview(conn, topic_type, topic_name, overview, len(books))
    return overview


def get_related_books(conn: sqlite3.Connection, book_id: int, limit: int = 6) -> list[dict]:
    """
    Get related books for a given book.
    Uses book_relations table if populated; falls back to tag overlap.
    """
    # Try book_relations first
    rows = conn.execute(
        """SELECT b.id, b.display_title, b.filename, b.publisher, b.collection,
                  b.game_system, b.product_type, b.tags, b.series, b.source,
                  b.page_count, b.has_bookmarks, b.description, b.min_level, b.max_level,
                  (f.book_id IS NOT NULL) AS is_favorite
           FROM book_relations r
           JOIN books b ON b.id = r.book_id_b
           LEFT JOIN user_data.favorites f ON f.book_id = b.id
           WHERE r.book_id_a = ?
             AND b.is_old_version = 0 AND b.is_draft = 0 AND b.is_duplicate = 0
           ORDER BY r.score DESC
           LIMIT ?""",
        (book_id, limit),
    ).fetchall()

    if rows:
        return [_row_to_summary(r) for r in rows]

    # Fallback: tag overlap (fetch book's tags, then find books sharing them)
    book_row = conn.execute("SELECT tags, series FROM books WHERE id = ?", (book_id,)).fetchone()
    if not book_row:
        return []

    try:
        book_tags = json.loads(book_row["tags"] or "[]")
    except (json.JSONDecodeError, TypeError):
        book_tags = []

    if not book_tags and not book_row["series"]:
        return []

    tag_counts: dict[int, int] = {}

    # Count shared tags
    for tag in book_tags:
        tag_rows = conn.execute(
            """SELECT id FROM books WHERE tags LIKE ?
               AND is_old_version = 0 AND is_draft = 0 AND is_duplicate = 0
               AND id != ?""",
            (f'%"{tag}"%', book_id),
        ).fetchall()
        for r in tag_rows:
            tag_counts[r["id"]] = tag_counts.get(r["id"], 0) + 1

    # Boost books in the same series
    if book_row["series"]:
        series_rows = conn.execute(
            """SELECT id FROM books WHERE series = ?
               AND is_old_version = 0 AND is_draft = 0 AND is_duplicate = 0
               AND id != ?""",
            (book_row["series"], book_id),
        ).fetchall()
        for r in series_rows:
            tag_counts[r["id"]] = tag_counts.get(r["id"], 0) + 10

    top_ids = sorted(tag_counts, key=lambda x: -tag_counts[x])[:limit]
    if not top_ids:
        return []

    placeholders = ",".join("?" * len(top_ids))
    rows = conn.execute(
        f"""SELECT b.id, b.display_title, b.filename, b.publisher, b.collection,
                   b.game_system, b.product_type, b.tags, b.series, b.source,
                   b.page_count, b.has_bookmarks, b.description, b.min_level, b.max_level,
                   (f.book_id IS NOT NULL) AS is_favorite
            FROM books b
            LEFT JOIN user_data.favorites f ON f.book_id = b.id
            WHERE b.id IN ({placeholders})""",
        top_ids,
    ).fetchall()
    id_to_row = {r["id"]: _row_to_summary(r) for r in rows}
    return [id_to_row[i] for i in top_ids if i in id_to_row]


def get_graph(
    conn: sqlite3.Connection,
    min_score: float = 0.25,
    limit: int = 300,
    game_system: str | None = None,
) -> dict:
    """Get graph nodes and edges for the D3 visualization."""
    # Get edges above threshold
    edge_params: list = [min_score]
    edge_filter = ""
    if game_system:
        edge_filter = """
            AND r.book_id_a IN (SELECT id FROM books WHERE game_system = ? AND is_old_version=0)
            AND r.book_id_b IN (SELECT id FROM books WHERE game_system = ? AND is_old_version=0)
        """
        edge_params = [min_score, game_system, game_system]

    edge_rows = conn.execute(
        f"""SELECT r.book_id_a, r.book_id_b, r.score
            FROM book_relations r
            WHERE r.score >= ? {edge_filter}
              AND r.book_id_a < r.book_id_b
            ORDER BY r.score DESC
            LIMIT {limit * 3}""",
        edge_params,
    ).fetchall()

    # Collect node IDs (limit to top nodes by edge count)
    node_edge_count: dict[int, int] = {}
    edges_to_use = []
    for r in edge_rows:
        node_edge_count[r["book_id_a"]] = node_edge_count.get(r["book_id_a"], 0) + 1
        node_edge_count[r["book_id_b"]] = node_edge_count.get(r["book_id_b"], 0) + 1
        edges_to_use.append(r)

    # Take top-N nodes by connectivity
    top_node_ids = sorted(node_edge_count, key=lambda x: -node_edge_count[x])[:limit]
    top_node_set = set(top_node_ids)

    # Filter edges to only those between included nodes
    final_edges = [
        r for r in edges_to_use
        if r["book_id_a"] in top_node_set and r["book_id_b"] in top_node_set
    ]

    if not top_node_ids:
        return {"nodes": [], "edges": []}

    # Fetch node details
    placeholders = ",".join("?" * len(top_node_ids))
    node_rows = conn.execute(
        f"""SELECT id, display_title, filename, game_system
            FROM books WHERE id IN ({placeholders})""",
        top_node_ids,
    ).fetchall()

    nodes = [
        {
            "id": r["id"],
            "label": r["display_title"] or r["filename"],
            "group": r["game_system"],
        }
        for r in node_rows
    ]
    edges = [
        {"source": r["book_id_a"], "target": r["book_id_b"], "score": r["score"]}
        for r in final_edges
    ]

    return {"nodes": nodes, "edges": edges}


def get_stats(conn: sqlite3.Connection) -> dict:
    """Get aggregate statistics."""
    total = conn.execute(
        "SELECT COUNT(*) FROM books WHERE is_old_version = 0"
    ).fetchone()[0]
    enriched = conn.execute(
        "SELECT COUNT(*) FROM books WHERE is_old_version = 0 AND date_enriched IS NOT NULL"
    ).fetchone()[0]
    with_bm = conn.execute(
        "SELECT COUNT(*) FROM books WHERE is_old_version = 0 AND has_bookmarks = 1"
    ).fetchone()[0]

    by_source = conn.execute(
        """SELECT source as value, COUNT(*) as count FROM books
           WHERE is_old_version = 0 AND source IS NOT NULL
           GROUP BY source ORDER BY count DESC"""
    ).fetchall()

    by_type = conn.execute(
        """SELECT product_type as value, COUNT(*) as count FROM books
           WHERE is_old_version = 0 AND product_type IS NOT NULL
           GROUP BY product_type ORDER BY count DESC"""
    ).fetchall()

    return {
        "total_books": total,
        "enriched_books": enriched,
        "books_with_bookmarks": with_bm,
        "by_source": [{"value": r["value"], "count": r["count"]} for r in by_source],
        "by_product_type": [{"value": r["value"], "count": r["count"]} for r in by_type],
    }
