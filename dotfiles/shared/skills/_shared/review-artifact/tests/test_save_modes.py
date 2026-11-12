#!/usr/bin/env python3
"""build_review.py --save artifact|local (spec 043 T034).

`--save artifact` must stay byte-identical to the pre-change builder: the
fixture golden_artifact.html was produced by the script before --save existed.
Run: python3 -m pytest dotfiles/shared/skills/_shared/review-artifact/tests
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
FIX = Path(__file__).resolve().parent / "fixtures"
BUILD = HERE / "build_review.py"


def build(tmp: Path, *extra: str, items: Path = FIX / "golden_items.json") -> str:
    out = tmp / "page.html"
    r = subprocess.run([sys.executable, str(BUILD), "--in", str(items), "--out", str(out), *extra],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return out.read_text(encoding="utf-8")


def page_src(html: str) -> str:
    return re.search(r'<script type="text/plain" id="src">(.*?)</script>', html, re.S).group(1)


class SaveModeTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)

    def tearDown(self):
        self._t.cleanup()

    def test_artifact_default_is_byte_identical_to_pre_change_output(self):
        golden = (FIX / "golden_artifact.html").read_text(encoding="utf-8")
        self.assertEqual(build(self.tmp), golden)
        self.assertEqual(build(self.tmp, "--save", "artifact"), golden)

    def test_local_has_the_standalone_save_surface(self):
        html = build(self.tmp, "--save", "local")
        src = page_src(html)
        for needle in ("Copy output", "Save output", "Save to VM", "codex-review-save",
                       "method:'PUT'", "new URL('decisions'", "unmarked"):
            self.assertIn(needle, src)
        self.assertNotIn("window.claude", html)
        self.assertNotIn("api.publish", html)
        self.assertNotIn("fonts.googleapis.com/css2", html.split('<style id="css">')[0])

    def test_local_output_name_comes_from_the_spec(self):
        spec = json.loads((FIX / "golden_items.json").read_text())
        spec["outputName"] = "rulings-7.json"
        p = self.tmp / "named.json"
        p.write_text(json.dumps(spec))
        self.assertIn('var OUTPUT_NAME = "rulings-7.json";', page_src(build(self.tmp, "--save", "local", items=p)))
        self.assertIn('var OUTPUT_NAME = "decisions.json";', page_src(build(self.tmp, "--save", "local")))

    def test_bad_output_name_is_refused(self):
        spec = json.loads((FIX / "golden_items.json").read_text())
        spec["outputName"] = "../x.json"
        p = self.tmp / "bad.json"
        p.write_text(json.dumps(spec))
        r = subprocess.run([sys.executable, str(BUILD), "--in", str(p), "--out", str(self.tmp / "o.html"),
                            "--save", "local"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("outputName", r.stderr)

    def test_unknown_save_mode_is_refused(self):
        r = subprocess.run([sys.executable, str(BUILD), "--in", str(FIX / "golden_items.json"),
                            "--out", str(self.tmp / "o.html"), "--save", "vm"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_local_export_shape_runs_in_a_stub_dom(self):
        src = page_src(build(self.tmp, "--save", "local"))
        harness = self.tmp / "h.js"
        harness.write_text(
            "var els = {};\n"
            "function el(){ return {textContent:'', innerHTML:'', addEventListener(){}, disabled:false}; }\n"
            "var document = {getElementById(id){ if(!els[id]) els[id]=el(); if(id==='state') els[id].textContent="
            "JSON.stringify({decisions:{},notes:{},savedAt:null,reviewId:'golden:1'}); return els[id]; },\n"
            "  querySelector(){ return null; }, querySelectorAll(){ return []; }};\n"
            "var fn = new Function('document', " + json.dumps(src + "\nreturn {output:output,state:state};") + ");\n"
            "var p = fn(document);\n"
            "p.state.decisions['g-1']='approve'; p.state.decisions['g-2']='pick'; p.state.picks['g-2']='beta';\n"
            "p.state.notes['g-1']='why';\n"
            "console.log(JSON.stringify(p.output()));\n")
        r = subprocess.run(["node", str(harness)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["schemaVersion"], 1)
        self.assertEqual(out["reviewId"], "golden:1")
        self.assertEqual(out["decisions"], {"g-1": "approve", "g-2": "pick"})
        self.assertEqual(out["picks"], {"g-2": "beta"})
        self.assertEqual(out["notes"], {"g-1": "why"})
        self.assertEqual(out["unmarked"], ["noise-class:label"])
        self.assertEqual(out["decided"], 2)
        self.assertEqual(out["tally"]["approve"], 1)


if __name__ == "__main__":
    unittest.main()
