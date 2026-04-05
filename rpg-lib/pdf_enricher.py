#!/usr/bin/env python3
"""
PDF Library Enricher — Phase 2: Claude API Classification

Reads the SQLite database created by pdf_indexer.py and uses the Claude API
to classify each book with game system, product type, tags, series, and description.

Usage:
    python pdf_enricher.py rpg_library.db
    python pdf_enricher.py rpg_library.db --dry-run --limit 10
    python pdf_enricher.py rpg_library.db --series-pass
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone

# lib/ lives in the parent mytools/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from lib.claudelib import make_client, call_api

DEFAULT_MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """\
You are classifying tabletop RPG PDF products. For each book, determine:

1. **game_system**: The RPG system this product is for. Use one of:
   D&D 5e, D&D 5e 2024, D&D 3.5e, D&D 4e, AD&D, OD&D, Pathfinder 1e, Pathfinder 2e,
   Call of Cthulhu, Savage Worlds, OSR, Fate, GURPS, Cypher System,
   Year Zero Engine, Powered by the Apocalypse, Blades in the Dark,
   Shadow of the Demon Lord, 13th Age, Dungeon Crawl Classics,
   System Neutral, Universal, Multiple Systems, Other: <name>

2. **product_type**: The primary classification. Use exactly one of:
   adventure, sourcebook, bestiary, magic_items, character_options,
   gm_aid, map_pack, character_sheet, setting, anthology, non_rpg

3. **tags**: A JSON array of tags. Use ONLY tags from the lists below — do not invent
   new tags outside these lists.

   Product type tags (include the matching one):
     adventure, sourcebook, bestiary, magic_items, character_options, gm_aid,
     map_pack, character_sheet, setting, anthology, non_rpg

   Content tags (include all that apply):
     monsters, encounters, combat, traps, dragons,
     spells, subclasses, feats, races, classes, backgrounds, skills, equipment, weapons, vehicles,
     npc, factions, lore, worldbuilding, treasure, random_tables, rules,
     dungeon, wilderness, urban, naval, planar, maps, battlemaps, hexcrawl, sandbox, mega_dungeon,
     handouts, tokens, miniatures, player_aid, fillable, character_sheet, print_and_play, cards,
     one_shot, campaign, solo_play, organized_play, quickstart,
     crafting, character_creation, names, locations, undead, lair,
     horror, sci_fi, steampunk, humor, historical, mystery, dark_fantasy, cyberpunk

   System tags (include one if applicable):
     5e, 5e_2024, 3_5e, 4e, ad_d, od_d, pf1e, pf2e, coc, savage_worlds,
     osr, fate, gurps, cypher, year_zero, pbta, blades, dcc, 13th_age,
     shadow_demon_lord, castles_and_crusades, zweihander, mothership, alien_rpg,
     dragonbane, dungeon_world, vtm, 2d20, conan, iron_kingdoms, tinyd6, dune,
     system_neutral

4. **series**: If this book is clearly part of a named series, provide the series name.
   Use null if not part of a series or if uncertain.

5. **description**: A 1-2 sentence summary of what this product contains.

6. **display_title**: A clean, human-readable title for this product. Derive it from
   the best available source: the collection folder name, pdf_title, or filename.
   Remove underscores, file extensions, product IDs, version numbers, and encoding
   artifacts. The result should be what you'd see on a bookshelf.
   Examples: "Dungeon Dressing: Altars 2.0 (5e)", "Zareth's Book of Hidden Ways",
   "Delta Green: Agent's Handbook".

Respond with ONLY a JSON array. Each element must have these fields:
  book_id, game_system, product_type, tags, series, description, display_title

Example response:
[
  {"book_id": 1, "game_system": "D&D 5e", "product_type": "character_options",
   "tags": ["character_options", "subclasses", "5e"], "series": null,
   "description": "A collection of homebrew subclasses for all 12 core classes.",
   "display_title": "Zareth's Book of Hidden Ways"},
  {"book_id": 2, "game_system": "System Neutral", "product_type": "gm_aid",
   "tags": ["gm_aid", "random_tables", "dungeon", "system_neutral"],
   "series": "Dungeon Dressing",
   "description": "Random tables for dressing dungeon altars with flavor and loot.",
   "display_title": "Dungeon Dressing: Altars 2.0 (5e)"}
]
"""

SERIES_SYSTEM_PROMPT = """\
You are analyzing RPG PDF products from a single publisher to identify series groupings.

A "series" is a set of products that share a common prefix or naming pattern and are
clearly related (e.g. "Dungeon Dressing: Altars", "Dungeon Dressing: Bridges" belong
to the "Dungeon Dressing" series).

Given a list of filenames/titles from one publisher, identify all series and which
books belong to each. Only group books when the series relationship is clear from
the naming pattern.

Respond with ONLY a JSON object mapping series names to arrays of book IDs:
{"Dungeon Dressing": [101, 102, 103], "Village Backdrop": [201, 202]}

If no series are detected, respond with: {}
"""

VALID_PRODUCT_TYPES = {
    "adventure", "sourcebook", "bestiary", "magic_items", "character_options",
    "gm_aid", "map_pack", "character_sheet", "setting", "anthology", "non_rpg",
}

# Canonical tag vocabulary — all valid tags after normalization
CANONICAL_TAGS = {
    # product types
    "adventure", "sourcebook", "bestiary", "magic_items", "character_options",
    "gm_aid", "map_pack", "character_sheet", "setting", "anthology", "non_rpg",
    "quickstart",
    # content — creatures & combat
    "monsters", "encounters", "combat", "traps", "dragons",
    # content — character
    "spells", "subclasses", "feats", "races", "classes", "backgrounds",
    "skills", "equipment", "weapons", "vehicles",
    # content — world
    "npc", "factions", "lore", "worldbuilding", "treasure",
    "random_tables", "rules",
    # content — environment
    "dungeon", "wilderness", "urban", "naval", "planar",
    "maps", "battlemaps", "hexcrawl", "sandbox", "mega_dungeon",
    # content — player aids
    "handouts", "tokens", "miniatures", "player_aid",
    "fillable", "character_sheet", "print_and_play", "cards",
    # content — misc
    "crafting", "character_creation", "names", "locations", "undead", "lair",
    "organized_play",
    # content — format
    "one_shot", "campaign", "solo_play",
    # genre
    "horror", "sci_fi", "steampunk", "humor", "historical",
    "mystery", "dark_fantasy", "cyberpunk",
    # systems
    "5e", "5e_2024", "3_5e", "4e", "ad_d", "od_d",
    "pf1e", "pf2e", "coc", "savage_worlds", "osr", "fate", "gurps",
    "cypher", "year_zero", "pbta", "blades", "dcc", "13th_age",
    "shadow_demon_lord", "system_neutral",
    "castles_and_crusades", "zweihander", "mothership", "alien_rpg",
    "dragonbane", "dungeon_world", "vtm", "2d20", "conan", "iron_kingdoms",
    "tinyd6", "dune",
    # D&D settings
    "forgotten_realms", "greyhawk", "eberron", "ravenloft", "spelljammer",
    "planescape", "dragonlance", "icewind_dale", "underdark", "waterdeep",
    # special
    "low_confidence",
}

# Aliases: raw tag → canonical tag
TAG_ALIASES = {
    # system variants
    "d&d5e": "5e", "dnd5e": "5e", "dnd 5e": "5e", "d&d 5e": "5e",
    "5th edition": "5e", "fifth edition": "5e", "dnd": "5e",
    "d&d5e_2024": "5e_2024", "dnd2024": "5e_2024", "one d&d": "5e_2024",
    "d&d 3.5e": "3_5e", "3.5e": "3_5e", "d&d3.5": "3_5e", "dnd3.5": "3_5e",
    "3_5": "3_5e", "3rd edition": "3_5e",
    "d&d 4e": "4e", "dnd4e": "4e", "4th edition": "4e",
    "ad&d": "ad_d", "advanced d&d": "ad_d", "advanced_dungeons_and_dragons": "ad_d",
    "od&d": "od_d", "original d&d": "od_d",
    "pathfinder": "pf1e", "pathfinder 1e": "pf1e", "pf": "pf1e", "pf1": "pf1e",
    "pathfinder 2e": "pf2e", "pathfinder2e": "pf2e", "pf2": "pf2e",
    "call of cthulhu": "coc", "call_of_cthulhu": "coc", "cthulhu": "coc",
    "savageworlds": "savage_worlds", "sw": "savage_worlds",
    "powered by the apocalypse": "pbta", "pba": "pbta",
    "dungeon world": "dungeon_world",
    "blades in the dark": "blades",
    "dungeon crawl classics": "dcc",
    "shadow of the demon lord": "shadow_demon_lord",
    "year zero engine": "year_zero", "year_zero_engine": "year_zero",
    "cypher system": "cypher", "cypher_system": "cypher",
    "universal": "system_neutral",
    # content variants
    "monster": "monsters", "creature": "monsters", "creatures": "monsters",
    "spell": "spells", "magic": "spells",
    "subclass": "subclasses",
    "feat": "feats",
    "race": "races", "ancestry": "races", "ancestries": "races",
    "class": "classes",
    "map": "maps", "battle_map": "battlemaps", "battle map": "battlemaps",
    "random_table": "random_tables", "tables": "random_tables", "table": "random_tables",
    "npcs": "npc",
    "encounter": "encounters",
    "dungeons": "dungeon",
    "city": "urban", "town": "urban",
    "sea": "naval", "ocean": "naval", "nautical": "naval",
    "sci-fi": "sci_fi", "scifi": "sci_fi", "science_fiction": "sci_fi",
    "steam_punk": "steampunk",
    "token": "tokens",
    "handout": "handouts",
    "one-shot": "one_shot", "oneshot": "one_shot",
    "megadungeon": "mega_dungeon",
    "hex_crawl": "hexcrawl", "hex crawl": "hexcrawl",
    "print and play": "print_and_play",
    "world_building": "worldbuilding",
    "loot": "treasure",
    "weapon": "weapons",
    "vehicle": "vehicles",
    "faction": "factions",
    "adventures": "adventure",
    "pregenerated": "player_aid", "pregenerated_characters": "player_aid",
    "cheatsheet": "player_aid", "reference": "player_aid",
    "dark fantasy": "dark_fantasy",
    "solo play": "solo_play",
    "castles & crusades": "castles_and_crusades",
    "vampire the masquerade": "vtm", "vampire: the masquerade": "vtm",
    "tiny_d6": "tinyd6", "tiny d6": "tinyd6",
    "alien rpg": "alien_rpg",
}


# ── Tag Normalization ─────────────────────────────────────────────────────────

def normalize_tag(tag: str) -> str | None:
    """Map a raw tag to its canonical form, or None if it should be dropped."""
    t = tag.strip().lower().replace(" ", "_").replace("-", "_")
    if t in CANONICAL_TAGS:
        return t
    if t in TAG_ALIASES:
        return TAG_ALIASES[t]
    # Try the un-underscored alias lookup too
    t2 = t.replace("_", " ")
    if t2 in TAG_ALIASES:
        return TAG_ALIASES[t2]
    return None  # drop unrecognized tags


def normalize_tags_in_db(conn: sqlite3.Connection, dry_run: bool = False,
                         min_count: int = 15) -> None:
    """Normalize tags: apply aliases, then drop tags appearing fewer than min_count times."""
    rows = conn.execute(
        "SELECT id, tags FROM books WHERE tags IS NOT NULL"
    ).fetchall()

    # First pass: compute frequency of each normalized tag across all books
    freq: dict[str, int] = {}
    parsed: list[tuple[int, list[str]]] = []
    for book_id, raw in rows:
        try:
            original = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        normalized_tags = []
        seen: set[str] = set()
        for tag in original:
            canon = normalize_tag(tag)
            if canon and canon not in seen:
                normalized_tags.append(canon)
                seen.add(canon)
                freq[canon] = freq.get(canon, 0) + 1
            elif not canon:
                # Count raw tags that didn't alias to anything
                raw_norm = tag.strip().lower().replace(" ", "_").replace("-", "_")
                freq[raw_norm] = freq.get(raw_norm, 0) + 1
        parsed.append((book_id, normalized_tags))

    # Determine which tags to keep: canonical list OR frequent enough
    keep = CANONICAL_TAGS | {t for t, c in freq.items() if c >= min_count}

    # Second pass: filter each book's tags
    updated = 0
    dropped_counts: dict[str, int] = {}
    for book_id, normalized_tags in parsed:
        final = [t for t in normalized_tags if t in keep]
        dropped = [t for t in normalized_tags if t not in keep]
        for t in dropped:
            dropped_counts[t] = dropped_counts.get(t, 0) + 1

        # Compare to original stored value
        original_raw = next(raw for bid, raw in rows if bid == book_id)
        if json.dumps(final, ensure_ascii=False) != original_raw:
            updated += 1
            if not dry_run:
                conn.execute(
                    "UPDATE books SET tags = ? WHERE id = ?",
                    (json.dumps(final, ensure_ascii=False), book_id),
                )

    if not dry_run:
        conn.commit()

    kept_distinct = len(keep & set(freq.keys()))
    print(f"Normalized {updated} books — {kept_distinct} distinct tags kept "
          f"(min_count={min_count})")
    if dropped_counts:
        top_dropped = sorted(dropped_counts.items(), key=lambda x: -x[1])[:20]
        print(f"Dropped {len(dropped_counts)} rare tags. Top:")
        for tag, count in top_dropped:
            print(f"  {count:4d}x  {tag!r}")


# ── Schema Migration ─────────────────────────────────────────────────────────

def migrate_enrichment_schema(conn: sqlite3.Connection) -> None:
    """Add enrichment columns if they don't exist yet."""
    cursor = conn.execute("PRAGMA table_info(books)")
    existing = {row[1] for row in cursor.fetchall()}

    new_columns = {
        "tags": "TEXT",
        "series": "TEXT",
        "display_title": "TEXT",
    }
    for col, typedef in new_columns.items():
        if col not in existing:
            print(f"  Migrating: adding {col} column...")
            conn.execute(f"ALTER TABLE books ADD COLUMN {col} {typedef}")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_books_game_system ON books(game_system)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_books_product_type ON books(product_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_books_series ON books(series)")
    conn.commit()


# ── Data Queries ──────────────────────────────────────────────────────────────

def get_unenriched_books(conn: sqlite3.Connection, publisher: str | None = None,
                         limit: int | None = None,
                         force: bool = False) -> list[dict]:
    """Get books that haven't been enriched yet, ordered by publisher for batching."""
    where = "WHERE is_old_version = 0"
    params = []
    if not force:
        where += " AND date_enriched IS NULL"
    if publisher:
        where += " AND publisher = ?"
        params.append(publisher)

    query = f"""
        SELECT id, filename, publisher, collection, pdf_title, pdf_author,
               has_bookmarks, first_page_text
        FROM books {where}
        ORDER BY publisher, collection, filename
    """
    if limit:
        query += f" LIMIT {limit}"

    books = []
    for row in conn.execute(query, params):
        book = {
            "id": row[0], "filename": row[1], "publisher": row[2],
            "collection": row[3], "pdf_title": row[4], "pdf_author": row[5],
            "has_bookmarks": row[6], "first_page_text": row[7],
        }
        # Get bookmark titles
        if book["has_bookmarks"]:
            bm_rows = conn.execute(
                "SELECT level, title FROM bookmarks WHERE book_id = ? ORDER BY id LIMIT 50",
                (book["id"],),
            ).fetchall()
            book["bookmarks"] = [(r[0], r[1]) for r in bm_rows]
        else:
            book["bookmarks"] = []
        books.append(book)
    return books


def get_books_for_series(conn: sqlite3.Connection,
                         min_books: int = 5) -> dict[str, list[dict]]:
    """Get books grouped by publisher for series detection, only publishers with enough books."""
    query = """
        SELECT id, filename, collection, pdf_title, publisher
        FROM books
        WHERE is_old_version = 0 AND publisher IS NOT NULL
        ORDER BY publisher, filename
    """
    by_publisher: dict[str, list[dict]] = {}
    for row in conn.execute(query):
        pub = row[4]
        if pub not in by_publisher:
            by_publisher[pub] = []
        by_publisher[pub].append({
            "id": row[0], "filename": row[1],
            "collection": row[2], "pdf_title": row[3],
        })
    return {pub: books for pub, books in by_publisher.items() if len(books) >= min_books}


# ── Prompt Building ───────────────────────────────────────────────────────────

def build_book_summary(book: dict) -> str:
    """Format one book's data for inclusion in the batch prompt."""
    lines = [f"[Book {book['id']}]"]
    lines.append(f"  filename: {book['filename']}")
    if book["publisher"]:
        lines.append(f"  publisher: {book['publisher']}")
    if book["collection"]:
        lines.append(f"  collection: {book['collection']}")
    if book["pdf_title"]:
        lines.append(f"  pdf_title: {book['pdf_title']}")
    if book["pdf_author"]:
        lines.append(f"  pdf_author: {book['pdf_author']}")

    if book["bookmarks"]:
        titles = [f"{'  ' * (level - 1)}{title}" for level, title in book["bookmarks"]]
        lines.append(f"  bookmarks ({len(titles)}):")
        for t in titles:
            lines.append(f"    {t}")
    elif book["first_page_text"]:
        text = book["first_page_text"][:1500]
        lines.append(f"  first_page_text: {text}")
    else:
        lines.append("  (no bookmarks or text available)")

    return "\n".join(lines)


def build_series_prompt(publisher: str, books: list[dict]) -> str:
    """Build the user message for series detection."""
    lines = [f"Publisher: {publisher}", f"Books ({len(books)}):", ""]
    for book in books:
        title = book["pdf_title"] or book["collection"] or book["filename"]
        lines.append(f"  [Book {book['id']}] {title}")
    return "\n".join(lines)


# ── Response Parsing ──────────────────────────────────────────────────────────

def parse_json_response(text: str) -> list | dict:
    """Parse JSON from Claude's response, stripping markdown fences if present."""
    text = text.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return json.loads(text)


def validate_enrichment(entry: dict, low_confidence_ids: set[int] | None = None) -> dict | None:
    """Validate and normalize a single enrichment entry. Returns None if invalid."""
    required = {"book_id", "game_system", "product_type", "tags", "description"}
    if not all(k in entry for k in required):
        return None

    # Normalize product_type
    pt = entry["product_type"]
    if pt not in VALID_PRODUCT_TYPES:
        # Try fuzzy match
        for valid in VALID_PRODUCT_TYPES:
            if valid in pt.lower().replace(" ", "_"):
                pt = valid
                break
        else:
            pt = "sourcebook"  # safe fallback
    entry["product_type"] = pt

    # Ensure tags is a list
    if not isinstance(entry.get("tags"), list):
        entry["tags"] = [pt]

    # Flag books with no bookmarks or text as low confidence
    if low_confidence_ids and entry["book_id"] in low_confidence_ids:
        if "low_confidence" not in entry["tags"]:
            entry["tags"].append("low_confidence")

    # series can be null/None
    if "series" not in entry:
        entry["series"] = None

    # display_title defaults to None if not provided
    if "display_title" not in entry:
        entry["display_title"] = None

    return entry


# ── Database Writes ───────────────────────────────────────────────────────────

def save_enrichments(conn: sqlite3.Connection, enrichments: list[dict]) -> int:
    """Save enrichment results to the database. Returns count of updated rows."""
    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    for entry in enrichments:
        tags_json = json.dumps(entry["tags"], ensure_ascii=False)
        conn.execute(
            """UPDATE books SET
                game_system = ?, product_type = ?, tags = ?,
                series = ?, description = ?, display_title = ?,
                date_enriched = ?
               WHERE id = ?""",
            (
                entry["game_system"], entry["product_type"], tags_json,
                entry.get("series"), entry["description"],
                entry.get("display_title"), now,
                entry["book_id"],
            ),
        )
        updated += 1
    conn.commit()
    return updated


def save_series(conn: sqlite3.Connection, series_map: dict[str, list[int]]) -> int:
    """Save series detection results. Returns count of updated rows."""
    updated = 0
    for series_name, book_ids in series_map.items():
        conn.execute(
            "UPDATE books SET series = ? WHERE id IN ({})".format(
                ",".join("?" * len(book_ids))
            ),
            [series_name] + book_ids,
        )
        updated += len(book_ids)
    conn.commit()
    return updated


def log_error(conn: sqlite3.Connection, context: str, error: str) -> None:
    """Log an enrichment error."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO errors (filepath, error_message, date_logged) VALUES (?, ?, ?)",
        (f"enrichment:{context}", error, now),
    )
    conn.commit()


# ── Main Logic ────────────────────────────────────────────────────────────────

def enrich_books(client, conn: sqlite3.Connection, books: list[dict],
                 model: str, batch_size: int, dry_run: bool) -> None:
    """Run enrichment pass on a list of books."""
    total = len(books)
    done = 0
    success = 0
    failed = 0
    t0 = time.monotonic()

    # Process in batches
    for i in range(0, total, batch_size):
        batch = books[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size
        publisher = batch[0]["publisher"] or "unknown"

        summaries = [build_book_summary(b) for b in batch]
        user_msg = "\n\n".join(summaries)

        if dry_run:
            print(f"\n[Batch {batch_num}/{total_batches}] Publisher: {publisher} "
                  f"({len(batch)} books)")
            print("-" * 60)
            print(user_msg[:2000])
            if len(user_msg) > 2000:
                print(f"  ... ({len(user_msg)} chars total)")
            print("-" * 60)
            done += len(batch)
            continue

        print(f"[Batch {batch_num}/{total_batches}] {publisher} ({len(batch)} books)...",
              end=" ", flush=True)

        # Track which books have no bookmarks or text
        low_confidence_ids = {
            b["id"] for b in batch
            if not b["bookmarks"] and not b["first_page_text"]
        }

        try:
            response_text = call_api(client, SYSTEM_PROMPT, user_msg, model)
            results = parse_json_response(response_text)

            if not isinstance(results, list):
                raise ValueError(f"Expected JSON array, got {type(results).__name__}")

            enrichments = []
            for entry in results:
                validated = validate_enrichment(entry, low_confidence_ids)
                if validated:
                    enrichments.append(validated)

            saved = save_enrichments(conn, enrichments)
            success += saved
            done += len(batch)

            elapsed = time.monotonic() - t0
            rate = done / elapsed if elapsed > 0 else 0
            print(f"{saved}/{len(batch)} enriched ({rate:.1f} books/s)", flush=True)

        except Exception as e:
            book_ids = [b["id"] for b in batch]
            log_error(conn, f"batch:{book_ids[0]}-{book_ids[-1]}", f"{type(e).__name__}: {e}")
            failed += len(batch)
            done += len(batch)
            print(f"ERROR: {e}", flush=True)

        # Small delay between batches to be a good API citizen
        if not dry_run:
            time.sleep(0.5)

    elapsed = time.monotonic() - t0
    print(f"\nEnrichment done in {elapsed:.1f}s — {success} enriched, {failed} failed")


def detect_all_series(client, conn: sqlite3.Connection, model: str,
                      dry_run: bool) -> None:
    """Run series detection pass across all publishers."""
    publishers = get_books_for_series(conn)
    print(f"Series detection: {len(publishers)} publishers with 5+ books")

    total_updated = 0
    for i, (publisher, books) in enumerate(publishers.items(), 1):
        user_msg = build_series_prompt(publisher, books)

        if dry_run:
            print(f"\n[{i}/{len(publishers)}] {publisher} ({len(books)} books)")
            print(user_msg[:1000])
            continue

        print(f"[{i}/{len(publishers)}] {publisher} ({len(books)} books)...",
              end=" ", flush=True)

        try:
            response_text = call_api(client, SERIES_SYSTEM_PROMPT, user_msg, model)
            series_map = parse_json_response(response_text)

            if not isinstance(series_map, dict):
                raise ValueError(f"Expected JSON object, got {type(series_map).__name__}")

            if series_map:
                updated = save_series(conn, series_map)
                total_updated += updated
                print(f"{len(series_map)} series, {updated} books tagged", flush=True)
            else:
                print("no series detected", flush=True)

        except Exception as e:
            log_error(conn, f"series:{publisher}", f"{type(e).__name__}: {e}")
            print(f"ERROR: {e}", flush=True)

        time.sleep(0.5)

    print(f"\nSeries detection done — {total_updated} books tagged")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Enrich RPG PDF database with Claude API classification"
    )
    parser.add_argument("db_path", help="Path to SQLite database file")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model (default: {DEFAULT_MODEL})")
    parser.add_argument("--batch-size", type=int, default=10, help="Books per API call (default: 10)")
    parser.add_argument("--publisher", help="Only enrich books from this publisher")
    parser.add_argument("--limit", type=int, help="Max books to enrich")
    parser.add_argument("--series-pass", action="store_true", help="Run series detection only")
    parser.add_argument("--normalize-tags", action="store_true",
                        help="Normalize existing tags to canonical vocabulary (no API calls)")
    parser.add_argument("--min-count", type=int, default=15,
                        help="Min occurrences for a tag to survive normalization (default: 15)")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts without calling API")
    parser.add_argument("--force", action="store_true", help="Re-enrich already-enriched books")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    print(f"Opening database {args.db_path}...")
    migrate_enrichment_schema(conn)

    if args.normalize_tags:
        normalize_tags_in_db(conn, dry_run=args.dry_run, min_count=args.min_count)
        conn.close()
        return

    if args.series_pass:
        client = None if args.dry_run else make_client()
        detect_all_series(client, conn, args.model, args.dry_run)
    else:
        books = get_unenriched_books(conn, args.publisher, args.limit, args.force)
        print(f"Books to enrich: {len(books)}")
        if not books:
            print("Nothing to do.")
            conn.close()
            return

        client = None if args.dry_run else make_client()
        enrich_books(client, conn, books, args.model, args.batch_size, args.dry_run)

    # Summary
    total = conn.execute("SELECT COUNT(*) FROM books WHERE is_old_version=0").fetchone()[0]
    enriched = conn.execute("SELECT COUNT(*) FROM books WHERE date_enriched IS NOT NULL").fetchone()[0]
    with_series = conn.execute("SELECT COUNT(*) FROM books WHERE series IS NOT NULL").fetchone()[0]
    print(f"\nDatabase: {enriched}/{total} enriched, {with_series} with series")

    conn.close()


if __name__ == "__main__":
    main()
