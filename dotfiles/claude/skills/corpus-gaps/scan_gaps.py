"""Find campaign files that are neither in the mneme corpus nor ruled out.

Read-only. Never edits corpus.yaml, the rulings file, or the palace; it only
lists candidates for the GM to rule on.

Run it with mneme's own interpreter so the extension list and the recipe's
baseline exclusions come from mneme, not from a copy here:

    "$(head -1 "$(command -v mneme)" | sed 's/^#!//')" scan_gaps.py <campaign-dir> [--json] [--all-ext]

A candidate is a file that git sees (tracked, or untracked and not ignored),
that mempalace could read, and that is in none of:
  - the corpus, as `mneme corpus toc --json` resolves it NOW;
  - .mneme/corpus.rulings.yaml (the GM's out-rulings);
  - the recipe's mechanical baseline exclusions.

Each candidate gets one signal, strongest first:
  new        added to git after corpus.yaml was last committed, or untracked
  sibling    in a directory whose other files a kind lists under `files:`
             (a `files:` list never picks up a new file by itself)
  backlog    older, never ruled on
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath

import yaml

try:
    from mneme.corpus.resolve import READABLE_EXTENSIONS, SKIP_FILENAMES
    from mneme.mempalace import recipe as mneme_recipe
except ImportError as e:  # wrong interpreter: refuse rather than guess the lists
    sys.exit(f"scan_gaps: cannot import mneme ({e}); run it with mneme's interpreter")

PROSE_EXTENSIONS = {".md", ".txt"}
RULINGS = ".mneme/corpus.rulings.yaml"
CORPUS = ".mneme/corpus.yaml"


def git(campaign: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(campaign), *args],
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        sys.exit(f"scan_gaps: git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def corpus_toc(campaign: Path, name: str) -> dict:
    cmd = ["mneme", "corpus", "toc", name, "--dir", str(campaign), "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        sys.exit(f"scan_gaps: {' '.join(cmd)} failed:\n{(proc.stderr or proc.stdout).strip()}")
    toc = json.loads(proc.stdout)
    if toc.get("valid") is False:
        sys.exit("scan_gaps: mneme reports the corpus is not valid; fix it with "
                 "`mneme corpus check` first")
    return toc


def baseline_excluded(path: str, baseline: tuple[str, ...]) -> bool:
    parts = PurePosixPath(path).parts
    for rule in baseline:
        if rule.endswith("/"):
            if rule.rstrip("/") in parts[:-1]:
                return True
        elif fnmatch.fnmatch(parts[-1], rule) or path == rule:
            return True
    return False


def load_rulings(campaign: Path) -> list[dict]:
    p = campaign / RULINGS
    if not p.is_file():
        return []
    raw = yaml.safe_load(p.read_text()) or {}
    return list(raw.get("excluded") or [])


def ruled_out(path: str, rulings: list[dict]) -> dict | None:
    for r in rulings:
        rp = str(r.get("path", ""))
        if (rp.endswith("/") and path.startswith(rp)) or path == rp:
            return r
    return None


def new_paths(campaign: Path, since: str | None) -> tuple[set[str], str | None]:
    """Paths added in git after ``since`` (default: the last commit to corpus.yaml)."""
    since = since or git(campaign, "log", "-1", "--format=%H", "--", CORPUS).strip()
    if not since:
        return set(), None
    prefix = git(campaign, "rev-parse", "--show-prefix").strip()
    out = git(campaign, "log", "--diff-filter=A", "--name-only", "--format=",
              f"{since}..HEAD", "--", ".")
    added = {line[len(prefix):] for line in out.splitlines() if line.startswith(prefix)}
    return added, since[:8]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("campaign_dir", type=Path)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--all-ext", action="store_true",
                    help="every extension mempalace reads, not just .md/.txt")
    ap.add_argument("--since", metavar="REV",
                    help="count files added after REV as new (default: the last "
                         "commit to corpus.yaml)")
    ap.add_argument("--depth", type=int, default=3,
                    help="group the backlog by its first N path components")
    ap.add_argument("--collapse", type=int, default=5,
                    help="group a backlog subtree once it has more than N files")
    args = ap.parse_args()
    campaign = args.campaign_dir.resolve()

    corpus = yaml.safe_load((campaign / CORPUS).read_text()) or {}
    name = corpus.get("campaign")
    if not name:
        sys.exit(f"scan_gaps: {CORPUS} has no campaign name")
    toc = corpus_toc(campaign, name)
    rec = mneme_recipe.load(toc["recipe_version"])

    declared: dict[str, str] = {}
    for kind, body in toc["kinds"].items():
        for f in body["files"]:
            declared[f["path"]] = kind

    # Directories whose files a kind lists one by one: kind per directory.
    listed_dirs: dict[str, set[str]] = defaultdict(set)
    for section in ("kinds", "campaign_kinds"):
        for kind, body in (corpus.get(section) or {}).items():
            for f in (body or {}).get("files") or []:
                listed_dirs[str(PurePosixPath(f).parent)].add(kind)

    rulings = load_rulings(campaign)
    added, since = new_paths(campaign, args.since)
    untracked = set(git(campaign, "ls-files", "-o", "--exclude-standard").splitlines())
    seen = git(campaign, "ls-files", "-co", "--exclude-standard").splitlines()

    exts = READABLE_EXTENSIONS if args.all_ext else PROSE_EXTENSIONS
    candidates: list[dict] = []
    hidden_ext = 0
    for path in sorted(set(seen)):
        p = PurePosixPath(path)
        if path in declared or p.name in SKIP_FILENAMES:
            continue
        if baseline_excluded(path, rec.mechanical.baseline_exclusions) or ruled_out(path, rulings):
            continue
        if p.suffix.lower() not in exts:
            hidden_ext += p.suffix.lower() in READABLE_EXTENSIONS
            continue
        parent = str(p.parent)
        if path in added or path in untracked:
            signal = "new"
        elif parent in listed_dirs:
            signal = "sibling"
        else:
            signal = "backlog"
        candidates.append({
            "path": path,
            "signal": signal,
            "untracked": path in untracked,
            "suggested_kinds": sorted(listed_dirs.get(parent, ())),
        })

    # Rulings that no longer match anything, or contradict the corpus.
    stale = [r for r in rulings
             if not any(s == r["path"] or (r["path"].endswith("/") and s.startswith(r["path"]))
                        for s in seen)]
    conflicts = [{"path": p, "kind": k, "ruling": r} for p, k in declared.items()
                 if (r := ruled_out(p, rulings))]

    # Collapse a large new/backlog subtree into one row: rule a pipeline tree once.
    # Siblings are never collapsed; each one is a file a `files:` list could take.
    def key(c: dict) -> tuple[str, str]:
        return c["signal"], "/".join(PurePosixPath(c["path"]).parent.parts[:args.depth])

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for c in candidates:
        if c["signal"] != "sibling":
            groups[key(c)].append(c)
    collapsed = {k: cs for k, cs in groups.items() if k[1] and len(cs) > args.collapse}
    rows = [c for c in candidates if key(c) not in collapsed]
    rows += [{"path": d + "/", "signal": sig, "files": len(cs),
              "untracked": all(c["untracked"] for c in cs), "suggested_kinds": []}
             for (sig, d), cs in sorted(collapsed.items())]

    report = {
        "campaign": name,
        "corpus_last_committed": since,
        "declared_files": len(declared),
        "rulings": len(rulings),
        "extensions": sorted(exts),
        "hidden_other_extensions": hidden_ext,
        "counts": {s: sum(1 for c in candidates if c["signal"] == s)
                   for s in ("new", "sibling", "backlog")},
        "candidates": rows,
        "stale_rulings": stale,
        "conflicts": conflicts,
    }
    if args.json:
        json.dump(report, sys.stdout, indent=2)
        print()
        return 0

    print(f"{name}: {len(declared)} declared, {len(rulings)} out-rulings, "
          f"corpus.yaml last committed {since or '(never)'}")
    for signal in ("new", "sibling", "backlog"):
        group = [r for r in rows if r["signal"] == signal]
        print(f"\n{signal} ({report['counts'][signal]} file(s))")
        for r in group:
            hint = f"  -> {', '.join(r['suggested_kinds'])}" if r["suggested_kinds"] else ""
            extra = f"  [{r['files']} files]" if "files" in r else ""
            extra += "  [untracked]" if r.get("untracked") else ""
            print(f"  {r['path']}{extra}{hint}")
    if hidden_ext:
        print(f"\n{hidden_ext} other minable file(s) not shown (--all-ext to list)")
    for r in stale:
        print(f"STALE ruling (matches nothing on disk): {r['path']}")
    for c in conflicts:
        print(f"CONFLICT: {c['path']} is declared in {c['kind']} but ruled out "
              f"({c['ruling']['path']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
