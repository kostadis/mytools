#!/usr/bin/env python3
"""Tests for build_review.py's card standard: proposed edit first, guess as an option.

Run: python3 -m pytest dotfiles/claude/skills/_shared/review-artifact/tests
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
BUILD, READ = HERE / "build_review.py", HERE / "read_decisions.py"

spec = importlib.util.spec_from_file_location("build_review", BUILD)
br = importlib.util.module_from_spec(spec)
spec.loader.exec_module(br)

EDIT = "&bull; <i>ivory trays</i> &rarr; <i>an ivory tray</i> (&times;2)"
Y = "In <code>session-summary.md</code>, two places.<br><b>Exact edits:</b><br>" + EDIT


def card(**kw) -> dict:
    base = {"id": "s1-01", "t": "[Minor] One tray, not several.", "y": Y,
            "n": "Keep verbatim.", "ev": "cue 904 <i>An ivory tray.</i>"}
    base.update(kw)
    return base


def page_items(html: str) -> list[dict]:
    src = re.search(r'<script type="text/plain" id="src">(.*?)</script>', html, re.S).group(1)
    return json.loads(re.search(r"var ITEMS = (.*?);\nvar EXTRA", src, re.S).group(1))


class LiftEditsTests(unittest.TestCase):
    def test_exact_edits_tail_becomes_the_edit(self) -> None:
        [it] = br.lift_edits([card()])
        self.assertEqual(it["edit"], EDIT)
        self.assertEqual(it["y"], "In <code>session-summary.md</code>, two places.")

    def test_explicit_edit_is_kept_and_y_untouched(self) -> None:
        [it] = br.lift_edits([card(edit="<b>x</b> &rarr; <b>y</b>")])
        self.assertEqual(it["edit"], "<b>x</b> &rarr; <b>y</b>")
        self.assertEqual(it["y"], Y)

    def test_card_without_exact_edits_has_no_edit(self) -> None:
        [it] = br.lift_edits([card(y="Drop the sentence.")])
        self.assertNotIn("edit", it)
        self.assertEqual(it["y"], "Drop the sentence.")

    def test_y_that_is_only_edits_keeps_a_placeholder(self) -> None:
        [it] = br.lift_edits([card(y="<b>Exact edits:</b><br>" + EDIT)])
        self.assertEqual(it["edit"], EDIT)
        self.assertTrue(it["y"])

    def test_input_items_are_not_mutated(self) -> None:
        c = card()
        br.lift_edits([c])
        self.assertEqual(c["y"], Y)
        self.assertNotIn("edit", c)


class GuessTests(unittest.TestCase):
    def test_guess_must_be_a_verdict_on_the_page(self) -> None:
        errs = br.validate({"title": "T", "items": [card(guess="maybe")]})
        self.assertTrue(any("guess" in e for e in errs), errs)

    def test_guess_may_be_an_extra_verdict(self) -> None:
        spec = {"title": "T", "items": [card(guess="chatter")],
                "extraVerdicts": [{"key": "chatter", "label": "Table chatter", "outcome": "Ignored."}]}
        self.assertEqual(br.validate(spec), [])

    def test_guess_is_display_only_never_a_saved_verdict(self) -> None:
        html = br.build({"title": "T", "items": [card(guess="approve", guessWhy="The tape has one.")]})
        state = json.loads(re.search(r'id="state">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(state["decisions"], {})
        [it] = page_items(html)
        self.assertEqual((it["guess"], it["guessWhy"]), ("approve", "The tape has one."))

    def test_read_decisions_does_not_export_the_guess(self) -> None:
        html = br.build({"title": "T", "reviewId": "t:1",
                         "items": [card(guess="approve", guessWhy="why"), card(id="s1-02", guess="reject")]})
        saved = re.sub(r'(id="state">)(.*?)(</script>)',
                       lambda m: m.group(1) + json.dumps({"decisions": {"s1-01": "reject"}, "notes": {},
                                                          "savedAt": "2026-10-19 18:00 UTC", "reviewId": "t:1"})
                       + m.group(3), html, count=1, flags=re.S)
        with tempfile.TemporaryDirectory() as d:
            page, out = Path(d) / "index.html", Path(d) / "decisions.json"
            page.write_text(saved, encoding="utf-8")
            subprocess.run([sys.executable, str(READ), "--html", str(page), "--out", str(out)], check=True,
                           capture_output=True)
            got = json.loads(out.read_text())
        self.assertEqual(got["decisions"], {"s1-01": "reject"})
        self.assertIn("s1-02", got["unmarked"])
        self.assertNotIn("guess", json.dumps(got))


class LayoutTests(unittest.TestCase):
    def test_page_carries_the_lifted_edit(self) -> None:
        [it] = page_items(br.build({"title": "T", "items": [card()]}))
        self.assertEqual(it["edit"], EDIT)

    def test_edit_renders_before_the_rationale(self) -> None:
        src = br.SRC
        self.assertLess(src.index("Proposed edit"), src.index('class="why"'))
        self.assertLess(src.index('class="why"'), src.index('class="outcomes"'))

    def test_no_body_text_below_15px(self) -> None:
        for rule in (".outcome{", ".ev{", ".why{", ".guess{", ".foot{"):
            block = br.CSS[br.CSS.index(rule):]
            size = float(re.search(r"font-size:([\d.]+)px", block[:block.index("}")]).group(1))
            self.assertGreaterEqual(size, 15, rule)


if __name__ == "__main__":
    unittest.main()
