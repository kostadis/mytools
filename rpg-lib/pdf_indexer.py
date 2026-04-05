#!/usr/bin/env python3
"""
PDF Library Indexer — Phase 1: TOC/Bookmark Extraction to SQLite

Recursively scans a folder of PDFs and extracts metadata, bookmarks,
and fallback text into a SQLite database using PyMuPDF (fitz).

Usage:
    python pdf_indexer.py /path/to/pdfs /path/to/library.db
"""

import argparse
import os
import re
import sqlite3
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import fitz  # PyMuPDF


DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL UNIQUE,
    relative_path TEXT NOT NULL,
    source TEXT,
    -- Folder hierarchy: derived from path relative to scan root
    publisher TEXT,
    collection TEXT,
    pdf_title TEXT,
    pdf_author TEXT,
    pdf_creator TEXT,
    page_count INTEGER,
    has_bookmarks INTEGER NOT NULL DEFAULT 0,
    is_old_version INTEGER NOT NULL DEFAULT 0,
    version_generation INTEGER,
    is_draft INTEGER NOT NULL DEFAULT 0,
    is_duplicate INTEGER NOT NULL DEFAULT 0,
    product_id TEXT,
    product_version TEXT,
    first_page_text TEXT,
    date_indexed TEXT NOT NULL,
    -- Phase 2 enrichment columns (populated later via Claude API)
    game_system TEXT,
    product_type TEXT,
    description TEXT,
    date_enriched TEXT
);

CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    level INTEGER NOT NULL,
    title TEXT NOT NULL,
    page_number INTEGER,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath TEXT NOT NULL,
    error_message TEXT NOT NULL,
    date_logged TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_books_filepath ON books(filepath);
CREATE INDEX IF NOT EXISTS idx_bookmarks_book_id ON bookmarks(book_id);
CREATE INDEX IF NOT EXISTS idx_errors_filepath ON errors(filepath);
"""


def migrate_db(conn: sqlite3.Connection, scan_root: str, source: str | None) -> None:
    """Add columns that didn't exist in earlier versions of the schema."""
    cursor = conn.execute("PRAGMA table_info(books)")
    existing = {row[1] for row in cursor.fetchall()}

    new_columns = {
        "relative_path": "TEXT NOT NULL DEFAULT ''",
        "source": "TEXT",
        "publisher": "TEXT",
        "collection": "TEXT",
        "is_old_version": "INTEGER NOT NULL DEFAULT 0",
        "version_generation": "INTEGER",
        "is_draft": "INTEGER NOT NULL DEFAULT 0",
        "is_duplicate": "INTEGER NOT NULL DEFAULT 0",
        "product_id": "TEXT",
        "product_version": "TEXT",
    }
    for col, typedef in new_columns.items():
        if col not in existing:
            print(f"  Migrating: adding {col} column...")
            conn.execute(f"ALTER TABLE books ADD COLUMN {col} {typedef}")

    # Backfill relative_path from filepath if any rows are empty
    rows = conn.execute("SELECT id, filepath FROM books WHERE relative_path = ''").fetchall()
    if rows:
        print(f"  Backfilling relative_path for {len(rows)} books...")
        for book_id, filepath in rows:
            rel = os.path.relpath(filepath, scan_root)
            pub, coll = parse_folder_hierarchy(filepath, scan_root)
            conn.execute(
                "UPDATE books SET relative_path=?, publisher=?, collection=? WHERE id=?",
                (rel, pub, coll, book_id),
            )

    # Backfill source for rows that don't have one yet
    if source:
        count = conn.execute(
            "SELECT COUNT(*) FROM books WHERE source IS NULL AND filepath LIKE ?",
            (scan_root + "%",),
        ).fetchone()[0]
        if count:
            print(f"  Backfilling source='{source}' for {count} books...")
            conn.execute(
                "UPDATE books SET source=? WHERE source IS NULL AND filepath LIKE ?",
                (source, scan_root + "%"),
            )

    # Backfill is_old_version and version_generation based on filename pattern
    old_count = conn.execute(
        "SELECT COUNT(*) FROM books WHERE is_old_version = 0 AND filename LIKE '%.old%pdf'"
    ).fetchone()[0]
    if old_count:
        print(f"  Backfilling is_old_version/version_generation for {old_count} books...")
        rows = conn.execute(
            "SELECT id, filename FROM books WHERE is_old_version = 0 AND filename LIKE '%.old%pdf'"
        ).fetchall()
        for book_id, filename in rows:
            is_old, gen = parse_version(filename)
            if is_old:
                conn.execute(
                    "UPDATE books SET is_old_version=1, version_generation=? WHERE id=?",
                    (gen, book_id),
                )

    # Backfill product_id and product_version from filenames
    rows = conn.execute(
        "SELECT id, filename FROM books WHERE product_id IS NULL AND product_version IS NULL"
    ).fetchall()
    backfilled = 0
    for book_id, filename in rows:
        pid, pver = parse_filename_metadata(filename)
        if pid or pver:
            conn.execute(
                "UPDATE books SET product_id=?, product_version=? WHERE id=?",
                (pid, pver, book_id),
            )
            backfilled += 1
    if backfilled:
        print(f"  Backfilling product_id/product_version for {backfilled} books...")

    # Backfill is_draft and is_duplicate from filenames
    draft_rows = conn.execute(
        "SELECT id, filename FROM books WHERE is_draft = 0 AND is_duplicate = 0"
    ).fetchall()
    draft_count = 0
    for book_id, filename in draft_rows:
        is_draft, is_dup = parse_draft_status(filename)
        if is_draft or is_dup:
            conn.execute(
                "UPDATE books SET is_draft=?, is_duplicate=? WHERE id=?",
                (is_draft, is_dup, book_id),
            )
            draft_count += 1
    if draft_count:
        print(f"  Backfilling is_draft/is_duplicate for {draft_count} books...")

    # Create indexes for migrated columns (must happen after columns exist)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_books_source ON books(source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_books_publisher ON books(publisher)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_books_product_id ON books(product_id)")

    conn.commit()


def init_db(db_path: str, scan_root: str, source: str | None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(DB_SCHEMA)
    conn.commit()
    migrate_db(conn, scan_root, source)
    return conn


def get_indexed_paths(conn: sqlite3.Connection) -> set[str]:
    cursor = conn.execute("SELECT filepath FROM books")
    return {row[0] for row in cursor.fetchall()}


def get_errored_paths(conn: sqlite3.Connection) -> set[str]:
    cursor = conn.execute("SELECT DISTINCT filepath FROM errors")
    return {row[0] for row in cursor.fetchall()}


def find_pdfs(folder: str) -> list[str]:
    pdfs = []
    dirs_scanned = 0
    skipped = 0
    for root, dirs, files in os.walk(folder):
        # Skip macOS resource fork directories
        dirs[:] = [d for d in dirs if d != "__MACOSX" and d != "_gsdata_"]
        dirs_scanned += 1
        for f in files:
            if not f.lower().endswith(".pdf"):
                continue
            # Skip macOS resource fork files (._filename.pdf)
            if f.startswith("._"):
                skipped += 1
                continue
            pdfs.append(os.path.join(root, f))
        print(f"\r  Scanning folders... {dirs_scanned} dirs, {len(pdfs)} PDFs found",
              end="", flush=True)
    print()  # newline after progress
    if skipped:
        print(f"  Skipped {skipped} macOS resource fork files")
    pdfs.sort()
    return pdfs


def extract_first_pages_text(doc: fitz.Document, max_pages: int = 2) -> str:
    """Extract text from the first 1-2 pages as fallback content."""
    texts = []
    for i in range(min(max_pages, len(doc))):
        page_text = doc[i].get_text().strip()
        if page_text:
            texts.append(page_text)
    combined = "\n\n".join(texts)
    # Cap at ~4000 chars to keep DB reasonable
    return combined[:4000] if combined else None


def parse_filename_metadata(filename: str) -> tuple[str | None, str | None]:
    """Extract product ID and version from filename.

    Examples:
      1549348-Adaptable_NPCs_(v1.4).pdf      -> ("1549348", "v1.4")
      925821-DDAL-DRW03_(v1.3).pdf            -> ("925821", "v1.3")
      1341626-Manual_(v2_0).pdf               -> ("1341626", "v2_0")
      Battlelords_V1.23_-_MOBILE.pdf          -> (None, "V1.23")
      Optimized_PDF_Monsters_v1.2.pdf         -> (None, "v1.2")
      plain_book.pdf                          -> (None, None)
    """
    # Product ID: numeric prefix before first hyphen
    product_id = None
    m = re.match(r'^(\d{4,})-', filename)
    if m:
        product_id = m.group(1)

    # Version: (vN.N) in parens, or _vN.N / _VN.N outside parens
    product_version = None
    m = re.search(r'\((v[\d._]+)[^)]*\)', filename, re.IGNORECASE)
    if m:
        product_version = m.group(1)
    else:
        m = re.search(r'[_\s](v\d+[\._]\d+(?:\.\d+)?)', filename, re.IGNORECASE)
        if m:
            product_version = m.group(1)

    return product_id, product_version


_DRAFT_KEYWORDS = re.compile(
    r'(?:^|[_\s\-.])'
    r'(draft|preview|playtest|play[_\s]test|beta|wip|proof|alpha|ashcan|pre[_\-]?release|early[_\s]release)'
    r'(?:[_\s\-.]|$)',
    re.IGNORECASE,
)
_DUPLICATE_SUFFIX = re.compile(r'\s*\(\d+\)\.pdf$', re.IGNORECASE)


def parse_draft_status(filename: str) -> tuple[int, int]:
    """Detect draft/WIP files and download duplicates.

    Returns (is_draft, is_duplicate):
      Dragonflight_-_Community_Draft.pdf   -> (1, 0)
      playtest_material_1 (1).pdf          -> (1, 1)  — draft AND duplicate
      EMP_Preview_12-30-22_v1.pdf          -> (1, 0)
      normal_book.pdf                      -> (0, 0)
      normal_book (1).pdf                  -> (0, 1)
    """
    is_draft = int(bool(_DRAFT_KEYWORDS.search(filename)))
    is_duplicate = int(bool(_DUPLICATE_SUFFIX.search(filename)))
    return is_draft, is_duplicate


def parse_version(filename: str) -> tuple[int, int | None]:
    """Detect old versions and assign a generation number.

    Returns (is_old_version, version_generation):
      book.pdf              -> (0, None)   — current version, highest generation
      book.old.pdf          -> (1, 0)      — oldest version
      book.old-001.pdf      -> (1, 1)      — next oldest
      book.old-002.pdf      -> (1, 2)
      book.old-003.pdf      -> (1, 3)      — most recent old version
    """
    m = re.search(r'\.old(?:-(\d+))?\.pdf$', filename, re.IGNORECASE)
    if not m:
        return 0, None
    num = m.group(1)
    generation = int(num) if num is not None else 0
    return 1, generation


def parse_folder_hierarchy(filepath: str, scan_root: str) -> tuple[str | None, str | None]:
    """Derive publisher and collection from the path relative to scan root.

    Given scan_root=/mnt/g/My Drive/Kickstarter:
      .../Kickstarter/2cgaming/Dragonflight/book.pdf
        -> publisher="2cgaming", collection="Dragonflight"
      .../Kickstarter/2cgaming/book.pdf
        -> publisher="2cgaming", collection=None
      .../Kickstarter/book.pdf
        -> publisher=None, collection=None
    """
    rel = os.path.relpath(filepath, scan_root)
    parts = Path(rel).parts  # e.g. ("2cgaming", "Dragonflight", "book.pdf")
    publisher = parts[0] if len(parts) > 1 else None
    # Everything between publisher and filename is the collection path
    collection = str(Path(*parts[1:-1])) if len(parts) > 2 else None
    return publisher, collection


def extract_pdf(filepath: str, scan_root: str, source: str | None) -> dict:
    """Extract all data from a PDF. Runs in a worker process — no DB access."""
    publisher, collection = parse_folder_hierarchy(filepath, scan_root)
    filename = os.path.basename(filepath)
    relative_path = os.path.relpath(filepath, scan_root)
    is_old_version, version_generation = parse_version(filename)
    is_draft, is_duplicate = parse_draft_status(filename)
    product_id, product_version = parse_filename_metadata(filename)

    doc = fitz.open(filepath)
    try:
        meta = doc.metadata or {}
        toc = doc.get_toc(simple=False)
        has_bookmarks = len(toc) > 0

        first_page_text = None
        if not has_bookmarks:
            first_page_text = extract_first_pages_text(doc)

        return {
            "filename": filename,
            "filepath": filepath,
            "relative_path": relative_path,
            "source": source,
            "publisher": publisher,
            "collection": collection,
            "pdf_title": meta.get("title") or None,
            "pdf_author": meta.get("author") or None,
            "pdf_creator": meta.get("creator") or None,
            "page_count": len(doc),
            "has_bookmarks": int(has_bookmarks),
            "is_old_version": is_old_version,
            "version_generation": version_generation,
            "is_draft": is_draft,
            "is_duplicate": is_duplicate,
            "product_id": product_id,
            "product_version": product_version,
            "first_page_text": first_page_text,
            "toc": [(level, title, page) for level, title, page, *_ in toc],
        }
    finally:
        doc.close()


def clear_errors(conn: sqlite3.Connection, filepath: str) -> None:
    """Remove old error entries for a file that has now succeeded."""
    conn.execute("DELETE FROM errors WHERE filepath = ?", (filepath,))


def save_pdf(conn: sqlite3.Connection, data: dict) -> None:
    """Save extracted PDF data to the database. Runs in the main thread."""
    clear_errors(conn, data["filepath"])
    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        """INSERT INTO books
           (filename, filepath, relative_path, source, publisher, collection,
            pdf_title, pdf_author, pdf_creator,
            page_count, has_bookmarks, is_old_version, version_generation,
            is_draft, is_duplicate,
            product_id, product_version, first_page_text, date_indexed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["filename"], data["filepath"], data["relative_path"],
            data["source"], data["publisher"], data["collection"],
            data["pdf_title"], data["pdf_author"], data["pdf_creator"],
            data["page_count"], data["has_bookmarks"],
            data["is_old_version"], data["version_generation"],
            data["is_draft"], data["is_duplicate"],
            data["product_id"], data["product_version"],
            data["first_page_text"], now,
        ),
    )
    book_id = cursor.lastrowid
    if data["toc"]:
        conn.executemany(
            """INSERT INTO bookmarks (book_id, level, title, page_number)
               VALUES (?, ?, ?, ?)""",
            [(book_id, level, title, page) for level, title, page in data["toc"]],
        )
    conn.commit()


def log_error(conn: sqlite3.Connection, filepath: str, error: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO errors (filepath, error_message, date_logged) VALUES (?, ?, ?)",
        (filepath, error, now),
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(
        description="Index PDF bookmarks and metadata into SQLite"
    )
    parser.add_argument("scan_folder", help="Root folder to scan for PDFs")
    parser.add_argument("db_path", help="Path to SQLite database file")
    parser.add_argument(
        "--source",
        help="Source label for these PDFs (e.g. kickstarter, drivethrurpg)",
    )
    parser.add_argument(
        "--reprocess-errors",
        action="store_true",
        help="Re-attempt previously failed PDFs",
    )
    parser.add_argument(
        "--workers", type=int, default=4,
        help="Number of parallel workers (default: 4)",
    )
    args = parser.parse_args()

    scan_folder = os.path.abspath(args.scan_folder)
    if not os.path.isdir(scan_folder):
        print(f"Error: {scan_folder} is not a directory", file=sys.stderr)
        sys.exit(1)

    print(f"Opening database {args.db_path}...")
    source = args.source
    conn = init_db(args.db_path, scan_folder, source)

    print(f"Scanning {scan_folder} for PDFs...")
    all_pdfs = find_pdfs(scan_folder)
    print(f"Found {len(all_pdfs)} PDFs")

    print("Checking for previously indexed files...")
    indexed = get_indexed_paths(conn)
    errored = get_errored_paths(conn) if not args.reprocess_errors else set()
    skip = indexed | errored
    to_process = [p for p in all_pdfs if p not in skip]

    if indexed:
        print(f"Already indexed: {len(indexed)}")
    if errored:
        print(f"Previously errored (skipping): {len(errored)}")
    print(f"To process: {len(to_process)}")

    if not to_process:
        print("Nothing to do.")
        conn.close()
        return

    workers = args.workers
    print(f"Processing with {workers} workers...")

    t0 = time.monotonic()
    success = 0
    failed = 0
    done = 0
    total = len(to_process)

    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_to_path = {
            executor.submit(extract_pdf, fp, scan_folder, source): fp
            for fp in to_process
        }
        for future in as_completed(future_to_path):
            filepath = future_to_path[future]
            rel = os.path.relpath(filepath, scan_folder)
            done += 1
            try:
                data = future.result()
                save_pdf(conn, data)
                success += 1
                status = "ok"
            except Exception as e:
                log_error(conn, filepath, f"{type(e).__name__}: {e}")
                failed += 1
                status = f"ERROR: {e}"

            elapsed = time.monotonic() - t0
            rate = done / elapsed if elapsed > 0 else 0
            print(
                f"[{done}/{total}] {rel}... {status} ({rate:.1f} files/s overall)",
                flush=True,
            )

    elapsed = time.monotonic() - t0
    print(f"\nDone in {elapsed:.1f}s — {success} indexed, {failed} errors")

    # Summary stats
    total_books = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    with_bm = conn.execute(
        "SELECT COUNT(*) FROM books WHERE has_bookmarks=1"
    ).fetchone()[0]
    total_bm = conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0]
    total_err = conn.execute("SELECT COUNT(*) FROM errors").fetchone()[0]
    print(f"Database: {total_books} books ({with_bm} with bookmarks), "
          f"{total_bm} bookmarks, {total_err} errors")

    conn.close()


if __name__ == "__main__":
    main()
