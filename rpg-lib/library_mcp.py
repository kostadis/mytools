#!/usr/bin/env python3
"""
RPG Library MCP Server

Exposes the RPG PDF library to Claude via the Model Context Protocol.

Usage (stdio, for Claude Desktop / Claude Code):
    python library_mcp.py [--db rpg_library.db]

Config for Claude Code (~/.claude/claude_code_config.json or settings):
    {
      "mcpServers": {
        "rpg-library": {
          "command": "python",
          "args": ["/path/to/rpg-lib/library_mcp.py", "--db", "/path/to/rpg_library.db"]
        }
      }
    }
"""

import argparse
import json
import sys
from pathlib import Path

import fastmcp

# ── locate the library_api package ───────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from library_api import db as libdb

# ── global DB paths (set from CLI args) ──────────────────────────────────────
_db_path: str = ""
_user_db_path: str = ""

mcp = fastmcp.FastMCP("RPG Library")

_TIER_LEVELS = {1: (1, 4), 2: (5, 10), 3: (11, 16), 4: (17, 20)}


def _conn():
    return libdb.get_db(_db_path, _user_db_path or None)


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def search_books(
    query: str = "",
    title_query: str = "",
    game_system: str = "",
    product_type: str = "",
    publisher: str = "",
    series: str = "",
    tags: str = "",
    tier: int = 0,
    char_level: int = 0,
    sort: str = "",
    sort_dir: str = "asc",
    include_old: bool = False,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    """Search the RPG PDF library.

    Args:
        query: Search across all fields (title, description, tags, publisher, series).
        title_query: Search only in title/filename.
        game_system: Filter to an exact game system (e.g. "D&D 5e", "Pathfinder 2e").
        product_type: Filter to product type (e.g. "Adventure", "Sourcebook", "Rules").
        publisher: Filter to exact publisher name.
        series: Filter to exact series name.
        tags: Comma-separated tags to filter by (e.g. "horror,undead").
        tier: D&D/Pathfinder tier (1–4). Finds adventures whose level range overlaps the tier.
              Tier 1=levels 1–4, Tier 2=5–10, Tier 3=11–16, Tier 4=17–20. Takes precedence over char_level.
        char_level: Specific character level (1–30). Finds adventures covering exactly this level.
        sort: Sort field — one of: title, publisher, game_system, page_count, series.
        sort_dir: "asc" or "desc".
        include_old: Include superseded old versions.
        page: Page number (1-based).
        per_page: Results per page (max 100).
    """
    per_page = min(per_page, 100)
    if tier and tier in _TIER_LEVELS:
        lmin, lmax = _TIER_LEVELS[tier]
    elif char_level:
        lmin = lmax = char_level
    else:
        lmin = lmax = None
    conn = _conn()
    try:
        result = libdb.search_books(
            conn,
            q=query or None,
            q_name=title_query or None,
            game_system=game_system or None,
            product_type=product_type or None,
            publisher=publisher or None,
            series=series or None,
            tags=tags or None,
            level_min=lmin,
            level_max=lmax,
            sort=sort or None,
            sort_dir=sort_dir,
            include_old=include_old,
            include_drafts=False,
            include_duplicates=False,
            grouped=False,
            page=page,
            per_page=per_page,
        )
        books = result["results"]
        return {
            "total": result["total"],
            "page": page,
            "per_page": per_page,
            "total_pages": result["total_pages"],
            "books": [_summarise(b) for b in books],
        }
    finally:
        conn.close()


@mcp.tool()
def get_book(book_id: int) -> dict:
    """Get full details for a single book by its ID.

    Returns title, description, tags, bookmarks (table of contents), publisher,
    game system, series, page count, and related book IDs.
    """
    conn = _conn()
    try:
        book = libdb.get_book(conn, book_id)
        if not book:
            return {"error": f"Book {book_id} not found"}
        d = dict(book)
        # parse tags from JSON string
        if isinstance(d.get("tags"), str):
            try:
                d["tags"] = json.loads(d["tags"])
            except Exception:
                pass
        # parse bookmarks
        if isinstance(d.get("bookmarks"), str):
            try:
                d["bookmarks"] = json.loads(d["bookmarks"])
            except Exception:
                d["bookmarks"] = []
        return d
    finally:
        conn.close()


@mcp.tool()
def get_topic(topic_type: str, topic_name: str) -> dict:
    """Get an overview of a topic (game system, tag, series, or publisher).

    Returns stats (book count, enriched count, product type breakdown, top publishers,
    top tags, top series, top game systems) and the list of books.

    Args:
        topic_type: One of "game_system", "tag", "series", "publisher".
        topic_name: The exact name of the topic (e.g. "D&D 5e", "horror", "Ravenloft").
    """
    valid = {"game_system", "tag", "series", "publisher"}
    if topic_type not in valid:
        return {"error": f"topic_type must be one of {valid}"}
    conn = _conn()
    try:
        data = libdb.get_topic(conn, topic_type, topic_name)
        if data is None:
            return {"error": f"Topic '{topic_name}' not found"}
        # Summarise books to keep response manageable
        data["books"] = [_summarise(b) for b in data["books"]]
        return data
    finally:
        conn.close()


@mcp.tool()
def get_related_books(book_id: int, limit: int = 8) -> list[dict]:
    """Get books related to a given book by tag/content similarity.

    Args:
        book_id: The ID of the book to find relations for.
        limit: Maximum number of related books to return (default 8, max 20).
    """
    limit = min(limit, 20)
    conn = _conn()
    try:
        books = libdb.get_related_books(conn, book_id, limit)
        return [_summarise(b) for b in books]
    finally:
        conn.close()


@mcp.tool()
def list_filters() -> dict:
    """List all available filter values: game systems, product types, publishers,
    series, sources, and tags — each with their book counts.

    Use this to discover what values are valid for search_books filters.
    """
    conn = _conn()
    try:
        return dict(libdb.get_filters(conn))
    finally:
        conn.close()


@mcp.tool()
def get_stats() -> dict:
    """Get overall library statistics: total books, enriched count, top publishers,
    game systems, tags, and product type breakdown.
    """
    conn = _conn()
    try:
        return dict(libdb.get_stats(conn))
    finally:
        conn.close()


@mcp.tool()
def find_books_by_tag(tag: str, limit: int = 30) -> list[dict]:
    """Find all books that have a specific tag.

    Args:
        tag: Exact tag string (e.g. "horror", "one-shot", "hex crawl").
        limit: Max books to return (default 30).
    """
    conn = _conn()
    try:
        result = libdb.search_books(
            conn,
            tags=tag,
            include_old=False,
            include_drafts=False,
            include_duplicates=False,
            grouped=False,
            per_page=min(limit, 200),
        )
        return [_summarise(b) for b in result["results"]]
    finally:
        conn.close()


# ── helper ────────────────────────────────────────────────────────────────────

def _summarise(book) -> dict:
    """Convert a db row / dict to a compact summary."""
    if hasattr(book, "keys"):
        b = dict(book)
    else:
        b = book
    tags = b.get("tags")
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = []
    return {
        "id": b.get("id"),
        "title": b.get("display_title") or b.get("filename"),
        "publisher": b.get("publisher"),
        "game_system": b.get("game_system"),
        "product_type": b.get("product_type"),
        "series": b.get("series"),
        "page_count": b.get("page_count"),
        "tags": tags,
        "description": (b.get("description") or "")[:300] or None,
        "min_level": b.get("min_level"),
        "max_level": b.get("max_level"),
    }


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RPG Library MCP Server")
    parser.add_argument("--db", default="./rpg_library.db", help="Path to SQLite database")
    parser.add_argument("--user-db", default="",
                        help="Path to user_data.db (default: user_data.db alongside --db)")
    args = parser.parse_args()

    global _db_path, _user_db_path
    _db_path = str(Path(args.db).resolve())

    if not Path(_db_path).exists():
        print(f"ERROR: Database not found: {_db_path}", file=sys.stderr)
        sys.exit(1)

    # Default user_data.db to same directory as the main DB
    user_db = args.user_db or str(Path(_db_path).parent / "user_data.db")
    _user_db_path = user_db if Path(user_db).exists() else ""

    print(f"RPG Library MCP: {_db_path}", file=sys.stderr)
    if _user_db_path:
        print(f"  user data: {_user_db_path}", file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    main()
