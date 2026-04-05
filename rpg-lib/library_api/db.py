"""Database access layer for the RPG Library API."""

import json
import sqlite3
from pathlib import Path


def get_db(db_path: str) -> sqlite3.Connection:
    """Open a read-only connection to the library database."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _parse_tags(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _row_to_summary(row: sqlite3.Row) -> dict:
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


def search_books(conn: sqlite3.Connection, q: str | None = None,
                 q_name: str | None = None,
                 game_system: str | None = None,
                 product_type: str | None = None,
                 publisher: str | None = None,
                 series: str | None = None,
                 source: str | None = None,
                 tags: str | None = None,
                 sort: str | None = None,
                 sort_dir: str | None = None,
                 include_old: bool = False,
                 include_drafts: bool = False,
                 include_duplicates: bool = False,
                 grouped: bool = True,
                 page: int = 1, per_page: int = 50) -> dict:
    """Search and filter books. Returns dict with results, total, pagination info."""
    conditions = []
    if not include_old:
        conditions.append("is_old_version = 0")
    if not include_drafts:
        conditions.append("is_draft = 0")
    if not include_duplicates:
        conditions.append("is_duplicate = 0")
    params = []

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

    where = " AND ".join(conditions) if conditions else "1=1"

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
            f"""SELECT id, display_title, filename, publisher, collection,
                       game_system, product_type, tags, series, source,
                       page_count, has_bookmarks, description
                FROM books WHERE id IN ({placeholders})""",
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
        f"""SELECT id, display_title, filename, publisher, collection,
                   game_system, product_type, tags, series, source,
                   page_count, has_bookmarks, description
            FROM books WHERE {where}
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


def get_books_by_ids(conn: sqlite3.Connection, book_ids: list[int]) -> list[dict]:
    """Fetch multiple books by ID, ordered by filename."""
    if not book_ids:
        return []
    placeholders = ",".join("?" * len(book_ids))
    rows = conn.execute(
        f"""SELECT id, display_title, filename, publisher, collection,
                   game_system, product_type, tags, series, source,
                   page_count, has_bookmarks, description
            FROM books WHERE id IN ({placeholders})
            ORDER BY filename""",
        book_ids,
    ).fetchall()
    return [_row_to_summary(r) for r in rows]


def get_book(conn: sqlite3.Connection, book_id: int) -> dict | None:
    """Get full book detail including bookmarks."""
    row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
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
