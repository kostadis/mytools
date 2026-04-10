"""FastAPI routes for the RPG Library API."""

import os
import subprocess
import sys

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from . import db
from .models import (
    BookDetail, BookSummary, BookText, FilterOptions, GraphResponse, NlqRequest,
    NlqResponse, SearchResponse, StatsResponse, TopicResponse,
)

router = APIRouter(prefix="/api/library", tags=["library"])

# DB path set by library_server.py at startup
_db_path: str = ""


def set_db_path(path: str) -> None:
    global _db_path
    _db_path = path


def _conn():
    return db.get_db(_db_path)


# ── Search & Browse ───────────────────────────────────────────────────────────

@router.get("/search", response_model=SearchResponse)
def search(
    q: str | None = Query(None, description="Search all fields"),
    q_name: str | None = Query(None, description="Search title/filename only"),
    game_system: str | None = None,
    product_type: str | None = None,
    publisher: str | None = None,
    series: str | None = None,
    source: str | None = None,
    tags: str | None = Query(None, description="Comma-separated tag list"),
    char_level: int | None = Query(None, description="Character level — finds adventures covering this level", ge=1, le=30),
    sort: str | None = Query(None, description="Sort field (e.g. publisher, game_system, page_count)"),
    sort_dir: str | None = Query(None, description="asc or desc"),
    include_old: bool = Query(False, description="Include old versions"),
    include_drafts: bool = Query(False, description="Include drafts/WIP"),
    include_duplicates: bool = Query(False, description="Include download duplicates"),
    grouped: bool = Query(True, description="Group results by collection/folder"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
):
    conn = _conn()
    try:
        return db.search_books(
            conn, q=q, q_name=q_name,
            game_system=game_system, product_type=product_type,
            publisher=publisher, series=series, source=source, tags=tags,
            level_min=char_level,
            level_max=char_level,
            sort=sort, sort_dir=sort_dir,
            include_old=include_old, include_drafts=include_drafts,
            include_duplicates=include_duplicates,
            grouped=grouped,
            page=page, per_page=per_page,
        )
    finally:
        conn.close()


@router.get("/books", response_model=list[BookSummary])
def get_books_by_ids(ids: str = Query(..., description="Comma-separated book IDs")):
    """Fetch multiple books by ID (for expanding variant groups)."""
    try:
        book_ids = [int(i.strip()) for i in ids.split(",") if i.strip()]
    except ValueError:
        return []
    conn = _conn()
    try:
        return db.get_books_by_ids(conn, book_ids)
    finally:
        conn.close()


@router.get("/book/{book_id}", response_model=BookDetail)
def get_book(book_id: int):
    conn = _conn()
    try:
        book = db.get_book(conn, book_id)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")
        return book
    finally:
        conn.close()


@router.get("/book/{book_id}/text", response_model=BookText)
def get_book_text(book_id: int):
    conn = _conn()
    try:
        text = db.get_book_text(conn, book_id)
        if not text:
            raise HTTPException(status_code=404, detail="Book not found")
        return text
    finally:
        conn.close()


# ── Filters & Stats ───────────────────────────────────────────────────────────

@router.get("/filters", response_model=FilterOptions)
def get_filters():
    conn = _conn()
    try:
        return db.get_filters(conn)
    finally:
        conn.close()


@router.get("/stats", response_model=StatsResponse)
def get_stats():
    conn = _conn()
    try:
        return db.get_stats(conn)
    finally:
        conn.close()


# ── PDF Access ────────────────────────────────────────────────────────────────

@router.post("/book/{book_id}/open")
def open_pdf(book_id: int):
    """Launch PDF in desktop app via wslview/xdg-open."""
    conn = _conn()
    try:
        book = db.get_book(conn, book_id)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")
    finally:
        conn.close()

    filepath = book["filepath"]
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"File not found: {filepath}")

    # Use explorer.exe on WSL (wslview often not installed), xdg-open on Linux
    if "microsoft" in os.uname().release.lower():
        # Convert WSL path to Windows path for explorer.exe
        try:
            win_path = subprocess.check_output(
                ["wslpath", "-w", filepath], text=True
            ).strip()
            cmd = ["explorer.exe", win_path]
        except Exception:
            cmd = ["xdg-open", filepath]
    elif sys.platform == "darwin":
        cmd = ["open", filepath]
    else:
        cmd = ["xdg-open", filepath]

    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"status": "ok", "filepath": filepath}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open: {e}")


# ── Wiki / NLQ endpoints ──────────────────────────────────────────────────────

@router.post("/nlq", response_model=NlqResponse)
def nlq_search(body: NlqRequest):
    """Natural language query: parse via Claude Haiku, then run FTS5 + structured search."""
    from .nlq import parse_query
    query_parsed = parse_query(body.query)
    conn = _conn()
    try:
        results = db.nlq_search(
            conn,
            keywords=query_parsed["keywords"],
            game_system=query_parsed["game_system"],
            product_type=query_parsed["product_type"],
            tags=query_parsed["tags"],
            level_min=query_parsed.get("level_min"),
            level_max=query_parsed.get("level_max"),
        )
        return {"query_parsed": query_parsed, "results": results, "total": len(results)}
    finally:
        conn.close()


@router.get("/topic/{topic_type}/{topic_name}", response_model=TopicResponse)
def get_topic(topic_type: str, topic_name: str):
    """Get topic hub page: overview + books for a game_system, tag, series, or publisher."""
    valid_types = {"game_system", "tag", "series", "publisher"}
    if topic_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"topic_type must be one of {valid_types}")
    conn = _conn()
    try:
        data = db.get_topic(conn, topic_type, topic_name)
        if data is None:
            raise HTTPException(status_code=404, detail="Topic not found")
        return data
    finally:
        conn.close()



@router.get("/book/{book_id}/related", response_model=list[BookSummary])
def get_related_books(book_id: int, limit: int = Query(6, ge=1, le=20)):
    """Get related books by tag similarity (uses book_relations if populated)."""
    conn = _conn()
    try:
        return db.get_related_books(conn, book_id, limit)
    finally:
        conn.close()


@router.get("/graph", response_model=GraphResponse)
def get_graph(
    min_score: float = Query(0.25, ge=0.0, le=1.0),
    limit: int = Query(300, ge=10, le=1000),
    game_system: str | None = None,
):
    """Get graph data (nodes + edges) for the D3 force visualization."""
    conn = _conn()
    try:
        return db.get_graph(conn, min_score=min_score, limit=limit, game_system=game_system)
    finally:
        conn.close()


@router.get("/book/{book_id}/pdf")
def stream_pdf(book_id: int):
    """Stream PDF file for browser preview."""
    conn = _conn()
    try:
        book = db.get_book(conn, book_id)
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")
    finally:
        conn.close()

    filepath = book["filepath"]
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"File not found: {filepath}")

    return FileResponse(
        filepath,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )
