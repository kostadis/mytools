#!/usr/bin/env python3
"""List a campaign's declared corpus files for one or more kinds, via mneme (mytools#87).

Every skill that reads campaign corpus files gets the list from here, which follows mneme's
consumer obligations (mneme/recipes/instructions/manage-mempalace.md § Consumer obligations):

1. Ask mneme on every use: ``mneme corpus toc NAME --dir ROOT --kind K --json``.
2. If mneme exits non-zero or reports ``valid: false``, REFUSE and print what mneme said.
   Never fall back to globbing or to a hardcoded path.
3. Take the files from ``kinds.<K>.files[].path`` and nothing else. An undeclared kind is a
   refusal ("kind 'K' is not declared for this campaign"), not an empty list.

Never reads ``.mneme/corpus.toc.json`` (a host-local snapshot that can be stale).

The campaign root is the nearest ancestor of the working directory (or of --campaign-dir)
that holds ``.mneme/``; with none, the directory itself is passed and mneme refuses it as
not declared. ``--dir`` makes mneme check that ROOT is the workspace it owns: a stale or
second checkout of a registered campaign is refused (store-alias clash), so a skill cannot
silently read the wrong copy.

Output, one line per file:  KIND <TAB> TRUST <TAB> ABSOLUTE-PATH
A declared kind with no files prints ``# KIND: declared, 0 files``.
Exit 0 on success; 2 on refusal (message on stderr, starting ``REFUSE:``).

Usage:  corpus_files.py KIND [KIND ...] [--campaign-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

MNEME_TIMEOUT_S = 120


class Refusal(Exception):
    pass


def campaign_root(start: Path) -> Path:
    """Nearest ancestor holding ``.mneme/``, stopping below $HOME (``~/.mneme`` is mneme's own
    state directory, not a campaign)."""
    start = start.resolve()
    home = Path.home().resolve()
    for d in (start, *start.parents):
        if d == home or d == d.parent:
            break
        if (d / ".mneme").is_dir():
            return d
    return start


def toc(root: Path, kind: str) -> dict:
    mneme = os.environ.get("MNEME_BIN") or shutil.which("mneme")
    if not mneme:
        raise Refusal("mneme is not on PATH; cannot resolve the declared corpus")
    cmd = [mneme, "corpus", "toc", root.name, "--dir", str(root), "--kind", kind, "--json"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=MNEME_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise Refusal(f"mneme timed out after {MNEME_TIMEOUT_S}s: {' '.join(cmd)}")
    if p.returncode != 0:
        msg = (p.stderr.strip() or p.stdout.strip() or f"exit {p.returncode}")
        if "store alias" in msg and "claimed by" in msg:
            msg += (f"\n  ({root} looks like a second checkout of a registered campaign; "
                    "run from the workspace mneme owns, e.g. ~/<campaign>/<campaign>.)")
        raise Refusal(f"mneme refused kind '{kind}' for {root}: {msg}")
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError as e:
        raise Refusal(f"mneme returned non-JSON for kind '{kind}': {e}")
    if data.get("error"):
        raise Refusal(f"mneme error for kind '{kind}': {data['error']}")
    if data.get("valid") is not True:
        raise Refusal(
            f"corpus for {root} is not valid: {json.dumps(data.get('findings', []))}"
        )
    kinds = data.get("kinds") or {}
    if kind not in kinds:
        raise Refusal(f"kind '{kind}' is not declared for this campaign ({root})")
    return kinds[kind]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("kinds", nargs="+", metavar="KIND")
    ap.add_argument("--campaign-dir", default=None)
    args = ap.parse_args(argv)

    root = campaign_root(Path(args.campaign_dir or os.getcwd()))
    lines: list[str] = []
    try:
        for kind in args.kinds:
            k = toc(root, kind)
            files = k.get("files") or []
            if not files:
                lines.append(f"# {kind}: declared, 0 files")
            for f in files:
                lines.append(f"{kind}\t{k.get('trust', '')}\t{root / f['path']}")
    except Refusal as e:
        print(f"REFUSE: {e}", file=sys.stderr)
        print("Do not glob or fall back to known paths. Report this to the GM.", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
