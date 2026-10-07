#!/usr/bin/env python3
"""Focused tests for the Codex batch-chapters adapter."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parents[1]
BATCH = HERE / "batch.py"
CODEX_HOME = HERE.parents[2]


class BatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.base = self.root / "campaign" / "summaries"
        self.env = {**os.environ, "CODEX_HOME": str(CODEX_HOME)}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_chapter(self, name: str, target: str = "Old text. Card text.") -> Path:
        review = self.base / name / "staged_review"
        review.mkdir(parents=True)
        (review.parent / "session-summary.md").write_text(target, encoding="utf-8")
        findings = {
            "findings": [
                {"id": "auto-1", "disposition": "auto", "edits": [
                    {"old": "Old text.", "new": "New text.", "count": 1}
                ]},
                {"id": "card-1", "disposition": "card", "edits": [
                    {"old": "Card text.", "new": "Approved text.", "count": 1}
                ]},
            ]
        }
        items = {
            "title": f"{name} review",
            "reviewId": f"batch:{name}:stage1",
            "outputName": "decisions_stage1.json",
            "items": [{"id": "card-1", "t": "Change the card text?",
                       "y": "Write the approved text.", "n": "Keep it."}],
        }
        (review / "findings_stage1.json").write_text(json.dumps(findings), encoding="utf-8")
        (review / "review_items_stage1.json").write_text(json.dumps(items), encoding="utf-8")
        return review

    def config(self, chapters: list[str]) -> Path:
        path = self.root / "batch.json"
        path.write_text(json.dumps({
            "campaign": str(self.root / "campaign"),
            "summaries": "summaries",
            "target": "session-summary.md",
            "chapters": [{"dir": chapter} for chapter in chapters],
        }), encoding="utf-8")
        return path

    def run_batch(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(BATCH), *args],
            text=True,
            capture_output=True,
            env=self.env,
            check=False,
        )

    def test_validate_builds_local_review_page(self) -> None:
        review = self.write_chapter("chapter-1")
        result = self.run_batch("validate", "--config", str(self.config(["chapter-1"])),
                                "--stage", "stage1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("items=1  OK", result.stdout)
        page = review / "review_stage1.html"
        self.assertTrue(page.is_file())
        self.assertIn("Change the card text?", page.read_text(encoding="utf-8"))

    def test_read_validates_saved_export_against_items(self) -> None:
        review = self.write_chapter("chapter-1")
        self.config(["chapter-1"])
        (review / "decisions_stage1.json").write_text(json.dumps({
            "schemaVersion": 1,
            "reviewId": "batch:chapter-1:stage1",
            "savedAt": "2026-10-07 16:00 UTC",
            "decisions": {"card-1": "approve"},
            "notes": {},
            "unmarked": [],
        }), encoding="utf-8")
        result = self.run_batch("read", "--config", str(self.root / "batch.json"),
                                "--stage", "stage1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("'approve': 1", result.stdout)

        payload = json.loads((review / "decisions_stage1.json").read_text(encoding="utf-8"))
        payload["decisions"] = {"stale-card": "approve"}
        (review / "decisions_stage1.json").write_text(json.dumps(payload), encoding="utf-8")
        stale = self.run_batch("read", "--config", str(self.root / "batch.json"),
                               "--stage", "stage1")
        self.assertEqual(stale.returncode, 1)
        self.assertIn("READ FAILED", stale.stdout)
        self.assertIn("stale export", stale.stdout)

    def test_apply_is_all_or_nothing_across_chapters(self) -> None:
        first = self.write_chapter("chapter-1")
        second = self.write_chapter("chapter-2", target="Old text. Card text changed upstream.")
        config = self.config(["chapter-1", "chapter-2"])
        for review in (first, second):
            (review / "decisions_stage1.json").write_text(json.dumps({
                "savedAt": "2026-10-07 16:00 UTC",
                "decisions": {"card-1": "approve"},
                "notes": {},
                "unmarked": [],
            }), encoding="utf-8")

        before = (first.parent / "session-summary.md").read_text(encoding="utf-8")
        result = self.run_batch("apply", "--config", str(config), "--stage", "stage1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("NOTHING WRITTEN", result.stdout)
        self.assertEqual((first.parent / "session-summary.md").read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
