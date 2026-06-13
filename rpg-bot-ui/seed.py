#!/usr/bin/env python3
"""Populate rpgbot.db from JSON files in the data/ directory.

Each file must be named <id>.json where <id> is the class identifier
(e.g. rogue-2024, fighter-2024).  The JSON must have top-level keys
'name' and 'edition' (used for the DB columns); everything else is
stored as the data blob.

Usage:
    python seed.py              — seed all files in data/
    python seed.py rogue-2024  — seed a specific class only
"""

import json
import os
import sqlite3
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(SCRIPT_DIR, "rpgbot.db")
DATA_DIR   = os.path.join(SCRIPT_DIR, "data")


def init_db(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS classes (
            id      TEXT PRIMARY KEY,
            name    TEXT NOT NULL,
            edition TEXT NOT NULL,
            data    TEXT NOT NULL
        )
    """)
    db.commit()


def seed_file(db: sqlite3.Connection, path: str, class_id: str) -> None:
    with open(path) as f:
        blob = json.load(f)

    name    = blob.get("name")    or class_id
    edition = blob.get("edition") or "unknown"

    db.execute(
        "INSERT OR REPLACE INTO classes (id, name, edition, data) VALUES (?, ?, ?, ?)",
        (class_id, name, edition, json.dumps(blob)),
    )
    db.commit()
    print(f"  seeded {class_id!r} ({name} · {edition})")


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else None

    db = sqlite3.connect(DB_PATH)
    init_db(db)

    files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
    if target:
        files = [f for f in files if f == f"{target}.json"]
        if not files:
            sys.exit(f"No data file found for {target!r} in {DATA_DIR}/")

    if not files:
        sys.exit(f"No .json files found in {DATA_DIR}/")

    print(f"Seeding {DB_PATH}")
    for fname in sorted(files):
        class_id = fname[:-5]
        seed_file(db, os.path.join(DATA_DIR, fname), class_id)

    db.close()
    print("Done.")


if __name__ == "__main__":
    main()
