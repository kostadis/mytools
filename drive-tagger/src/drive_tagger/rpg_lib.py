"""Thin client for the local rpg-lib service.

Used by load_worklist() when DT_RPG_LIB_URL is set to restrict the Drive
worklist to books curated by rpg-lib (canonical, not old/dup/draft).
"""

from __future__ import annotations

import json
import sys
import urllib.request


def load_filenames(base_url: str) -> set[str]:
    """Return all canonical book filenames from rpg-lib (paginated)."""
    url = base_url.rstrip("/")
    filenames: set[str] = set()
    page = 1
    while True:
        with urllib.request.urlopen(
            f"{url}/api/library/search?per_page=500&page={page}", timeout=15
        ) as resp:
            data = json.load(resp)
        for book in data["results"]:
            fn = book.get("filename")
            if fn:
                filenames.add(fn)
        if page >= data["total_pages"]:
            break
        page += 1
    print(f"[rpg-lib] {len(filenames)} canonical filenames loaded", file=sys.stderr)
    return filenames
