#!/usr/bin/env python3
"""
RPG Library Server — FastAPI backend + Vue SPA frontend.

Usage:
    python library_server.py [--db rpg_library.db] [--port 8000] [--dev]
"""

import argparse
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from library_api import db, routes

app = FastAPI(title="RPG Library", version="1.0.0")

# CORS — allow all origins (local server, Obsidian app://, Vite dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router)

# SPA serving — set up after argument parsing
_frontend_dist: Path | None = None


def setup_spa(frontend_dist: Path) -> None:
    """Mount Vue SPA static files and catch-all route."""
    global _frontend_dist
    _frontend_dist = frontend_dist

    if not frontend_dist.exists():
        print(f"Warning: frontend dist not found at {frontend_dist}")
        print("Run 'cd frontend && npm run build' to build the frontend")
        return

    assets = frontend_dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # Serve index.html for any non-API route — never cache it
        index = frontend_dist / "index.html"
        if index.exists():
            return FileResponse(
                str(index),
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )
        return {"error": "Frontend not built. Run: cd frontend && npm run build"}


def main():
    parser = argparse.ArgumentParser(description="RPG Library Server")
    parser.add_argument("--db", default="./rpg_library.db", help="Path to SQLite database")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    parser.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    parser.add_argument("--user-db", default=None, help="Path to user-data DB (default: alongside --db)")
    parser.add_argument("--dev", action="store_true", help="Development mode (auto-reload)")
    args = parser.parse_args()

    # Derive user-data DB path and ensure schema exists
    user_db_path = args.user_db or str(Path(args.db).parent / "user_data.db")
    db.init_user_db(user_db_path)

    # Set DB paths for routes
    routes.set_db_path(args.db, user_db_path)

    # Set up SPA serving
    frontend_dist = Path(__file__).parent / "frontend" / "dist"
    setup_spa(frontend_dist)

    print(f"RPG Library Server")
    print(f"  Database: {args.db}")
    print(f"  User data: {user_db_path}")
    print(f"  API: http://{args.host}:{args.port}/api/library/")
    print(f"  UI:  http://{args.host}:{args.port}/")

    uvicorn.run(
        "library_server:app" if args.dev else app,
        host=args.host,
        port=args.port,
        reload=args.dev,
    )


if __name__ == "__main__":
    main()
