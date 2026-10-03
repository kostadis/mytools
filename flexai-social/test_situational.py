"""Tests for situational.py and its two app routes. No network: a fake poster stands in for the Sparks."""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "fixtures"))

import situational as sit  # noqa: E402
from fixtures.build_fixtures import build_fixtures  # noqa: E402

CLEF_PROBS = {"bargains": 0.6, "questions_motives": 0.25, "hostile": 0.1, "helps": 0.05}


def fake_post(calls):
    def post(url, body, timeout):
        calls.append((url, body))
        if url.endswith("/v1/systemone"):
            return {"answers": {"stance": {"type": "choice", "choice": "bargains", "probabilities": dict(CLEF_PROBS)}}}
        if url.endswith("/chat/completions"):
            return {"choices": [{"message": {"content": "  Passage costs coin, beardling.  "}}]}
        raise AssertionError(url)
    return post


def test_suggest_ranks_every_stance_high_first():
    calls = []
    res = sit.suggest("Gorglak", "", "They want passage and have no money.", post=fake_post(calls))
    keys = [k for k, _ in res["stances"]]
    assert keys[:2] == ["bargains", "questions_motives"]
    assert set(keys) == set(sit.STANCES)            # missing stances are scored 0, not dropped
    body = calls[0][1]
    assert body["questions"]["stance"]["criteria"] == sit.STANCES
    assert "Gorglak" in body["state"] and "no money" in body["state"]


def test_suggest_requires_a_situation():
    with pytest.raises(ValueError):
        sit.suggest("Gorglak", "", "   ", post=fake_post([]))


def test_bad_reply_is_a_backend_error():
    with pytest.raises(sit.BackendError):
        sit.suggest("X", "", "y", post=lambda u, b, t: {"oops": 1})


def test_roll_follows_the_weights():
    stances = [("bargains", 0.9), ("hostile", 0.1), ("helps", 0.0)]
    rng = random.Random(0)
    draws = [sit.roll(stances, rng) for _ in range(2000)]
    assert "helps" not in draws
    assert 0.85 < draws.count("bargains") / len(draws) < 0.95


def test_voice_line_strips_and_names_the_stance():
    calls = []
    res = sit.voice_line("Gorglak", "", "No money.", "bargains", post=fake_post(calls))
    assert res["line"] == "Passage costs coin, beardling."
    prompt = calls[0][1]["messages"][0]["content"]
    assert sit.STANCES["bargains"] in prompt
    with pytest.raises(ValueError):
        sit.voice_line("Gorglak", "", "x", "dances", post=fake_post([]))


def test_find_notes_prefers_voice_file(tmp_path):
    (tmp_path / "voice").mkdir()
    (tmp_path / "docs" / "npcs").mkdir(parents=True)
    (tmp_path / "voice" / "gorglak.md").write_text("Speaks in grunts.")
    (tmp_path / "docs" / "npcs" / "gorglak.md").write_text("Dossier.")
    text, path = sit.find_notes("Gorglak the Trader", str(tmp_path))   # falls back to the first name
    assert text == "Speaks in grunts." and path.endswith("voice/gorglak.md")
    assert sit.find_notes("Nobody", str(tmp_path)) == ("", None)
    (tmp_path / "voice" / "vizeran_voice.md").write_text("Archmage.")   # the campaigns' naming
    assert sit.find_notes("Vizeran", str(tmp_path))[0] == "Archmage."
    assert sit.find_notes("Gorglak", None) == ("", None)


@pytest.fixture()
def client(tmp_path):
    import app as app_module
    build_fixtures(tmp_path)
    app = app_module.create_app(data_dir=tmp_path)
    app.config["SIT_POST"] = fake_post([])
    return app.test_client()


def test_routes(client, monkeypatch):
    monkeypatch.delenv("CAMPAIGN_DIR", raising=False)
    r = client.post("/api/situational/suggest", json={"npc": "Gorglak", "situation": "No money."})
    assert r.status_code == 200
    d = r.get_json()
    assert d["stances"][0]["key"] == "bargains" and d["rolled"] in sit.STANCES
    r = client.post("/api/situational/line", json={"npc": "Gorglak", "situation": "No money.", "stance": "bargains"})
    assert r.get_json()["line"].startswith("Passage")
    assert client.post("/api/situational/suggest", json={"npc": "G", "situation": ""}).status_code == 400


def test_backend_down_is_a_502(client):
    def down(url, body, timeout):
        raise sit.BackendError("connection refused")
    client.application.config["SIT_POST"] = down
    r = client.post("/api/situational/suggest", json={"npc": "G", "situation": "x"})
    assert r.status_code == 502 and "Decision model unavailable" in r.get_json()["error"]
