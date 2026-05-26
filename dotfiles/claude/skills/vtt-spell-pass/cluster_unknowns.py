#!/usr/bin/env python3
"""Cluster transcript unknown proper-nouns by similarity so a single user
decision covers many variants.

Reads the JSON output of `find_unknowns.py` (passed on stdin or via --in)
plus the same glossary + npcs-dir, then groups unknowns into clusters:

1. **Bound to known canonical**: every unknown that's "close enough" to a
   known canonical (edit distance ≤ 3, OR phonetic key match) is bucketed
   under that canonical. One question per canonical replaces N questions.

2. **Cross-unknown cluster**: remaining unknowns are clustered by edit
   distance ≤ 2 to each other, OR matching phonetic key (devowel + dedup
   consecutive consonants). User answers once per cluster.

3. **Singletons**: leftovers each get their own one-member cluster.

Outputs JSON to stdout:
  {
    "clusters": [
      {
        "id": 1,
        "proposed_canonical": "Glabbagool",       # or null
        "confidence": "high",                     # high | medium | low
        "reason": "edit distance to known",
        "members": [
          {"token": "Glavagul",  "count": 4, "context": "..."},
          {"token": "Lavagul",   "count": 2, "context": "..."},
          {"token": "Lavagul's", "count": 1, "context": "..."}
        ]
      },
      ...
    ]
  }

Confidence ranking:
  high   - every member within ed ≤ 2 of the proposed canonical
  medium - cluster members agree (ed ≤ 2 to each other or phonetic), no
           single canonical proposed (or canonical match is ed=3)
  low    - phonetic-only match, or singleton with no neighbors
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from find_unknowns import (  # type: ignore
    parse_glossary,
    parse_npc_dossiers,
    load_extra,
)


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins = cur[j - 1] + 1
            dele = prev[j] + 1
            sub = prev[j - 1] + (ca != cb)
            cur.append(min(ins, dele, sub))
        prev = cur
    return prev[-1]


_VOWELS = set("aeiouy")


def phonetic_key(s: str) -> str:
    """Crude phonetic squash: lowercase, drop vowels (except leading),
    collapse consecutive duplicate consonants, drop punctuation.
    Useful for catching e.g. Glavagul/Glabbagool/Globul as related.
    """
    s = re.sub(r"[^A-Za-z]+", "", s).lower()
    if not s:
        return ""
    out = [s[0]]
    for ch in s[1:]:
        if ch in _VOWELS:
            continue
        if out and out[-1] == ch:
            continue
        out.append(ch)
    return "".join(out)


def _max_ed_for_length(n: int) -> int:
    """Length-scaled edit-distance threshold to avoid short-token noise."""
    if n <= 4:
        return 1
    if n <= 7:
        return 2
    return 3


def best_known_match(token: str, knowns: list[str]) -> tuple[str | None, int, str]:
    """Return (best_canonical, distance, reason) or (None, -1, '').

    Match rules (tightened to avoid short-token false positives):
      - exact (case-insensitive)
      - substring, but only if BOTH sides have ≥ 5 chars on the shorter side
      - edit distance ≤ length-scaled threshold (1 for ≤4 chars, 2 for ≤7,
        3 for ≥8) AND first letter matches when token len ≤ 6
      - phonetic key match, requires first letter match AND shared length
        within 2 chars
    """
    if not knowns:
        return None, -1, ""

    tok = token.strip()
    tok_lc = tok.lower()
    tok_phon = phonetic_key(tok)
    best: tuple[str | None, int, str] = (None, 999, "")

    short_tok = len(tok_lc) <= 6
    max_ed = _max_ed_for_length(len(tok_lc))

    for k in knowns:
        k_lc = k.lower()
        if k_lc == tok_lc:
            return k, 0, "exact"
        # Substring — both sides need ≥ 5 chars on the shorter side
        shorter = min(len(tok_lc), len(k_lc))
        if shorter >= 5:
            if tok_lc in k_lc or k_lc in tok_lc:
                return k, 1, "substring"
        # Edit distance, length-scaled
        d = levenshtein(tok_lc, k_lc)
        ed_limit = min(max_ed, _max_ed_for_length(len(k_lc)))
        if d <= ed_limit and d < best[1]:
            # First-letter must match when either side is short
            if short_tok or len(k_lc) <= 6:
                if tok_lc[:1] != k_lc[:1]:
                    continue
            best = (k, d, "edit_distance")
        # Phonetic — require first-letter match and similar length
        if tok_phon and tok_phon == phonetic_key(k):
            if (
                tok_lc[:1] == k_lc[:1]
                and abs(len(tok_lc) - len(k_lc)) <= 3
                and best[1] > 2
            ):
                best = (k, 2, "phonetic")

    if best[0] is None:
        return None, -1, ""
    return best


def cross_cluster(tokens: list[str]) -> list[list[str]]:
    """Cluster tokens against each other by ed ≤ 2 OR phonetic key match.
    Simple union-find.
    """
    parent: dict[str, str] = {t: t for t in tokens}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    phon_buckets: dict[str, list[str]] = {}
    for t in tokens:
        k = phonetic_key(t)
        phon_buckets.setdefault(k, []).append(t)

    # Phonetic-key matches (skip empty key)
    for k, group in phon_buckets.items():
        if not k or len(group) < 2:
            continue
        first = group[0]
        for other in group[1:]:
            union(first, other)

    # Edit-distance pairs (length-scaled, first-letter must match for short)
    for i, a in enumerate(tokens):
        for b in tokens[i + 1 :]:
            if find(a) == find(b):
                continue
            a_lc, b_lc = a.lower(), b.lower()
            limit = min(_max_ed_for_length(len(a_lc)), _max_ed_for_length(len(b_lc)))
            if levenshtein(a_lc, b_lc) > limit:
                continue
            if (len(a_lc) <= 6 or len(b_lc) <= 6) and a_lc[:1] != b_lc[:1]:
                continue
            union(a, b)

    clusters: dict[str, list[str]] = {}
    for t in tokens:
        clusters.setdefault(find(t), []).append(t)
    return list(clusters.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", type=Path,
                    help="JSON output of find_unknowns.py (default: stdin)")
    ap.add_argument("--glossary", required=True, type=Path)
    ap.add_argument("--npcs-dir", required=True, type=Path)
    ap.add_argument("--extra-known", type=Path)
    args = ap.parse_args()

    if args.in_path:
        data = json.loads(args.in_path.read_text(encoding="utf-8"))
    else:
        data = json.load(sys.stdin)

    unknowns = data.get("unknown_propers", [])
    if not unknowns:
        print(json.dumps({"clusters": []}, indent=2))
        return

    # Rebuild known set the same way find_unknowns does
    replacements, canonicals = parse_glossary(args.glossary)
    npc_names = parse_npc_dossiers(args.npcs_dir)
    extra = load_extra(args.extra_known)
    wrong_forms = {w for w, _ in replacements}
    knowns_set = set(canonicals) | npc_names | extra | wrong_forms
    # Keep only multi-character names; single letters are noise
    knowns = [k for k in knowns_set if len(k) >= 3]

    # Map wrong-forms to their canonical so a match on "Glabigle" proposes
    # "Glabbagool" (the canonical) rather than "Glabigle" itself.
    wrong_to_canon: dict[str, str] = {}
    for w, c in replacements:
        wrong_to_canon[w.lower()] = c
    canonicals_lc = {c.lower() for c in canonicals} | {n.lower() for n in npc_names} | {e.lower() for e in extra}

    def resolve_canonical(matched: str) -> str:
        """If the matched name is a known wrong-form, return its canonical."""
        if matched.lower() in canonicals_lc:
            return matched
        if matched.lower() in wrong_to_canon:
            return wrong_to_canon[matched.lower()]
        return matched

    # Build a map token -> meta (count, contexts)
    meta: dict[str, dict] = {u["token"]: u for u in unknowns}
    tokens = list(meta.keys())

    # Phase A: bind each token to best known canonical
    bound: dict[str, list[str]] = {}      # canonical -> [tokens]
    bind_info: dict[str, tuple[int, str]] = {}  # canonical -> (worst_distance, reason_set)
    leftover: list[str] = []
    for t in tokens:
        matched, dist, reason = best_known_match(t, knowns)
        if matched is None:
            leftover.append(t)
            continue
        canon = resolve_canonical(matched)
        bound.setdefault(canon, []).append(t)
        prev_d, prev_reasons = bind_info.get(canon, (0, ""))
        bind_info[canon] = (max(prev_d, dist), (prev_reasons + "," + reason).strip(","))

    # Phase B: cluster leftover tokens against each other
    cross_clusters = cross_cluster(leftover) if leftover else []

    # Build output clusters
    out_clusters = []
    cid = 0

    # Bound-to-known clusters first (sorted by total count desc)
    def total_count(toks: list[str]) -> int:
        return sum(meta[t]["count"] for t in toks)

    for canon, toks in sorted(bound.items(), key=lambda kv: -total_count(kv[1])):
        worst_d, reason = bind_info[canon]
        if worst_d == 0:
            confidence = "high"
        elif worst_d <= 2:
            confidence = "high"
        elif worst_d == 3:
            confidence = "medium"
        else:
            confidence = "low"
        cid += 1
        out_clusters.append({
            "id": cid,
            "proposed_canonical": canon,
            "confidence": confidence,
            "reason": reason,
            "members": [
                {
                    "token": t,
                    "count": meta[t]["count"],
                    "context": (meta[t]["contexts"] or [""])[0],
                }
                for t in sorted(toks, key=lambda x: -meta[x]["count"])
            ],
        })

    # Cross-unknown clusters
    for group in sorted(cross_clusters, key=lambda g: -total_count(g)):
        cid += 1
        out_clusters.append({
            "id": cid,
            "proposed_canonical": None,
            "confidence": "medium" if len(group) > 1 else "low",
            "reason": "cross-unknown" if len(group) > 1 else "singleton",
            "members": [
                {
                    "token": t,
                    "count": meta[t]["count"],
                    "context": (meta[t]["contexts"] or [""])[0],
                }
                for t in sorted(group, key=lambda x: -meta[x]["count"])
            ],
        })

    print(json.dumps({"clusters": out_clusters}, indent=2))


if __name__ == "__main__":
    main()
