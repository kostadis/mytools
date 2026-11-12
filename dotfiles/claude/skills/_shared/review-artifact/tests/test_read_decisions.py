#!/usr/bin/env python3
"""Tests for read_decisions.py class-card expansion (spec 041, FR-017/FR-017a).

Run: python3 -m pytest dotfiles/claude/skills/_shared/review-artifact/tests
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
BUILD, READ = HERE / "build_review.py", HERE / "read_decisions.py"

CARDS = [
    {"id": "noise-class:label", "group": "Classified noise", "members": ["n-1", "n-2"],
     "t": "Classified noise: label", "y": "Keep.", "n": "Fix.", "ev": "2 occurrences"},
    {"id": "noise-class:idiom", "group": "Classified noise", "members": ["n-3"],
     "t": "Classified noise: idiom", "y": "Keep.", "n": "Fix.", "ev": "1 occurrence"},
    {"id": "npc-claim-1", "t": "claim", "y": "Keep.", "n": "Fix.", "ev": "x"},
]


class ClassCardReadBackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.items = self.dir / "items.json"
        self.items.write_text(json.dumps({"title": "T", "reviewId": "r:1", "items": CARDS}), encoding="utf-8")
        self.page = self.dir / "page.html"
        b = subprocess.run([sys.executable, str(BUILD), "--in", str(self.items), "--out", str(self.page)],
                           capture_output=True, text=True)
        self.assertEqual(b.returncode, 0, b.stderr)

    def tearDown(self):
        self.tmp.cleanup()

    def saved(self, decisions, notes=None, page=None):
        html = (page or self.page).read_text(encoding="utf-8")
        state = {"decisions": decisions, "notes": notes or {}, "picks": {}, "savedAt": "2026-11-12 10:00 UTC",
                 "reviewId": "r:1"}
        out = self.dir / "saved.html"
        out.write_text(re.sub(r'(<script[^>]*id="state"[^>]*>).*?(</script>)',
                              lambda m: m.group(1) + json.dumps(state) + m.group(2), html, flags=re.S),
                       encoding="utf-8")
        return out

    def read(self, html, *extra):
        return subprocess.run([sys.executable, str(READ), "--html", str(html), "--items", str(self.items), *extra],
                              capture_output=True, text=True)

    def test_page_carries_members(self):
        self.assertIn('"members"', self.page.read_text(encoding="utf-8"))

    def test_approve_expands_to_each_member_with_card_note(self):
        r = self.read(self.saved({"noise-class:label": "approve", "npc-claim-1": "reject"},
                                 {"noise-class:label": "chapter labels", "npc-claim-1": "fix"}))
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertEqual(d["decisions"], {"n-1": "approve", "n-2": "approve", "npc-claim-1": "reject"})
        card = "GM class verdict on batch card [noise-class:label] (2 occurrences): chapter labels"
        self.assertEqual(d["notes"], {"n-1": card, "n-2": card, "npc-claim-1": "fix"})
        self.assertEqual(d["classes"], {"noise-class:label": {"verdict": "approve", "members": ["n-1", "n-2"]}})
        self.assertEqual(d["unmarked"], ["noise-class:idiom"])  # never inferred
        self.assertNotIn("n-3", d["decisions"])

    def test_reject_expands(self):
        d = json.loads(self.read(self.saved({"noise-class:idiom": "reject"})).stdout)
        self.assertEqual(d["decisions"], {"n-3": "reject"})
        # No GM note on the card: the member still records that its verdict came from a class card.
        self.assertEqual(d["notes"], {"n-3": "GM class verdict on batch card [noise-class:idiom] (1 occurrences)"})

    def test_discuss_and_undecided_class_cards_make_no_member_decision(self):
        r = self.read(self.saved({"noise-class:label": "discuss", "npc-claim-1": "approve"}))
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertEqual(d["decisions"], {"npc-claim-1": "approve"})
        self.assertIn("noise-class:label", d["discuss"])
        self.assertEqual(d["unmarked"], ["noise-class:idiom"])
        self.assertEqual(d["classes"], {})

    def test_membership_change_is_stale_exit_2(self):
        spec = json.loads(self.items.read_text())
        spec["items"][0]["members"] = ["n-1", "n-2", "n-9"]
        self.items.write_text(json.dumps(spec), encoding="utf-8")
        r = self.read(self.saved({"noise-class:label": "approve"}))
        self.assertEqual(r.returncode, 2)
        self.assertIn("membership", r.stderr)

    def test_pages_without_class_cards_read_as_before(self):
        spec = {"title": "T", "reviewId": "r:2", "items": [CARDS[2]]}
        items = self.dir / "plain.json"; items.write_text(json.dumps(spec), encoding="utf-8")
        page = self.dir / "plain.html"
        subprocess.run([sys.executable, str(BUILD), "--in", str(items), "--out", str(page)], check=True)
        state = {"decisions": {"npc-claim-1": "approve"}, "notes": {}, "picks": {}, "savedAt": "x", "reviewId": "r:2"}
        html = re.sub(r'(<script[^>]*id="state"[^>]*>).*?(</script>)',
                      lambda m: m.group(1) + json.dumps(state) + m.group(2), page.read_text(), flags=re.S)
        saved = self.dir / "plain-saved.html"; saved.write_text(html)
        r = subprocess.run([sys.executable, str(READ), "--html", str(saved), "--items", str(items)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertEqual(d["decisions"], {"npc-claim-1": "approve"})
        self.assertNotIn("classes", d)


if __name__ == "__main__":
    unittest.main()
