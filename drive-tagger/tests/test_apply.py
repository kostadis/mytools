"""Tests for consolidate.apply() (issue #88).

Fully offline — isolated_config (tests/conftest.py) points CONFIG at a
tmp_path scratch dir and swaps in a fake embedder so fastembed never runs.

Store-handle discipline: every Store() used to seed/inspect data is closed
before the next one opens (turbovecdb.Collection takes a cross-process
FileLock per collection dir) — apply() itself opens/closes its own Store()
internally, so tests must not hold a handle open across a call to apply().
"""

import json

import pytest

from drive_tagger.config import CONFIG
from drive_tagger.consolidate import apply
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
        text=name,
    )
    if categories:
        store.assign_categories(doc_id, categories)


def _categories_by_name(store):
    return {c["name"]: c for c in store.list_categories()}


def _write_decisions(payload):
    CONFIG.consolidation_dir.mkdir(parents=True, exist_ok=True)
    path = CONFIG.consolidation_dir / "decisions.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def seeded(isolated_config):
    """Seed categories A/B (approved merge target), C (rejected pair target
    D), E (ignored pair target F) with a few documents, then close the
    handle so apply() can open its own."""
    store = Store()
    _add_doc(store, "doc1", "Doc 1", ["B"])
    _add_doc(store, "doc2", "Doc 2", ["A"])
    _add_doc(store, "doc3", "Doc 3", ["C"])
    _add_doc(store, "doc4", "Doc 4", ["D"])
    _add_doc(store, "doc5", "Doc 5", ["E"])
    _add_doc(store, "doc6", "Doc 6", ["F"])
    store.close()
    return isolated_config


def test_approved_merge_is_applied(seeded):
    decisions_path = _write_decisions(
        {
            "cluster-approved": {
                "status": "approved",
                "canonical": "A",
                "sources": ["B"],
                "decided_at": "2026-07-03T00:00:00",
            },
        }
    )

    result = apply(decisions_path)

    assert len(result["merged"]) == 1
    assert result["merged"][0] == {"id": "cluster-approved", "canonical": "A", "sources": ["B"]}

    store = Store()
    try:
        doc1 = store.get_document("doc1")
        assert doc1["categories"] == ["A"]
        assert store.category_exists("B") is False
        assert _categories_by_name(store)["A"]["member_count"] == 2
    finally:
        store.close()


def test_rejected_and_ignored_are_inert(seeded):
    decisions_path = _write_decisions(
        {
            "cluster-rejected": {"status": "rejected", "decided_at": "2026-07-03T00:00:00"},
            "cluster-ignored": {"status": "ignored", "decided_at": "2026-07-03T00:00:00"},
        }
    )

    result = apply(decisions_path)

    assert result["merged"] == []
    assert {s["id"] for s in result["skipped"]} == {"cluster-rejected", "cluster-ignored"}

    store = Store()
    try:
        # Nothing touched: C/D and E/F remain separate, docs unchanged.
        assert store.category_exists("C") is True
        assert store.category_exists("D") is True
        assert store.category_exists("E") is True
        assert store.category_exists("F") is True
        assert store.get_document("doc3")["categories"] == ["C"]
        assert store.get_document("doc4")["categories"] == ["D"]
        assert store.get_document("doc5")["categories"] == ["E"]
        assert store.get_document("doc6")["categories"] == ["F"]
    finally:
        store.close()


def test_apply_is_idempotent(seeded):
    decisions_path = _write_decisions(
        {
            "cluster-approved": {
                "status": "approved",
                "canonical": "A",
                "sources": ["B"],
                "decided_at": "2026-07-03T00:00:00",
            },
        }
    )

    first = apply(decisions_path)
    second = apply(decisions_path)

    # Same decisions.json -> same reported merge both times (driven by the
    # file's content, not by "did anything actually change").
    assert first["merged"] == second["merged"]

    store = Store()
    try:
        assert store.get_document("doc1")["categories"] == ["A"]
        assert store.category_exists("B") is False
        assert _categories_by_name(store)["A"]["member_count"] == 2
    finally:
        store.close()


def test_apply_regenerates_report(seeded):
    decisions_path = _write_decisions(
        {
            "cluster-approved": {
                "status": "approved",
                "canonical": "A",
                "sources": ["B"],
                "decided_at": "2026-07-03T00:00:00",
            },
        }
    )

    apply(decisions_path)

    assert (CONFIG.reports_dir / "DRIVE-TAGS.md").exists()
    assert (CONFIG.reports_dir / "categories.json").exists()
    assert (CONFIG.reports_dir / "graph.json").exists()


def test_apply_skips_invalid_entries(seeded):
    decisions_path = _write_decisions(
        {
            "cluster-missing-canonical": {
                "status": "approved",
                "sources": ["B"],
                "decided_at": "2026-07-03T00:00:00",
            },
            "cluster-missing-sources": {
                "status": "approved",
                "canonical": "A",
                "decided_at": "2026-07-03T00:00:00",
            },
        }
    )

    result = apply(decisions_path)

    assert result["merged"] == []
    assert {s["id"] for s in result["skipped"]} == {
        "cluster-missing-canonical",
        "cluster-missing-sources",
    }

    store = Store()
    try:
        # Untouched — B never merged since neither entry was valid.
        assert store.category_exists("B") is True
        assert store.get_document("doc1")["categories"] == ["B"]
    finally:
        store.close()
