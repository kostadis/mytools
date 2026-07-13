#!/usr/bin/env python3
"""Find type-duplicate dossiers in a facts_to_state.py state_dossiers/ dir —
the same entity extracted under two or more different `(type, subject)` keys
(e.g. npc_glabbagool.md + monster_glabbagool.md + object_glabbagool.md).

facts_to_state.py groups facts by (type, subject), not by subject alone (see
CampaignGenerator's docs/cli/ensemble_workflow.md, "Known limitation — type
duplicates"). Alias review does not fix this — aliases collapse name
variants, not type variants. This scanner surfaces the candidate groups for
a human to confirm are genuinely the same entity before merging (a shared
name across types is not always the same entity — a location and an NPC can
coincidentally share a name).

Inputs:
  --dossier-dir <path>   state_dossiers/ directory (default: docs/ensemble/state_dossiers)
  --decisions <path>     optional .type_merge_decisions.json — groups already
                          fully decided (see apply_type_merge.py schema) are
                          excluded from the output so re-runs are resumable.

Outputs JSON to stdout:
  {
    "total_dossiers": N,
    "single_type": N,          # no decision needed
    "candidate_groups": [
      {
        "key": "glabbagool",   # normalised subject name
        "members": [
          {"file": "npc_glabbagool.md", "name": "Glabbagool", "type": "npc",
           "n_facts": 151, "chapters": "34-61"},
          ...
        ]
      },
      ...
    ],
    "already_decided": N        # candidate groups skipped because a decision
                                 # already covers every member
  }

Frontmatter format (facts_to_state.py output):
  ---
  name: Glabbagool
  type: npc
  n_facts: 151
  chapters: 34-61
  ---
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

_FIELD_RE = {
    "name": re.compile(r"^name:\s*(.+?)\s*$", re.M),
    "type": re.compile(r"^type:\s*(\S+)\s*$", re.M),
    "n_facts": re.compile(r"^n_facts:\s*(\d+)\s*$", re.M),
    "chapters": re.compile(r"^chapters:\s*(\S+)\s*$", re.M),
}


def _norm_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().casefold())


def parse_frontmatter(path: Path) -> "dict | None":
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    front = text[:end] if end != -1 else text[:400]
    out = {}
    for field, rx in _FIELD_RE.items():
        m = rx.search(front)
        if m:
            out[field] = m.group(1)
    if "name" not in out or "type" not in out:
        return None
    out["n_facts"] = int(out.get("n_facts", 0))
    out.setdefault("chapters", "")
    return out


def load_decided_keys(decisions_path: "Path | None") -> set[str]:
    """A group is fully decided if every one of its members appears in some
    resolution sub-group of a decision recorded under that key. We only need
    the key set here — apply_type_merge.py does the member-level bookkeeping."""
    if decisions_path is None or not decisions_path.exists():
        return set()
    try:
        data = json.loads(decisions_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    return {d["key"] for d in data.get("groups", []) if d.get("key")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dossier-dir", default="docs/ensemble/state_dossiers", metavar="DIR")
    ap.add_argument("--decisions", default=None, metavar="FILE")
    args = ap.parse_args()

    dossier_dir = Path(args.dossier_dir)
    decided_keys = load_decided_keys(Path(args.decisions) if args.decisions else None)

    groups: dict[str, list[dict]] = defaultdict(list)
    skipped_unparsed = 0
    total = 0
    for f in sorted(dossier_dir.glob("*.md")):
        total += 1
        fm = parse_frontmatter(f)
        if fm is None:
            skipped_unparsed += 1
            continue
        key = _norm_key(fm["name"])
        groups[key].append({
            "file": f.name, "name": fm["name"], "type": fm["type"],
            "n_facts": fm["n_facts"], "chapters": fm["chapters"],
        })

    single_type = 0
    candidates = []
    already_decided = 0
    for key, members in sorted(groups.items()):
        types = {m["type"] for m in members}
        if len(types) <= 1:
            single_type += len(members)
            continue
        if key in decided_keys:
            already_decided += 1
            continue
        members.sort(key=lambda m: -m["n_facts"])
        candidates.append({"key": key, "members": members})

    candidates.sort(key=lambda g: -sum(m["n_facts"] for m in g["members"]))

    print(json.dumps({
        "total_dossiers": total,
        "unparsed": skipped_unparsed,
        "single_type": single_type,
        "candidate_groups": candidates,
        "already_decided": already_decided,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
