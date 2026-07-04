"""Post-run link-relation consolidation: deterministic grouping of near-synonym
relation types + apply of human-approved merge decisions.

The counterpart of ``consolidate.py`` (which does the same for category names).
Two entry points, both driven from the CLI (`drive-tagger consolidate *-links`)
and orchestrated interactively by the /drive-consolidate-links skill:

  collect_relations() - read-only. Groups the *rogue* relation types (those
                        outside the 5 canonical relations) into families by
                        string similarity (single-linkage union-find over a
                        normalized edit-distance matrix), writes
                        reports/consolidation/link_clusters.json.
  apply_relations()   - reads a link_decisions.json (same schema shape as the
                        category decisions.json), folds approved families via
                        graph.merge_relations, regenerates reports/.

The relation vocabulary is tiny, so "clustering" is over relation *strings*, not
embeddings — but the generic union-find / confidence / stable-id primitives are
reused verbatim from consolidate.py. String distance only proposes tight
families; the human regroups semantically (the skill's Split option) where it
misses a family (e.g. ``series-member`` <-> ``sequel-to``).

Nothing here talks to Drive, the DGX judge, or an LLM API.
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import numpy as np

from .config import CONFIG
from .consolidate import _cluster_id, _confidence, _union_find_clusters
from .graph import Graph

# The intended controlled vocabulary. Relations outside this set are the rogue
# types a consolidation targets. (This mirrors pipeline._ALLOWED_RELATIONS; a
# later follow-up promotes it to one shared constant.)
CANONICAL_RELATIONS = ("supersedes", "part-of", "duplicate-of", "references", "related-to")

SAMPLE_NOTES_CAP = 5
# Trailing hyphen-tokens stripped when deriving a relation's stem, so that
# `complementary-to` / `complementary-version` / `series-member` / `series-part`
# collapse onto a shared stem and group deterministically.
_SUFFIX_TOKENS = {"of", "to", "version", "resource", "part", "member"}

# Directional antonyms: a family holding BOTH sides can't be safely folded onto
# one canonical — that would reverse edge direction. When detected, the tool
# withholds `suggested_canonical` (emits None) so the review UI cannot offer a
# one-tap approve; the human must split or remap to a non-directional canonical.
_ANTONYM_STEMS = [
    frozenset({"sequel", "prequel"}),
    frozenset({"predecessor", "successor"}),
    frozenset({"supersedes", "superseded"}),
    frozenset({"ancestor", "descendant"}),
]


# -- string distance (pure, no I/O — unit-testable) --------------------------

def _stem(rel: str) -> str:
    """Relation stem: drop trailing connective/format tokens (e.g.
    ``complementary-to`` -> ``complementary``, ``series-member`` -> ``series``).
    Plural/adjective variants (``complements`` vs ``complementary``) are caught
    by the edit-distance fallback, not here."""
    toks = rel.lower().split("-")
    while len(toks) > 1 and toks[-1] in _SUFFIX_TOKENS:
        toks.pop()
    return "-".join(toks)


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _norm_lev(a: str, b: str) -> float:
    m = max(len(a), len(b))
    return 0.0 if m == 0 else _levenshtein(a, b) / m


def _antonym_conflict(names: list[str]) -> Optional[str]:
    """If the family's relation tokens contain both sides of a directional
    antonym pair, return "a vs b"; else None. Folding such a family onto one
    canonical would reverse edge direction."""
    tokens: set[str] = set()
    for r in names:
        tokens.update(r.lower().split("-"))
    for pair in _ANTONYM_STEMS:
        if pair <= tokens:
            return " vs ".join(sorted(pair))
    return None


def _relation_distance_matrix(names: list[str]) -> np.ndarray:
    """Symmetric distance in [0, 1]: 0 when two relations share a stem, else the
    smaller of the normalized edit distance on the raw names and on the stems.
    Diagonal is +inf (mirrors _pairwise_cosine_distance in consolidate.py)."""
    n = len(names)
    stems = [_stem(x) for x in names]
    d = np.zeros((n, n), dtype=float)
    for i in range(n):
        for j in range(i + 1, n):
            if stems[i] == stems[j]:
                dist = 0.0
            else:
                dist = min(_norm_lev(names[i], names[j]), _norm_lev(stems[i], stems[j]))
            d[i, j] = d[j, i] = dist
    np.fill_diagonal(d, np.inf)
    return d


# -- collect ----------------------------------------------------------------

def collect_relations(*, threshold: Optional[float] = None) -> dict:
    """Read-only: group rogue relation types into merge-candidate families and
    write reports/consolidation/link_clusters.json. Returns the result dict."""
    thr = threshold if threshold is not None else CONFIG.relation_cluster_threshold
    CONFIG.ensure_dirs()

    graph = Graph()
    try:
        links = graph.all_links()
    finally:
        graph.close()

    counts = Counter(ln["relation"] for ln in links)
    notes: dict[str, list[str]] = defaultdict(list)
    for ln in links:
        if ln.get("note"):
            notes[ln["relation"]].append(ln["note"])

    canonical_counts = {r: counts.get(r, 0) for r in CANONICAL_RELATIONS}
    rogue = sorted(r for r in counts if r not in CANONICAL_RELATIONS)

    def _member(rel: str) -> dict:
        return {
            "relation": rel,
            "count": counts[rel],
            "sample_notes": sorted(set(notes.get(rel, [])))[:SAMPLE_NOTES_CAP],
        }

    def _singleton(rel: str) -> dict:
        # Rogue relations that didn't group still warrant review (map to a
        # canonical or leave), so they carry a stable id like clusters do.
        return {"id": _cluster_id([rel]), **_member(rel)}

    clusters: list[dict] = []
    singletons: list[dict] = []
    if rogue:
        dist = _relation_distance_matrix(rogue)
        for group in _union_find_clusters(len(rogue), dist, thr):
            if len(group) < 2:
                singletons.append(_singleton(rogue[group[0]]))
                continue
            member_names = [rogue[i] for i in group]
            conf, lo, hi = _confidence(dist, group, thr)
            members_out = [_member(r) for r in sorted(member_names, key=lambda r: -counts[r])]
            # Suggested canonical = the highest-count member (the human may
            # instead map the family onto a canonical-5 relation, option B) —
            # UNLESS the family mixes directional antonyms, where folding onto
            # one side would reverse edges. Then withhold the suggestion.
            antonym = _antonym_conflict(member_names)
            cluster = {
                "id": _cluster_id(member_names),
                "members": members_out,
                "suggested_canonical": None if antonym else max(member_names, key=lambda r: (counts[r], r)),
                "confidence": conf,
                "reason": f"string<={thr:.2f}, intra-cluster [{lo:.4f}, {hi:.4f}]",
                "min_distance": lo,
                "max_distance": hi,
            }
            if antonym:
                cluster["warning"] = (
                    f"directional antonyms ({antonym}) — folding onto one canonical "
                    f"would reverse edge direction; split, or remap to a non-directional "
                    f"canonical (part-of / related-to)"
                )
            clusters.append(cluster)

    conf_rank = {"high": 0, "medium": 1, "low": 2}
    clusters.sort(key=lambda c: (conf_rank[c["confidence"]], c["max_distance"]))
    singletons.sort(key=lambda s: -s["count"])

    result = {
        "clusters": clusters,
        "singletons": singletons,
        "canonical_counts": canonical_counts,
        "n_clusters": len(clusters),
        "n_rogue_types": len(rogue),
        "n_rogue_edges": sum(counts[r] for r in rogue),
    }
    result["path"] = _write_link_clusters_json(thr, result)
    return result


def _write_link_clusters_json(threshold: float, result: dict) -> Path:
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "threshold": threshold,
        "canonical_counts": result["canonical_counts"],
        "clusters": result["clusters"],
        "singletons": result["singletons"],
    }
    path = CONFIG.consolidation_dir / "link_clusters.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


# -- apply ------------------------------------------------------------------

def apply_relations(decisions_path: Path) -> dict:
    """Fold every `approved` family in decisions_path via graph.merge_relations,
    skip everything else, then regenerate reports/. Safe to re-run
    (merge_relations is idempotent once the sources are gone)."""
    decisions = json.loads(Path(decisions_path).read_text(encoding="utf-8"))

    merged, skipped = [], []
    graph = Graph()
    try:
        for cluster_id, d in decisions.items():
            if not isinstance(d, dict) or d.get("status") != "approved":
                skipped.append({"id": cluster_id, "status": d.get("status") if isinstance(d, dict) else "invalid"})
                continue
            canonical = (d.get("canonical") or "").strip()
            sources = [s.strip() for s in (d.get("sources") or []) if s and s.strip()]
            if not canonical or not sources:
                skipped.append({"id": cluster_id, "status": "invalid"})
                continue
            res = graph.merge_relations(sources, into=canonical)
            merged.append({
                "id": cluster_id,
                "canonical": canonical,
                "sources": sources,
                "rewritten": res["rewritten"],
                "deduped": res["deduped"],
            })
    finally:
        graph.close()  # close before report.generate() opens its own Store/Graph

    from . import report as report_mod

    report_paths = report_mod.generate()
    return {"merged": merged, "skipped": skipped, "report_paths": report_paths}
