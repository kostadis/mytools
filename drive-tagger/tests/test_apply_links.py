"""link_consolidate.apply_relations — offline, mirrors test_apply.py discipline."""
import json

from drive_tagger.config import CONFIG
from drive_tagger.graph import Graph
from drive_tagger.link_consolidate import apply_relations


def _seed_graph():
    """Populate the graph, then close the handle (apply opens its own Graph)."""
    g = Graph()
    g.add_link("A", "B", "complementary")
    g.add_link("C", "D", "complementary-to")
    g.add_link("E", "F", "sequel-to")     # rejected family — must stay untouched
    g.add_link("G", "H", "related-to")    # canonical — untouched
    g.close()


def _relset():
    g = Graph()
    rels = sorted(ln["relation"] for ln in g.all_links())
    g.close()
    return rels


def _write_decisions(entries: dict) -> None:
    CONFIG.ensure_dirs()
    (CONFIG.consolidation_dir / "link_decisions.json").write_text(
        json.dumps(entries), encoding="utf-8"
    )


def test_approved_family_merged(isolated_config):
    _seed_graph()
    _write_decisions({
        "fam1": {"status": "approved", "canonical": "complements",
                 "sources": ["complementary", "complementary-to"]},
        "fam2": {"status": "rejected"},
    })
    result = apply_relations(CONFIG.consolidation_dir / "link_decisions.json")

    assert len(result["merged"]) == 1
    assert result["merged"][0]["canonical"] == "complements"
    assert {"id": "fam2", "status": "rejected"} in result["skipped"]
    # both complementary* rewritten to complements; sequel-to / related-to intact
    assert _relset() == ["complements", "complements", "related-to", "sequel-to"]


def test_idempotent(isolated_config):
    _seed_graph()
    _write_decisions({
        "fam1": {"status": "approved", "canonical": "complements",
                 "sources": ["complementary", "complementary-to"]},
    })
    p = CONFIG.consolidation_dir / "link_decisions.json"
    apply_relations(p)
    before = _relset()
    apply_relations(p)  # re-run: sources already gone
    assert _relset() == before


def test_report_regenerated(isolated_config):
    _seed_graph()
    _write_decisions({"fam1": {"status": "approved", "canonical": "complements",
                               "sources": ["complementary"]}})
    result = apply_relations(CONFIG.consolidation_dir / "link_decisions.json")
    assert result["report_paths"]["index"].exists()
    assert result["report_paths"]["graph"].exists()


def test_invalid_entries_skipped(isolated_config):
    _seed_graph()
    _write_decisions({
        "no_canonical": {"status": "approved", "sources": ["complementary"]},
        "no_sources": {"status": "approved", "canonical": "complements"},
    })
    result = apply_relations(CONFIG.consolidation_dir / "link_decisions.json")
    assert result["merged"] == []
    assert {"id": "no_canonical", "status": "invalid"} in result["skipped"]
    assert {"id": "no_sources", "status": "invalid"} in result["skipped"]
    # nothing changed
    assert "complementary" in _relset()
