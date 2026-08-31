#!/usr/bin/env python3
"""
check_5etools_load.py
=====================
Diagnose (and repair) 5etools adventure/book JSON that loads far enough to show
its table of contents but leaves the content pane stuck on "loading".

The symptom
-----------
The sidebar TOC appears, the main pane never does. That is not a data-fetch
problem — the file loaded fine. It is an *exception thrown during render*:

    BookUtil._showBookContent()                     // js/bookutils.js
        Renderer.adventureBook.getEntryIdLookup()   // throws on duplicate ids
        ...
        this._removeLoadingOverlay()                // never reached

`getEntryIdLookup` ends with:

    if (!isSilent) if (out.__BAD) throw new Error(`IDs were already in storage: ...`)

so a single duplicate `id` anywhere in the document aborts `_showBookContent`
before it removes the loading overlay. The TOC is built earlier, from
`adventure[0].contents`, which is why it survives. Any exception inside
`recursiveRender` has the same effect.

What this tool does
-------------------
1.  Finds duplicate ids the same way 5etools does — walking every node, and
    skipping the "mapParent" key, whose `{"id": ...}` is a *reference* to
    another node rather than a definition.
2.  Optionally re-runs the check with the real 5etools code via node, which
    also catches render-time exceptions this tool doesn't model. Auto-detected
    from a local 5etools checkout; see --fivetools.
3.  With --fix, renames only the colliding nodes to fresh unused ids. It does
    not renumber the whole document: ids are referenced by "mapParent", so a
    blanket renumber would silently break map linkage.

Usage
-----
    python3 lib/check_5etools_load.py FILE_OR_DIR...            # diagnose
    python3 lib/check_5etools_load.py FILE_OR_DIR... --fix      # repair in place
    python3 lib/check_5etools_load.py DIR --no-node             # skip the node probe

Exits non-zero if any file would fail to load (and was not repaired).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# 5etools passes `keyBlocklist: new Set(["mapParent"])` when walking for ids,
# because a mapParent's `id` points at another node instead of naming this one.
REF_KEYS = frozenset({"mapParent"})

# Where a document's chapter list lives, by format.
DATA_PROPS = ("adventureData", "bookData")

# Common locations for a 5etools checkout, used for the node probe.
FIVETOOLS_CANDIDATES = (
    "~/src/5etools-src",
    "~/src/5etools-kostadis",
)


# ── id walking ────────────────────────────────────────────────────────────────

def iter_id_nodes(node: Any, path: str = "") -> Iterator[tuple[dict, str]]:
    """Yield (dict_node, path) for every node carrying an "id", in document order.

    Mirrors Renderer.adventureBook.getEntryIdLookup: every node counts, except
    anything under a reference key such as "mapParent".
    """
    if isinstance(node, dict):
        if "id" in node:
            yield node, path
        for key, value in node.items():
            if key in REF_KEYS:
                continue
            yield from iter_id_nodes(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from iter_id_nodes(value, f"{path}[{i}]")


def iter_data_blocks(doc: dict) -> Iterator[tuple[str, list]]:
    """Yield (path_label, chapter_list) for each data block in the document."""
    for prop in DATA_PROPS:
        for i, block in enumerate(doc.get(prop) or []):
            data = block.get("data")
            if isinstance(data, list):
                yield f"{prop}[{i}].data", data


def find_duplicate_ids(doc: dict) -> list[tuple[str, str, str]]:
    """Return [(id, first_path, duplicate_path), ...] — empty means 5etools is happy.

    Scoped **per data block**, matching the code this models: PROBE_JS calls
    `getEntryIdLookup(block.data)` once per block, so an id only has to be
    unique inside its own block. A document-wide `seen` would report a
    multi-block homebrew — two `adventureData` entries, or `adventureData`
    plus `bookData`, each numbering from "000" — as a pile of duplicates that
    5etools itself is perfectly happy with, and `--fix` would then renumber to
    repair a non-problem. No official adventure has more than one block, which
    is why the 98/61 clean run never showed it.
    """
    dupes: list[tuple[str, str, str]] = []
    for label, data in iter_data_blocks(doc):
        seen: dict[str, str] = {}
        for node, path in iter_id_nodes(data, label):
            eid = node["id"]
            if not isinstance(eid, str):
                continue
            if eid in seen:
                dupes.append((eid, seen[eid], path))
            else:
                seen[eid] = path
    return dupes


def collect_map_parent_refs(doc: dict) -> set[str]:
    """Ids referenced by a "mapParent" — renaming one of these breaks map linkage."""
    refs: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            parent = node.get("mapParent")
            if isinstance(parent, dict) and isinstance(parent.get("id"), str):
                refs.add(parent["id"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(doc)
    return refs


# ── repair ────────────────────────────────────────────────────────────────────

def repair_duplicate_ids(doc: dict) -> list[tuple[str, str, str]]:
    """Rename colliding nodes to fresh unused ids. Returns [(path, old, new), ...].

    Only the *later* occurrences move; the first keeps its id. Deliberately not a
    full renumber — see the module docstring.
    """
    taken: set[str] = set()
    for _, data in iter_data_blocks(doc):
        for node, _path in iter_id_nodes(data, ""):
            if isinstance(node.get("id"), str):
                taken.add(node["id"])

    # Start above the highest purely-numeric id so new ids sort after existing
    # ones instead of filling gaps.
    numeric = [int(i) for i in taken if i.isdigit()]
    counter = max(numeric) + 1 if numeric else 0
    width = max((len(i) for i in taken if i.isdigit()), default=3)

    def next_id() -> str:
        nonlocal counter
        while True:
            candidate = f"{counter:0{width}d}"
            counter += 1
            if candidate not in taken:
                taken.add(candidate)
                return candidate

    renames: list[tuple[str, str, str]] = []
    for label, data in iter_data_blocks(doc):
        # Per block, for the same reason as find_duplicate_ids. `taken` above
        # stays document-wide on purpose: a replacement id should be unused
        # everywhere, which is a safe superset of what 5etools requires.
        seen: dict[str, str] = {}
        for node, path in iter_id_nodes(data, label):
            eid = node["id"]
            if not isinstance(eid, str):
                continue
            if eid in seen:
                new_id = next_id()
                node["id"] = new_id
                renames.append((path, eid, new_id))
            else:
                seen[eid] = path
    return renames


# ── node probe (authoritative: runs the real 5etools code) ────────────────────

PROBE_JS = r"""
const [,, root, target] = process.argv;
const href = (f) => new URL(`file://${root}/js/${f}`).href;
for (const f of ["parser.js", "utils.js", "utils-ui.js", "utils-config.js", "render.js", "render-dice.js"]) {
	await import(href(f));
}
const fs = await import("node:fs");
const doc = JSON.parse(fs.readFileSync(target, "utf8"));
const blocks = [...(doc.adventureData || []), ...(doc.bookData || [])];
const out = [];
for (const block of blocks) {
	const data = block?.data;
	if (!Array.isArray(data)) continue;
	try {
		globalThis.Renderer.adventureBook.getEntryIdLookup(data);
	} catch (e) {
		out.push(`getEntryIdLookup: ${e.message}`);
	}
	const renderer = new globalThis.Renderer();
	renderer.setLazyImages(true);
	data.forEach((chapter, i) => {
		try {
			renderer.recursiveRender(chapter, []);
		} catch (e) {
			out.push(`render data[${i}] ${JSON.stringify(chapter?.name ?? "")}: ${e.message}`);
		}
	});
}
console.log(JSON.stringify(out));
"""


def find_fivetools(explicit: str | None = None) -> Path | None:
    """Locate a 5etools checkout for the node probe."""
    candidates = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("FIVETOOLS_DIR"):
        candidates.append(os.environ["FIVETOOLS_DIR"])
    candidates.extend(FIVETOOLS_CANDIDATES)
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if (path / "js" / "render.js").is_file():
            return path
    return None


def node_probe(fivetools: Path, target: Path) -> list[str] | None:
    """Run the real 5etools renderer over a file. Returns problems, or None if unavailable."""
    if not shutil.which("node"):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / "probe.mjs"
        probe.write_text(PROBE_JS, encoding="utf-8")
        try:
            proc = subprocess.run(
                ["node", str(probe), str(fivetools), str(target)],
                capture_output=True, text=True, timeout=120,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


# ── driver ────────────────────────────────────────────────────────────────────

def iter_target_files(targets: list[str]) -> Iterator[Path]:
    for target in targets:
        path = Path(target).expanduser()
        if path.is_dir():
            yield from sorted(p for p in path.rglob("*.json") if not p.name.endswith(".bak"))
        else:
            yield path


def check_file(path: Path, *, fix: bool, fivetools: Path | None) -> bool:
    """Report on one file. Returns True if it should load in 5etools afterwards."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"SKIP {path}: {exc}")
        return True

    if not isinstance(doc, dict) or not any(doc.get(prop) for prop in DATA_PROPS):
        return True  # not an adventure/book document

    dupes = find_duplicate_ids(doc)
    problems = node_probe(fivetools, path) if fivetools else None

    if not dupes and not problems:
        extra = "" if problems is None else " (verified against 5etools)"
        print(f"OK   {path.name}{extra}")
        return True

    print(f"FAIL {path.name}")
    for eid, first, dup in dupes:
        print(f"       duplicate id '{eid}': {first} and {dup}")
    for problem in problems or []:
        print(f"       5etools: {problem}")

    if not fix:
        if dupes:
            print("       -> rerun with --fix to rename the colliding nodes")
        return False

    if not dupes:
        print("       -> not a duplicate-id problem; --fix cannot repair this")
        return False

    refs = collect_map_parent_refs(doc)
    renames = repair_duplicate_ids(doc)
    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)
    path.write_text(json.dumps(doc, indent="\t", ensure_ascii=False), encoding="utf-8")

    print(f"       backup: {backup.name}")
    for node_path, old, new in renames:
        note = "  <-- also referenced by a mapParent; check map linkage" if old in refs else ""
        print(f"       renamed {node_path}: '{old}' -> '{new}'{note}")

    if fivetools:
        after = node_probe(fivetools, path)
        if after:
            print("       still failing after repair:")
            for problem in after:
                print(f"         {problem}")
            return False
        if after is not None:
            print("       repaired (verified against 5etools)")
            return True
    print("       repaired")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose/repair 5etools adventure JSON stuck on 'loading'.",
    )
    parser.add_argument("targets", nargs="+", help="JSON files, or directories to search")
    parser.add_argument("--fix", action="store_true",
                        help="rename colliding ids in place (keeps a .bak)")
    parser.add_argument("--fivetools", metavar="DIR",
                        help="5etools checkout to verify against (default: auto-detect)")
    parser.add_argument("--no-node", action="store_true",
                        help="skip the node probe and use the built-in checks only")
    args = parser.parse_args(argv)

    fivetools = None if args.no_node else find_fivetools(args.fivetools)
    if not args.no_node and fivetools is None:
        print("note: no 5etools checkout found — using built-in checks only "
              "(set FIVETOOLS_DIR or pass --fivetools to verify against the real renderer)\n")

    files = list(iter_target_files(args.targets))
    if not files:
        print("No JSON files found.")
        return 1

    bad = [path for path in files if not check_file(path, fix=args.fix, fivetools=fivetools)]

    print(f"\nTotal: {len(files)} file(s), {len(bad)} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
