"""Post-run category consolidation: deterministic clustering of near-duplicate
categories + apply of human-approved merge decisions.

Two entry points, both driven from the CLI (`drive-tagger consolidate ...`)
and orchestrated interactively by the /drive-consolidate skill:

  collect()  - read-only. Clusters categories by embedding similarity
               (single-linkage union-find over cosine distance), writes
               reports/consolidation/clusters.json.
  apply()    - reads a decisions.json (see schema below), merges approved
               clusters via store.merge_categories, regenerates reports/.

Nothing here talks to Drive, the DGX judge, or an LLM API. Single-threaded,
single-process — this runs after a `pipeline` run has already finished.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Optional

import numpy as np

from .config import CONFIG
from .store import Store

SAMPLE_DOCS_CAP = 8
_PUNCT_RE = re.compile(r"[^\w\s]")


# -- clustering (pure, no I/O — unit-testable without a Store) ---------------

def _pairwise_cosine_distance(vectors: np.ndarray) -> np.ndarray:
    """n x n cosine distance matrix. Defensive L2-normalize (turbovecdb
    normalizes on ingest, but don't assume it upstream of this function)."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    unit = vectors / np.clip(norms, 1e-9, None)
    dist = 1.0 - (unit @ unit.T)
    np.fill_diagonal(dist, np.inf)
    return dist


def _union_find_clusters(n: int, dist: np.ndarray, threshold: float) -> list[list[int]]:
    """Single-linkage clustering via union-find: index i and j land in the
    same group iff there's a *path* of pairwise distances each <= threshold
    connecting them (NOT that every pair in the group is within threshold —
    that's the well-known single-linkage chaining property; see plan §0/§3
    for why that's expected here, not a bug). ~20 lines, no sklearn/scipy."""
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    ii, jj = np.where(np.triu(dist <= threshold, k=1))
    for i, j in zip(ii.tolist(), jj.tolist()):
        union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _confidence(dist: np.ndarray, idxs: list[int], threshold: float) -> tuple[str, float, float]:
    """(confidence, min_intra_distance, max_intra_distance) for a cluster.
    Confidence is driven by the LOOSEST (max) intra-cluster pair relative to
    threshold — this is what exposes single-linkage chaining/hub artifacts
    (a hub-chained cluster has a huge max-intra distance even though every
    individual *edge* that built it was <= threshold)."""
    if len(idxs) < 2:
        return "high", 0.0, 0.0
    sub = [dist[a, b] for x, a in enumerate(idxs) for b in idxs[x + 1:]]
    lo, hi = min(sub), max(sub)
    if hi <= threshold:
        conf = "high"
    elif hi <= 2 * threshold:
        conf = "medium"
    else:
        conf = "low"
    return conf, round(float(lo), 4), round(float(hi), 4)


def _cluster_id(member_names: list[str]) -> str:
    """Stable id = hash of sorted member names. Used as the decisions.json
    key so re-runs of collect() (same membership -> same id) let the skill
    recognize already-decided clusters. If cluster membership changes across
    runs (new near-dupe categories appear), the id changes too — that's
    intentional: it's a genuinely different cluster to review."""
    key = "|".join(sorted(n.lower() for n in member_names))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _member_entries(member_names: list[str], members_by_cat: dict[str, list[str]]) -> list[dict]:
    """Build the `members` list shared by every cluster/pair entry: one dict
    per member name with its live member_count (from inverted document
    membership, not stored metadata) and up to SAMPLE_DOCS_CAP sample doc
    names, sorted by descending member_count."""
    return [
        {
            "name": nm,
            "member_count": len(members_by_cat.get(nm, [])),
            "sample_docs": sorted(members_by_cat.get(nm, []))[:SAMPLE_DOCS_CAP],
        }
        for nm in sorted(member_names, key=lambda nm: -len(members_by_cat.get(nm, [])))
    ]


def _pick_canonical(member_names: list[str], members_by_cat: dict[str, list[str]]) -> str:
    """Canonical = highest actual member count (from inverted membership),
    tie-broken by name for determinism. Shared by embedding clusters and
    lexical pairs so both signals pick a canonical the same way."""
    ranked = sorted(
        member_names,
        key=lambda nm: (-len(members_by_cat.get(nm, [])), nm.lower()),
    )
    return ranked[0]


def _normalize_name(name: str) -> str:
    """Lowercase, strip punctuation/apostrophes, collapse whitespace, and
    naively singularize every whitespace-separated token: a lexical signal
    independent of embedding distance, for name-level dupes that embedding
    distance cannot reliably catch at *any* threshold (issue #99;
    DEDUP_BLIND_SPOTS.md failure mode 2 — e.g. "Floating City" / "Floating
    Cities" sit at cosine distance 0.36, past every chaining cliff).

    Singularization rule per token, in this exact order (load-bearing —
    do not reorder or add a blanket 'es' strip):
      1. if the token ends in "ies", replace the trailing "ies" with "y"
      2. else if the token ends in a single trailing "s", strip that one "s"

    Deliberately no exception word-list (e.g. "series" -> "sery" is
    harmless, non-colliding noise, not a defect; "N.E.W." / "New" is a
    known, accepted false-positive collision from punctuation-stripping).
    This is a human-reviewed signal (the drive-consolidate skill's
    AskUserQuestion flow) — a wrong-but-non-colliding normalization is not
    worth suppressing at the risk of also suppressing real pairs.
    """
    lowered = name.lower()
    cleaned = _PUNCT_RE.sub("", lowered)
    tokens = []
    for tok in cleaned.split():
        if tok.endswith("ies"):
            tok = tok[:-3] + "y"
        elif tok.endswith("s"):
            tok = tok[:-1]
        tokens.append(tok)
    return " ".join(tokens)


def _lexical_pairs(names: list[str], members_by_cat: dict[str, list[str]]) -> list[dict]:
    """Group `names` by _normalize_name() and emit one entry per group with
    2+ distinct original names — the lexical/name-normalization signal from
    issue #99. Entry shape mirrors an embedding cluster entry exactly (same
    `id` / `members` / `suggested_canonical` keys) so the drive-consolidate
    skill's existing review UI works unchanged. No `confidence` /
    `min_distance` / `max_distance` — those are embedding-specific and
    meaningless for a lexical match, so they're omitted rather than
    fabricated."""
    groups: dict[str, list[str]] = {}
    for nm in names:
        groups.setdefault(_normalize_name(nm), []).append(nm)

    items = []
    for normalized, group_names in groups.items():
        member_names = sorted(set(group_names))
        if len(member_names) < 2:
            continue
        items.append(
            (
                normalized,
                {
                    "id": _cluster_id(member_names),
                    "members": _member_entries(member_names, members_by_cat),
                    "suggested_canonical": _pick_canonical(member_names, members_by_cat),
                    "reason": f"lexical: normalized to '{normalized}'",
                },
            )
        )
    items.sort(key=lambda t: t[0])
    return [entry for _, entry in items]


# -- collect -------------------------------------------------------------

def collect(*, threshold: Optional[float] = None, diagnostics: bool = False) -> dict:
    CONFIG.ensure_dirs()
    thr = CONFIG.consolidate_cluster_threshold if threshold is None else threshold

    store = Store()
    try:
        cats = store.all_categories_with_vectors()
        docs = store.all_documents()
    finally:
        store.close()

    # category name -> member doc names (invert all_documents(); this is also
    # the source of truth for member counts/canonical choice below — NOT the
    # stored member_count metadata, which can drift from actual membership).
    members_by_cat: dict[str, list[str]] = {}
    for d in docs:
        for cname in d.get("categories", []) or []:
            members_by_cat.setdefault(cname, []).append(d.get("name", d["id"]))

    # Lexical pass runs over every category name regardless of whether it has
    # a vector — it's a pure name-normalization signal, not embedding-based
    # (issue #99), so it must be computed before `cats` gets narrowed to the
    # vector-bearing subset below, and before the n == 0 early-return: lexical
    # pairs can exist even with zero embeddable categories.
    all_names = [c["name"] for c in cats]
    lexical_pairs = _lexical_pairs(all_names, members_by_cat)

    cats = [c for c in cats if c.get("vector")]  # defensive: skip vector-less rows
    names = [c["name"] for c in cats]
    vecs = np.array([c["vector"] for c in cats], dtype=np.float32)
    n = len(names)

    if n == 0:
        result = {
            "clusters": [],
            "singletons": [],
            "n_clusters": 0,
            "n_absorbed": 0,
            "n_singletons": 0,
            "lexical_pairs": lexical_pairs,
        }
        path = _write_clusters_json(thr, result)
        return {**result, "path": path}

    dist = _pairwise_cosine_distance(vecs)

    if diagnostics:
        _print_diagnostics(names, dist)

    groups = _union_find_clusters(n, dist, thr)
    multi = [g for g in groups if len(g) > 1]
    singleton_idxs = {i for g in groups if len(g) == 1 for i in g}

    clusters_out = []
    for group in multi:
        member_names = [names[i] for i in group]
        conf, lo, hi = _confidence(dist, group, thr)
        canonical = _pick_canonical(member_names, members_by_cat)
        members_out = _member_entries(member_names, members_by_cat)
        clusters_out.append(
            {
                "id": _cluster_id(member_names),
                "members": members_out,
                "suggested_canonical": canonical,
                "confidence": conf,
                "reason": f"cosine<={thr:.4f}, intra-cluster [{lo:.4f}, {hi:.4f}]",
                "min_distance": lo,
                "max_distance": hi,
            }
        )
    # Present tightest/most-confident clusters first (highest-yield review order).
    clusters_out.sort(key=lambda c: ({"high": 0, "medium": 1, "low": 2}[c["confidence"]], c["max_distance"]))

    singletons_out = [
        {"name": names[i], "member_count": len(members_by_cat.get(names[i], []))}
        for i in sorted(singleton_idxs, key=lambda i: names[i].lower())
    ]

    result = {
        "clusters": clusters_out,
        "singletons": singletons_out,
        "n_clusters": len(clusters_out),
        "n_absorbed": sum(len(c["members"]) for c in clusters_out),
        "n_singletons": len(singletons_out),
        "lexical_pairs": lexical_pairs,
    }
    path = _write_clusters_json(thr, result)
    return {**result, "path": path}


def _write_clusters_json(threshold: float, result: dict) -> Path:
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "threshold": threshold,
        "embed_provider": CONFIG.embed_provider,
        "clusters": result["clusters"],
        "singletons": result["singletons"],
        "lexical_pairs": result.get("lexical_pairs", []),
    }
    path = CONFIG.consolidation_dir / "clusters.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _print_diagnostics(names: list[str], dist: np.ndarray) -> None:
    """Sorted nearest category-pair distances, for threshold calibration
    (see plan §0 for the methodology this mirrors)."""
    n = len(names)
    nn_dist = dist.min(axis=1)
    nn_idx = dist.argmin(axis=1)
    order = np.argsort(nn_dist)
    print(f"\n{n} categories — nearest-neighbor distance, tightest 40 pairs:")
    seen = set()
    shown = 0
    for i in order:
        j = int(nn_idx[i])
        key = tuple(sorted((int(i), j)))
        if key in seen:
            continue
        seen.add(key)
        print(f"  {dist[i, j]:.4f}  {names[i]!r} <-> {names[j]!r}")
        shown += 1
        if shown >= 40:
            break
    print("\nNearest-neighbor distance percentiles:")
    for p in (1, 5, 10, 25, 50):
        print(f"  p{p}: {np.percentile(nn_dist, p):.4f}")


# -- apply -----------------------------------------------------------------

def apply(decisions_path: Path) -> dict:
    """Merge every `approved` entry in decisions_path, skip everything else,
    then regenerate reports/. See plan §4 for the decisions.json schema.
    Safe to re-run (merge_categories is idempotent for already-merged
    sources)."""
    decisions = json.loads(Path(decisions_path).read_text(encoding="utf-8"))

    merged, skipped = [], []
    store = Store()
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
            store.merge_categories(sources, into=canonical, description=d.get("description", ""))
            merged.append({"id": cluster_id, "canonical": canonical, "sources": sources})
    finally:
        store.close()  # close before report.generate() opens its own Store/Graph

    from . import report as report_mod

    report_paths = report_mod.generate()
    return {"merged": merged, "skipped": skipped, "report_paths": report_paths}
