"""Tests for the pure clustering primitives in consolidate.py (issue #88):
_union_find_clusters, _confidence, _cluster_id. Plus the lexical
name-normalization pass (issue #99): _normalize_name, _lexical_pairs,
_member_entries. Plus the prefix-containment pass (issue #100):
_prefix_pairs.

No Store, no fixture — these are pure functions over hand-built distance
matrices / name lists. Fully offline by construction.
"""

import numpy as np

from drive_tagger.consolidate import (
    SAMPLE_DOCS_CAP,
    _cluster_id,
    _confidence,
    _lexical_pairs,
    _member_entries,
    _normalize_name,
    _prefix_pairs,
    _union_find_clusters,
)


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


# -- _normalize_name (issue #99 — lexical name-normalization pass) --------

KNOWN_DUPLICATE_PAIRS = [
    ("Dungeon Generator", "Dungeon Generators"),
    ("Explorer's Journal", "Explorer's Journals"),
    ("Floating City", "Floating Cities"),
    ("Gamemaster Screen", "Gamemaster Screens"),
    ("Smugglers' Lair", "Smugglers' Lairs"),
]


def test_normalize_name_collides_known_duplicate_pairs():
    for singular, plural in KNOWN_DUPLICATE_PAIRS:
        assert _normalize_name(singular) == _normalize_name(plural), (singular, plural)


def test_normalize_name_collides_floating_city_and_cities():
    # Flagship case from DEDUP_BLIND_SPOTS.md: a literal singular/plural of
    # the same word that sits at cosine distance 0.36 — far past any usable
    # embedding threshold — so this lexical pass is the only signal that
    # catches it.
    assert _normalize_name("Floating City") == _normalize_name("Floating Cities")


def test_normalize_name_does_not_collide_unrelated_names():
    assert _normalize_name("Bestiary") != _normalize_name("Character Sheet Templates")


# -- _lexical_pairs (issue #99) -------------------------------------------


def test_lexical_pairs_groups_known_pairs_and_excludes_singletons():
    names = [
        "Dungeon Generator",
        "Dungeon Generators",
        "Floating City",
        "Floating Cities",
        "Bestiary",  # singleton -- no normalized-form collision
    ]
    members_by_cat = {
        "Dungeon Generator": ["a.pdf"],
        "Dungeon Generators": ["b.pdf", "c.pdf"],
        "Floating City": ["d.pdf"],
        "Floating Cities": ["e.pdf", "f.pdf", "g.pdf"],
        "Bestiary": ["h.pdf"],
    }

    pairs = _lexical_pairs(names, members_by_cat)
    groups = [frozenset(m["name"] for m in p["members"]) for p in pairs]

    assert len(pairs) == 2
    assert frozenset({"Dungeon Generator", "Dungeon Generators"}) in groups
    assert frozenset({"Floating City", "Floating Cities"}) in groups
    assert not any("Bestiary" in g for g in groups)

    # Shape matches an embedding cluster entry, minus the embedding-only keys.
    for p in pairs:
        assert set(p) == {"id", "members", "suggested_canonical", "reason"}
        assert p["reason"].startswith("lexical: normalized to '")


def test_lexical_pairs_suggested_canonical_is_highest_member_count():
    names = ["Dungeon Generator", "Dungeon Generators"]
    members_by_cat = {
        "Dungeon Generator": ["a.pdf"],
        "Dungeon Generators": ["b.pdf", "c.pdf", "d.pdf"],
    }

    pairs = _lexical_pairs(names, members_by_cat)

    assert len(pairs) == 1
    assert pairs[0]["suggested_canonical"] == "Dungeon Generators"
    assert pairs[0]["id"] == _cluster_id(["Dungeon Generator", "Dungeon Generators"])


# -- _member_entries (refactored out of collect(), issue #99) -------------


# -- _prefix_pairs (issue #100 — prefix-containment human-review pass) ---

# Full 20-pair table from DEDUP_BLIND_SPOTS.md failure mode 3's "Full scan
# output" (corpus scan, 2026-07-04). NOTE: that table's own stated exclusion
# rule ("restricted to A having 2+ words") was not actually enforced
# consistently by the ad hoc script that produced it — 4 of the 20 pairs have
# a base that is a single *whitespace* token (a bare or hyphenated one-word
# facet: "High-Level", "Zero-Level", "Sci-Fi", "Hârn" — the same kind of
# one-lexical-unit facet as "Horror"/"Fantasy"). Per this issue's explicit
# whitespace-only-tokenization + len(base_tokens) >= 2 rule, those 4 are
# correctly excluded here, not a miss — see _prefix_pairs' docstring. The
# other 16 all have a base with 2+ whitespace tokens and must be found.
BASELINE_PREFIX_PAIRS_FOUND = [
    ("System-Agnostic Sci-Fi", "System-Agnostic Sci-Fi Scenarios"),
    ("Legendary Games", "Legendary Games Modules"),
    ("Castles & Crusades", "Castles & Crusades Content"),
    ("Castles & Crusades", "Castles & Crusades Maps"),
    ("Call of Cthulhu", "Call of Cthulhu Content"),
    ("Fairy Tale", "Fairy Tale Campaigns"),
    ("Forgotten Realms", "Forgotten Realms Campaign"),
    ("Call of Cthulhu", "Call of Cthulhu Scenarios"),
    ("Forgotten Realms", "Forgotten Realms Aftermath"),
    ("Call of Cthulhu", "Call of Cthulhu Handouts"),
    ("Call of Cthulhu", "Call of Cthulhu Investigator Handbooks"),
    ("Chivalry & Sorcery", "Chivalry & Sorcery Content"),
    ("Call of Cthulhu", "Call of Cthulhu Coloring Books"),
    ("Call of Cthulhu", "Call of Cthulhu Keeper Decks"),
    ("Silk Road", "Silk Road Framework"),
    ("Medieval Medicine", "Medieval Medicine Manuals"),
]

# The 4 baseline-table rows excluded by the len(base_tokens) >= 2 floor,
# because their base is a single whitespace token — same treatment as any
# other one-word Pass-2 facet.
BASELINE_SINGLE_TOKEN_BASE_EXTENSIONS_EXCLUDED = [
    "High-Level Adventures",
    "Zero-Level Character Generators",
    "Sci-Fi Horror Campaign",
    "Hârn Bestiary",
]

# All 33 distinct names referenced across the full 20-pair baseline table
# (20 pairs x 2 names minus 7 repeated-base duplicates: Call of Cthulhu is
# the base of 6 pairs -> 5 duplicates, Castles & Crusades and Forgotten
# Realms are each the base of 2 -> 1 duplicate each; 40 - 7 = 33).
BASELINE_ALL_NAMES = sorted(
    {n for pair in BASELINE_PREFIX_PAIRS_FOUND for n in pair}
    | {
        "High-Level", "High-Level Adventures",
        "Zero-Level", "Zero-Level Character Generators",
        "Sci-Fi", "Sci-Fi Horror Campaign",
        "Hârn", "Hârn Bestiary",
    }
)


def test_prefix_pairs_reproduces_baseline_16_and_excludes_single_token_bases():
    assert len(BASELINE_ALL_NAMES) == 33

    pairs = _prefix_pairs(BASELINE_ALL_NAMES, {})
    found = {(p["base"], p["extension"]) for p in pairs}

    assert found == set(BASELINE_PREFIX_PAIRS_FOUND)
    assert len(found) == 16

    # The 4 single-whitespace-token-base pairs must NOT appear, even though
    # both names are present in the input and the token-containment
    # relationship holds — the len(base_tokens) >= 2 floor is what excludes
    # them.
    extensions_found = {p["extension"] for p in pairs}
    for excluded_extension in BASELINE_SINGLE_TOKEN_BASE_EXTENSIONS_EXCLUDED:
        assert excluded_extension not in extensions_found


def test_prefix_pairs_call_of_cthulhu_produces_six_separate_entries():
    pairs = _prefix_pairs(BASELINE_ALL_NAMES, {})
    coc_entries = [p for p in pairs if p["base"] == "Call of Cthulhu"]

    # Call of Cthulhu is the base of 6 distinct pairs in the baseline data —
    # unlike _lexical_pairs (which groups by normalized form into one
    # equivalence class), prefix containment is pairwise, so this must
    # produce 6 separate entries, not one merged group.
    assert len(coc_entries) == 6
    assert {e["extension"] for e in coc_entries} == {
        "Call of Cthulhu Content",
        "Call of Cthulhu Scenarios",
        "Call of Cthulhu Handouts",
        "Call of Cthulhu Investigator Handbooks",
        "Call of Cthulhu Coloring Books",
        "Call of Cthulhu Keeper Decks",
    }


def test_prefix_pairs_excludes_single_word_pass2_facet_pattern():
    # These are the existing, intentional Pass-2 facet decompositions named
    # in issue #100 — a single-word base is NOT a prefix-pair candidate even
    # though the token-prefix relationship literally holds, because
    # len(base_tokens) < 2.
    names = [
        "Campaign", "Campaign Supplements",
        "RPG", "RPG Playkit",
        "Horror", "Horror Themes",
        "Fantasy", "Fantasy Technology",
    ]
    assert _prefix_pairs(names, {}) == []


def test_prefix_pairs_whitespace_only_tokenization_does_not_split_hyphens():
    names = ["System-Agnostic Sci-Fi", "System-Agnostic Sci-Fi Scenarios"]
    pairs = _prefix_pairs(names, {})

    assert len(pairs) == 1
    assert pairs[0]["base"] == "System-Agnostic Sci-Fi"
    assert pairs[0]["extension"] == "System-Agnostic Sci-Fi Scenarios"

    # "System-Agnostic" must remain one token (["System-Agnostic"]), not
    # split into ["System", "Agnostic"] — verified indirectly: a bare
    # "System-Agnostic" (1 whitespace token) fails the >= 2 floor and
    # generates no pair, even though it IS a whitespace-prefix of
    # "System-Agnostic Sci-Fi". If hyphens were treated as token
    # separators, "System-Agnostic" would count as 2 tokens and this would
    # incorrectly produce a pair.
    lone_names = ["System-Agnostic", "System-Agnostic Sci-Fi"]
    assert _prefix_pairs(lone_names, {}) == []


def test_prefix_pairs_entry_shape_and_member_count():
    names = ["Call of Cthulhu", "Call of Cthulhu Scenarios"]
    members_by_cat = {
        "Call of Cthulhu": ["a.pdf", "b.pdf", "c.pdf", "d.pdf"],
        "Call of Cthulhu Scenarios": [f"doc_{i}.pdf" for i in range(29)],
    }

    pairs = _prefix_pairs(names, members_by_cat)

    assert len(pairs) == 1
    entry = pairs[0]
    assert entry["id"] == _cluster_id(["Call of Cthulhu", "Call of Cthulhu Scenarios"])
    assert entry["base"] == "Call of Cthulhu"
    assert entry["extension"] == "Call of Cthulhu Scenarios"
    assert entry["suggested_canonical"] == "Call of Cthulhu"
    assert "Call of Cthulhu" in entry["reason"]
    assert "Call of Cthulhu Scenarios" in entry["reason"]

    member_names = {m["name"] for m in entry["members"]}
    assert member_names == {"Call of Cthulhu", "Call of Cthulhu Scenarios"}
    counts = {m["name"]: m["member_count"] for m in entry["members"]}
    assert counts == {"Call of Cthulhu": 4, "Call of Cthulhu Scenarios": 29}


def test_member_entries_sorts_by_member_count_desc_and_caps_sample_docs():
    member_names = ["Low Count Cat", "High Count Cat"]
    members_by_cat = {
        "Low Count Cat": ["only_one.pdf"],
        "High Count Cat": [f"doc_{i}.pdf" for i in range(SAMPLE_DOCS_CAP + 5)],
    }

    entries = _member_entries(member_names, members_by_cat)

    assert [e["name"] for e in entries] == ["High Count Cat", "Low Count Cat"]
    assert entries[0]["member_count"] == SAMPLE_DOCS_CAP + 5
    assert len(entries[0]["sample_docs"]) == SAMPLE_DOCS_CAP
    assert entries[0]["sample_docs"] == sorted(members_by_cat["High Count Cat"])[:SAMPLE_DOCS_CAP]
    assert entries[1]["member_count"] == 1
    assert entries[1]["sample_docs"] == ["only_one.pdf"]
