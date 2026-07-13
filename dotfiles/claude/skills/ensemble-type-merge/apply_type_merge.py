#!/usr/bin/env python3
"""Deterministically apply confirmed type-merge decisions, producing
docs/ensemble/merged_dossiers/ from docs/ensemble/state_dossiers/.

No LLM call, no re-synthesis — this is pure file concatenation/copy, exactly
like the Stage 2e workflow documented in CampaignGenerator's
docs/cli/ensemble_workflow.md, but decision-aware: only groups the human
explicitly confirmed as "merged" get concatenated; everything else (single-
type entities, groups the human said are different entities, and groups with
no decision yet) is copied through unmodified so nothing silently drops out
of the synthesis corpus.

Inputs:
  --dossier-dir <path>   source dir (default: docs/ensemble/state_dossiers)
  --out-dir <path>       destination dir (default: docs/ensemble/merged_dossiers)
  --decisions <path>     .type_merge_decisions.json (default:
                          docs/ensemble/.type_merge_decisions.json)

Decisions file schema:
  {
    "groups": [
      {
        "key": "glabbagool",              # normalised subject name
        "resolution": [
          {"status": "merged", "members": ["npc_glabbagool.md", "monster_glabbagool.md"],
           "primary": "npc_glabbagool.md"},
          {"status": "kept_separate", "members": ["object_glabbagool.md"]}
        ]
      },
      ...
    ]
  }

A "merged" sub-group's members are concatenated (densest/primary file's name
and frontmatter lead) with an HTML-comment source marker before each member's
full text, separated by a `---` divider — the exact format the Stage 2e
heredoc snippet already produced by hand. "kept_separate" members, and any
member not mentioned in any decision, are copied through under their
original filename, unchanged.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def load_decisions(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("groups", [])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dossier-dir", default="docs/ensemble/state_dossiers", metavar="DIR")
    ap.add_argument("--out-dir", default="docs/ensemble/merged_dossiers", metavar="DIR")
    ap.add_argument("--decisions", default="docs/ensemble/.type_merge_decisions.json", metavar="FILE")
    args = ap.parse_args()

    src = Path(args.dossier_dir)
    dst = Path(args.out_dir)
    dst.mkdir(parents=True, exist_ok=True)

    all_files = {f.name: f for f in src.glob("*.md")}
    handled: set[str] = set()

    n_merged_groups = 0
    n_merged_files = 0
    n_kept_separate = 0
    n_copied_undecided = 0

    for group in load_decisions(Path(args.decisions)):
        for sub in group.get("resolution", []):
            members = [m for m in sub.get("members", []) if m in all_files]
            if not members:
                continue
            if sub.get("status") == "merged" and len(members) > 1:
                primary = sub.get("primary") or members[0]
                if primary not in members:
                    primary = members[0]
                ordered = [primary] + [m for m in members if m != primary]
                parts = []
                for name in ordered:
                    parts.append(f"<!-- source: {name} -->\n")
                    parts.append(all_files[name].read_text(encoding="utf-8").rstrip())
                (dst / primary).write_text(
                    "\n\n---\n\n".join(parts) + "\n", encoding="utf-8")
                n_merged_groups += 1
                n_merged_files += len(members)
                handled.update(members)
            else:
                for name in members:
                    shutil.copy(all_files[name], dst / name)
                    n_kept_separate += 1
                    handled.add(name)

    for name, path in sorted(all_files.items()):
        if name in handled:
            continue
        shutil.copy(path, dst / name)
        n_copied_undecided += 1

    total_out = len(list(dst.glob("*.md")))
    print(f"Merged groups:        {n_merged_groups}  ({n_merged_files} source files)")
    print(f"Kept-separate files:  {n_kept_separate}")
    print(f"Copied unchanged:     {n_copied_undecided}  "
          f"(single-type, or no type-merge decision yet)")
    print(f"Total in {dst}: {total_out}")


if __name__ == "__main__":
    main()
