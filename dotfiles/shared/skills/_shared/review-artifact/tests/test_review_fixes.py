#!/usr/bin/env python3
"""Regression tests for the spec 043 review findings (T046): reviewId derivation, the Codex NPC loop,
extra verdicts and picks through normalize(), local chrome escaping, unmarked notes, the group marker,
token substitution order and the shared slug rule.

Run: python3 -m pytest dotfiles/shared/skills/_shared/review-artifact/tests
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
DOTFILES = HERE.parents[3]
FIX = Path(__file__).resolve().parent / "fixtures"
BUILD, READ = HERE / "build_review.py", HERE / "read_decisions.py"
VTT = DOTFILES / "codex/skills/vtt-spell-pass/render_review.py"
sys.path.insert(0, str(HERE))
import build_review  # noqa: E402
import read_decisions  # noqa: E402
import review_ids  # noqa: E402
from serve_review import ReviewConfig, make_server  # noqa: E402

SHA = "cd" * 32
SCHEMA = None
for _p in os.environ.get("PYTHONPATH", "").split(os.pathsep):
    _s = Path(_p) / "pipelines/summary_native/review/schemas/card-decisions.v1.schema.json"
    if _p and _s.is_file():
        SCHEMA = json.loads(_s.read_text(encoding="utf-8"))
        break


def run(*args):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True)


def page_src(html: str) -> str:
    return re.search(r'<script type="text/plain" id="src">(.*?)</script>', html, re.S).group(1)


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Tmp(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)

    def tearDown(self):
        self._t.cleanup()

    def write(self, name: str, obj) -> Path:
        p = self.tmp / name
        p.write_text(json.dumps(obj), encoding="utf-8")
        return p

    def build(self, spec: dict, *extra: str) -> str:
        r = run(BUILD, "--in", self.write("items.json", spec), "--out", self.tmp / "p.html", *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return (self.tmp / "p.html").read_text(encoding="utf-8")


class ReviewIdTests(Tmp):
    """Finding 1 and 9."""

    def test_valid_text_is_unchanged_and_others_get_slug_plus_hash(self):
        self.assertEqual(review_ids.derive_review_id("stage0:ch63"), "stage0:ch63")
        a = review_ids.derive_review_id("vtt-spell-pass:/a b/c d.vtt")
        b = review_ids.derive_review_id("vtt-spell-pass:/a-b/c-d.vtt")
        self.assertRegex(a, review_ids.REVIEW_ID_RE.pattern)
        self.assertNotEqual(a, b)  # same slug, different text: the hash keeps them apart
        self.assertEqual(a, review_ids.derive_review_id("vtt-spell-pass:/a b/c d.vtt"))
        long = review_ids.derive_review_id("x/" * 300)
        self.assertLessEqual(len(long), 128)
        self.assertTrue(review_ids.REVIEW_ID_RE.fullmatch(long))

    def test_vtt_spell_pass_renders_with_a_path_containing_spaces_and_slashes(self):
        queue = {"target_vtt": "/home/gm/My Campaign/sessions/ch 15 – the \"Vault\"/transcript.cleaned.vtt",
                 "session_dir": "/home/gm/My Campaign/sessions/ch 15",
                 "items": [{"id": "tok__canon", "token": "Tok", "canonical": "Canon", "context": "…Tok…", "count": 2}]}
        q = self.write("queue.json", queue)
        r = run(VTT, "--queue", q, "--output", self.tmp / "review.html")
        self.assertEqual(r.returncode, 0, r.stderr)
        state = json.loads(re.search(r'<script type="application/json" id="state">(.*?)</script>',
                                     (self.tmp / "review.html").read_text(encoding="utf-8"), re.S).group(1))
        rid = state["reviewId"]
        self.assertTrue(review_ids.REVIEW_ID_RE.fullmatch(rid), rid)
        self.assertTrue(rid.startswith("vtt-spell-pass:"))
        # the id is a pure function of the path: a second render, and a consumer, derive the same one
        self.assertEqual(rid, review_ids.derive_review_id(f"vtt-spell-pass:{queue['target_vtt']}"))
        # and the export validates against an items file carrying it
        spec = {"reviewId": rid, "items": [{"id": "tok__canon"}]}
        export = {"schemaVersion": 1, "reviewId": rid, "savedAt": "2026-11-12 10:00 UTC",
                  "decisions": {"tok__canon": "approve"}, "notes": {}, "unmarked": []}
        self.assertEqual(read_decisions.normalize(export, spec)["reviewId"], rid)

    def test_batch_validate_rewrites_a_chapter_id_with_a_space(self):
        batch = DOTFILES / "codex/skills/_shared/batch-chapters/batch.py"
        base = self.tmp / "camp" / "summaries"
        ch = base / "Chapter 63"
        (ch / "staged_review").mkdir(parents=True)
        (ch / "session-summary.md").write_text("Old text.", encoding="utf-8")
        (ch / "staged_review/findings_stage1.json").write_text(json.dumps({"findings": [
            {"id": "c1", "disposition": "card", "edits": [{"old": "Old text.", "new": "New.", "count": 1}]}]}))
        items = {"title": "Chapter 63 Stage 1", "reviewId": "stage1:Chapter 63",
                 "items": [{"id": "c1", "t": "T", "y": "Y", "n": "N"}]}
        (ch / "staged_review/review_items_stage1.json").write_text(json.dumps(items))
        cfg = self.write("batch.json", {"campaign": str(self.tmp / "camp"), "summaries": "summaries",
                                        "target": "session-summary.md", "chapters": [{"dir": "Chapter 63"}]})
        env = {**os.environ, "CODEX_HOME": str(DOTFILES / "codex")}
        r = subprocess.run([sys.executable, str(batch), "validate", "--config", str(cfg), "--stage", "stage1"],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        new = json.loads((ch / "staged_review/review_items_stage1.json").read_text())["reviewId"]
        self.assertEqual(new, review_ids.derive_review_id("stage1:Chapter 63"))
        self.assertTrue((ch / "staged_review/review_stage1.html").is_file())

    def test_one_slug_rule_and_the_128_cap(self):
        title = "A very long title: " + "word " * 80
        spec = {"title": title, "items": [{"id": "a", "t": "t", "y": "y", "n": "n"}]}
        page = self.build(spec, "--save", "local")
        state = json.loads(re.search(r'id="state">(.*?)</script>', page, re.S).group(1))
        self.assertLessEqual(len(state["reviewId"]), 128)
        self.assertEqual(state["reviewId"], read_decisions.expected_review_id(spec))
        self.assertEqual(state["reviewId"], review_ids.slug_review_id(title))
        # neither module carries its own copy of the rule any more
        for f in (BUILD, READ):
            self.assertNotRegex(f.read_text(encoding="utf-8"), r're\.sub\(r"\[\^A-Za-z0-9_\.:-\]\+"')


class ExtraVerdictTests(Tmp):
    """Finding 3."""

    SPEC = {"title": "X", "reviewId": "x:1",
            "extraVerdicts": [{"key": "defer", "label": "Defer", "outcome": "Later."}],
            "items": [{"id": "a", "t": "t", "y": "y", "n": "n"},
                      {"id": "b", "t": "t", "y": "y", "n": "n", "picks": ["alpha", "beta"]},
                      {"id": "c", "t": "t", "y": "y", "n": "n"}]}

    def export(self, **kw):
        e = {"schemaVersion": 1, "reviewId": "x:1", "savedAt": "2026-11-12 10:00 UTC",
             "decisions": {"a": "defer", "b": "pick"}, "notes": {}, "unmarked": ["c"],
             "picks": {"b": "beta"}, "extraVerdicts": ["defer"]}
        e.update(kw)
        return e

    def test_normalize_accepts_declared_extras_and_keeps_picks(self):
        n = read_decisions.normalize(self.export(), self.SPEC)
        self.assertEqual(n["decisions"], {"a": "defer", "b": "pick"})
        self.assertEqual(n["picks"], {"b": "beta"})
        self.assertEqual(n["tally"]["defer"], 1)
        self.assertEqual(n["tally"]["pick"], 1)

    def test_normalize_refuses_undeclared_verdicts_and_unoffered_picks(self):
        with self.assertRaises(read_decisions.DecisionError):
            read_decisions.normalize(self.export(decisions={"a": "chatter"}, unmarked=["b", "c"]), self.SPEC)
        with self.assertRaises(read_decisions.DecisionError):
            read_decisions.normalize(self.export(picks={"b": "gamma"}), self.SPEC)
        with self.assertRaises(read_decisions.DecisionError):  # a card that offered no picks cannot be picked
            read_decisions.normalize(self.export(decisions={"a": "pick"}, unmarked=["b", "c"], picks={"a": "z"}),
                                     self.SPEC)

    def test_plain_page_output_is_unchanged(self):
        spec = {"title": "P", "reviewId": "p:1", "items": [{"id": "a", "t": "t", "y": "y", "n": "n"}]}
        n = read_decisions.normalize({"schemaVersion": 1, "reviewId": "p:1", "savedAt": "s",
                                      "decisions": {"a": "approve"}, "notes": {}, "unmarked": []}, spec)
        self.assertEqual(sorted(n), ["decided", "decisions", "discuss", "notes", "reviewId", "savedAt",
                                     "schemaVersion", "tally", "unmarked"])
        self.assertEqual(n["tally"], {"approve": 1, "discuss": 0, "reject": 0})
        with self.assertRaises(read_decisions.DecisionError):
            read_decisions.normalize({"schemaVersion": 1, "reviewId": "p:1", "savedAt": "s",
                                      "decisions": {"a": "defer"}, "notes": {}, "unmarked": []}, spec)

    def test_cli_in_without_items_uses_the_export_declaration(self):
        d = self.write("d.json", self.export())
        r = run(READ, "--in", d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["picks"], {"b": "beta"})
        bad = self.write("bad.json", self.export(decisions={"a": "chatter"}, unmarked=["b", "c"]))
        self.assertEqual(run(READ, "--in", bad).returncode, 2)

    def test_cli_in_with_items(self):
        r = run(READ, "--in", self.write("d.json", self.export()), "--items", self.write("i.json", self.SPEC))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["decisions"], {"a": "defer", "b": "pick"})

    def test_save_to_vm_endpoint_accepts_them(self):
        page = self.tmp / "page.html"
        page.write_text("<html></html>", encoding="utf-8")
        cfg = ReviewConfig(page, self.write("i.json", self.SPEC), self.tmp / "out.json", "tok", self.SPEC)
        server = make_server(cfg, "127.0.0.1", 0)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}{cfg.base_path}decisions"

            def put(body):
                req = urllib.request.Request(url, data=json.dumps(body).encode(), method="PUT",
                                             headers={"Content-Type": "application/json"})
                return urllib.request.urlopen(req)

            self.assertEqual(put(self.export()).status, 200)
            saved = json.loads((self.tmp / "out.json").read_text())
            self.assertEqual(saved["picks"], {"b": "beta"})
            self.assertEqual(saved["decisions"]["a"], "defer")
            with self.assertRaises(urllib.error.HTTPError) as cm:
                put(self.export(decisions={"a": "nope"}, unmarked=["b", "c"]))
            self.assertEqual(cm.exception.code, 422)
        finally:
            server.shutdown()
            server.server_close()
            t.join(timeout=2)

    def test_the_local_page_export_declares_its_extra_verdicts(self):
        src = page_src(self.build(self.SPEC, "--save", "local"))
        self.assertIn("out.extraVerdicts = EXTRA.map", src)
        plain = page_src(self.build({"title": "P", "items": [{"id": "a", "t": "t", "y": "y", "n": "n"}]},
                                    "--save", "local"))
        self.assertIn("if(EXTRA.length) out.extraVerdicts", plain)  # emitted only when there are extras


def card_items(group: bool = True) -> dict:
    items = [
        {"id": "sign", "members": ["sign"], "draftSha256": SHA, "t": "Sign", "y": "Sign.", "n": "Keep.", "ev": "d"},
        {"id": "find", "members": ["find"], "t": "Claim", "y": "Keep.", "n": "Fix.", "ev": "e"},
    ]
    if group:
        items.append({"id": "noise-class:label", "group": "Classified noise", "members": ["n-1", "n-2", "n-3"],
                      "t": "Class", "y": "Keep.", "n": "Fix.", "ev": "3 occurrences"})
    return {"title": "NPC review", "reviewId": "packet-1", "items": items}


class NpcLocalLoopTests(Tmp):
    """Findings 2 and 6: --npc --in --items for a page built with --save local."""

    def export(self, decisions, notes=None, **kw):
        e = {"schemaVersion": 1, "reviewId": "packet-1", "savedAt": "2026-11-12 21:04 UTC",
             "decisions": decisions, "notes": notes or {}, "unmarked": [i for i in ("sign", "find", "noise-class:label")
                                                                         if i not in decisions]}
        e.update(kw)
        return e

    def npc(self, export, items=None, review="npc-review-abc", *extra):
        out = self.tmp / "cards.json"
        r = run(READ, "--npc", "--in", self.write("d.json", export), "--items", self.write("i.json", items or card_items()),
                "--review", review, "--out", out, *extra)
        return r, out

    def test_local_export_to_card_decisions_with_echoes_from_the_items_file(self):
        # the export carries NO members or sha; a tampered one would be ignored
        e = self.export({"sign": "approve", "noise-class:label": "reject"}, {"find": "later"},
                        members={"sign": ["evil"]})
        r, out = self.npc(e)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(out.read_text())
        self.assertEqual(d["packetId"], "packet-1")
        self.assertEqual(d["reviewId"], "npc-review-abc")
        self.assertEqual(d["savedAt"], "2026-11-12 21:04 UTC")
        self.assertEqual(d["cards"]["sign"], {"verdict": "approve", "note": "", "members": ["sign"], "draftSha256": SHA})
        self.assertEqual(d["cards"]["noise-class:label"]["members"], ["n-1", "n-2", "n-3"])
        self.assertNotIn("find", d["cards"])
        if SCHEMA:
            import jsonschema
            jsonschema.validate(d, SCHEMA)
        else:  # minimal structural check when CampaignGenerator is not on PYTHONPATH
            self.assertEqual(sorted(d), ["cards", "packetId", "reviewId", "savedAt", "schemaVersion"])

    def test_stale_or_foreign_exports_are_refused(self):
        r, _ = self.npc(self.export({"sign": "approve"}, reviewId="other"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("reviewId", r.stderr)
        e = self.export({"sign": "approve"})
        e["unmarked"] = ["find"]  # item set differs from the items file
        self.assertEqual(self.npc(e)[0].returncode, 2)
        r, _ = self.npc(self.export({"sign": "approve"}, savedAt=""))
        self.assertEqual(r.returncode, 1)

    def test_in_needs_items(self):
        r = run(READ, "--npc", "--in", self.write("d.json", self.export({"sign": "approve"})), "--review", "x")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--items", r.stderr)

    def test_items_file_with_picks_or_extras_is_refused(self):
        items = card_items()
        items["extraVerdicts"] = [{"key": "defer", "label": "Defer", "outcome": "x"}]
        r, _ = self.npc(self.export({"sign": "approve"}), items)
        self.assertEqual(r.returncode, 2)

    def test_unmarked_card_with_a_note_is_reported_not_dropped(self):
        e = self.export({"sign": "approve"}, {"find": "this one is wrong, see ch 4", "noise-class:label": "hm"})
        r, out = self.npc(e)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(list(json.loads(out.read_text())["cards"]), ["sign"])  # file unchanged by the notes
        self.assertIn("UNMARKED CARDS WITH A NOTE (2)", r.stdout)
        self.assertIn("find: this one is wrong, see ch 4", r.stdout)
        self.assertIn("noise-class:label: hm", r.stdout)
        self.assertIn("1 of 3 cards marked", r.stdout)
        self.assertIn("2 unmarked card(s) carry a note", r.stdout)

    def test_no_unmarked_notes_means_no_heading(self):
        r, _ = self.npc(self.export({"sign": "approve"}, {"sign": "ok"}))
        self.assertNotIn("UNMARKED CARDS", r.stdout)

    def test_unmarked_note_is_reported_on_the_html_path_too(self):
        page = self.tmp / "p.html"
        r = run(BUILD, "--in", self.write("i.json", card_items()), "--out", page)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = page.read_text(encoding="utf-8")
        state = {"decisions": {"sign": "approve"}, "notes": {"find": "careful"}, "picks": {},
                 "savedAt": "2026-11-12 10:00 UTC", "reviewId": "packet-1"}
        saved = self.tmp / "saved.html"
        saved.write_text(re.sub(r'(<script[^>]*id="state"[^>]*>).*?(</script>)',
                                lambda m: m.group(1) + json.dumps(state) + m.group(2), text, flags=re.S),
                         encoding="utf-8")
        r = run(READ, "--npc", "--html", saved, "--review", "r", "--out", self.tmp / "o.json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("find: careful", r.stdout)


class ChromeEscapingTests(Tmp):
    """Finding 5: what the retired Codex builder did is what --save local does."""

    def test_vtt_spell_pass_footer_in_local_mode_matches_the_retired_codex_builder(self):
        vtt = load(VTT, "vtt_render")
        queue = {"target_vtt": "/x/t.vtt", "session_dir": "/x",
                 "items": [{"id": "a", "token": "T", "canonical": "C", "context": "c", "count": 1}],
                 "summary": {"auto_dismissed": [{"token": "um", "count": 1, "reason": "plain <word>"}]}}
        spec = vtt.shared_spec(queue)
        self.assertIn("<b>Auto-dismissed", spec["footer"])  # the adapter passes HTML...
        src = page_src(vtt.load_shared_builder().build(spec, save="local"))
        # ...and the retired builder's page script did esc(FOOTER) / esc(LEDE) / esc(EYEBROW): text, not markup.
        footer = re.search(r"var FOOTER = (.*?);\n", src).group(1)
        self.assertNotIn("<b>", footer)
        self.assertIn("&lt;b&gt;Auto-dismissed", footer)
        self.assertIn("&lt;code&gt;um&lt;/code&gt;", footer)
        art = page_src(vtt.load_shared_builder().build(spec, save="artifact"))
        self.assertIn("\\u003cb>Auto-dismissed", re.search(r"var FOOTER = (.*?);\n", art).group(1))


class GroupMarkerTests(Tmp):
    """Finding 7."""

    def test_group_and_member_count_are_rendered_only_when_present(self):
        with_group = page_src(self.build(card_items(), "--save", "local"))
        self.assertIn("'Applies to ' + it.members.length + ' items'", with_group)
        self.assertIn(".group{", self.build(card_items()))
        plain = self.build(card_items(group=False))
        self.assertNotIn("Applies to", plain)
        self.assertNotIn(".group{", plain)

    def test_a_page_without_members_is_byte_identical_to_the_golden(self):
        html = self.build(json.loads((FIX / "golden_items.json").read_text()))
        self.assertEqual(html, (FIX / "golden_artifact.html").read_text(encoding="utf-8"))

    def test_marker_text_in_a_stub_dom(self):
        import shutil
        if not shutil.which("node"):
            self.skipTest("node not installed")
        src = page_src(self.build(card_items(), "--save", "local"))
        h = self.tmp / "h.js"
        h.write_text(
            "var els={}; function el(){return {textContent:'',innerHTML:'',value:'',addEventListener(){},disabled:false};}\n"
            "var document={getElementById(id){ if(!els[id]) els[id]=el(); if(id==='state') els[id].textContent="
            "JSON.stringify({decisions:{},notes:{},savedAt:null,reviewId:'packet-1'}); return els[id]; },"
            "querySelector(){return null;},querySelectorAll(){return [];}};\n"
            "new Function('document'," + json.dumps(src) + ")(document);\n"
            "console.log(els.app.innerHTML);\n")
        r = subprocess.run(["node", str(h)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Classified noise &middot; Applies to 3 items", r.stdout)
        self.assertEqual(r.stdout.count("Applies to"), 1)  # the single-member cards carry none


class TokenOrderTests(Tmp):
    """Finding 8: a value is never re-scanned for template tokens."""

    TEXT = "literal __OUTPUT_NAME__ and __ITEMS__ and __STATE__ and __SRC__ in user text"

    def spec(self, **kw):
        s = {"title": "T __TITLE__ __CSS__", "reviewId": "__SRC__:x", "outputName": "out.json",
             "eyebrow": "e __OUTPUT_NAME__", "lede": "l __ITEMS__",
             "items": [{"id": "a", "t": self.TEXT, "y": self.TEXT, "n": "n", "ev": self.TEXT}]}
        s.update(kw)
        return s

    def test_tokens_in_user_text_survive_in_both_modes(self):
        for mode in ("artifact", "local"):
            html = self.build(self.spec(), "--save", mode)
            items = json.loads(re.search(r"var ITEMS = (\[.*?\]);\n", page_src(html), re.S).group(1)
                               .replace("\\u003c", "<"))
            self.assertEqual(items[0]["t"], self.TEXT, mode)
            self.assertEqual(items[0]["ev"], self.TEXT, mode)
            self.assertIn("var TITLE = \"T __TITLE__ __CSS__\";", page_src(html), mode)
            state = json.loads(re.search(r'id="state">(.*?)</script>', html, re.S).group(1))
            self.assertEqual(state["reviewId"], "__SRC__:x", mode)
        local = page_src(self.build(self.spec(), "--save", "local"))
        self.assertIn('var OUTPUT_NAME = "out.json";', local)  # the real one is still filled


class DeadCodeTests(unittest.TestCase):
    """Finding 10."""

    def test_raw_decisions_is_gone_and_items_parse_once(self):
        text = READ.read_text(encoding="utf-8")
        self.assertNotIn("raw_decisions", text)
        self.assertNotIn("def page_item_ids", text)
        self.assertNotIn("def page_picks", text)
        self.assertEqual(text.count("def page_items"), 1)


class DocTests(unittest.TestCase):
    """Finding 4."""

    def test_npc_loop_section_appears_once_and_names_both_transports(self):
        doc = (DOTFILES / "shared/skills/grounding-refresh/references/review-and-apply.md").read_text(encoding="utf-8")
        self.assertEqual(doc.count("## The NPC verification review loop (card contract)"), 1)
        self.assertNotIn("~/.codex", doc.split("## The NPC verification review loop")[1].split("\n## ")[0].replace(
            "${CODEX_HOME:-~/.codex}", ""))
        for needle in ("--html saved.html", "--save local", "--in decisions.json --items items.json"):
            self.assertIn(needle, doc)


if __name__ == "__main__":
    unittest.main()
