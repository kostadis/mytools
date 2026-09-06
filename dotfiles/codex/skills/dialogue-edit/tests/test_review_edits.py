"""Offline invariant tests; synthetic rulings here are not campaign approvals."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
MODULE = SKILL / "scripts" / "review_edits.py"
spec = importlib.util.spec_from_file_location("dialogue_review", MODULE)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.session = self.root / "session"
        self.session.mkdir()
        self.draft = self.session / "narration" / "scene_01.md"
        self.draft.parent.mkdir()
        self.original = '### Narrator\r\n\r\n“I can… can,” I say.\r\n\r\n“At the ravine?”\r\n\r\n“over. Yeah”\r\n'
        self.draft.write_bytes(self.original.encode())
        self.source = self.session / "scene_extractions_smoothed" / "01.md"
        self.source.parent.mkdir()
        self.source.write_text('Speaker: “I can… can,”\nSpeaker: “At the ravine?”\nSpeaker: “over. Yeah”\n')
        self.voice = self.root / "voice.md"
        self.voice.write_text("Preserve questions, expressive pauses, and radio play.\n")
        self.proposals = self.session / "proposals.json"
        self.run = self.session / "dialogue_edit" / "scene01-r1"
        self.edits = [
            self.edit("s1-copy", "I can… can", "I can", "I can… can"),
            self.edit("s1-question", "At the ravine?", "At the ravine.", "At the ravine?"),
            self.edit("s1-radio", "over. Yeah", "over.", "over. Yeah"),
        ]
        self.inputs = {p: p.read_bytes() for p in (self.draft, self.source, self.voice)}

    def edit(self, eid, before, after, quote):
        return {"id": eid, "before": before, "after": after, "scope": "dialogue",
                "support": "supported", "reason": "Synthetic test proposal; the GM must judge it.",
                "evidence": [{"path": str(self.source), "quote": quote}]}

    def prepare(self, edits=None):
        self.proposals.write_text(json.dumps({"scene": "Test scene", "edits": self.edits if edits is None else edits}))
        return review.prepare(self.session, self.draft, self.source, [self.voice], self.proposals, self.run)

    def decisions(self, choices=None, **extra):
        record = review.read_json(self.run / "review.json")
        payload = {"schemaVersion": 1, "reviewId": record["reviewId"], "savedAt": "synthetic test only",
                   "decisions": choices if choices is not None else {"s1-copy": "approve", "s1-question": "reject"}}
        payload.update(extra)
        path = self.session / "decisions.json"
        path.write_text(json.dumps(payload))
        return path

    def assert_inputs_unchanged(self):
        for path, data in self.inputs.items():
            self.assertEqual(path.read_bytes(), data)

    def test_prepare_preserves_inputs_and_full_candidate(self):
        result = self.prepare()
        self.assertEqual(result["proposals"], 3)
        self.assert_inputs_unchanged()
        self.assertEqual((self.run / "original.md").read_bytes(), self.inputs[self.draft])
        candidate = (self.run / "candidate.md").read_bytes().decode()
        self.assertIn("I can", candidate)
        self.assertIn("At the ravine.", candidate)  # Candidate is not approved.
        self.assertFalse((self.run / "applied").exists())

    def test_mixed_decisions_exact_application_and_newlines(self):
        self.prepare()
        decisions = self.decisions()
        result, _ = review.apply_review(self.run, decisions, "r1", write=False)
        self.assertEqual(result["status"], "dry_run")
        self.assertFalse((self.run / "applied").exists())
        result, _ = review.apply_review(self.run, decisions, "r1", write=True)
        self.assertEqual(result["status"], "applied_partial")
        self.assertEqual(result["unresolved"], ["s1-radio"])
        self.assertEqual(Path(result["output"]).read_bytes(), self.original.replace("I can… can", "I can").encode())
        self.assert_inputs_unchanged()

    def test_no_approval_does_not_write_revision(self):
        self.prepare()
        result, _ = review.apply_review(self.run, self.decisions({}), "r1", write=True)
        self.assertEqual(result["status"], "no_approved_changes")
        self.assertFalse((self.run / "applied").exists())

    def test_no_proposals_has_no_invalid_empty_page(self):
        result = self.prepare([])
        self.assertEqual(result["status"], "no_changes_proposed")
        self.assertFalse((self.run / "review_page.json").exists())
        self.assert_inputs_unchanged()

    def test_each_stale_input_refuses_before_output(self):
        self.prepare()
        decisions = self.decisions()
        for path in self.inputs:
            with self.subTest(path=path):
                path.write_bytes(self.inputs[path] + b" changed")
                with self.assertRaisesRegex(review.Refusal, "Stale input"):
                    review.apply_review(self.run, decisions, "r1", write=True)
                self.assertFalse((self.run / "applied").exists())
                path.write_bytes(self.inputs[path])

    def test_changed_candidate_refuses(self):
        self.prepare()
        decisions = self.decisions()
        (self.run / "candidate.md").write_text("Unreviewed replacement")
        with self.assertRaisesRegex(review.Refusal, "Candidate differs"):
            review.apply_review(self.run, decisions, "r1", write=True)

    def test_mutated_proposals_cannot_reuse_old_approval(self):
        self.prepare()
        decisions = self.decisions()
        path = self.run / "review.json"
        obj = review.read_json(path)
        obj["payload"]["edits"][0]["after"] = "I perform a new action"
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(review.Refusal, "Review changed"):
            review.apply_review(self.run, decisions, "r1", write=True)
        # Recomputed identity still does not authorize reuse of the old decision.
        obj["reviewId"] = "dialogue-edit:" + review.digest(review.encoded(obj["payload"]))
        path.write_text(json.dumps(obj))
        (self.run / "candidate.md").write_bytes(review.render(self.original, obj["payload"]["edits"]).encode())
        with self.assertRaisesRegex(review.Refusal, "different proposal set"):
            review.apply_review(self.run, decisions, "r1", write=True)

    def test_invalid_decisions_and_duplicate_keys_refuse(self):
        self.prepare()
        for choices, extra in [({"foreign": "approve"}, {}), ({"s1-copy": "accept"}, {}),
                               ({"s1-copy": "approve"}, {"unmarked": []}),
                               ({"s1-copy": "approve"}, {"notes": {"foreign": "note"}})]:
            with self.subTest(choices=choices, extra=extra):
                with self.assertRaises(review.Refusal):
                    review.apply_review(self.run, self.decisions(choices, **extra), "r1", write=True)
        path = self.session / "bad.json"
        path.write_text('{"decisions": {}, "decisions": {"x": "approve"}}')
        with self.assertRaisesRegex(review.Refusal, "Duplicate JSON"):
            review.read_json(path)
        self.assertFalse((self.run / "applied").exists())

    def test_unresolved_and_out_of_scope_approval_refuse(self):
        self.edits[0]["support"] = "unresolved"
        self.edits[1]["scope"] = "out-of-scope"
        self.prepare()
        for eid in ["s1-copy", "s1-question"]:
            with self.subTest(eid=eid), self.assertRaisesRegex(review.Refusal, "unresolved evidence or out-of-scope"):
                review.apply_review(self.run, self.decisions({eid: "approve"}), "r1", write=True)
        self.assertFalse((self.run / "applied").exists())

    def test_overlapping_ambiguous_and_unanchored_proposals_refuse(self):
        for edits in [self.edits + [dict(self.edits[0], id="overlap")],
                      [dict(self.edits[0], evidence=[])],
                      [dict(self.edits[0], before="absent")],
                      [dict(self.edits[0], before="“", after="'", evidence=self.edits[0]["evidence"])]]:
            with self.subTest(edits=edits), self.assertRaises(review.Refusal):
                self.prepare(edits)
            self.assertFalse(self.run.exists())

    def test_exact_offset_disambiguates_repeated_text(self):
        edit = self.edit("punct", "“", "‘", "At the ravine?")
        edit["start"] = self.original.index("“At")
        self.prepare([edit])
        result, _ = review.apply_review(self.run, self.decisions({"punct": "approve"}), "r1", write=True)
        expected = self.original[:edit["start"]] + "‘" + self.original[edit["start"] + 1:]
        self.assertEqual(Path(result["output"]).read_bytes(), expected.encode())

    def test_existing_runs_and_revisions_are_never_overwritten(self):
        self.prepare()
        old = (self.run / "review.json").read_bytes()
        with self.assertRaisesRegex(review.Refusal, "already exists"):
            self.prepare()
        self.assertEqual((self.run / "review.json").read_bytes(), old)
        decisions = self.decisions()
        result, _ = review.apply_review(self.run, decisions, "r1", write=True)
        before = Path(result["output"]).read_bytes()
        with self.assertRaisesRegex(review.Refusal, "already exists"):
            review.apply_review(self.run, decisions, "r1", write=True)
        self.assertEqual(Path(result["output"]).read_bytes(), before)

    def test_protected_and_symlinked_destinations_refuse(self):
        for target in [self.draft.parent / "bad", self.source.parent / "bad"]:
            with self.subTest(target=target), self.assertRaises(review.Refusal):
                review.run_path(self.session, target, new=True)
        parent = self.session / "dialogue_edit"
        parent.symlink_to(self.source.parent, target_is_directory=True)
        with self.assertRaisesRegex(review.Refusal, "symlink"):
            self.prepare()
        parent.unlink()
        self.prepare()
        (self.run / "applied").symlink_to(self.draft.parent, target_is_directory=True)
        with self.assertRaisesRegex(review.Refusal, "symlink"):
            review.apply_review(self.run, self.decisions(), "r1", write=True)
        self.assert_inputs_unchanged()

    def test_shared_page_and_cli_round_trip(self):
        self.edits[0]["reason"] = "Keep literal <script> & </script> harmless in evidence"
        self.prepare()
        page = self.run / "review.html"
        builder = SKILL.parent / "_shared" / "review-page" / "build_review.py"
        subprocess.run([sys.executable, str(builder), "--in", str(self.run / "review_page.json"),
                        "--out", str(page)], check=True, capture_output=True, text=True)
        self.assertIn("&lt;script&gt;", page.read_text())
        decisions = self.decisions(unmarked=["s1-radio"], discuss=[], notes={})
        proc = subprocess.run([sys.executable, str(MODULE), "apply", "--run-dir", str(self.run),
                               "--decisions", str(decisions), "--revision", "cli-r1"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse((self.run / "applied").exists())
        proc = subprocess.run([sys.executable, str(MODULE), "apply", "--run-dir", str(self.run),
                               "--decisions", str(decisions), "--revision", "cli-r1", "--write"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "applied_partial")

    def test_symlink_run_and_malformed_decisions_refuse(self):
        self.prepare()
        decisions = self.decisions()
        alias = self.run.parent / "alias"
        alias.symlink_to(self.run, target_is_directory=True)
        with self.assertRaisesRegex(review.Refusal, "Run directory cannot be a symlink"):
            review.apply_review(alias, decisions, "r1", write=True)
        decisions.write_text("[]")
        proc = subprocess.run([sys.executable, str(MODULE), "apply", "--run-dir", str(self.run),
                               "--decisions", str(decisions), "--revision", "r1", "--write"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("REFUSED: Decision record must be an object", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertFalse((self.run / "applied").exists())


if __name__ == "__main__":
    unittest.main()
