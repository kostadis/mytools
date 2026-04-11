"""Tests for flexai_social.py and app.py.

Uses hand-generated tiny workbooks built into a pytest tmp_path by
fixtures/build_fixtures.py — no commercial xlsx files are needed or shipped.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "fixtures"))

import flexai_social as fs  # noqa: E402
from fixtures.build_fixtures import build_fixtures  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def fixture_data_dir(tmp_path_factory) -> Path:
    """Build the tiny FlexAI workbooks once per test session."""
    data_dir = tmp_path_factory.mktemp("flexai_data")
    build_fixtures(data_dir)
    return data_dir


@pytest.fixture(scope="session")
def table(fixture_data_dir: Path):
    return fs.load_tables(fixture_data_dir)


@pytest.fixture()
def passing_by_a(table):
    return fs.get_cell(table, "ally", "normal", "passing_by", "A")


@pytest.fixture()
def combat_a(table):
    return fs.get_cell(table, "ally", "normal", "combat", "A")


class FakeRandom:
    """Minimal drop-in for `random.Random` that returns a pre-programmed roll."""

    def __init__(self, value: int):
        self._value = value

    def randint(self, lo: int, hi: int) -> int:  # pragma: no cover - trivial
        assert lo <= self._value <= hi
        return self._value


# ---------------------------------------------------------------------------
# parse_range
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("01-40", (1, 40)),
        ("41-50", (41, 50)),
        ("96-00", (96, 100)),     # trailing 00 means 100
        ("70-00", (70, 100)),
        ("00", (100, 100)),       # single 00 also means 100
        ("45", (45, 45)),
        ("-", None),
        ("\u2013", None),         # en dash
        ("n/a", None),
        ("N/A", None),
        ("", None),
        (None, None),
        (37, (37, 37)),           # already a number
    ],
)
def test_parse_range(raw, expected):
    assert fs.parse_range(raw) == expected


# ---------------------------------------------------------------------------
# Load & shape
# ---------------------------------------------------------------------------


def test_canonical_lists_are_stable():
    assert fs.list_roles() == ["ally", "asset", "acquaintance", "opponent", "bystander"]
    assert fs.list_sizes() == ["normal", "minion", "elite", "solo"]
    assert fs.list_ranks() == ["A", "B", "C", "D"]
    assert fs.list_choices() == [
        "diplomacy", "intimidate", "sense_motive",
        "mislead", "gather_info", "subject_info",
    ]
    assert "passing_by" in fs.list_contexts()
    assert "lull" in fs.list_contexts()


def test_load_tables_shape(table, passing_by_a):
    # Only Ally is in the tiny fixture.
    assert "ally" in table
    assert "normal" in table["ally"]
    assert "passing_by" in table["ally"]["normal"]
    assert "A" in table["ally"]["normal"]["passing_by"]
    assert "B" in table["ally"]["normal"]["passing_by"]

    # Every cell carries all five sub-maps.
    for key in ("npc_turn", "success_results", "failure_results", "dcs_5e", "dcs_pf2e"):
        assert key in passing_by_a

    # NPC-turn was fully populated for Passing By/A.
    npc = passing_by_a["npc_turn"]
    assert npc["diplomacy"] == (1, 40)
    assert npc["intimidate"] == (41, 50)
    assert npc["sense_motive"] == (51, 70)
    assert npc["mislead"] == (71, 80)
    assert npc["gather_info"] == (81, 90)
    assert npc["subject_info"] == (91, 100)


def test_combat_a_unavailable_choices_are_none(combat_a):
    # Diplomacy, Gather Info and Subject Info are "-" in Combat.
    assert combat_a["npc_turn"]["diplomacy"] is None
    assert combat_a["npc_turn"]["gather_info"] is None
    assert combat_a["npc_turn"]["subject_info"] is None
    # Mislead in Combat is 70-00 -> (70, 100).
    assert combat_a["npc_turn"]["mislead"] == (70, 100)


# ---------------------------------------------------------------------------
# NPC turn roll
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "roll, expected",
    [
        (1,   "diplomacy"),
        (40,  "diplomacy"),
        (41,  "intimidate"),
        (50,  "intimidate"),
        (51,  "sense_motive"),
        (70,  "sense_motive"),
        (71,  "mislead"),
        (80,  "mislead"),
        (81,  "gather_info"),
        (90,  "gather_info"),
        (91,  "subject_info"),
        (100, "subject_info"),
    ],
)
def test_roll_npc_turn_edges(passing_by_a, roll, expected):
    got_roll, choice = fs.roll_npc_turn(passing_by_a, rng=FakeRandom(roll))
    assert got_roll == roll
    assert choice == expected


def test_roll_npc_turn_skips_none_buckets(combat_a):
    # Diplomacy is None in Combat/A — a "would-be Diplomacy" roll falls through
    # to the next populated bucket. In Combat/A: Intimidate=1-31, SM=32-69,
    # Mislead=70-100; there are no 0-value cells to fall through *from*,
    # so this check is really "rolls land where expected".
    got_roll, choice = fs.roll_npc_turn(combat_a, rng=FakeRandom(1))
    assert choice == "intimidate"


# ---------------------------------------------------------------------------
# Result roll
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "roll, expected",
    [
        (1,   "ignores_you"),
        (10,  "ignores_you"),
        (11,  "helps"),
        (30,  "helps"),
        (31,  "answers_grudgingly"),
        (40,  "answers_grudgingly"),
        (41,  "answers"),
        (60,  "answers"),
        (61,  "answers_willingly"),
        (80,  "answers_willingly"),
        (81,  "volunteers_info"),
        (90,  "volunteers_info"),
        (91,  "questions_motives"),
        (95,  "questions_motives"),
        (96,  "reveals_plot_clue"),
        (100, "reveals_plot_clue"),
    ],
)
def test_roll_success_result_edges(passing_by_a, roll, expected):
    got_roll, result = fs.roll_result(passing_by_a, success=True, rng=FakeRandom(roll))
    assert got_roll == roll
    assert result == expected


@pytest.mark.parametrize(
    "roll, expected",
    [
        (1,   "turns_hostile"),
        (5,   "turns_hostile"),
        (6,   "leaves"),
        (20,  "leaves"),
        (21,  "ignores_you"),
        (50,  "ignores_you"),
        (51,  "answers_grudgingly"),
        (70,  "answers_grudgingly"),
        (71,  "challenges_you"),
        (80,  "challenges_you"),
        (81,  "questions_motives"),
        (90,  "questions_motives"),
        (91,  "red_herring"),
        (95,  "red_herring"),
        (96,  "lies"),
        (100, "lies"),
    ],
)
def test_roll_failure_result_edges(passing_by_a, roll, expected):
    got_roll, result = fs.roll_result(passing_by_a, success=False, rng=FakeRandom(roll))
    assert got_roll == roll
    assert result == expected


# ---------------------------------------------------------------------------
# DC lookup & attempt resolution
# ---------------------------------------------------------------------------


def test_available_choices_5e(passing_by_a):
    pairs = fs.available_choices(passing_by_a, system="5e")
    assert dict(pairs) == {
        "diplomacy": 5,
        "intimidate": 8,
        "sense_motive": 6,
        "mislead": 7,
        "gather_info": 6,
        "subject_info": 7,
    }


def test_available_choices_pf2e(passing_by_a):
    pairs = fs.available_choices(passing_by_a, system="pf2e")
    assert dict(pairs) == {
        "diplomacy": 10,
        "intimidate": 13,
        "sense_motive": 11,
        "mislead": 12,
        "gather_info": 11,
        "subject_info": 12,
    }


def test_available_choices_excludes_unavailable(combat_a):
    keys = [c for c, _ in fs.available_choices(combat_a, system="5e")]
    assert keys == ["intimidate", "sense_motive", "mislead"]


def test_attempt_unavailable_auto_fails(combat_a):
    out = fs.attempt(combat_a, "diplomacy", pc_total=999, system="5e")
    assert out["success"] is False
    assert out["dc"] is None
    assert out["result"] is None
    assert out["roll"] is None
    assert out["notes"] is not None
    assert "unavailable" in out["notes"].lower()


def test_attempt_success_rolls_on_success_table(passing_by_a):
    # Diplomacy 5E DC is 5; pc_total 10 beats it, rng pinned to 15 -> Helps
    out = fs.attempt(
        passing_by_a,
        "diplomacy",
        pc_total=10,
        system="5e",
        rng=FakeRandom(15),
    )
    assert out["success"] is True
    assert out["dc"] == 5
    assert out["roll"] == 15
    assert out["result"] == "helps"


def test_attempt_failure_rolls_on_failure_table(passing_by_a):
    # Diplomacy 5E DC is 5; pc_total 3 misses it, rng pinned to 3 -> Turns Hostile
    out = fs.attempt(
        passing_by_a,
        "diplomacy",
        pc_total=3,
        system="5e",
        rng=FakeRandom(3),
    )
    assert out["success"] is False
    assert out["dc"] == 5
    assert out["roll"] == 3
    assert out["result"] == "turns_hostile"


def test_display_names():
    assert fs.display("ally") == "Ally"
    assert fs.display("long_rest") == "Long Rest"
    assert fs.display("grant_plot_clue") == "Can Grant Plot Clue"
    assert fs.display("reveals_plot_clue") == "Reveals Plot Clue"


# ---------------------------------------------------------------------------
# Flask smoke test
# ---------------------------------------------------------------------------


def test_flask_routes_smoke(table):
    from app import create_app  # noqa: WPS433 - local import to keep fs-only tests fast

    app = create_app(table=table)
    client = app.test_client()

    # Main page renders.
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"FlexAI Social" in resp.data

    # Cell API.
    resp = client.get(
        "/api/cell",
        query_string={
            "role": "ally",
            "size": "normal",
            "context": "passing_by",
            "rank": "A",
            "system": "5e",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["dcs"]["diplomacy"] == 5
    assert "npc_turn" in body
    assert "success_results" in body
    assert "failure_results" in body

    # NPC turn roll API.
    resp = client.post(
        "/api/roll/npc-turn",
        json={"role": "ally", "size": "normal", "context": "passing_by", "rank": "A"},
    )
    assert resp.status_code == 200
    j = resp.get_json()
    assert 1 <= j["roll"] <= 100
    assert j["choice"] in fs.CHOICES + [None]

    # Attempt API.
    resp = client.post(
        "/api/attempt",
        json={
            "role": "ally",
            "size": "normal",
            "context": "passing_by",
            "rank": "A",
            "system": "5e",
            "choice": "diplomacy",
            "pc_total": 20,
        },
    )
    assert resp.status_code == 200
    j = resp.get_json()
    assert j["dc"] == 5
    assert j["success"] is True
    assert j["result"] is not None

    # /rules route renders the markdown.
    resp = client.get("/rules")
    assert resp.status_code == 200
    assert b"Social Encounters" in resp.data
