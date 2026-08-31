#!/usr/bin/env python3
"""Tests for lib/fix_adventure_json.py — chapter/ID normalisation."""

from lib.fix_adventure_json import ID_REF_KEYS, assign_ids, reset_ids
from lib.validate_adventure import validate


def _all_ids(entries):
    """Collect every id in the tree, in document order.

    Skips reference keys the way `Renderer.adventureBook.getEntryIdLookup`
    does: a `mapParent`'s "id" names *another* node, so counting it here
    would report a phantom duplicate for every map in the document.
    """
    out = []

    def walk(node):
        if isinstance(node, dict):
            if "id" in node:
                out.append(node["id"])
            for key, value in node.items():
                if key in ID_REF_KEYS:
                    continue
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(entries)
    return out


class TestAssignIds:
    def test_inset_readaloud_gets_an_id(self):
        # insetReadaloud carries an id in official 5etools data (7k+ of them),
        # so it must be part of the numbering rather than skipped.
        data = [{"type": "section", "name": "A", "entries": [
            {"type": "insetReadaloud", "entries": ["Boxed text."]},
        ]}]
        reset_ids()
        assign_ids(data)
        assert data[0]["entries"][0]["id"] == "001"

    def test_stale_id_on_unnumbered_type_is_renumbered(self):
        # Regression: a stale id left on a type the pass didn't number survived
        # and could collide with a freshly-assigned one, which makes 5etools'
        # getEntryIdLookup throw and leaves the adventure stuck on "loading".
        data = [{"type": "section", "name": "A", "entries": [
            {"type": "quote", "id": "002", "entries": ["Words."]},
            {"type": "entries", "name": "B", "entries": []},
            {"type": "entries", "name": "C", "entries": []},
        ]}]
        reset_ids()
        assign_ids(data)
        ids = _all_ids(data)
        assert len(ids) == len(set(ids)), ids

    def test_ids_unique_across_mixed_tree(self):
        data = [
            {"type": "section", "name": "A", "entries": [
                {"type": "entries", "name": "A1", "id": "555", "entries": [
                    {"type": "inset", "entries": ["x"]},
                    {"type": "insetReadaloud", "id": "001", "entries": ["y"]},
                ]},
            ]},
            {"type": "section", "name": "B", "entries": [
                {"type": "insetReadaloud", "entries": ["z"]},
            ]},
        ]
        reset_ids()
        assign_ids(data)
        ids = _all_ids(data)
        assert len(ids) == len(set(ids)), ids
        assert ids == sorted(ids), ids

    def test_renumbered_tree_passes_the_validator(self):
        data = [{"type": "section", "name": "A", "entries": [
            {"type": "entries", "name": "A1", "id": "003", "entries": []},
            {"type": "insetReadaloud", "id": "003", "entries": ["dup"]},
        ]}]
        reset_ids()
        assign_ids(data)
        doc = {
            "_meta": {"sources": [{"json": "T", "abbreviation": "T", "full": "T"}]},
            "adventure": [{"name": "T", "id": "T", "source": "T",
                           "contents": [{"name": "A", "headers": []}]}],
            "adventureData": [{"id": "T", "source": "T", "data": data}],
        }
        result = validate(doc)
        assert not any("duplicate id" in e for e in result.errors), result.errors


class TestAssignIdsPreservesMapLinkage:
    """A "mapParent" holds a reference to another node's id.

    5etools blocklists the key when collecting ids, and nothing in this
    module rewrites references — so renumbering a referenced node silently
    detaches a player-version map from its DM original.
    """

    def _doc_with_map(self):
        return [{
            "type": "section", "name": "Chapter 1", "entries": [
                {"type": "image", "id": "03c",
                 "href": {"type": "internal", "path": "map.webp"}},
                {"type": "image", "id": "03d",
                 "href": {"type": "internal", "path": "map-player.webp"},
                 "mapParent": {"id": "03c"}},
                {"type": "entries", "name": "A1. Cave", "entries": ["Dark."]},
            ],
        }]

    def test_referenced_id_keeps_its_value(self):
        data = self._doc_with_map()
        reset_ids()
        assign_ids(data)
        assert data[0]["entries"][0]["id"] == "03c"
        assert data[0]["entries"][1]["mapParent"] == {"id": "03c"}

    def test_reference_still_resolves_to_a_real_node(self):
        data = self._doc_with_map()
        reset_ids()
        assign_ids(data)
        assert "03c" in set(_all_ids(data))

    def test_preserved_id_is_never_handed_out_to_another_node(self):
        # The counter must step over "03c" — it is not a numeric id, but a
        # preserved id that *does* look numeric would otherwise be reissued.
        data = [{
            "type": "section", "name": "Ch", "entries": [
                {"type": "image", "id": "002",
                 "href": {"type": "internal", "path": "m.webp"}},
                {"type": "image", "id": "x9",
                 "href": {"type": "internal", "path": "p.webp"},
                 "mapParent": {"id": "002"}},
            ] + [{"type": "entries", "name": f"R{i}", "entries": ["x"]}
                 for i in range(6)],
        }]
        reset_ids()
        assign_ids(data)
        ids = _all_ids(data)
        assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"
        assert ids.count("002") == 1

    def test_map_parent_id_is_not_treated_as_a_node_id(self):
        data = self._doc_with_map()
        reset_ids()
        assign_ids(data)
        # The reference dict must not have been renumbered as if it were a node.
        assert data[0]["entries"][1]["mapParent"] == {"id": "03c"}


class TestAssignIdsReachesEveryContainer:
    """`getEntryIdLookup` collects ids from every node, so uniqueness has to
    hold outside `entries[]`/`items[]` too — map images live in `images[]`."""

    def test_ids_inside_images_are_renumbered(self):
        data = [{
            "type": "section", "name": "Ch", "entries": [
                {"type": "gallery", "images": [
                    {"type": "image", "id": "032",
                     "href": {"type": "internal", "path": "a.webp"}},
                ]},
            ],
        }]
        reset_ids()
        assign_ids(data)
        assert data[0]["entries"][0]["images"][0]["id"] != "032"

    def test_untouched_numeric_image_id_no_longer_collides(self):
        # "032" in images[] used to survive the pass untouched and then
        # collide with the freshly-assigned "032" — the fatal duplicate that
        # leaves 5etools stuck on its loading overlay.
        data = [{
            "type": "section", "name": "Ch", "entries": [
                {"type": "gallery", "images": [
                    {"type": "image", "id": "032",
                     "href": {"type": "internal", "path": "a.webp"}},
                ]},
            ] + [{"type": "entries", "name": f"R{i}", "entries": ["x"]}
                 for i in range(40)],
        }]
        reset_ids()
        assign_ids(data)
        ids = _all_ids(data)
        assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"


class TestCollectMapParentRefs:
    def test_finds_nested_references(self):
        from lib.fix_adventure_json import collect_map_parent_refs
        data = [{"entries": [{"entries": [{"mapParent": {"id": "abc"}}]}]}]
        assert collect_map_parent_refs(data) == {"abc"}

    def test_empty_when_no_maps(self):
        from lib.fix_adventure_json import collect_map_parent_refs
        assert collect_map_parent_refs([{"type": "section", "entries": ["x"]}]) == set()
