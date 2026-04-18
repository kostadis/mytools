"""Tests for flexai_combat.py and app.py.

Uses a hand-generated tiny workbook built into a pytest tmp_path by
fixtures/build_fixtures.py — no commercial xlsx file is needed or shipped.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "fixtures"))

import flexai_combat as fc  # noqa: E402
from fixtures.build_fixtures import build_fixtures  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def fixture_data_dir(tmp_path_factory) -> Path:
    data_dir = tmp_path_factory.mktemp("flexai_combat_data")
    build_fixtures(data_dir)
    return data_dir


@pytest.fixture(scope="session")
def table(fixture_data_dir: Path):
    return fc.load_tables(fixture_data_dir)


@pytest.fixture()
def fresh_a(table):
    return fc.get_cell(table, "brute", "normal", "fresh", "A")


@pytest.fixture()
def ambushing_a(table):
    return fc.get_cell(table, "brute", "normal", "ambushing", "A")


class FakeRandom:
    """Returns a pre-programmed roll; drop-in for `random.Random`."""

    def __init__(self, value: int):
        self._value = value

    def randint(self, lo: int, hi: int) -> int:  # pragma: no cover - trivial
        assert lo <= self._value <= hi
        return self._value


class SequenceRandom:
    """Returns a sequence of pre-programmed rolls in order."""

    def __init__(self, values):
        self._values = list(values)
        self._i = 0

    def randint(self, lo: int, hi: int) -> int:  # pragma: no cover - trivial
        v = self._values[self._i]
        self._i += 1
        assert lo <= v <= hi
        return v


# ---------------------------------------------------------------------------
# parse_range
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("01-30", (1, 30)),
        ("31-50", (31, 50)),
        ("96-00", (96, 100)),   # trailing 00 means 100
        ("70-00", (70, 100)),
        ("00", (100, 100)),
        ("45", (45, 45)),
        ("-", None),
        ("\u2013", None),
        ("n/a", None),
        ("", None),
        (None, None),
        (37, (37, 37)),
    ],
)
def test_parse_range(raw, expected):
    assert fc.parse_range(raw) == expected


# ---------------------------------------------------------------------------
# Canonical vocab
# ---------------------------------------------------------------------------


def test_canonical_lists_are_stable():
    assert fc.list_roles() == [
        "brute", "soldier", "artillery", "skirmisher",
        "lurker", "controller", "leader",
    ]
    assert fc.list_sizes() == ["normal", "minion", "elite", "solo"]
    assert fc.list_stances() == [
        "fresh", "ambushing", "unprepared", "bloodied",
        "cornered", "overwhelmed", "relentless", "mindless",
    ]
    assert fc.list_ranks() == ["A", "B", "C", "D"]
    assert fc.list_outcomes() == [
        "attack_main", "attack_secondary", "maneuver",
        "use_defend", "ability", "flee",
    ]
    assert fc.list_targets() == [
        "frontline", "rearguard", "closest", "farthest",
        "strongest", "weakest", "ranged_enemy", "melee_enemy",
    ]
    assert fc.list_tiers() == ("simple", "full", "advanced")


def test_canon_outcome_row_parses_compound_labels():
    assert fc.canon_outcome_row("Attack Main") == ("attack_main", None)
    assert fc.canon_outcome_row("Use/Defend") == ("use_defend", None)
    assert fc.canon_outcome_row("Attack Main, Minor Surge") == (
        "attack_main", "minor_surge",
    )
    assert fc.canon_outcome_row("Ability, Major Lull") == (
        "ability", "major_lull",
    )
    assert fc.canon_outcome_row("nonsense") is None


def test_display_names():
    assert fc.display("brute") == "Brute"
    assert fc.display("use_defend") == "Use / Defend"
    assert fc.display("ranged_enemy") == "Ranged Enemy"
    assert fc.display("major_surge") == "Major Surge"


# ---------------------------------------------------------------------------
# Load & shape
# ---------------------------------------------------------------------------


def test_load_tables_shape(table, fresh_a):
    assert "brute" in table
    assert "normal" in table["brute"]
    assert "fresh" in table["brute"]["normal"]
    assert "A" in table["brute"]["normal"]["fresh"]
    assert "B" in table["brute"]["normal"]["fresh"]
    assert fresh_a is not None
    assert "outcomes" in fresh_a
    assert "targeting" in fresh_a


def test_fresh_a_outcome_buckets(fresh_a):
    out = fresh_a["outcomes"]
    assert out[("attack_main", None)] == (1, 30)
    assert out[("attack_secondary", None)] == (31, 50)
    assert out[("maneuver", None)] == (51, 60)
    assert out[("use_defend", None)] == (61, 65)
    assert out[("ability", None)] == (66, 80)
    assert out[("flee", None)] is None
    assert out[("attack_main", "minor_surge")] == (81, 85)
    assert out[("attack_main", "major_surge")] == (94, 94)
    assert out[("attack_main", "minor_lull")] == (97, 97)
    assert out[("attack_main", "major_lull")] == (99, 99)
    # "Ability, Major Lull" = "00" -> (100, 100)
    assert out[("ability", "major_lull")] == (100, 100)


def test_fresh_a_targeting_buckets(fresh_a):
    t = fresh_a["targeting"]
    assert t["frontline"] == (1, 20)
    assert t["rearguard"] == (21, 30)
    assert t["closest"] == (31, 55)
    assert t["farthest"] == (56, 65)
    assert t["strongest"] == (66, 80)
    assert t["weakest"] == (81, 90)
    assert t["ranged_enemy"] == (91, 95)
    assert t["melee_enemy"] == (96, 100)


def test_ambushing_a_has_unavailable_buckets(ambushing_a):
    out = ambushing_a["outcomes"]
    assert out[("attack_main", None)] == (1, 60)
    assert out[("attack_secondary", None)] is None
    assert out[("use_defend", None)] is None


# ---------------------------------------------------------------------------
# Simple AI rolls
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "roll, expected",
    [
        (1,  "attack_main"),
        (12, "attack_main"),
        (13, "attack_secondary"),
        (14, "attack_secondary"),
        (15, "maneuver"),
        (16, "use_defend"),
        (17, "ability"),
        (19, "ability"),
        (20, "flee"),
    ],
)
def test_roll_simple_outcome_edges(roll, expected):
    got_roll, outcome = fc.roll_simple_outcome(rng=FakeRandom(roll))
    assert got_roll == roll
    assert outcome == expected


@pytest.mark.parametrize(
    "roll, expected",
    [
        (1,  "frontline"),
        (5,  "frontline"),
        (6,  "rearguard"),
        (7,  "rearguard"),
        (8,  "closest"),
        (13, "closest"),
        (14, "farthest"),
        (15, "strongest"),
        (16, "strongest"),
        # 17 is unmapped in the Guidebook — treated as reroll -> None.
        (17, None),
        (18, "weakest"),
        (19, "ranged_enemy"),
        (20, "melee_enemy"),
    ],
)
def test_roll_simple_target_edges(roll, expected):
    got_roll, target = fc.roll_simple_target(rng=FakeRandom(roll))
    assert got_roll == roll
    assert target == expected


# ---------------------------------------------------------------------------
# Full/Advanced AI rolls
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "roll, outcome, surge",
    [
        (1,   "attack_main",      None),
        (30,  "attack_main",      None),
        (31,  "attack_secondary", None),
        (50,  "attack_secondary", None),
        (51,  "maneuver",         None),
        (65,  "use_defend",       None),
        (80,  "ability",          None),
        (81,  "attack_main",      "minor_surge"),
        (85,  "attack_main",      "minor_surge"),
        (94,  "attack_main",      "major_surge"),
        (97,  "attack_main",      "minor_lull"),
        (99,  "attack_main",      "major_lull"),
        (100, "ability",          "major_lull"),
    ],
)
def test_roll_full_outcome_edges(fresh_a, roll, outcome, surge):
    got_roll, got_outcome, got_surge = fc.roll_full_outcome(
        fresh_a, rng=FakeRandom(roll)
    )
    assert got_roll == roll
    assert got_outcome == outcome
    assert got_surge == surge


@pytest.mark.parametrize(
    "roll, expected",
    [
        (1,   "frontline"),
        (20,  "frontline"),
        (21,  "rearguard"),
        (55,  "closest"),
        (56,  "farthest"),
        (66,  "strongest"),
        (81,  "weakest"),
        (91,  "ranged_enemy"),
        (96,  "melee_enemy"),
        (100, "melee_enemy"),
    ],
)
def test_roll_targeting_edges(fresh_a, roll, expected):
    got_roll, target = fc.roll_targeting(fresh_a, rng=FakeRandom(roll))
    assert got_roll == roll
    assert target == expected


# ---------------------------------------------------------------------------
# resolve_turn
# ---------------------------------------------------------------------------


def test_resolve_turn_simple_ignores_role():
    # Simple tier doesn't read the table, so an unknown role is fine.
    out = fc.resolve_turn(
        {},  # empty table
        "brute", "normal", "fresh", "A",
        tier="simple",
        rng=SequenceRandom([1, 5]),  # d20=1 -> attack_main; d20=5 -> frontline
    )
    assert out["tier"] == "simple"
    assert out["outcome"] == "attack_main"
    assert out["target"] == "frontline"
    assert out["surge"] is None


def test_resolve_turn_full_drops_surge(table):
    out = fc.resolve_turn(
        table, "brute", "normal", "fresh", "A",
        tier="full",
        rng=SequenceRandom([81, 30]),  # d100=81 -> attack_main+minor_surge
    )
    assert out["tier"] == "full"
    assert out["outcome"] == "attack_main"
    assert out["surge"] is None  # dropped in "full" tier
    assert out["target"] == "rearguard"  # d100=30 -> rearguard


def test_resolve_turn_advanced_keeps_surge(table):
    out = fc.resolve_turn(
        table, "brute", "normal", "fresh", "A",
        tier="advanced",
        rng=SequenceRandom([81, 100]),
    )
    assert out["tier"] == "advanced"
    assert out["outcome"] == "attack_main"
    assert out["surge"] == "minor_surge"
    assert out["target"] == "melee_enemy"


def test_resolve_turn_missing_cell_returns_notes(table):
    out = fc.resolve_turn(
        table, "brute", "normal", "fresh", "C",  # rank C not in fixture
        tier="full",
    )
    assert out["outcome"] is None
    assert out["target"] is None
    assert out["notes"] is not None


def test_resolve_turn_unknown_tier_raises(table):
    with pytest.raises(ValueError):
        fc.resolve_turn(table, "brute", "normal", "fresh", "A", tier="magic")


# ---------------------------------------------------------------------------
# Flask smoke test
# ---------------------------------------------------------------------------


def test_flask_routes_smoke(table):
    from app import create_app  # noqa: WPS433

    app = create_app(table=table)
    client = app.test_client()

    resp = client.get("/")
    assert resp.status_code == 200
    assert b"FlexAI Combat" in resp.data

    resp = client.get(
        "/api/cell",
        query_string={
            "role": "brute", "size": "normal",
            "stance": "fresh", "rank": "A",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "outcomes" in body
    assert "targeting" in body

    resp = client.post(
        "/api/resolve",
        json={
            "role": "brute", "size": "normal",
            "stance": "fresh", "rank": "A",
            "tier": "advanced",
        },
    )
    assert resp.status_code == 200
    j = resp.get_json()
    assert 1 <= j["outcome_roll"] <= 100
    assert 1 <= j["target_roll"] <= 100
    assert j["tier"] == "advanced"

    resp = client.post(
        "/api/resolve",
        json={"tier": "simple"},
    )
    assert resp.status_code == 200
    j = resp.get_json()
    assert 1 <= j["outcome_roll"] <= 20
    assert 1 <= j["target_roll"] <= 20

    resp = client.get("/rules")
    assert resp.status_code == 200
    assert b"Combat" in resp.data
