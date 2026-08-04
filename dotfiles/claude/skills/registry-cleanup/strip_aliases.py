#!/usr/bin/env python3
"""Remove specific (entity, alias) pairs from a campaign entity registry.

`registry.py` has add / alias / merge / mark-distinct / mark-rejected and NO
`unalias` and NO `rename` — the CLI was written assuming aliases are only ever
added. Removing bad alias data therefore means editing entity_registry.yaml
directly, which this script does as safely as it can:

  * line-oriented edit, so YAML formatting/ordering/comments survive intact
    (a yaml.safe_load + yaml.dump round-trip would reformat all ~4000 lines
    and bury the real change in noise)
  * every removal is keyed on (entity, alias), never on the alias alone —
    the same surface form may legitimately attach to a different entity
  * parses the result and asserts the entity count is unchanged BEFORE writing
  * refuses to run without --backup unless --no-backup is explicit
  * reports any requested pair it could not find, so a typo is loud

Always run `registry project` afterwards to regenerate aliases.json and
entity_inventory.md.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import yaml


def strip(path: Path, pairs: list[tuple[str, str]], dry_run: bool) -> tuple[list, set]:
    lines = path.read_text(encoding="utf-8").splitlines()

    want: dict[str, set[str]] = {}
    for entity, alias in pairs:
        want.setdefault(entity, set()).add(alias)

    before = yaml.safe_load(path.read_text(encoding="utf-8"))
    n_before = len(before.get("entities") or [])

    out, cur, removed = [], None, []
    for ln in lines:
        if ln.startswith("- name: "):
            cur = ln[len("- name: "):].strip().strip("\"'")
        if ln.startswith("  - ") and cur in want:
            val = ln[4:].strip().strip("\"'")
            if val in want[cur]:
                removed.append((cur, val))
                continue
        out.append(ln)

    # an entity whose alias list is now empty must lose its `aliases:` key too
    final = []
    for i, ln in enumerate(out):
        if ln.strip() == "aliases:":
            nxt = out[i + 1] if i + 1 < len(out) else ""
            if not nxt.startswith("  - "):
                continue
        final.append(ln)

    txt = "\n".join(final) + "\n"
    after = yaml.safe_load(txt)
    n_after = len(after.get("entities") or [])
    if n_after != n_before:
        raise SystemExit(f"REFUSING TO WRITE: entity count changed {n_before} -> {n_after}")

    if not dry_run:
        path.write_text(txt, encoding="utf-8")

    return removed, set(pairs) - set(removed)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--registry", required=True, type=Path)
    ap.add_argument("--pair", action="append", default=[], metavar="ENTITY::ALIAS",
                    help="repeatable; e.g. --pair 'Glabbagool::Glabagool'")
    ap.add_argument("--pairs-file", type=Path,
                    help="file of ENTITY::ALIAS lines (# comments ok)")
    ap.add_argument("--backup", type=Path, help="write a copy here before editing")
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    raw = list(args.pair)
    if args.pairs_file:
        for ln in args.pairs_file.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                raw.append(ln)
    if not raw:
        ap.error("no pairs given (--pair or --pairs-file)")

    pairs = []
    for item in raw:
        if "::" not in item:
            ap.error(f"malformed pair {item!r}; expected ENTITY::ALIAS")
        entity, alias = item.split("::", 1)
        pairs.append((entity.strip(), alias.strip()))

    if not args.dry_run and not args.no_backup:
        dest = args.backup or args.registry.with_suffix(args.registry.suffix + ".bak")
        shutil.copy2(args.registry, dest)
        print(f"backup: {dest}")

    removed, missing = strip(args.registry, pairs, args.dry_run)

    verb = "would remove" if args.dry_run else "removed"
    print(f"{verb} {len(removed)} of {len(pairs)} alias(es)")
    for entity, alias in removed:
        print(f"   - {alias!r} from {entity!r}")
    if missing:
        print(f"\nNOT FOUND ({len(missing)}) — check spelling/entity:")
        for entity, alias in sorted(missing):
            print(f"   ? {alias!r} on {entity!r}")
        return 1
    if not args.dry_run:
        print("\nNow run:  registry project   (regenerates aliases.json + entity_inventory.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
