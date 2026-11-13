#!/usr/bin/env python3
"""Tests for corpus_files.py — the mneme consumer-obligation helper (mytools#87).

A fake `mneme` (via MNEME_BIN) stands in for the real one, so the tests pin the contract:
refuse on non-zero / invalid / undeclared kind, never glob, read only files[].path.

Run: python3 -m pytest dotfiles/claude/skills/_shared/corpus/tests
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / "corpus_files.py"


class CorpusFilesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / "camp"
        (self.root / ".mneme").mkdir(parents=True)
        (self.root / "docs").mkdir()
        # A file that exists but is NOT in the TOC: the helper must never list it.
        (self.root / "docs" / "stray.md").write_text("x")
        self.fake = base / "fake_mneme.py"
        self.argv_log = base / "argv.json"
        self.payload = base / "payload.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _fake(self, *, rc: int = 0, stdout: dict | None = None, stderr: str = "") -> None:
        self.payload.write_text(json.dumps({"rc": rc, "stdout": stdout, "stderr": stderr}))
        self.fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\n"
            f"open({str(self.argv_log)!r},'w').write(json.dumps(sys.argv[1:]))\n"
            f"p=json.load(open({str(self.payload)!r}))\n"
            "if p['stdout'] is not None: print(json.dumps(p['stdout']))\n"
            "sys.stderr.write(p['stderr'])\n"
            "sys.exit(p['rc'])\n"
        )
        self.fake.chmod(0o755)

    def _run(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        env = {**os.environ, "MNEME_BIN": str(self.fake)}
        return subprocess.run(
            [sys.executable, str(HELPER), *args],
            cwd=cwd or self.root, env=env, capture_output=True, text=True,
        )

    @staticmethod
    def _toc(kinds: dict, valid: bool = True) -> dict:
        return {"schema": 1, "campaign": "camp", "valid": valid, "findings": [], "kinds": kinds}

    def test_lists_only_toc_paths_absolute_with_trust(self) -> None:
        self._fake(stdout=self._toc({"grounding": {"trust": "authoritative", "files": [
            {"path": "docs/world_state.md"}, {"path": "docs/party.md"}]}}))
        r = self._run("grounding")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), [
            f"grounding\tauthoritative\t{self.root / 'docs/world_state.md'}",
            f"grounding\tauthoritative\t{self.root / 'docs/party.md'}",
        ])
        self.assertNotIn("stray.md", r.stdout)

    def test_passes_name_dir_kind_json(self) -> None:
        self._fake(stdout=self._toc({"party": {"trust": "authoritative", "files": []}}))
        self._run("party", cwd=self.root / "docs")  # from a subdirectory
        argv = json.loads(self.argv_log.read_text())
        self.assertEqual(argv, ["corpus", "toc", "camp", "--dir", str(self.root.resolve()),
                                "--kind", "party", "--json"])

    def test_declared_empty_kind_is_not_a_refusal(self) -> None:
        self._fake(stdout=self._toc({"party": {"trust": "authoritative", "files": []}}))
        r = self._run("party")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "# party: declared, 0 files")

    def test_refuses_on_mneme_nonzero(self) -> None:
        self._fake(rc=1, stderr="error: campaign declares no corpus (.mneme/corpus.yaml is absent)")
        r = self._run("grounding")
        self.assertEqual(r.returncode, 2)
        self.assertIn("REFUSE:", r.stderr)
        self.assertIn("declares no corpus", r.stderr)
        self.assertEqual(r.stdout, "")

    def test_refuses_invalid(self) -> None:
        self._fake(stdout=self._toc({"grounding": {"files": [{"path": "docs/x.md"}]}}, valid=False))
        r = self._run("grounding")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not valid", r.stderr)
        self.assertEqual(r.stdout, "")

    def test_refuses_undeclared_kind_even_if_mneme_exits_zero(self) -> None:
        self._fake(stdout=self._toc({"party": {"files": []}}))
        r = self._run("grounding")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not declared", r.stderr)

    def test_one_bad_kind_refuses_the_whole_call(self) -> None:
        self._fake(rc=1, stderr="error: kind 'lore' is not declared for this campaign")
        r = self._run("grounding", "lore")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stdout, "")

    def test_root_walk_stops_below_home(self) -> None:
        sys.path.insert(0, str(HELPER.parent))
        import corpus_files  # noqa: E402
        fake_home = Path(self.tmp.name) / "home"
        (fake_home / ".mneme").mkdir(parents=True)  # mneme's own state dir
        nocorpus = fake_home / "storm" / "camp"
        nocorpus.mkdir(parents=True)
        old = os.environ.get("HOME")
        os.environ["HOME"] = str(fake_home)
        try:
            self.assertEqual(corpus_files.campaign_root(nocorpus), nocorpus.resolve())
        finally:
            if old is None:
                del os.environ["HOME"]
            else:
                os.environ["HOME"] = old

    def test_never_reads_toc_snapshot(self) -> None:
        self.assertNotIn("corpus.toc.json\"", HELPER.read_text().replace("``.mneme/corpus.toc.json``", ""))


if __name__ == "__main__":
    unittest.main()
