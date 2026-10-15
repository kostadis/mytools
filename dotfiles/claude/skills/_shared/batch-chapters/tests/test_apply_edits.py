#!/usr/bin/env python3
"""Tests for `batch.py apply-edits` and the count check it shares with `apply`.

Run: python3 -m pytest dotfiles/claude/skills/_shared/batch-chapters/tests
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BATCH = Path(__file__).resolve().parents[1] / "batch.py"


class ApplyEditsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "summaries/ch1").mkdir(parents=True)
        (self.root / "summaries/ch2").mkdir(parents=True)
        self.a = self.root / "summaries/ch1/session-summary.md"
        self.b = self.root / "summaries/ch2/session-summary.md"
        self.a.write_text("Cassian, her brother. Her brother again.\n", encoding="utf-8")
        self.b.write_text("his sister Elara\r\nwindows line\r\n", encoding="utf-8", newline="")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_edits(self, edits, *extra):
        f = self.root / "edits.json"
        f.write_text(json.dumps(edits), encoding="utf-8")
        return subprocess.run([sys.executable, str(BATCH), "apply-edits", str(f), "--root", str(self.root), *extra],
                              capture_output=True, text=True)

    def test_applies_in_order_per_file(self):
        r = self.run_edits([
            {"file": "summaries/ch1/session-summary.md", "old": "brother", "new": "cousin", "count": 2},
            {"file": "summaries/ch1/session-summary.md", "old": "her cousin.", "new": "her cousin (called brother).", "count": 1},
            {"file": str(self.b), "old": "his sister", "new": "his cousin", "count": 1},
        ])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.a.read_text(encoding="utf-8"),
                         "Cassian, her cousin (called brother). Her cousin again.\n")
        # CRLF survives: the file is written back byte for byte apart from the edit
        self.assertEqual(self.b.read_bytes(), b"his cousin Elara\r\nwindows line\r\n")
        self.assertIn("edits=2", r.stdout)

    def test_any_mismatch_writes_nothing_and_reports_all(self):
        before_a, before_b = self.a.read_bytes(), self.b.read_bytes()
        r = self.run_edits([
            {"file": "summaries/ch1/session-summary.md", "old": "brother", "new": "cousin", "count": 1},
            {"file": "summaries/ch2/session-summary.md", "old": "his sister", "new": "his cousin", "count": 1},
            {"file": "summaries/ch2/session-summary.md", "old": "absent", "new": "x", "count": 1},
        ])
        self.assertEqual(r.returncode, 1)
        self.assertIn("NOTHING WRITTEN", r.stdout)
        self.assertIn("expected 1 of 'brother', found 2", r.stdout)
        self.assertIn("expected 1 of 'absent', found 0", r.stdout)
        self.assertEqual(self.a.read_bytes(), before_a)
        self.assertEqual(self.b.read_bytes(), before_b)  # its first edit matched, still not written

    def test_count_sees_earlier_edits(self):
        # the second edit's old only exists after the first edit ran
        r = self.run_edits([
            {"file": "summaries/ch1/session-summary.md", "old": "Cassian", "new": "Lord Cassian", "count": 1},
            {"file": "summaries/ch1/session-summary.md", "old": "Lord Cassian", "new": "Lord Cassian Meliamne", "count": 1},
        ])
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(self.a.read_text(encoding="utf-8").startswith("Lord Cassian Meliamne,"))

    def test_dry_run_writes_nothing(self):
        before = self.a.read_bytes()
        r = self.run_edits([{"file": "summaries/ch1/session-summary.md", "old": "brother", "new": "cousin", "count": 2}],
                           "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("summaries/ch1/session-summary.md  edits=1  replacements=2  changed", r.stdout)
        self.assertIn("dry run", r.stdout)
        self.assertEqual(self.a.read_bytes(), before)

    def test_refuses_replicas_and_vtt(self):
        (self.root / "docs/summaries").mkdir(parents=True)
        rep = self.root / "docs/summaries/001-x.md"; rep.write_text("her brother\n", encoding="utf-8")
        hdr = self.root / "summaries/ch1/npc.md"
        hdr.write_text("<!-- published by summary_native -->\nher brother\n", encoding="utf-8")
        vtt = self.root / "summaries/ch1/x.cleaned.vtt"; vtt.write_text("WEBVTT\n\nher brother\n", encoding="utf-8")
        r = self.run_edits([{"file": str(p), "old": "brother", "new": "cousin", "count": 1} for p in (rep, hdr, vtt)]
                           + [{"file": "summaries/ch1/session-summary.md", "old": "Cassian", "new": "C", "count": 1}])
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout.count("looks like a replica"), 3, r.stdout)
        self.assertIn("transcript_corrections.yaml", r.stdout)
        self.assertIn("Cassian", self.a.read_text(encoding="utf-8"))

    def test_bad_entries(self):
        r = self.run_edits([{"file": "summaries/ch1/session-summary.md", "old": "", "new": "x", "count": 1},
                            {"file": "summaries/ch1/session-summary.md", "old": "a", "new": "x", "count": 0},
                            {"file": "summaries/ch1/session-summary.md", "old": "a", "new": "x"},
                            {"file": "nope.md", "old": "a", "new": "x", "count": 1}])
        self.assertEqual(r.returncode, 1)
        self.assertIn("non-empty", r.stdout)
        self.assertIn("integer >= 1", r.stdout)
        self.assertIn("missing count", r.stdout)
        self.assertIn("no such file", r.stdout)


class ExistingApplyStillCountChecks(unittest.TestCase):
    """`apply` now goes through the shared count_replace helper; keep its contract."""

    def test_apply_refuses_mismatch_and_applies_match(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t); sd = root / "camp/summaries/ch1"; R = sd / "staged_review"; R.mkdir(parents=True)
            (sd / "session-summary.md").write_text("Old text. Card text.", encoding="utf-8")
            (R / "findings_stage1.json").write_text(json.dumps({"findings": [
                {"id": "a1", "disposition": "auto", "edits": [{"old": "Old text.", "new": "New text.", "count": 1}]},
                {"id": "c1", "disposition": "card", "edits": [{"old": "Card text.", "new": "Approved.", "count": 1}]}]}),
                encoding="utf-8")
            (R / "decisions_stage1.json").write_text(json.dumps(
                {"savedAt": "now", "decisions": {"c1": "approve"}}), encoding="utf-8")
            cfg = root / "batch.json"
            cfg.write_text(json.dumps({"campaign": str(root / "camp"), "chapters": [{"dir": "ch1"}]}), encoding="utf-8")
            r = subprocess.run([sys.executable, str(BATCH), "apply", "--config", str(cfg), "--stage", "stage1"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual((sd / "session-summary.md").read_text(encoding="utf-8"), "New text. Approved.")
            r = subprocess.run([sys.executable, str(BATCH), "apply", "--config", str(cfg), "--stage", "stage1"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("found 0", r.stdout)


if __name__ == "__main__":
    unittest.main()
