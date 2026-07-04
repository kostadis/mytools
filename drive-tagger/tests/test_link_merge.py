"""graph.merge_relations — the link-relation mutation primitive."""
from drive_tagger.graph import Graph


def _g(tmp_path):
    return Graph(path=tmp_path / "graph.sqlite")


def _relations(g):
    return sorted((ln["src_id"], ln["dst_id"], ln["relation"]) for ln in g.all_links())


def test_rewrite_relation(tmp_path):
    g = _g(tmp_path)
    g.add_link("A", "B", "complementary")
    g.add_link("C", "D", "complements")
    res = g.merge_relations(["complementary"], into="complements")
    assert res["rewritten"] == 1 and res["deduped"] == 0
    assert _relations(g) == [("A", "B", "complements"), ("C", "D", "complements")]
    g.close()


def test_collision_dedups_onto_existing_into(tmp_path):
    g = _g(tmp_path)
    g.add_link("A", "B", "complements")     # the target edge already exists
    g.add_link("A", "B", "complementary")   # collides on rewrite
    res = g.merge_relations(["complementary"], into="complements")
    assert res["rewritten"] == 0 and res["deduped"] == 1
    assert _relations(g) == [("A", "B", "complements")]
    g.close()


def test_two_sources_collapse(tmp_path):
    g = _g(tmp_path)
    g.add_link("A", "B", "sequel-to")
    g.add_link("A", "B", "prequel-to")
    res = g.merge_relations(["sequel-to", "prequel-to"], into="series-member")
    assert res["rewritten"] == 1 and res["deduped"] == 1
    assert _relations(g) == [("A", "B", "series-member")]
    g.close()


def test_idempotent_after_sources_gone(tmp_path):
    g = _g(tmp_path)
    g.add_link("A", "B", "complementary")
    g.merge_relations(["complementary"], into="complements")
    res2 = g.merge_relations(["complementary"], into="complements")  # sources gone
    assert res2["rewritten"] == 0 and res2["deduped"] == 0
    assert _relations(g) == [("A", "B", "complements")]
    g.close()


def test_self_filter_into_out_of_sources(tmp_path):
    g = _g(tmp_path)
    g.add_link("A", "B", "series-part")
    # 'series-member' appears in sources but equals into -> filtered out.
    res = g.merge_relations(["series-member", "series-part"], into="series-member")
    assert res["sources"] == ["series-part"]
    assert _relations(g) == [("A", "B", "series-member")]
    g.close()


def test_empty_sources_noop(tmp_path):
    g = _g(tmp_path)
    g.add_link("A", "B", "related-to")
    res = g.merge_relations([], into="related-to")
    assert res == {"into": "related-to", "sources": [], "rewritten": 0, "deduped": 0}
    assert _relations(g) == [("A", "B", "related-to")]
    g.close()
