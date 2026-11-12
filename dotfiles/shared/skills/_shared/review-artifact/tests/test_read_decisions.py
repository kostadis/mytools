#!/usr/bin/env python3
"""Tests for read_decisions.py: the --html reader (no class-card expansion any more, spec 043 T038)
and the --npc card decisions writer.

Run: python3 -m pytest dotfiles/shared/skills/_shared/review-artifact/tests
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
SHA = "ab" * 32

CARDS = [
    {"id": "noise-class:label", "group": "Classified noise", "members": ["n-1", "n-2"],
     "t": "Classified noise: label", "y": "Keep.", "n": "Fix.", "ev": "2 occurrences"},
    {"id": "npc-signoff-1", "members": ["npc-signoff-1"], "draftSha256": SHA,
     "t": "Sign", "y": "Sign.", "n": "Keep unsigned.", "ev": "draft"},
    {"id": "npc-claim-1", "members": ["npc-claim-1"], "t": "claim", "y": "Keep.", "n": "Fix.", "ev": "x"},
]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.items = self.dir / "items.json"
        self.items.write_text(json.dumps({"title": "T", "reviewId": "packet-x", "items": CARDS}), encoding="utf-8")
        self.page = self.dir / "page.html"
        b = subprocess.run([sys.executable, str(BUILD), "--in", str(self.items), "--out", str(self.page)],
                           capture_output=True, text=True)
        self.assertEqual(b.returncode, 0, b.stderr)

    def tearDown(self):
        self.tmp.cleanup()

    def saved(self, decisions, notes=None, picks=None, saved_at="2026-11-12 10:00 UTC"):
        html = self.page.read_text(encoding="utf-8")
        state = {"decisions": decisions, "notes": notes or {}, "picks": picks or {}, "savedAt": saved_at,
                 "reviewId": "packet-x"}
        out = self.dir / "saved.html"
        out.write_text(re.sub(r'(<script[^>]*id="state"[^>]*>).*?(</script>)',
                              lambda m: m.group(1) + json.dumps(state) + m.group(2), html, flags=re.S),
                       encoding="utf-8")
        return out

    def run_read(self, *args):
        return subprocess.run([sys.executable, str(READ), *args], capture_output=True, text=True)


class HtmlModeTests(Base):
    def test_class_cards_are_not_expanded_any_more(self):
        r = self.run_read("--html", str(self.saved({"noise-class:label": "approve", "npc-claim-1": "reject"},
                                                   {"noise-class:label": "chapter labels"})),
                          "--items", str(self.items))
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertEqual(d["decisions"], {"noise-class:label": "approve", "npc-claim-1": "reject"})
        self.assertEqual(d["notes"], {"noise-class:label": "chapter labels"})
        self.assertNotIn("classes", d)
        self.assertEqual(d["unmarked"], ["npc-signoff-1"])

    def test_card_extra_fields_reach_the_page(self):
        html = self.page.read_text(encoding="utf-8")
        self.assertIn('"members"', html)
        self.assertIn(SHA, html)


class NpcModeTests(Base):
    def npc(self, saved, *extra, review="npc-review-abc"):
        out = self.dir / "d.json"
        r = self.run_read("--npc", "--html", str(saved), "--review", review, "--out", str(out), *extra)
        return r, out

    def test_writes_the_card_decisions_file_with_echoes_from_the_page(self):
        r, out = self.npc(self.saved({"noise-class:label": "approve", "npc-signoff-1": "reject"},
                                     {"npc-signoff-1": "fix the date"}))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(out.read_text()), {
            "schemaVersion": 1, "packetId": "packet-x", "reviewId": "npc-review-abc",
            "savedAt": "2026-11-12 10:00 UTC",
            "cards": {
                "noise-class:label": {"verdict": "approve", "note": "", "members": ["n-1", "n-2"]},
                "npc-signoff-1": {"verdict": "reject", "note": "fix the date", "members": ["npc-signoff-1"],
                                  "draftSha256": SHA},
            }})

    def test_unmarked_cards_are_omitted(self):
        r, out = self.npc(self.saved({"npc-claim-1": "discuss"}))
        self.assertEqual(list(json.loads(out.read_text())["cards"]), ["npc-claim-1"])

    def test_unsaved_page_is_exit_1(self):
        r, _ = self.npc(self.saved({}, saved_at=None))
        self.assertEqual(r.returncode, 1)

    def test_pick_verdict_is_refused(self):
        r, _ = self.npc(self.saved({"npc-claim-1": "pick"}, picks={"npc-claim-1": "w"}))
        self.assertEqual(r.returncode, 2)
        self.assertIn("pick", r.stderr)

    def test_extra_verdict_page_is_refused(self):
        spec = json.loads(self.items.read_text())
        spec["extraVerdicts"] = [{"key": "defer", "label": "Defer", "outcome": "Later."}]
        self.items.write_text(json.dumps(spec))
        subprocess.run([sys.executable, str(BUILD), "--in", str(self.items), "--out", str(self.page)], check=True)
        r, _ = self.npc(self.saved({"npc-claim-1": "approve"}))
        self.assertEqual(r.returncode, 2)

    def test_review_flag_is_required(self):
        r = self.run_read("--npc", "--html", str(self.saved({"npc-claim-1": "approve"})))
        self.assertEqual(r.returncode, 2)

    def test_card_without_members_is_refused(self):
        spec = json.loads(self.items.read_text())
        del spec["items"][2]["members"]
        self.items.write_text(json.dumps(spec))
        subprocess.run([sys.executable, str(BUILD), "--in", str(self.items), "--out", str(self.page)], check=True)
        r, _ = self.npc(self.saved({"npc-claim-1": "approve"}))
        self.assertEqual(r.returncode, 2)
        self.assertIn("members", r.stderr)


if __name__ == "__main__":
    unittest.main()
