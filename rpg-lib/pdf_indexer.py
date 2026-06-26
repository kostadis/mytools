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
    is_printer_friendly INTEGER NOT NULL DEFAULT 0,
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
        "is_printer_friendly": "INTEGER NOT NULL DEFAULT 0",
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

    # Backfill product_id and product_version from filenames (now also catches
    # bare-dotted DriveThru versions like "Manual_1.0.2.pdf" — see
    # parse_filename_metadata) and the printer-friendly flag.
    backfill_product_metadata(conn)
    backfill_printer_friendly(conn)

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


_PRODUCT_ID_PREFIX_RE = re.compile(r'^\d{4,}-')

# A version token, matched four ways (each in its own capture group):
#   (1) v/ver prefix + digits       -> v1.4, ver1_5, v_2, v2_7_1
#   (2) DriveThru "update<N>"       -> update6, update_3 (BeneBads-style)
#   (3) bare date YYYYMMDD          -> 20191023 (optionally separated)
#   (4) BARE multi-segment dotted   -> 1.0.1, 1.0.2, 1.1 (>= 2 numeric segments)
# DriveThru stamps versions as bare dotted numbers with NO v prefix
# ("Manual_of_the_Planes_1.0.2"), which the old v-only regex missed entirely,
# leaving product_version NULL and every version looking like a distinct product.
# Branch (4) requires >= 2 numeric segments and a non-digit before it, so a single
# bare integer that is real title content ("100 NPCs", "Volume 2") is NOT a
# version. The product-ID prefix is stripped before matching so the numeric ID is
# never mistaken for a version.
_VERSION_TOKEN_RE = re.compile(
    r'v(?:er)?[\s_.\-]?(\d+(?:[._]\d+)*)'                  # (1) v-prefixed
    r'|update[\s_\-]?(\d+)'                                # (2) update<N>
    r'|(?<!\d)(20\d{2})[._\-]?(\d{2})[._\-]?(\d{2})(?!\d)'  # (3) date YYYYMMDD
    r'|(?<!\d)(\d+(?:[._]\d+)+)',                          # (4) bare dotted
    re.I,
)

# Printer-friendly / accessible editions — the cleanest text layer for
# conversion. Mirrors pdf-translators/batch_convert._FMT_PREFERRED_RE. Must NOT
# match "-PF" (Pathfinder conversion); pdf_enricher owns that distinct concept.
_PRINTER_FRIENDLY_RE = re.compile(
    r'printer[\s_\-]?friendly|print[\s_\-]?friendly|printfriendly'
    r'|accessibl?e|screen[\s_\-]?reader',
    re.I,
)

# Format / layout tokens stripped from the title key so the same content in
# different exports collapses to one product. Mirrors batch_convert._FMT_RE
# (+ "digital", a DriveThru export label). Word-bounded English tokens avoid
# mid-word strips ("Rampage", "Shadowdale").
_FORMAT_TOKEN_RE = re.compile(
    r'printer[\s_\-]?friendly|print[\s_\-]?friendly|printfriendly'
    r'|optimi[sz]ed|full[\s_\-]?res|hi[\s_\-]?res|high[\s_\-]?res'
    r'|accessibl?e|compressed|colou?r|phone|image[\s_\-]?only'
    r'|quick[\s_\-]?load|digital'
    r'|low[\s_\-]?res|lowres|screen[\s_\-]?reader|selectable'
    r'|\bspreads?\b|\d+[\s_\-]?page|\bpages?\b|\bhd\b|\bsd\b|\bfinal\b'
    r'|pdf',
    re.I,
)


def parse_version_tuple(filename: str) -> tuple[int, ...]:
    """Comparable version tuple from a filename, or () if it carries no version.

    Strips the extension and product-ID prefix first, then takes the LAST
    version token (so a title's own numbers don't shadow a trailing version).
    Returns () — not (0,) — when there is no version, so callers can tell
    "unversioned" apart from "version 0". Mirrors the proven
    pdf-translators/batch_convert._parse_version logic, extended with the
    update<N> and YYYYMMDD forms.
    """
    name = _PRODUCT_ID_PREFIX_RE.sub('', filename.rsplit('.', 1)[0])
    last = None
    for last in _VERSION_TOKEN_RE.finditer(name):
        pass
    if last is None:
        return ()
    g = last.groups()  # (v, update, year, month, day, bare)
    if g[2] is not None:  # date branch
        return (int(g[2]), int(g[3]), int(g[4]))
    token = g[0] or g[1] or g[5] or ''
    nums = tuple(int(p) for p in re.split(r'[._]', token) if p.isdigit())
    return nums


def parse_printer_friendly(filename: str) -> int:
    """1 if the filename marks a printer-friendly / accessible edition, else 0."""
    return int(bool(_PRINTER_FRIENDLY_RE.search(filename)))


def normalize_title_key(filename: str) -> str:
    """Group key for true variants of ONE product: drop extension, product-ID
    prefix, version tokens, and format tokens, then collapse separators. Two
    files share a key iff they are version/format variants of the same title.
    Mirrors batch_convert._variant_title_key."""
    stem = filename.rsplit('.', 1)[0]
    stem = _PRODUCT_ID_PREFIX_RE.sub('', stem)
    stem = _FORMAT_TOKEN_RE.sub(' ', stem)
    stem = _VERSION_TOKEN_RE.sub(' ', stem)
    stem = re.sub(r'[\(\)\[\]_\-\s.]+', ' ', stem).strip().lower()
    return stem


def parse_filename_metadata(filename: str) -> tuple[str | None, str | None]:
    """Extract product ID and version string from filename.

    Examples:
      1549348-Adaptable_NPCs_(v1.4).pdf      -> ("1549348", "v1.4")
      925821-DDAL-DRW03_(v1.3).pdf            -> ("925821", "v1.3")
      1341626-Manual_(v2_0).pdf               -> ("1341626", "v2_0")
      2327454-Manual_of_the_Planes_1.0.2.pdf  -> ("2327454", "1.0.2")  # bare dotted
      Battlelords_V1.23_-_MOBILE.pdf          -> (None, "V1.23")
      plain_book.pdf                          -> (None, None)
    """
    # Product ID: numeric prefix before first hyphen
    product_id = None
    m = re.match(r'^(\d{4,})-', filename)
    if m:
        product_id = m.group(1)

    # Version: last version token (v-prefixed, bare-dotted, update<N>, or date),
    # stored verbatim for display. Product ID is stripped first so it can't be
    # read as a version.
    product_version = None
    name = _PRODUCT_ID_PREFIX_RE.sub('', filename.rsplit('.', 1)[0])
    last = None
    for last in _VERSION_TOKEN_RE.finditer(name):
        pass
    if last is not None:
        product_version = last.group(0)

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


def backfill_product_metadata(conn: sqlite3.Connection) -> int:
    """(Re)extract product_id / product_version for rows missing either.

    Re-runnable: rows that legitimately have no version keep product_version
    NULL and are re-checked cheaply on each run; only rows whose computed value
    changed are written. Catches bare-dotted DriveThru versions that the old
    v-prefix-only regex left NULL even when product_id was already set."""
    rows = conn.execute(
        "SELECT id, filename, product_id, product_version FROM books "
        "WHERE product_id IS NULL OR product_version IS NULL"
    ).fetchall()
    n = 0
    for book_id, filename, pid0, pver0 in rows:
        pid, pver = parse_filename_metadata(filename)
        if (pid or pver) and (pid, pver) != (pid0, pver0):
            conn.execute(
                "UPDATE books SET product_id=?, product_version=? WHERE id=?",
                (pid, pver, book_id),
            )
            n += 1
    if n:
        print(f"  Backfilling product_id/product_version for {n} books...")
    conn.commit()
    return n


def backfill_printer_friendly(conn: sqlite3.Connection) -> int:
    """Set is_printer_friendly=1 for rows whose filename marks a printer-friendly
    / accessible edition. Re-runnable; only flips 0 -> 1."""
    rows = conn.execute(
        "SELECT id, filename FROM books WHERE is_printer_friendly = 0"
    ).fetchall()
    n = 0
    for book_id, filename in rows:
        if parse_printer_friendly(filename):
            conn.execute(
                "UPDATE books SET is_printer_friendly=1 WHERE id=?", (book_id,)
            )
            n += 1
    if n:
        print(f"  Backfilling is_printer_friendly for {n} books...")
    conn.commit()
    return n


def flag_content_duplicates(conn: sqlite3.Connection, dry_run: bool = False) -> int:
    """Flag phantom duplicates by content fingerprint.

    The same PDF dropped into multiple product folders shows up as multiple
    rows with distinct ``filepath`` values but identical
    ``(filename, page_count, pdf_title, pdf_author)``. The pre-existing
    ``_DUPLICATE_SUFFIX`` regex only catches ``book (1).pdf``-style filenames
    and misses this entire class — typical examples include free-sample PDFs
    and product catalogues that publishers ship inside every product folder.

    Within each ``(filename, page_count, pdf_title, pdf_author)`` cluster
    that has more than one row, the row with the lowest ``id`` is the
    canonical keeper; the rest are flagged ``is_duplicate=1``. Filepath data
    is preserved on every row, so an audit query for "where does this file
    live on disk" still works against the flagged rows.

    Idempotent: only considers rows that are not already flagged. Running
    twice flags zero additional rows.

    Returns the number of rows flagged. With ``dry_run=True``, returns the
    count without writing.
    """
    rows = conn.execute(
        """SELECT id, filename, page_count,
                  COALESCE(pdf_title, '') AS t,
                  COALESCE(pdf_author, '') AS a
           FROM books
           WHERE is_duplicate = 0
           ORDER BY filename, page_count, t, a, id"""
    ).fetchall()

    to_flag: list[int] = []
    cur_key: tuple | None = None
    for row_id, fn, pc, t, a in rows:
        key = (fn, pc, t, a)
        if key != cur_key:
            cur_key = key
            # First row of this cluster — the keeper
            continue
        to_flag.append(row_id)

    if not to_flag or dry_run:
        return len(to_flag)

    # Batch the UPDATE to avoid an unbounded parameter list
    batch_size = 500
    for i in range(0, len(to_flag), batch_size):
        batch = to_flag[i:i + batch_size]
        placeholders = ",".join("?" * len(batch))
        conn.execute(
            f"UPDATE books SET is_duplicate = 1 WHERE id IN ({placeholders})",
            batch,
        )
    conn.commit()
    return len(to_flag)


def elect_latest_versions(
    conn: sqlite3.Connection, dry_run: bool = False
) -> list[tuple[int, str, str | None, str]]:
    """Elect the latest version of each product and mark superseded ones old.

    DriveThru ships many files per product, e.g. ``Manual_of_the_Planes`` at
    ``1.0.1`` / ``1.0.2`` / ``1.1``. Only the newest should surface (and be
    converted). This clusters the current, non-draft, non-duplicate books that
    are NOT already ``.old`` renames, and within each cluster marks every file
    below the highest version ``is_old_version=1``.

    Clustering key is ``(product_id or 'coll:'+collection, normalize_title_key)``
    — product_id PLUS normalized title. This is critical: a DriveThru product_id
    is often a BUNDLE of distinct works (one id can hold 14 different adventures),
    so grouping on product_id alone would mark distinct titles as old. Requiring
    the same normalized title means only true version-variants of the SAME work
    collapse.

    Same-version format variants (``1.1`` vs ``1.1 Quick Load``) share a version
    tuple and are NOT marked old — both stay current; the format choice (prefer
    printer-friendly) is made downstream by the API representative and
    batch_convert. Files with no detectable version are left untouched.

    ``version_generation`` on a flagged row is its rank among the losers (0 = the
    newest loser), distinct from the ``.old``-rename counter (those rows are
    excluded here). Idempotent: already-flagged rows fall out of the WHERE, so a
    second run flags nothing.

    Returns a preview list of ``(id, filename, product_version, winner_filename)``
    for every row it flags. With ``dry_run=True`` it returns the same preview and
    writes nothing.
    """
    from collections import defaultdict

    rows = conn.execute(
        """SELECT id, filename, product_id, collection, product_version
           FROM books
           WHERE is_old_version = 0 AND is_draft = 0 AND is_duplicate = 0
             AND filename NOT LIKE '%.old%pdf'"""
    ).fetchall()

    clusters: dict[tuple, list] = defaultdict(list)
    for row_id, filename, product_id, collection, product_version in rows:
        group_key = product_id if product_id else f"coll:{collection or ''}"
        clusters[(group_key, normalize_title_key(filename))].append(
            (row_id, filename, product_version, parse_version_tuple(filename))
        )

    preview: list[tuple[int, str, str | None, str]] = []
    to_flag: list[tuple[int, int]] = []  # (id, generation)
    for members in clusters.values():
        versioned = [m for m in members if m[3]]  # m[3] = version tuple, () = none
        distinct = {m[3] for m in versioned}
        if len(distinct) < 2:
            continue  # nothing to supersede (one version, or only format variants)
        max_ver = max(distinct)
        winner = max(versioned, key=lambda m: m[3])[1]  # a max-version filename
        losers = sorted((m for m in versioned if m[3] < max_ver),
                        key=lambda m: m[3], reverse=True)
        for gen, (row_id, filename, product_version, _vt) in enumerate(losers):
            to_flag.append((row_id, gen))
            preview.append((row_id, filename, product_version, winner))

    if dry_run or not to_flag:
        return preview

    batch_size = 500
    for i in range(0, len(to_flag), batch_size):
        conn.executemany(
            "UPDATE books SET is_old_version=1, version_generation=? WHERE id=?",
            [(gen, row_id) for row_id, gen in to_flag[i:i + batch_size]],
        )
    conn.commit()
    return preview


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
    is_printer_friendly = parse_printer_friendly(filename)
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
            "is_printer_friendly": is_printer_friendly,
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
            is_draft, is_duplicate, is_printer_friendly,
            product_id, product_version, first_page_text, date_indexed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["filename"], data["filepath"], data["relative_path"],
            data["source"], data["publisher"], data["collection"],
            data["pdf_title"], data["pdf_author"], data["pdf_creator"],
            data["page_count"], data["has_bookmarks"],
            data["is_old_version"], data["version_generation"],
            data["is_draft"], data["is_duplicate"], data["is_printer_friendly"],
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
    parser.add_argument("scan_folder", nargs="?",
                        help="Root folder to scan for PDFs (omit when using "
                             "--dedup-content against an existing DB)")
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
    parser.add_argument(
        "--dedup-content",
        action="store_true",
        help="Flag phantom duplicates by content fingerprint "
             "(filename, page_count, pdf_title, pdf_author) and exit. "
             "Does not scan; runs against the existing DB.",
    )
    parser.add_argument(
        "--recompute-variants",
        action="store_true",
        help="Against the existing DB (no scan): backfill product_version / "
             "is_printer_friendly, then elect the latest version per "
             "(product_id-or-collection, title) and mark superseded files "
             "is_old_version=1. Idempotent. Pair with --dry-run to review first.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --dedup-content or --recompute-variants: report what would "
             "change without writing.",
    )
    args = parser.parse_args()

    if args.dedup_content:
        if not os.path.exists(args.db_path):
            print(f"Error: database not found: {args.db_path}", file=sys.stderr)
            sys.exit(1)
        conn = sqlite3.connect(args.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        n = flag_content_duplicates(conn, dry_run=args.dry_run)
        verb = "Would flag" if args.dry_run else "Flagged"
        print(f"{verb} {n} content-duplicate rows.")
        conn.close()
        return

    if args.recompute_variants:
        if not os.path.exists(args.db_path):
            print(f"Error: database not found: {args.db_path}", file=sys.stderr)
            sys.exit(1)
        conn = sqlite3.connect(args.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        # Ensure the is_printer_friendly column exists, then backfill the
        # metadata the election reads/surfaces. These write regardless of
        # --dry-run (they only populate, never hide); the election is what
        # --dry-run gates.
        existing = {r[1] for r in conn.execute("PRAGMA table_info(books)").fetchall()}
        if "is_printer_friendly" not in existing:
            conn.execute("ALTER TABLE books ADD COLUMN is_printer_friendly "
                         "INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        if not args.dry_run:
            backfill_product_metadata(conn)
            backfill_printer_friendly(conn)
        preview = elect_latest_versions(conn, dry_run=args.dry_run)
        verb = "Would mark" if args.dry_run else "Marked"
        print(f"{verb} {len(preview)} file(s) as superseded (old version):")
        for _bid, fn, pver, winner in preview:
            print(f"  old: {fn}  (v={pver}) -> winner: {winner}")
        conn.close()
        return

    if not args.scan_folder:
        parser.error("scan_folder is required unless --dedup-content or "
                     "--recompute-variants is set")

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

    # Elect the latest version per product so superseded editions are hidden
    # (and not re-converted downstream). Idempotent; safe to run every scan.
    elected = elect_latest_versions(conn)
    if elected:
        print(f"Elected latest versions — marked {len(elected)} superseded "
              f"file(s) as old.")

    # Summary stats
    total_books = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    with_bm = conn.execute(
        "SELECT COUNT(*) FROM books WHERE has_bookmarks=1"
    ).fetchone()[0]
    total_bm = conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0]
    total_err = conn.execute("SELECT COUNT(*) FROM errors").fetchone()[0]
    print(f"Database: {total_books} books ({with_bm} with bookmarks), "
          f"{total_bm} bookmarks, {total_err} errors")

    if success:
        print("\n*** Reminder: the database changed — back it up with "
              "./backup_db.sh (or run the full ./refresh_library.sh) ***")

    conn.close()


if __name__ == "__main__":
    main()
