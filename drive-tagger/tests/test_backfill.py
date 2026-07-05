"""Tests for the LLM-drafted description backfill (issue #98):
consolidate._backfill_targets (pure) plus backfill.draft()/apply_descriptions().
DEDUP_BLIND_SPOTS.md failure mode 1 — empty-description categories embed on
their bare name and drift from true siblings; backfilling a real description
fixes the embedding signal.

Fully offline — isolated_config (tests/conftest.py) points CONFIG at a
tmp_path scratch dir and swaps in a fake embedder so fastembed never runs.
draft()'s chat call is faked via an injected client (mirrors pipeline._judge's
client-injection pattern) — no network call is ever made in these tests.

Store-handle discipline: every Store() used to seed/inspect data is closed
before the next one opens (turbovecdb.Collection takes a cross-process
FileLock per collection dir) — draft()/apply_descriptions() each open/close
their own Store() internally, so tests must not hold a handle open across a
call to either.
"""

import json

import pytest

from drive_tagger.backfill import apply_descriptions, draft
from drive_tagger.consolidate import _backfill_targets
from drive_tagger.store import Store


def _add_doc(store, doc_id, name, categories=None):
    store.add_document(
        {
            "id": doc_id,
            "name": name,
            "mime_type": "text/plain",
            "modified_time": "",
            "md5_checksum": "",
            "web_view_link": "",
        },
        text=f"{name} — sample body text describing this document's content.",
    )
    if categories:
        store.assign_categories(doc_id, categories)


class _FakeChoice:
    def __init__(self, content):
        self.message = type("_Msg", (), {"content": content})()


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeClient:
    """Returns a fixed drafted description for every call — no network,
    mirrors the `.chat.completions.create(...).choices[0].message.content`
    shape the real OpenAI client returns."""

    def __init__(self, content="A drafted description of this category."):
        self.content = content
        self.calls = 0
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.calls += 1
        return _FakeResponse(self.content)


# -- _backfill_targets (pure, no Store) --------------------------------------


def test_backfill_targets_selects_only_multiword_empty_description():
    categories = [
        {"name": "Name Generators", "description": "", "member_count": 197},
        {"name": "Urban Fantasy", "description": "Stories set in a modern city.", "member_count": 12},
        {"name": "Gothic", "description": "A tone facet.", "member_count": 9},
    ]

    targets = _backfill_targets(categories)

    assert [t["name"] for t in targets] == ["Name Generators"]


def test_backfill_targets_never_selects_single_word_facet_tokens():
    """Explicit, named assertion for the 235-single-word-facet-token
    protection (DEDUP_BLIND_SPOTS.md failure mode 1): a single-word category
    with an empty description (e.g. "Absurdist", "Gothic") is the existing,
    intentional Pass-2 facet pattern — the name IS the content by design —
    and must NEVER be selected for backfill even though its description is
    also empty."""
    categories = [
        {"name": "Absurdist", "description": "", "member_count": 4},
        {"name": "Gothic", "description": "", "member_count": 9},
    ]

    assert _backfill_targets(categories) == []


def test_backfill_targets_ignores_nonempty_multiword_categories():
    categories = [
        {"name": "Plot Hooks", "description": "Adventure seeds and hooks.", "member_count": 67},
    ]

    assert _backfill_targets(categories) == []


# -- draft --------------------------------------------------------------------


@pytest.fixture
def seeded_targets(isolated_config):
    """Two multi-word, empty-description categories (Name Generators, Urban
    Environments) with a couple of member documents each — the shape of the
    real 132-target backlog, at test scale."""
    store = Store()
    _add_doc(store, "doc1", "Random Village Name List", ["Name Generators"])
    _add_doc(store, "doc2", "NPC Name Table", ["Name Generators"])
    _add_doc(store, "doc3", "City Map Pack", ["Urban Environments"])
    store.close()
    return isolated_config


def test_draft_writes_artifact_and_does_not_mutate_store(seeded_targets, tmp_path):
    fake_client = _FakeClient(content="Tools for generating random names for NPCs and places.")
    out_path = tmp_path / "description_backfill.json"

    result = draft(client=fake_client, out_path=out_path)

    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    names = {e["name"] for e in payload}
    assert names == {"Name Generators", "Urban Environments"}
    for entry in payload:
        assert entry["drafted_description"] == "Tools for generating random names for NPCs and places."
        assert "member_count" in entry
        assert isinstance(entry["sample_docs"], list) and entry["sample_docs"]

    assert result["path"] == out_path
    assert len(result["drafted"]) == 2
    assert fake_client.calls == 2  # one chat call per target, never a network call

    # Critical: draft() must be read-only. Re-open a FRESH Store (not the one
    # used to seed data) and confirm the categories are STILL empty-
    # description — proving draft() never called create_category or any
    # other mutating Store method.
    store = Store()
    try:
        by_name = {c["name"]: c for c in store.list_categories()}
        assert by_name["Name Generators"]["description"] == ""
        assert by_name["Urban Environments"]["description"] == ""
    finally:
        store.close()


def test_draft_defaults_out_path_to_consolidation_dir(seeded_targets):
    from drive_tagger.config import CONFIG

    fake_client = _FakeClient()
    result = draft(client=fake_client)

    assert result["path"] == CONFIG.consolidation_dir / "description_backfill.json"
    assert result["path"].exists()


# -- apply_descriptions ---------------------------------------------------


def test_apply_descriptions_writes_drafted_text_without_changing_membership(seeded_targets, tmp_path):
    store = Store()
    try:
        before = {c["name"]: c for c in store.list_categories()}
    finally:
        store.close()

    descriptions_path = tmp_path / "description_backfill.json"
    descriptions_path.write_text(
        json.dumps(
            [
                {
                    "name": "Name Generators",
                    "member_count": before["Name Generators"]["member_count"],
                    "sample_docs": ["Random Village Name List", "NPC Name Table"],
                    "drafted_description": "Tools for generating random names.",
                },
                {
                    "name": "Urban Environments",
                    "member_count": before["Urban Environments"]["member_count"],
                    "sample_docs": ["City Map Pack"],
                    "drafted_description": "Maps and descriptions of city settings.",
                },
            ]
        ),
        encoding="utf-8",
    )

    result = apply_descriptions(descriptions_path=descriptions_path)

    assert {a["name"] for a in result["applied"]} == {"Name Generators", "Urban Environments"}
    assert result["skipped"] == []

    store = Store()
    try:
        after = {c["name"]: c for c in store.list_categories()}
    finally:
        store.close()

    assert after["Name Generators"]["description"] == "Tools for generating random names."
    assert after["Urban Environments"]["description"] == "Maps and descriptions of city settings."
    # member_count unchanged (create_category preserves the existing count).
    assert after["Name Generators"]["member_count"] == before["Name Generators"]["member_count"]
    assert after["Urban Environments"]["member_count"] == before["Urban Environments"]["member_count"]
    # No new/deleted categories.
    assert set(after.keys()) == set(before.keys())


def test_apply_descriptions_skips_malformed_and_empty_entries(seeded_targets, tmp_path):
    descriptions_path = tmp_path / "description_backfill.json"
    descriptions_path.write_text(
        json.dumps(
            [
                {"name": "Name Generators", "drafted_description": ""},  # empty description -> skip
                {"member_count": 3, "drafted_description": "no name here"},  # missing name -> skip
                "not-a-dict",  # malformed -> skip
            ]
        ),
        encoding="utf-8",
    )

    result = apply_descriptions(descriptions_path=descriptions_path)

    assert result["applied"] == []
    assert len(result["skipped"]) == 3

    store = Store()
    try:
        by_name = {c["name"]: c for c in store.list_categories()}
        assert by_name["Name Generators"]["description"] == ""  # untouched
    finally:
        store.close()


# -- round-trip: draft()'s own output feeds apply_descriptions() unmodified --


def test_draft_then_apply_round_trip(seeded_targets, tmp_path):
    """The two tests above each construct the artifact independently (draft's
    test writes it via draft(); apply's test hand-writes it) — that leaves a
    blind spot if the two ever drift on field names. This test proves the
    real contract: draft()'s own output file, completely unmodified, is
    exactly what apply_descriptions() can consume."""
    fake_client = _FakeClient(content="A grounded, on-topic description.")
    artifact_path = tmp_path / "description_backfill.json"

    draft(client=fake_client, out_path=artifact_path)
    result = apply_descriptions(descriptions_path=artifact_path)

    assert {a["name"] for a in result["applied"]} == {"Name Generators", "Urban Environments"}
    assert result["skipped"] == []

    store = Store()
    try:
        by_name = {c["name"]: c for c in store.list_categories()}
        assert by_name["Name Generators"]["description"] == "A grounded, on-topic description."
        assert by_name["Urban Environments"]["description"] == "A grounded, on-topic description."
    finally:
        store.close()
