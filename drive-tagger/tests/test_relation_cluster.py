"""Pure relation string-distance + grouping (no Store, no Graph)."""
from drive_tagger.consolidate import _union_find_clusters
from drive_tagger.link_consolidate import (
    _antonym_conflict,
    _relation_distance_matrix,
    _stem,
)


def test_stem_strips_suffix_tokens_and_singularizes():
    assert _stem("complementary-to") == "complementary"
    assert _stem("complementary-version") == "complementary"
    assert _stem("series-member") == "series"
    assert _stem("series-part") == "series"
    assert _stem("complements") == "complements"  # plural caught by edit-distance, not stem
    assert _stem("related-to") == "related"


def test_shared_stem_is_zero_distance():
    names = ["complementary-to", "complementary-version"]
    d = _relation_distance_matrix(names)
    assert d[0, 1] == 0.0


def test_unrelated_relations_are_far():
    names = ["complements", "duplicate-of"]
    d = _relation_distance_matrix(names)
    assert d[0, 1] > 0.34


def test_grouping_families(tmp_path=None):
    names = [
        "complementary", "complementary-to", "complementary-version",
        "series-member", "series-part",
        "sequel-to", "prequel-to",
        "references",  # a lone, distinct relation
    ]
    d = _relation_distance_matrix(names)
    groups = _union_find_clusters(len(names), d, 0.34)
    as_sets = {frozenset(names[i] for i in g) for g in groups}

    assert {"complementary", "complementary-to", "complementary-version"} in as_sets
    assert {"series-member", "series-part"} in as_sets
    assert {"sequel-to", "prequel-to"} in as_sets
    assert {"references"} in as_sets


def test_antonym_conflict_detected():
    assert _antonym_conflict(["sequel-to", "prequel-to", "sequel-of"]) == "prequel vs sequel"
    assert _antonym_conflict(["predecessor", "successor-of"]) == "predecessor vs successor"
    # non-directional families are clean
    assert _antonym_conflict(["complements", "complementary", "supplements"]) is None
    assert _antonym_conflict(["series-member", "series-part"]) is None


def test_diagonal_is_inf():
    import numpy as np
    d = _relation_distance_matrix(["a-of", "b-of"])
    assert np.isinf(d[0, 0]) and np.isinf(d[1, 1])
