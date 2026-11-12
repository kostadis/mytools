#!/usr/bin/env python3
"""npc_review_items.py shim + the NPC loop against a real CampaignGenerator review (spec 043 T039).

The CampaignGenerator half needs a checkout that has `review cards`: run with
PYTHONPATH=<CampaignGenerator worktree>. Without one those tests skip. A wrapper named
`summary_native` is put on PATH that runs that checkout, never whatever is installed.

Run: PYTHONPATH=<CG> python3 -m pytest dotfiles/shared/skills/_shared/review-artifact/tests
"""

from __future__ import annotations

import html as htmllib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
SHIM, BUILD, READ = HERE / "npc_review_items.py", HERE / "build_review.py", HERE / "read_decisions.py"
sys.path.insert(0, str(HERE))
import npc_review_items  # noqa: E402
import read_decisions  # noqa: E402


def cg_checkout() -> Path | None:
    for p in os.environ.get("PYTHONPATH", "").split(os.pathsep):
        if p and (Path(p) / "tests" / "_custody_fixture.py").is_file() \
                and (Path(p) / "pipelines/summary_native/review/cards.py").is_file():
            return Path(p).resolve()
    return None


CG = cg_checkout()
SKIP = "set PYTHONPATH to a CampaignGenerator checkout with `review cards` (spec 043)"

FIXTURE_SCRIPT = """
import json, sys, tempfile
from pathlib import Path
from tests import _custody_fixture as fx
t = Path(sys.argv[1])
f = fx.build(t, deterministic=True)
print(json.dumps({"root": str(f.root), "review_id": f.review_id}))
"""


def page_state_saved(page: Path, out: Path, decisions: dict, notes: dict | None = None) -> Path:
    """What the artifact does on Save: the page with its state block filled in."""
    text = page.read_text(encoding="utf-8")
    old = json.loads(re.search(r'<script type="application/json" id="state">(.*?)</script>', text, re.S).group(1))
    state = {"decisions": decisions, "notes": notes or {}, "picks": {}, "savedAt": "2026-11-12 21:04 UTC",
             "reviewId": old["reviewId"]}
    out.write_text(re.sub(r'(<script[^>]*id="state"[^>]*>).*?(</script>)',
                          lambda m: m.group(1) + json.dumps(state) + m.group(2), text, flags=re.S), encoding="utf-8")
    return out


class ShimUnitTests(unittest.TestCase):
    """No CampaignGenerator needed: the card -> item mapping and the refusals."""

    CARD = {
        "id": "npc-signoff-x", "kind": "signoff", "npc": "X", "title": "Sign off <b>X</b>",
        "body": "<script>alert(1)</script> & draft", "approveMeans": "Sign <i>this</i>.",
        "rejectMeans": "Keep.", "draftSha256": "cd" * 32, "previousDiscussion": "Previously discussed by GM: <u>why</u>",
        "evidence": [{"source": "docs/<x>.md", "anchor": "L1", "excerpt": "<img src=x>", "missingReason": None}],
        "members": [{"itemId": "npc-signoff-x", "action": "signoff_npc_draft", "itemRevision": 1,
                     "reviewDigest": "d", "expectedDecisionRevision": 0, "line": None}],
    }

    def test_every_string_is_escaped_and_extras_pass_through(self):
        it = npc_review_items.to_item(self.CARD)
        self.assertEqual(it["t"], htmllib.escape(self.CARD["title"]))
        self.assertEqual(it["y"], "Sign &lt;i&gt;this&lt;/i&gt;.")
        for raw in ("<script>", "<img", "<u>", "docs/<x>"):
            self.assertNotIn(raw, it["ev"])
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; draft", it["ev"])
        self.assertIn("&lt;img src=x&gt;", it["ev"])
        self.assertEqual(it["members"], ["npc-signoff-x"])
        self.assertEqual(it["draftSha256"], "cd" * 32)

    def test_previous_discussion_is_shown_escaped_outside_the_body(self):
        it = npc_review_items.to_item(self.CARD)
        self.assertIn("Previously discussed by GM: &lt;u&gt;why&lt;/u&gt;", it["ev"])
        card = dict(self.CARD, previousDiscussion=None)
        self.assertNotIn("Previously discussed", npc_review_items.to_item(card)["ev"])

    def test_noise_class_card_gets_a_group(self):
        it = npc_review_items.to_item(dict(self.CARD, kind="noise_class", draftSha256=None))
        self.assertEqual(it["group"], "Classified noise")
        self.assertNotIn("draftSha256", it)

    def test_dropped_flags_are_refused(self):
        for flag in ("--allow-stale", "--undecided"):
            r = subprocess.run([sys.executable, str(SHIM), "/x/docs/reviews/r", "--out", "/tmp/nope.json", flag],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, flag)
            self.assertIn(flag, r.stderr)

    def test_missing_summary_native_fails_clearly(self):
        r = subprocess.run([sys.executable, str(SHIM), "/x/docs/reviews/r", "--out", "/tmp/nope.json"],
                           capture_output=True, text=True, env={"PATH": "/nonexistent", "HOME": "/nonexistent"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("summary_native", r.stderr)


class StaticNoStoreReadTests(unittest.TestCase):
    """SC-006: no kit .py reads the review store."""

    def test_no_kit_python_file_names_the_store(self):
        needles = ("manifest.json", '"items"', "'items'", "events/", "docs/reviews")
        for p in sorted(HERE.rglob("*.py")):
            if p.name == "test_npc_shim.py":
                continue
            text = p.read_text(encoding="utf-8")
            for n in needles:
                if n in ('"items"', "'items'"):
                    # the only legitimate "items" is the items-file JSON key; a store read joins it to a path
                    self.assertFalse(re.search(r"""/\s*["']items["']|["']items["']\s*/|["']items/""", text),
                                     f"{p.name}: an items path join")
                    continue
                self.assertNotIn(n, text, f"{p.name} mentions {n}")


@unittest.skipUnless(CG, SKIP)
class NpcLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._t.name)
        env = dict(os.environ, PYTHONPATH=str(CG))
        r = subprocess.run([sys.executable, "-c", FIXTURE_SCRIPT, str(cls.tmp / "fx")], cwd=CG, env=env,
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise unittest.SkipTest(f"cannot build the CampaignGenerator fixture: {r.stderr[-300:]}")
        info = json.loads(r.stdout.strip().splitlines()[-1])
        cls.root, cls.review_id = Path(info["root"]), info["review_id"]
        cls.bin = cls.tmp / "bin"
        cls.bin.mkdir()
        wrapper = cls.bin / "summary_native"
        wrapper.write_text(f'#!/bin/sh\nPYTHONPATH="{CG}" exec "{sys.executable}" '
                           f'-m pipelines.summary_native.cli "$@"\n')
        wrapper.chmod(0o755)
        cls.env = dict(os.environ, PATH=f"{cls.bin}{os.pathsep}{os.environ['PATH']}", PYTHONPATH=str(CG))

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    def sh(self, *cmd, **kw):
        return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, env=self.env, **kw)

    def shim(self, out: Path, *extra):
        return self.sh(sys.executable, SHIM, self.root / "docs/reviews" / self.review_id, "--out", out, *extra)

    def packet(self):
        out = self.tmp / "ref.json"
        r = self.sh("summary_native", "review", "cards", "export", self.review_id, "--campaign-dir", self.root,
                    "--out", out, "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(out.read_text(encoding="utf-8"))

    def items(self):
        out = self.tmp / "items.json"
        r = self.shim(out)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(out.read_text(encoding="utf-8")), out

    def test_shim_cards_equal_the_packets(self):
        pk, (doc, _) = self.packet(), self.items()
        self.assertEqual(doc["reviewId"], pk["packetId"])
        self.assertEqual([i["id"] for i in doc["items"]], [c["id"] for c in pk["cards"]])
        for it, c in zip(doc["items"], pk["cards"]):
            self.assertEqual(it["t"], htmllib.escape(c["title"]))
            self.assertEqual(it["y"], htmllib.escape(c["approveMeans"]))
            self.assertEqual(it["n"], htmllib.escape(c["rejectMeans"]))
            self.assertEqual(it["members"], [m["itemId"] for m in c["members"]])
            self.assertEqual(it.get("draftSha256"), c["draftSha256"])

    def test_filters_map_to_export_flags(self):
        pk = self.packet()
        want = pk["cards"][0]["id"]
        out = self.tmp / "one.json"
        r = self.shim(out, "--ids", want)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([i["id"] for i in json.loads(out.read_text())["items"]], [want])
        r = self.shim(out, "--action", "signoff_npc_draft")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(all(i.get("draftSha256") for i in json.loads(out.read_text())["items"]))

    def build_page(self):
        doc, path = self.items()
        page = self.tmp / "page.html"
        b = self.sh(sys.executable, BUILD, "--in", path, "--out", page)
        self.assertEqual(b.returncode, 0, b.stderr)
        return page, doc

    def test_campaign_markup_arrives_escaped_and_extras_reach_the_page(self):
        page, doc = self.build_page()
        text = page.read_text(encoding="utf-8")
        # the draft's own header comment is HTML-shaped campaign text
        self.assertNotIn("<!-- summary_native npc draft", text)
        self.assertIn("&lt;!-- summary_native npc draft", text.replace("\\u003c", "<"))
        by_id = {i["id"]: i for i in read_decisions.page_items(text)}
        for it in doc["items"]:
            self.assertEqual(by_id[it["id"]]["members"], it["members"])
            self.assertEqual(by_id[it["id"]].get("draftSha256"), it.get("draftSha256"))
        self.assertTrue(any(i.get("draftSha256") for i in by_id.values()))

    def test_saved_page_to_decide_plan_end_to_end(self):
        page, doc = self.build_page()
        sign = next(i for i in doc["items"] if i.get("draftSha256"))
        finding = next(i for i in doc["items"] if not i.get("draftSha256"))
        saved = page_state_saved(page, self.tmp / "saved.html",
                                 {sign["id"]: "approve", finding["id"]: "approve"}, {finding["id"]: "fine as is"})
        dfile = self.tmp / "d.json"
        r = self.sh(sys.executable, READ, "--npc", "--html", saved, "--review", self.review_id, "--out", dfile)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(dfile.read_text(encoding="utf-8"))
        self.assertEqual(sorted(d["cards"]), sorted([sign["id"], finding["id"]]))
        self.assertEqual(d["cards"][sign["id"]]["draftSha256"], sign["draftSha256"])
        self.assertEqual(d["packetId"], doc["reviewId"])

        import jsonschema
        schema = json.loads((CG / "pipelines/summary_native/review/schemas/card-decisions.v1.schema.json").read_text())
        jsonschema.validate(d, schema)

        r = self.sh("summary_native", "review", "cards", "decide", self.review_id, "--decisions", dfile,
                    "--reviewer", "GM", "--campaign-dir", self.root, "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        env = json.loads(r.stdout)
        self.assertEqual(env["code"], "REVIEW_CARDS_PLAN")
        counts = env["data"]["counts"]
        self.assertEqual((counts["record"], counts["refused"], counts["noop"], counts["supersede"]), (2, 0, 0, 0))
        marked = {c["cardId"]: c["state"] for c in env["data"]["cards"] if c["verdict"]}
        self.assertEqual(marked, {sign["id"]: "applied", finding["id"]: "applied"})
        self.__class__.last_decisions = d  # for the report


if __name__ == "__main__":
    unittest.main()
