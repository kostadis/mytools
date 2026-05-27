#!/usr/bin/env python3
"""Symlink-farm 5etools JSON sidecars into a 5etools homebrew directory.

Walks the rpg-lib books table, resolves each book's sibling 5etools-format
JSON via :func:`library_api.sidecar.resolve_fivetools_json`, and creates a
symlink in the target homebrew directory. Rewrites
``<homebrew-dir>/index.json``'s ``toImport`` list to match.

Source of truth stays in the library; 5etools sees a flat directory of
JSON files. Re-run after ingesting new books.

Usage:
    RPG_LIBRARY_ROOT=/path/to/library \\
        python3 fivetools_symlink_farm.py \\
        --db rpg_library.db \\
        --homebrew-dir /path/to/5etools-kostadis/homebrew

Symlinks created by this script are tagged with a ``rpglib_`` filename
prefix so re-runs can clean up stale links and manual homebrew files in
the same directory are left untouched.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from library_api import sidecar

TAG = "rpglib_"


def _link_name(book_id: int, src: Path) -> str:
    return f"{TAG}{book_id:07d}__{src.name}"


def _is_managed(name: str) -> bool:
    return name.startswith(TAG) and name.endswith(".json")


def _symlink_target(link: Path) -> Path | None:
    if not link.is_symlink():
        return None
    try:
        return link.resolve(strict=False)
    except OSError:
        return None


def _load_index(path: Path) -> dict:
    if not path.exists():
        return {"toImport": []}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        sys.exit(f"could not parse {path}: {exc}")


def _write_index(path: Path, index: dict) -> None:
    path.write_text(json.dumps(index, indent="\t") + "\n")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--db",
        default="rpg_library.db",
        help="path to rpg_library.db (default: ./rpg_library.db)",
    )
    p.add_argument(
        "--homebrew-dir",
        required=True,
        type=Path,
        help="target 5etools homebrew/ directory",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without touching disk",
    )
    args = p.parse_args()

    library_root = sidecar.get_library_root()
    if library_root is None:
        sys.exit("RPG_LIBRARY_ROOT not set — set it before running")
    if not library_root.is_dir():
        sys.exit(f"RPG_LIBRARY_ROOT is not a directory: {library_root}")

    homebrew: Path = args.homebrew_dir
    if not homebrew.is_dir():
        sys.exit(f"homebrew dir does not exist: {homebrew}")
    index_path = homebrew / "index.json"

    db_path = args.db
    if not Path(db_path).is_file():
        sys.exit(f"db not found: {db_path}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, filename, relative_path FROM books "
        "WHERE relative_path IS NOT NULL AND relative_path != ''"
    ).fetchall()
    conn.close()

    desired: dict[str, Path] = {}
    skipped = 0
    for row in rows:
        src = sidecar.resolve_fivetools_json(
            {"relative_path": row["relative_path"]}, library_root
        )
        if src is None:
            skipped += 1
            continue
        desired[_link_name(row["id"], src)] = src

    existing_managed = {
        p.name: p for p in homebrew.iterdir() if _is_managed(p.name)
    }

    created = updated = unchanged = removed = 0
    conflicts: list[Path] = []

    for name, src in desired.items():
        link = homebrew / name
        if link.is_symlink():
            cur = _symlink_target(link)
            if cur == src.resolve(strict=False):
                unchanged += 1
                continue
            if not args.dry_run:
                link.unlink()
                link.symlink_to(src)
            updated += 1
        elif link.exists():
            conflicts.append(link)
        else:
            if not args.dry_run:
                link.symlink_to(src)
            created += 1

    for name, link in existing_managed.items():
        if name not in desired:
            if not args.dry_run:
                link.unlink()
            removed += 1

    index = _load_index(index_path)
    raw = index.get("toImport") or []
    manual = [n for n in raw if not (isinstance(n, str) and _is_managed(n))]
    new_to_import = manual + sorted(desired.keys())
    index["toImport"] = new_to_import
    if not args.dry_run:
        _write_index(index_path, index)

    suffix = "  [dry run]" if args.dry_run else ""
    print(
        f"books scanned:   {len(rows)}\n"
        f"with sidecars:   {len(desired)} (skipped {skipped})\n"
        f"symlinks:        created={created} updated={updated} "
        f"unchanged={unchanged} removed={removed}{suffix}\n"
        f"index.json:      {len(new_to_import)} entries "
        f"({len(manual)} manual + {len(desired)} managed){suffix}"
    )
    if conflicts:
        print(
            f"\nWARN: {len(conflicts)} non-symlink path(s) collided with managed names:",
            file=sys.stderr,
        )
        for c in conflicts:
            print(f"  {c}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
