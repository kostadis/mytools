#!/usr/bin/env python3
"""RPGBOT Builder API — FastAPI backend.

Serves class data from rpgbot.db and the static builder.html.

Endpoints:
    GET /api/classes            list all classes (id, name, edition)
    GET /api/classes/{id}       full class data blob + injected meta
    GET /builder.html           the builder view
    GET /                       redirect to /builder.html?class=rogue-2024
"""

import json
import os
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(SCRIPT_DIR, "rpgbot.db")

app = FastAPI(title="RPGBOT Builder", docs_url="/api/docs")


def _db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


# ─── API ─────────────────────────────────────────────────────────────────────

@app.get("/api/classes")
def list_classes():
    """Return all available classes."""
    with _db() as db:
        rows = db.execute(
            "SELECT id, name, edition FROM classes ORDER BY edition, name"
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/classes/{class_id}")
def get_class(class_id: str):
    """Return full data blob for a class, with injected meta key."""
    with _db() as db:
        row = db.execute(
            "SELECT id, name, edition, data FROM classes WHERE id = ?",
            (class_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Class '{class_id}' not found")

    blob = json.loads(row["data"])
    blob["meta"] = {
        "id":      row["id"],
        "name":    row["name"],
        "edition": row["edition"],
    }
    return blob


# ─── Root redirect ────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return RedirectResponse("/builder.html?class=rogue-2024")


# ─── Static files (last, catches everything else) ─────────────────────────────

app.mount("/", StaticFiles(directory=SCRIPT_DIR, html=True), name="static")
