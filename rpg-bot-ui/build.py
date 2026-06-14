#!/usr/bin/env python3
"""Generate self-contained HTML files from rpgbot.db.

Supports two types of builders:
1. Class builders (rogue-2024, etc.) using builder.html template
2. Spell builders (arcane-trickster-spells) using spell-builder.html template

Usage:
    python3 build.py                    build all classes  →  dist/
    python3 build.py rogue-2024         build one class    →  dist/
    python3 build.py arcane-trickster-spells --spell    build spell builder
    python3 build.py rogue-2024 -o .    write to current dir
"""

import argparse
import json
import os
import sqlite3

SCRIPT_DIR       = os.path.dirname(os.path.abspath(__file__))
DB_PATH          = os.path.join(SCRIPT_DIR, 'rpgbot.db')
CLASS_TEMPLATE   = os.path.join(SCRIPT_DIR, 'builder.html')
SPELL_TEMPLATE   = os.path.join(SCRIPT_DIR, 'spell-builder.html')

# Exact strings the generator finds and replaces.
DATA_SENTINEL      = 'let D = null;'
BOOTSTRAP_SENTINEL = '// ─── Bootstrap'


def build_class(class_id: str, out_dir: str, is_spell: bool = False) -> str:
    db = sqlite3.connect(DB_PATH)
    row = db.execute(
        "SELECT name, edition, data FROM classes WHERE id = ?", (class_id,)
    ).fetchone()
    db.close()

    if not row:
        raise ValueError(f"'{class_id}' not found in DB — run seed.py first")

    name, edition, data_json = row
    data = json.loads(data_json)

    # Inject meta if not present (for class data)
    if 'meta' not in data:
        data['meta'] = {'id': class_id, 'name': name, 'edition': edition}

    # Choose template based on type
    template_path = SPELL_TEMPLATE if is_spell else CLASS_TEMPLATE

    with open(template_path, encoding='utf-8') as f:
        html = f.read()

    # ── Substitution 1: embed data ──────────────────────────────────────────
    if DATA_SENTINEL not in html:
        raise RuntimeError(f"DATA_SENTINEL {DATA_SENTINEL!r} not found in template")
    inline = f'const D = {json.dumps(data, ensure_ascii=False)};'
    html = html.replace(DATA_SENTINEL, inline, 1)

    # ── Substitution 2: remove the fetch bootstrap ──────────────────────────
    if BOOTSTRAP_SENTINEL not in html:
        raise RuntimeError(f"BOOTSTRAP_SENTINEL {BOOTSTRAP_SENTINEL!r} not found in template")
    boot_idx    = html.index(BOOTSTRAP_SENTINEL)
    script_idx  = html.rindex('</script>')
    html = html[:boot_idx] + "document.addEventListener('DOMContentLoaded', init);\n" + html[script_idx:]

    # ── Write output ────────────────────────────────────────────────────────
    os.makedirs(out_dir, exist_ok=True)
    # For spell builders, use the ID directly; for classes, add -builder suffix
    if is_spell:
        out_path = os.path.join(out_dir, f'{class_id}.html')
    else:
        out_path = os.path.join(out_dir, f'{class_id}-builder.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return out_path


def list_classes() -> list[str]:
    db = sqlite3.connect(DB_PATH)
    rows = db.execute("SELECT id FROM classes ORDER BY edition, id").fetchall()
    db.close()
    return [r[0] for r in rows]


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Build self-contained HTML from rpgbot.db'
    )
    parser.add_argument('class_id', nargs='?', help='ID to build (omit to build all)')
    parser.add_argument('-o', '--out', default='dist', metavar='DIR',
                        help='Output directory (default: dist/)')
    parser.add_argument('--spell', action='store_true',
                        help='Build as spell builder (uses spell-builder.html)')
    args = parser.parse_args()

    ids = list_classes()
    if not ids:
        raise SystemExit("rpgbot.db is empty — run seed.py first")

    if args.class_id:
        if args.class_id not in ids:
            raise SystemExit(f"'{args.class_id}' not in DB.  Available: {', '.join(ids)}")
        ids = [args.class_id]

    out_dir = os.path.abspath(args.out)
    print(f"Building {len(ids)} item(s) → {out_dir}/")
    for cid in ids:
        out = build_class(cid, out_dir, is_spell=args.spell)
        size = os.path.getsize(out)
        print(f"  {cid:30s}  →  {os.path.basename(out)}  ({size//1024}KB)")


if __name__ == '__main__':
    main()
