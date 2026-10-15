#!/usr/bin/env python3
"""Tests for npc_review_items.py: a summary_native NPC review -> build_review.py items.

Run: python3 -m pytest dotfiles/claude/skills/_shared/review-artifact/tests
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ADAPTER, BUILD, READ = HERE / "npc_review_items.py", HERE / "build_review.py", HERE / "read_decisions.py"
DRAFT = "docs/npcs/summary_native/ch1-2/draft/npc_rimardo.md"
EVID = "docs/npcs/summary_native/ch1-2/evidence/npc_rimardo.md"


class NpcReviewItemsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.camp = Path(self.tmp.name) / "Camp"
        self.rdir = self.camp / "docs/reviews/npc-review-abc"
        (self.camp / DRAFT).parent.mkdir(parents=True)
        (self.camp / EVID).parent.mkdir(parents=True)
        self.draft = b"# Rimardo\n\nRimardo sold <b>3</b> horses & a cart.\n"
        (self.camp / DRAFT).write_bytes(self.draft)
        (self.camp / EVID).write_text("---\nsubject: Rimardo the Trader\n---\nevidence\n", encoding="utf-8")
        sha = hashlib.sha256(self.draft).hexdigest()
        items = [
            {"item_id": "npc-signoff-1", "revision": 1, "rationale": "sign-off required",
             "locator": {"anchor": "whole-draft", "source_path": DRAFT},
             "input_bindings": [{"path": DRAFT}], "evidence": [], "diagnostics": [],
             "proposed_action": {"action": "signoff_npc_draft",
                                 "details": {"draft_path": DRAFT, "draft_sha256": sha, "npc": "Rimardo",
                                             "mechanical_verdict": "pass"}}},
            {"item_id": "npc-claim-1", "revision": 2, "rationale": "\"3\" appears nowhere in the evidence",
             "claim_text": "Rimardo sold 3 horses </script> & a cart.",
             "locator": {"display_line": 3, "source_path": DRAFT},
             "input_bindings": [{"path": DRAFT}, {"path": EVID}],
             "evidence": [{"source_path": EVID, "anchor": "line:3", "exact_excerpt": "He sold horses. " * 60}],
             "diagnostics": [{"message": "number not in evidence"}],
             "proposed_action": {"action": "review_claim_against_evidence", "details": {}}},
            {"item_id": "npc-pres-1", "revision": 1, "rationale": "differs only in quote marks",
             "claim_text": "said “hi”", "locator": {"display_line": 4, "source_path": DRAFT},
             "input_bindings": [{"path": DRAFT}],
             "evidence": [{"source_path": EVID, "missing_reason": "quote marks only"}], "diagnostics": [],
             "proposed_action": {"action": "review_presentation", "details": {}}},
        ]
        for it in items:
            d = self.rdir / "items" / it["item_id"]; d.mkdir(parents=True)
            (d / f"{it['revision']}.json").write_text(json.dumps(it), encoding="utf-8")
        (self.rdir / "manifest.json").write_text(json.dumps({"review_id": "npc-review-abc", "items": [
            {"item_id": i["item_id"], "revision": i["revision"]} for i in items]}), encoding="utf-8")
        ev = self.rdir / "events"; ev.mkdir()
        # sign-off decided; the claim was decided on revision 1 only (now stale); presentation decided then withdrawn
        for name, e in {
            "d-0": {"item_id": "npc-signoff-1", "item_revision": 1, "decision_revision": 1, "verdict": "approve",
                    "disposition": "document_signoff", "reviewer": "GM"},
            "d-1": {"item_id": "npc-claim-1", "item_revision": 1, "decision_revision": 1, "verdict": "approve",
                    "disposition": "accept_no_change", "reviewer": "GM"},
            "d-2": {"item_id": "npc-pres-1", "item_revision": 1, "decision_revision": 1, "verdict": "approve",
                    "disposition": "accept_no_change", "reviewer": "GM"},
            "w-2": {"kind": "withdrawal", "item_id": "npc-pres-1", "item_revision": 1, "decision_revision": 2},
        }.items():
            (ev / f"{name}.json").write_text(json.dumps(e), encoding="utf-8")
        self.out = Path(self.tmp.name) / "items.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_adapter(self, *args):
        return subprocess.run([sys.executable, str(ADAPTER), str(self.rdir), "--out", str(self.out), *args],
                              capture_output=True, text=True)

    def doc(self):
        return json.loads(self.out.read_text(encoding="utf-8"))

    def test_all_items_contract_shaped_and_buildable(self):
        r = self.run_adapter()
        self.assertEqual(r.returncode, 0, r.stderr)
        d = self.doc()
        self.assertEqual([c["id"] for c in d["items"]], ["npc-claim-1", "npc-pres-1", "npc-signoff-1"])
        for c in d["items"]:
            for k in ("id", "t", "y", "n", "ev"):
                self.assertTrue(c[k], (c["id"], k))
            # every card carries a keep-as-is outcome
            self.assertRegex(c["y"] + c["n"], r"Keep (as-is|the draft as it is)")
        self.assertTrue(d["reviewId"].startswith("npc-review-abc:"))
        self.assertNotIn("state", d)  # never pre-fill
        claim = d["items"][0]
        self.assertIn("Rimardo the Trader", claim["t"])  # subject from the evidence front matter
        self.assertIn("&lt;/script&gt;", claim["ev"])
        self.assertIn("<details>", claim["ev"])  # long excerpt folded
        sign = d["items"][2]
        self.assertIn("&lt;b&gt;3&lt;/b&gt; horses &amp; a cart", sign["ev"])  # full draft text, escaped
        self.assertIn("Already decided", sign["ev"])
        page = Path(self.tmp.name) / "page.html"
        b = subprocess.run([sys.executable, str(BUILD), "--in", str(self.out), "--out", str(page)],
                           capture_output=True, text=True)
        self.assertEqual(b.returncode, 0, b.stderr)
        rd = subprocess.run([sys.executable, str(READ), "--html", str(page), "--items", str(self.out)],
                            capture_output=True, text=True)
        self.assertEqual(rd.returncode, 1)  # unsaved page is never "no decisions"

    def test_undecided_filter(self):
        r = self.run_adapter("--undecided")
        self.assertEqual(r.returncode, 0, r.stderr)
        # signoff has a current decision; the claim's is on an old revision; the presentation's was withdrawn
        self.assertEqual([c["id"] for c in self.doc()["items"]], ["npc-claim-1", "npc-pres-1"])

    def test_ids_and_action_filters(self):
        r = self.run_adapter("--ids", "npc-pres-1,npc-signoff-1", "--action", "signoff_npc_draft")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([c["id"] for c in self.doc()["items"]], ["npc-signoff-1"])
        ids = Path(self.tmp.name) / "ids.txt"; ids.write_text("npc-claim-1\n", encoding="utf-8")
        self.assertEqual(self.run_adapter("--ids-file", str(ids)).returncode, 0)
        self.assertEqual([c["id"] for c in self.doc()["items"]], ["npc-claim-1"])
        bad = self.run_adapter("--ids", "npc-nope")
        self.assertEqual(bad.returncode, 2)
        self.assertIn("npc-nope", bad.stderr)

    def test_nothing_left_is_an_error(self):
        r = self.run_adapter("--undecided", "--action", "signoff_npc_draft")
        self.assertEqual(r.returncode, 1)
        self.assertFalse(self.out.exists())

    def test_stale_draft_refused_unless_allowed(self):
        (self.camp / DRAFT).write_bytes(self.draft + b"edited\n")
        r = self.run_adapter()
        self.assertEqual(r.returncode, 2)
        self.assertIn("npc-signoff-1", r.stderr)
        self.assertFalse(self.out.exists())
        r = self.run_adapter("--allow-stale")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("STALE", self.doc()["items"][2]["ev"])


if __name__ == "__main__":
    unittest.main()
