"""
generate_obsidian.py — Generate an Obsidian wiki vault from the RPG library DB.

Each topic (game system, tag, series, publisher) gets a Markdown page with:
  - YAML frontmatter
  - Static [[wikilinks]] to related topics
  - A dataviewjs block that calls the local API for live stats + book list

Books are NOT given individual pages — clicking a book title opens the web tool.

Usage:
  python generate_obsidian.py rpg_library.db /path/to/vault
  python generate_obsidian.py rpg_library.db /path/to/vault --api-url http://localhost:8000
  python generate_obsidian.py rpg_library.db /path/to/vault --min-tag-books 50
"""

import argparse
import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path


# ── Filename sanitisation ─────────────────────────────────────────────────────

def safe_filename(name: str) -> str:
    """Return a filesystem-safe filename (no extension)."""
    # Replace characters invalid on Windows (Google Drive is Windows-mounted)
    name = re.sub(r'[\\/:*?"<>|]', '-', name)
    name = re.sub(r'-+', '-', name).strip('-').strip()
    return name or 'unnamed'


def wikilink(name: str, display: str | None = None) -> str:
    """Return an Obsidian [[wikilink]], optionally with display text."""
    safe = safe_filename(name)
    if display and display != safe:
        return f"[[{safe}|{display}]]"
    return f"[[{safe}]]"


# ── DB queries ────────────────────────────────────────────────────────────────

def get_game_systems(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    rows = conn.execute(
        """SELECT game_system, COUNT(*) n FROM books
           WHERE game_system IS NOT NULL AND is_old_version=0
             AND is_draft=0 AND is_duplicate=0
           GROUP BY game_system ORDER BY n DESC"""
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def get_top_tags(conn: sqlite3.Connection, min_books: int) -> list[tuple[str, int]]:
    rows = conn.execute(
        "SELECT tags FROM books WHERE tags IS NOT NULL AND is_old_version=0"
        " AND is_draft=0 AND is_duplicate=0"
    ).fetchall()
    counts: dict[str, int] = {}
    for (raw,) in rows:
        try:
            for t in json.loads(raw):
                counts[t] = counts.get(t, 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass
    return [(t, c) for t, c in sorted(counts.items(), key=lambda x: -x[1])
            if c >= min_books]


def get_top_series(conn: sqlite3.Connection, min_books: int) -> list[tuple[str, int]]:
    rows = conn.execute(
        """SELECT series, COUNT(*) n FROM books
           WHERE series IS NOT NULL AND series != '' AND is_old_version=0
             AND is_draft=0 AND is_duplicate=0
           GROUP BY series ORDER BY n DESC"""
    ).fetchall()
    return [(r[0], r[1]) for r in rows if r[1] >= min_books]


def get_top_publishers(conn: sqlite3.Connection, min_books: int) -> list[tuple[str, int]]:
    rows = conn.execute(
        """SELECT publisher, COUNT(*) n FROM books
           WHERE publisher IS NOT NULL AND publisher != '' AND is_old_version=0
             AND is_draft=0 AND is_duplicate=0
           GROUP BY publisher ORDER BY n DESC"""
    ).fetchall()
    return [(r[0], r[1]) for r in rows if r[1] >= min_books]


def get_system_top_tags(conn: sqlite3.Connection, system: str, limit: int = 12) -> list[str]:
    rows = conn.execute(
        "SELECT tags FROM books WHERE game_system=? AND tags IS NOT NULL"
        " AND is_old_version=0 AND is_draft=0 AND is_duplicate=0",
        (system,)
    ).fetchall()
    counts: dict[str, int] = {}
    for (raw,) in rows:
        try:
            for t in json.loads(raw):
                counts[t] = counts.get(t, 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass
    return [t for t, _ in sorted(counts.items(), key=lambda x: -x[1])[:limit]]


def get_tag_cooccurring(conn: sqlite3.Connection, tag: str,
                         limit_tags: int = 8, limit_systems: int = 5) -> tuple[list[str], list[str]]:
    """Return (related_tags, top_systems) for a tag."""
    rows = conn.execute(
        "SELECT tags, game_system FROM books WHERE tags LIKE ?"
        " AND is_old_version=0 AND is_draft=0 AND is_duplicate=0",
        (f'%"{tag}"%',)
    ).fetchall()
    tag_counts: dict[str, int] = {}
    sys_counts: dict[str, int] = {}
    for raw, game_sys in rows:
        try:
            for t in json.loads(raw):
                if t != tag:
                    tag_counts[t] = tag_counts.get(t, 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass
        if game_sys:
            sys_counts[game_sys] = sys_counts.get(game_sys, 0) + 1
    related = [t for t, _ in sorted(tag_counts.items(), key=lambda x: -x[1])[:limit_tags]]
    systems = [s for s, _ in sorted(sys_counts.items(), key=lambda x: -x[1])[:limit_systems]]
    return related, systems


def get_series_info(conn: sqlite3.Connection, series: str) -> dict:
    """Return game_system and publisher for a series."""
    row = conn.execute(
        """SELECT game_system, publisher,
              GROUP_CONCAT(DISTINCT tags) as all_tags
           FROM books WHERE series=? AND is_old_version=0
             AND is_draft=0 AND is_duplicate=0
           GROUP BY series""",
        (series,)
    ).fetchone()
    if not row:
        return {}
    # Extract most common tags
    tag_counts: dict[str, int] = {}
    for raw in (conn.execute(
        "SELECT tags FROM books WHERE series=? AND tags IS NOT NULL",
        (series,)
    ).fetchall()):
        try:
            for t in json.loads(raw[0]):
                tag_counts[t] = tag_counts.get(t, 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass
    top_tags = [t for t, _ in sorted(tag_counts.items(), key=lambda x: -x[1])[:6]]
    return {
        "game_system": row["game_system"],
        "publisher": row["publisher"],
        "top_tags": top_tags,
    }


def get_publisher_info(conn: sqlite3.Connection, publisher: str,
                       limit: int = 8) -> dict:
    """Return top game_systems and series for a publisher."""
    sys_rows = conn.execute(
        """SELECT game_system, COUNT(*) n FROM books
           WHERE publisher=? AND game_system IS NOT NULL
             AND is_old_version=0 AND is_draft=0 AND is_duplicate=0
           GROUP BY game_system ORDER BY n DESC LIMIT ?""",
        (publisher, limit)
    ).fetchall()
    ser_rows = conn.execute(
        """SELECT series, COUNT(*) n FROM books
           WHERE publisher=? AND series IS NOT NULL AND series != ''
             AND is_old_version=0 AND is_draft=0 AND is_duplicate=0
           GROUP BY series ORDER BY n DESC LIMIT ?""",
        (publisher, limit)
    ).fetchall()
    return {
        "top_systems": [r[0] for r in sys_rows],
        "top_series": [r[0] for r in ser_rows],
    }


def get_library_stats(conn: sqlite3.Connection) -> dict:
    total = conn.execute(
        "SELECT COUNT(*) FROM books WHERE is_old_version=0 AND is_draft=0 AND is_duplicate=0"
    ).fetchone()[0]
    enriched = conn.execute(
        "SELECT COUNT(*) FROM books WHERE is_old_version=0 AND is_draft=0"
        " AND is_duplicate=0 AND date_enriched IS NOT NULL"
    ).fetchone()[0]
    return {"total": total, "enriched": enriched}


# ── Dataview JS block ─────────────────────────────────────────────────────────

def dataviewjs_block(topic_type: str, topic_name: str, api_url: str) -> str:
    escaped_name = topic_name.replace("'", "\\'").replace("\\", "\\\\")
    return f"""```dataviewjs
const API = '{api_url}/api/library'
const TYPE = '{topic_type}'
const NAME = '{escaped_name}'

try {{
  const r = await fetch(`${{API}}/topic/${{TYPE}}/${{encodeURIComponent(NAME)}}`)
  if (!r.ok) throw new Error(`HTTP ${{r.status}}`)
  const d = await r.json()
  const s = d.stats

  const pct = s.total > 0 ? Math.round(s.enriched / s.total * 100) : 0
  dv.paragraph(`📚 **${{s.total.toLocaleString()}} books** · ${{s.enriched.toLocaleString()}} enriched (${{pct}}%)`)

  if (s.by_product_type.length) {{
    const types = s.by_product_type.slice(0, 6).map(t => `${{t.value}}: **${{t.count}}**`).join(' · ')
    dv.paragraph(types)
  }}

  if (s.top_publishers.length) {{
    dv.header(4, 'Top Publishers')
    dv.paragraph(s.top_publishers.slice(0, 10).map(p => `${{p.value}} (${{p.count}})`).join(' · '))
  }}
  if (s.top_series.length) {{
    dv.header(4, 'Top Series')
    dv.paragraph(s.top_series.slice(0, 10).map(p => `${{p.value}} (${{p.count}})`).join(' · '))
  }}
  if (s.top_game_systems.length) {{
    dv.header(4, 'Game Systems')
    dv.paragraph(s.top_game_systems.slice(0, 8).map(p => `${{p.value}} (${{p.count}})`).join(' · '))
  }}
  if (s.top_tags.length) {{
    dv.header(4, 'Top Tags')
    dv.paragraph(s.top_tags.slice(0, 15).map(t => t.value + ' (' + t.count + ')').join('  '))
  }}

  const shown = Math.min(d.books.length, 200)
  dv.header(4, `Books (${{shown < d.books.length ? `first ${{shown}} of ` : ''}}${{d.books.length.toLocaleString()}})`)
  dv.table(
    ['Title', 'Publisher', 'Type', 'Series', 'Level'],
    d.books.slice(0, 200).map(b => [
      `[${{(b.display_title || b.filename).replace(/\\|/g, '-')}}]({api_url}/book/${{b.id}})`,
      b.publisher || '',
      b.product_type || '',
      b.series || '',
      b.min_level ? (b.min_level === b.max_level ? String(b.min_level) : `${{b.min_level}}\u2013${{b.max_level}}`) : ''
    ])
  )
}} catch(e) {{
  dv.paragraph('> [!warning] Could not load data\\n> Ensure the RPG Library server is running.\\n> Error: ' + e.message)
}}
```"""


# ── Page generators ───────────────────────────────────────────────────────────

def game_system_page(name: str, book_count: int, top_tags: list[str],
                     all_systems: list[tuple[str, int]], api_url: str) -> str:
    # Related systems: top 5 others by count
    related_sys = [s for s, _ in all_systems if s != name][:5]
    tag_links = " · ".join(wikilink(t) for t in top_tags)
    sys_links = " · ".join(wikilink(s) for s in related_sys)

    lines = [
        f"---",
        f"type: game_system",
        f"name: \"{name}\"",
        f"book_count: {book_count}",
        f"---",
        f"",
        f"# {name}",
        f"",
    ]
    if tag_links:
        lines += [f"**Top tags:** {tag_links}", ""]
    if sys_links:
        lines += [f"**See also:** {sys_links}", ""]
    lines += [
        "---",
        "",
        dataviewjs_block("game_system", name, api_url),
    ]
    return "\n".join(lines)


def tag_page(tag: str, book_count: int, related_tags: list[str],
             top_systems: list[str], api_url: str) -> str:
    tag_links = " · ".join(wikilink(t) for t in related_tags)
    sys_links = " · ".join(wikilink(s) for s in top_systems)
    display = tag.replace("_", " ")

    lines = [
        f"---",
        f"type: tag",
        f"name: \"{tag}\"",
        f"book_count: {book_count}",
        f"---",
        f"",
        f"# {display}",
        f"",
    ]
    if sys_links:
        lines += [f"**Game systems:** {sys_links}", ""]
    if tag_links:
        lines += [f"**Related tags:** {tag_links}", ""]
    lines += [
        "---",
        "",
        dataviewjs_block("tag", tag, api_url),
    ]
    return "\n".join(lines)


def series_page(name: str, book_count: int, info: dict, api_url: str) -> str:
    game_sys = info.get("game_system")
    publisher = info.get("publisher")
    top_tags = info.get("top_tags", [])

    lines = [
        f"---",
        f"type: series",
        f"name: \"{name}\"",
        f"book_count: {book_count}",
    ]
    if game_sys:
        lines.append(f"game_system: \"{game_sys}\"")
    if publisher:
        lines.append(f"publisher: \"{publisher}\"")
    lines += ["---", "", f"# {name}", ""]

    meta = []
    if game_sys:
        meta.append(f"**System:** {wikilink(game_sys)}")
    if publisher:
        meta.append(f"**Publisher:** {wikilink(safe_filename(publisher), publisher)}")
    if meta:
        lines += [" · ".join(meta), ""]
    if top_tags:
        lines += ["**Tags:** " + " · ".join(wikilink(t) for t in top_tags), ""]

    lines += ["---", "", dataviewjs_block("series", name, api_url)]
    return "\n".join(lines)


def publisher_page(name: str, book_count: int, info: dict, api_url: str) -> str:
    top_systems = info.get("top_systems", [])
    top_series = info.get("top_series", [])

    lines = [
        f"---",
        f"type: publisher",
        f"name: \"{name}\"",
        f"book_count: {book_count}",
        f"---",
        f"",
        f"# {name}",
        f"",
    ]
    if top_systems:
        lines += ["**Systems:** " + " · ".join(wikilink(s) for s in top_systems), ""]
    if top_series:
        lines += ["**Series:** " + " · ".join(wikilink(s, s) for s in top_series[:6]), ""]

    lines += ["---", "", dataviewjs_block("publisher", name, api_url)]
    return "\n".join(lines)


def home_page(stats: dict, systems: list[tuple[str, int]],
              tags: list[tuple[str, int]], series: list[tuple[str, int]],
              publishers: list[tuple[str, int]], api_url: str) -> str:
    today = date.today().isoformat()

    sys_rows = "\n".join(
        f"| {wikilink(s, s)} | {n:,} |"
        for s, n in systems[:20]
    )

    # Group tags roughly by theme
    tag_links = " · ".join(
        f"{wikilink(t, t.replace('_',' '))} ({n:,})"
        for t, n in tags[:40]
    )

    ser_links = " · ".join(
        f"{wikilink(s, s)} ({n:,})"
        for s, n in series[:20]
    )

    pub_links = " · ".join(
        f"{wikilink(safe_filename(p), p)} ({n:,})"
        for p, n in publishers[:20]
    )

    return f"""---
type: home
generated: {today}
---

# 📚 RPG Library Wiki

> [Browse the full library]({api_url}) · [Explore the graph]({api_url}/graph)

**{stats['total']:,} books** · **{stats['enriched']:,} enriched** · Generated {today}

---

## 🎲 Game Systems

| System | Books |
|--------|------:|
{sys_rows}

---

## 🏷️ Tags

{tag_links}

---

## 📖 Series

{ser_links}

---

## 🏢 Publishers

{pub_links}
"""


def adventures_by_level_page(api_url: str) -> str:
    """Generate the 'Adventures by Level' index page."""
    escaped_url = api_url.replace("'", "\\'")
    return f"""---
type: index
name: "Adventures by Level"
---

# Adventures by Level

Browse adventures grouped by character level tier. A book appears in a tier if its level range overlaps with that tier.

---

```dataviewjs
const API = '{escaped_url}/api/library'

try {{
  const r = await fetch(`${{API}}/search?product_type=adventure&per_page=500&grouped=false`)
  if (!r.ok) throw new Error(`HTTP ${{r.status}}`)
  const d = await r.json()

  const leveled = d.results.filter(b => b.min_level != null)
  leveled.sort((a, b) => a.min_level - b.min_level || a.max_level - b.max_level)

  const unleveled = d.results.filter(b => b.min_level == null)

  const tiers = [
    {{ label: 'Tier 1 — Levels 1–4',  min: 1,  max: 4  }},
    {{ label: 'Tier 2 — Levels 5–10', min: 5,  max: 10 }},
    {{ label: 'Tier 3 — Levels 11–16',min: 11, max: 16 }},
    {{ label: 'Tier 4 — Levels 17–20',min: 17, max: 20 }},
    {{ label: 'High Level (21+)',      min: 21, max: 99 }},
  ]

  const levelStr = b => b.min_level === b.max_level
    ? String(b.min_level)
    : `${{b.min_level}}\u2013${{b.max_level}}`

  for (const tier of tiers) {{
    const books = leveled.filter(b => b.min_level <= tier.max && b.max_level >= tier.min)
    if (!books.length) continue
    dv.header(2, `${{tier.label}} (${{books.length}})`)
    dv.table(
      ['Title', 'Level', 'System', 'Publisher', 'Series'],
      books.map(b => [
        `[${{(b.display_title || b.filename).replace(/\\|/g, '-')}}]({escaped_url}/book/${{b.id}})`,
        levelStr(b),
        b.game_system || '',
        b.publisher || '',
        b.series || '',
      ])
    )
  }}

  if (unleveled.length) {{
    dv.header(2, `Unleveled Adventures (${{unleveled.length}})`)
    dv.table(
      ['Title', 'System', 'Publisher', 'Series'],
      unleveled.map(b => [
        `[${{(b.display_title || b.filename).replace(/\\|/g, '-')}}]({escaped_url}/book/${{b.id}})`,
        b.game_system || '',
        b.publisher || '',
        b.series || '',
      ])
    )
  }}

  dv.paragraph(`_${{leveled.length}} leveled · ${{unleveled.length}} unleveled · ${{d.results.length}} total adventures_`)
}} catch(e) {{
  dv.paragraph('> [!warning] Could not load data\\n> Ensure the RPG Library server is running.\\n> Error: ' + e.message)
}}
```"""


# ── Write helper ──────────────────────────────────────────────────────────────

def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Obsidian wiki from RPG library DB."
    )
    parser.add_argument("db", help="Path to rpg_library.db")
    parser.add_argument("vault", help="Path to Obsidian vault directory")
    parser.add_argument("--api-url", default="http://localhost:8000",
                        help="Base URL of the library server (default: http://localhost:8000)")
    parser.add_argument("--min-tag-books", type=int, default=30,
                        help="Minimum books for a tag page (default: 30)")
    parser.add_argument("--min-series-books", type=int, default=3,
                        help="Minimum books for a series page (default: 3)")
    parser.add_argument("--min-publisher-books", type=int, default=10,
                        help="Minimum books for a publisher page (default: 10)")
    args = parser.parse_args()

    vault = Path(args.vault)
    vault.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    print("Loading data...")
    stats = get_library_stats(conn)
    systems = get_game_systems(conn)
    tags = get_top_tags(conn, args.min_tag_books)
    series = get_top_series(conn, args.min_series_books)
    publishers = get_top_publishers(conn, args.min_publisher_books)

    print(f"  {len(systems)} game systems, {len(tags)} tags, "
          f"{len(series)} series, {len(publishers)} publishers")

    # Build sets for cross-linking validation
    system_names = {s for s, _ in systems}
    tag_names = {t for t, _ in tags}
    series_names = {s for s, _ in series}
    publisher_safe = {safe_filename(p) for p, _ in publishers}

    # Home page
    print("Writing Home.md...")
    write_file(
        vault / "Home.md",
        home_page(stats, systems, tags, series, publishers, args.api_url)
    )

    # Game System pages
    print(f"Writing {len(systems)} game system pages...")
    for name, count in systems:
        top_tags = [t for t in get_system_top_tags(conn, name) if t in tag_names]
        content = game_system_page(name, count, top_tags, systems, args.api_url)
        write_file(vault / "Game Systems" / f"{safe_filename(name)}.md", content)

    # Tag pages
    print(f"Writing {len(tags)} tag pages...")
    for tag, count in tags:
        related, top_sys = get_tag_cooccurring(conn, tag)
        related = [t for t in related if t in tag_names][:8]
        top_sys = [s for s in top_sys if s in system_names][:5]
        content = tag_page(tag, count, related, top_sys, args.api_url)
        write_file(vault / "Tags" / f"{safe_filename(tag)}.md", content)

    # Series pages
    print(f"Writing {len(series)} series pages...")
    for name, count in series:
        info = get_series_info(conn, name)
        # Only link to systems/publishers that have their own pages
        if info.get("game_system") not in system_names:
            info["game_system"] = None
        info["top_tags"] = [t for t in info.get("top_tags", []) if t in tag_names]
        content = series_page(name, count, info, args.api_url)
        write_file(vault / "Series" / f"{safe_filename(name)}.md", content)

    # Publisher pages
    print(f"Writing {len(publishers)} publisher pages...")
    for name, count in publishers:
        info = get_publisher_info(conn, name)
        info["top_systems"] = [s for s in info["top_systems"] if s in system_names]
        info["top_series"] = [s for s in info["top_series"] if s in series_names]
        content = publisher_page(name, count, info, args.api_url)
        write_file(vault / "Publishers" / f"{safe_filename(name)}.md", content)

    # Adventures by Level index page
    print("Writing Adventures by Level.md...")
    write_file(vault / "Adventures by Level.md", adventures_by_level_page(args.api_url))

    conn.close()

    total = (1 + len(systems) + len(tags) + len(series) + len(publishers) + 1)
    print(f"\nDone. {total} pages written to {vault}")
    print(f"Open {vault} as an Obsidian vault.")


if __name__ == "__main__":
    main()
