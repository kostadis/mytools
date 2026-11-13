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

``--brief`` (consumer obligations 4-5, mneme 009) asks ``mneme corpus brief NAME --dir ROOT
--json`` instead: the GM's load-now files plus a per-kind map of everything else. Output:

    # campaign: NAME
    BRIEF <TAB> KINDS <TAB> TRUST <TAB> BYTES <TAB> ABSOLUTE-PATH      (declared order)
    MAP <TAB> KIND <TAB> TRUST <TAB> FILES <TAB> BYTES <TAB> SEARCHABLE-FILES <TAB> standard|extra

A briefing consumer reads the BRIEF paths and nothing else up front; MAP rows say what else
exists and which palace wing (= the kind) to search. No brief, an invalid corpus, or a brief
file absent from this checkout is a refusal: never substitute a whole kind for the brief.

Exit 0 on success; 2 on refusal (message on stderr, starting ``REFUSE:``).

Usage:  corpus_files.py KIND [KIND ...] [--campaign-dir DIR]
        corpus_files.py --brief [--campaign-dir DIR]
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


def _mneme_json(root: Path, args: list[str], what: str) -> dict:
    """Run ``mneme corpus ARGS NAME --dir ROOT --json``; refuse on any failure."""
    mneme = os.environ.get("MNEME_BIN") or shutil.which("mneme")
    if not mneme:
        raise Refusal("mneme is not on PATH; cannot resolve the declared corpus")
    cmd = [mneme, "corpus", args[0], root.name, "--dir", str(root), *args[1:], "--json"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=MNEME_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise Refusal(f"mneme timed out after {MNEME_TIMEOUT_S}s: {' '.join(cmd)}")
    if p.returncode != 0:
        msg = (p.stderr.strip() or p.stdout.strip() or f"exit {p.returncode}")
        if "store alias" in msg and "claimed by" in msg:
            msg += (f"\n  ({root} looks like a second checkout of a registered campaign; "
                    "run from the workspace mneme owns, e.g. ~/<campaign>/<campaign>.)")
        if "migrate-brief" in msg:
            msg += ("\n  (The GM declares the brief: `mneme corpus migrate-brief CAMPAIGN` "
                    "previews it, `--apply` writes it.)")
        raise Refusal(f"mneme refused {what} for {root}: {msg}")
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError as e:
        raise Refusal(f"mneme returned non-JSON for {what}: {e}")
    if data.get("error"):
        raise Refusal(f"mneme error for {what}: {data['error']}: {data.get('detail', '')}")
    return data


def toc(root: Path, kind: str) -> dict:
    data = _mneme_json(root, ["toc", "--kind", kind], f"kind '{kind}'")
    if data.get("valid") is not True:
        raise Refusal(
            f"corpus for {root} is not valid: {json.dumps(data.get('findings', []))}"
        )
    kinds = data.get("kinds") or {}
    if kind not in kinds:
        raise Refusal(f"kind '{kind}' is not declared for this campaign ({root})")
    return kinds[kind]


def brief(root: Path) -> list[str]:
    """The brief answer as output lines (see module docstring)."""
    data = _mneme_json(root, ["brief"], "the brief")
    if data.get("schema") != 1:
        raise Refusal(f"unexpected brief schema {data.get('schema')!r} (this helper reads 1)")
    files = data.get("brief") or []
    if not files:
        raise Refusal(f"mneme returned an empty brief for {root}")
    lines = [f"# campaign: {data.get('campaign', root.name)}"]
    for f in files:
        path = root / f["path"]
        if not path.is_file():
            raise Refusal(f"brief file {f['path']} is not on disk at {path}")
        lines.append("\t".join(["BRIEF", ",".join(f.get("kinds") or []), str(f.get("trust", "")),
                                str(f.get("bytes", "")), str(path)]))
    for name, k in (data.get("kinds") or {}).items():
        lines.append("\t".join(["MAP", name, str(k.get("trust", "")), str(k.get("files", "")),
                                str(k.get("bytes", "")), str(k.get("searchable_files", "")),
                                "standard" if k.get("standard") else "extra"]))
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("kinds", nargs="*", metavar="KIND")
    ap.add_argument("--brief", action="store_true",
                    help="print the GM's load-now files and the per-kind map")
    ap.add_argument("--campaign-dir", default=None)
    args = ap.parse_args(argv)
    if args.brief == bool(args.kinds):
        ap.error("give either one or more KINDs or --brief, not both and not neither")

    root = campaign_root(Path(args.campaign_dir or os.getcwd()))
    lines: list[str] = []
    try:
        if args.brief:
            lines = brief(root)
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
