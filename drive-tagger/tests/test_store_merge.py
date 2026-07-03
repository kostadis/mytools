"""Tests for the category-merge primitives added to Store (issue #87):
all_categories_with_vectors, merge_categories, rename_category.

Fully offline — isolated_config (tests/conftest.py) points CONFIG at a
tmp_path scratch dir and swaps in a fake embedder so fastembed never runs.
"""

import pytest

from drive_tagger.store import Store


@pytest.fixture
def store(isolated_config):
    s = Store()
    yield s
    s.close()


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


# -- membership correctness -------------------------------------------------


def test_doc_in_only_source_moves_to_target(store):
    _add_doc(store, "doc1", "Doc 1", ["B"])

    store.merge_categories(["B"], into="A")

    doc = store.get_document("doc1")
    assert doc["categories"] == ["A"]


def test_doc_in_only_target_is_unaffected_but_counted(store):
    _add_doc(store, "doc1", "Doc 1", ["A"])
    _add_doc(store, "doc2", "Doc 2", ["B"])

    store.merge_categories(["B"], into="A")

    doc1 = store.get_document("doc1")
    assert doc1["categories"] == ["A"]
    assert _categories_by_name(store)["A"]["member_count"] == 2


def test_doc_in_both_source_and_target_counts_once(store):
    _add_doc(store, "doc1", "Doc 1", ["A", "B"])

    store.merge_categories(["B"], into="A")

    doc1 = store.get_document("doc1")
    assert doc1["categories"].count("A") == 1
    assert _categories_by_name(store)["A"]["member_count"] == 1


def test_member_count_is_recomputed_not_additive(store):
    # Pre-merge: A has 2 members (doc1, doc2), B has 2 members (doc2, doc3).
    # doc2 is in both. A naive additive merge would report 4; real
    # post-merge membership is 3 distinct docs.
    _add_doc(store, "doc1", "Doc 1", ["A"])
    _add_doc(store, "doc2", "Doc 2", ["A", "B"])
    _add_doc(store, "doc3", "Doc 3", ["B"])

    store.merge_categories(["B"], into="A")

    assert _categories_by_name(store)["A"]["member_count"] == 3


def test_multiple_sources_and_multiple_docs_batch_update(store):
    # Exercises the batch update_metadata(ids=[...], metadatas=[...]) path
    # with more than one element. Each doc keeps a distinct extra category
    # so the assertions catch not just "didn't crash" but genuine per-id
    # fidelity (e.g. a bug that broadcast one doc's metadata to every id in
    # the batch would still pass if all docs ended up with identical
    # categories, which is why the "Keep-N" markers differ per doc).
    _add_doc(store, "doc1", "Doc 1", ["B", "Keep-1"])
    _add_doc(store, "doc2", "Doc 2", ["C", "Keep-2"])
    _add_doc(store, "doc3", "Doc 3", ["A"])

    store.merge_categories(["B", "C"], into="A")

    assert store.get_document("doc1")["categories"] == ["A", "Keep-1"]
    assert store.get_document("doc2")["categories"] == ["A", "Keep-2"]
    assert store.get_document("doc3")["categories"] == ["A"]
    assert _categories_by_name(store)["A"]["member_count"] == 3


# -- source deletion ----------------------------------------------------


def test_source_category_row_is_deleted(store):
    _add_doc(store, "doc1", "Doc 1", ["B"])

    store.merge_categories(["B"], into="A")

    assert store.category_exists("B") is False
    assert "B" not in _categories_by_name(store)


# -- rename ---------------------------------------------------------------


def test_rename_category(store):
    _add_doc(store, "doc1", "Doc 1", ["Old"])

    store.rename_category("Old", "New")

    doc = store.get_document("doc1")
    assert doc["categories"] == ["New"]
    assert store.category_exists("Old") is False
    assert _categories_by_name(store)["New"]["member_count"] == 1


# -- idempotency ------------------------------------------------------------


def test_re_merge_after_source_already_gone_is_noop(store):
    _add_doc(store, "doc1", "Doc 1", ["B"])
    store.merge_categories(["B"], into="A")

    before_count = _categories_by_name(store)["A"]["member_count"]
    before_doc_cats = store.get_document("doc1")["categories"]

    # Re-run with the same (now-nonexistent) source — must not raise.
    store.merge_categories(["B"], into="A")

    after_count = _categories_by_name(store)["A"]["member_count"]
    after_doc_cats = store.get_document("doc1")["categories"]

    assert after_count == before_count
    assert after_doc_cats == before_doc_cats
    assert store.category_exists("B") is False


# -- description behavior ----------------------------------------------------


def test_merge_into_existing_target_without_description_leaves_it_untouched(store):
    store.create_category("A", "original description")
    _add_doc(store, "doc1", "Doc 1", ["B"])

    store.merge_categories(["B"], into="A")

    assert _categories_by_name(store)["A"]["description"] == "original description"


def test_merge_into_existing_target_with_explicit_description_updates_it(store):
    store.create_category("A", "original description")
    _add_doc(store, "doc1", "Doc 1", ["B"])

    store.merge_categories(["B"], into="A", description="new, better description")

    assert _categories_by_name(store)["A"]["description"] == "new, better description"


# -- all_categories_with_vectors ---------------------------------------------


def test_all_categories_with_vectors_returns_vectors_for_every_category(store):
    store.create_category("A", "desc a")
    store.create_category("B", "desc b")

    cats = store.all_categories_with_vectors()

    by_name = {c["name"]: c for c in cats}
    assert set(by_name) == {"A", "B"}
    for c in by_name.values():
        assert c["vector"] is not None
        assert len(c["vector"]) == 8  # isolated_config sets embed_dim=8
