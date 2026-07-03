"""Tests for the pure clustering primitives in consolidate.py (issue #88):
_union_find_clusters, _confidence, _cluster_id.

No Store, no fixture — these are pure functions over hand-built distance
matrices. Fully offline by construction.
"""

import numpy as np

from drive_tagger.consolidate import _cluster_id, _confidence, _union_find_clusters


def _symmetric(n, pairs, default=1.0):
    """Build an n x n distance matrix from a dict of {(i, j): dist} pairs
    (symmetric), filling everything else with `default` and inf on the
    diagonal (matching _pairwise_cosine_distance's convention)."""
    dist = np.full((n, n), default, dtype=np.float64)
    for (i, j), d in pairs.items():
        dist[i, j] = d
        dist[j, i] = d
    np.fill_diagonal(dist, np.inf)
    return dist


# -- _union_find_clusters -----------------------------------------------------


def test_union_find_groups_tight_pairs_and_isolates_far_point():
    # 5 points: {0,1} tight pair, {2,3} tight pair, 4 isolated.
    dist = _symmetric(
        5,
        {
            (0, 1): 0.01,
            (2, 3): 0.02,
        },
        default=0.9,
    )

    groups = _union_find_clusters(5, dist, threshold=0.05)

    group_sets = sorted((sorted(g) for g in groups), key=lambda g: g[0])
    assert group_sets == [[0, 1], [2, 3], [4]]


def test_union_find_threshold_boundary_is_inclusive():
    dist = _symmetric(2, {(0, 1): 0.05}, default=0.9)

    groups_at_threshold = _union_find_clusters(2, dist, threshold=0.05)
    groups_below_threshold = _union_find_clusters(2, dist, threshold=0.04)

    assert sorted(sorted(g) for g in groups_at_threshold) == [[0, 1]]
    assert sorted(sorted(g) for g in groups_below_threshold) == [[0], [1]]


# -- chaining / confidence (the load-bearing mitigation, plan §0/§3) --------


def test_hub_chains_two_far_groups_into_one_with_low_confidence():
    # H (index 0) is within threshold of A (1) and B (2), but A and B are
    # far apart (> 2x threshold). Single-linkage must still fuse {H, A, B}
    # into one group (that's the well-known chaining property) — and the
    # confidence signal must catch it as "low" so it doesn't look like a
    # clean merge.
    threshold = 0.05
    dist = _symmetric(
        3,
        {
            (0, 1): 0.03,  # H <-> A: within threshold
            (0, 2): 0.04,  # H <-> B: within threshold
            (1, 2): 0.30,  # A <-> B: far apart (> 2x threshold)
        },
    )

    groups = _union_find_clusters(3, dist, threshold=threshold)
    assert sorted(sorted(g) for g in groups) == [[0, 1, 2]]

    conf, lo, hi = _confidence(dist, [0, 1, 2], threshold)
    assert conf == "low"
    assert hi == 0.30
    assert lo == 0.03


def test_tight_group_is_high_confidence():
    threshold = 0.05
    dist = _symmetric(
        3,
        {
            (0, 1): 0.01,
            (0, 2): 0.02,
            (1, 2): 0.015,
        },
    )

    groups = _union_find_clusters(3, dist, threshold=threshold)
    assert sorted(sorted(g) for g in groups) == [[0, 1, 2]]

    conf, lo, hi = _confidence(dist, [0, 1, 2], threshold)
    assert conf == "high"
    assert hi <= threshold


def test_medium_confidence_when_max_intra_distance_between_thr_and_2x_thr():
    threshold = 0.05
    dist = _symmetric(
        2,
        {
            (0, 1): 0.08,  # > thr (0.05), <= 2*thr (0.10)
        },
    )

    conf, lo, hi = _confidence(dist, [0, 1], threshold)
    assert conf == "medium"


def test_confidence_singleton_is_high_by_convention():
    dist = _symmetric(1, {})
    conf, lo, hi = _confidence(dist, [0], threshold=0.05)
    assert conf == "high"
    assert lo == 0.0 and hi == 0.0


# -- _cluster_id ---------------------------------------------------------


def test_cluster_id_stable_across_order_and_case():
    id_a = _cluster_id(["Bestiary", "monster bestiary", "Bestiaries"])
    id_b = _cluster_id(["MONSTER BESTIARY", "bestiaries", "bestiary"])
    assert id_a == id_b


def test_cluster_id_differs_for_different_membership():
    id_a = _cluster_id(["A", "B"])
    id_b = _cluster_id(["A", "B", "C"])
    assert id_a != id_b
