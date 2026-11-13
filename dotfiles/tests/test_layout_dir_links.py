"""check-skill-layout.py accepts a shared directory linked as a whole."""
import json
import subprocess
import sys
from pathlib import Path

CHECK = Path(__file__).resolve().parent.parent / "check-skill-layout.py"


def build(tmp: Path, link_dirs: bool):
    (tmp / "shared/skills/_shared/kit").mkdir(parents=True)
    (tmp / "shared/skills/_shared/kit/a.py").write_text("x = 1\n")
    for side in ("claude", "codex"):
        (tmp / side / "skills/_shared").mkdir(parents=True)
        if link_dirs:
            (tmp / side / "skills/_shared/kit").symlink_to(
                "../../../shared/skills/_shared/kit"
            )
    (tmp / "skill-layout.json").write_text(json.dumps({
        "shared_skills": ["_shared"],
        "intentional_adapters": {"paired": [], "claude_only": [], "codex_only": []},
    }))
    (tmp / "skill-compatibility.json").write_text(json.dumps({"skills": []}))


def run(tmp: Path):
    return subprocess.run(
        [sys.executable, str(CHECK), "--dotfiles", str(tmp)],
        capture_output=True, text=True,
    )


def test_directory_link_is_accepted(tmp_path):
    build(tmp_path, link_dirs=True)
    r = run(tmp_path)
    assert r.returncode == 0, r.stderr


def test_missing_link_is_still_reported(tmp_path):
    build(tmp_path, link_dirs=False)
    r = run(tmp_path)
    assert r.returncode == 1
    assert "missing: _shared/kit/a.py" in r.stderr


def test_copied_directory_is_still_reported(tmp_path):
    build(tmp_path, link_dirs=False)
    for side in ("claude", "codex"):
        d = tmp_path / side / "skills/_shared/kit"
        d.mkdir()
        (d / "a.py").write_text("x = 1\n")
    r = run(tmp_path)
    assert r.returncode == 1
    assert "copied, not linked" in r.stderr
