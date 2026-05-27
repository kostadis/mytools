"""Sidecar artifacts that live next to a PDF on disk.

The indexer records each book by its path **relative to the scan root** in
``books.relative_path``. To read a sibling artifact (e.g. a 5etools-format
JSON produced by an external converter and stored next to the PDF), the
runtime needs the scan root re-supplied as configuration — the DB itself
is portable across machines and does not embed it.

The root is set at process start from the ``RPG_LIBRARY_ROOT`` environment
variable. If unset, sidecar lookups return ``None`` (callers should treat
that as "not configured").
"""

from __future__ import annotations

import os
from pathlib import Path


def get_library_root() -> Path | None:
    """Return the configured library root, or ``None`` if unset/blank."""
    root = os.environ.get("RPG_LIBRARY_ROOT", "").strip()
    return Path(root) if root else None


def resolve_fivetools_json(book: dict, library_root: Path | None) -> Path | None:
    """Resolve the 5etools-format JSON sibling for a book.

    Returns the path if it exists on disk, else ``None``. Returns ``None``
    when the library root is unconfigured or the book lacks a
    ``relative_path``.
    """
    if library_root is None:
        return None
    rel = book.get("relative_path")
    if not rel:
        return None
    pdf = library_root / rel
    candidate = pdf.parent / f"{pdf.stem}.json"
    return candidate if candidate.is_file() else None
