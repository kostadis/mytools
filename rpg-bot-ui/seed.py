#!/usr/bin/env python3
"""Populate rpgbot.db from JSON files in the data/ directory.

Each file must be named <id>.json where <id> is the identifier
(e.g. rogue-2024, fighter-2024, arcane-trickster-spells).
The JSON structure depends on the type:
- Classes: top-level 'name' and 'edition' keys, plus subclasses, species, etc.
- Spells: 'meta' with name/edition, 'ui' with knownPerLevel, 'spells' with level arrays

Usage:
    python seed.py              — seed all files in data/
    python seed.py rogue-2024  — seed a specific class only
    python seed.py arcane-trickster-spells  — seed spell data
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

    # Determine type and extract metadata
    if 'meta' in blob:
        # Spell data format with meta
        name = blob['meta'].get('name', class_id)
        edition = blob['meta'].get('edition', 'unknown')
    elif 'cantrip' in blob or 'level1' in blob:
        # Spell data format without meta (simpler structure)
        # Infer name from id
        name = class_id.replace('-spells', '').replace('-', ' ').title()
        name = 'Arcane Trickster' if 'arcane-trickster' in class_id else name
        edition = '2024'
        # Wrap in meta for consistency
        blob['meta'] = {'id': class_id, 'name': name, 'edition': edition}
        # knownPerLevel uses string keys matching the data structure
        blob['ui'] = {'knownPerLevel': {'cantrip': 2, 'level1': 2, 'level2': 2, 'level3': 2, 'level4': 2}}
        blob['slots'] = {
            1: 2, 2: 3, 3: 4, 4: 4, 5: 4, 6: 4, 7: 4, 8: 4, 9: 4, 10: 4,
            11: 4, 12: 4, 13: 4, 14: 4, 15: 4, 16: 4, 17: 4, 18: 4, 19: 4, 20: 4
        }
        name = blob['meta']['name']
        edition = blob['meta']['edition']
    else:
        # Class data format
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
