"""verify_enhanced.py: names with an internal apostrophe are one name, not a truncated invention."""
import pathlib
import subprocess
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "verify_enhanced.py"

CHAPTER = """# Chapter 1 – The Demon Prince

Graz’zt watches from his throne. The party bows to Graz’zt and leaves.
"""

SUMMARY = """# Chapter 1 – The Demon Prince

Date: not stated in chapter

## Summary
The party bows to Graz’zt and leaves; Graz’zt's gaze follows them.

## Scenes
### The throne
#### The party meets the prince.
- The party bows to Graz’zt.

## NPCs
### Graz’zt
A demon prince who watches from his throne.
"""


def run(tmp_path, chapter, summary):
    c = tmp_path / "chapter.md"; c.write_text(chapter, encoding="utf-8")
    s = tmp_path / "summary.md"; s.write_text(summary, encoding="utf-8")
    return subprocess.run([sys.executable, str(SCRIPT), "--chapter", str(c), "--summary", str(s)],
                          capture_output=True, text=True).stdout


def test_internal_apostrophe_name_mid_sentence_is_not_invented(tmp_path):
    out = run(tmp_path, CHAPTER, SUMMARY)
    assert "Graz," not in out and "Graz\n" not in out
    assert "RESULT: CLEAN" in out


def test_invented_apostrophe_name_still_fails(tmp_path):
    out = run(tmp_path, CHAPTER, SUMMARY.replace("bows to Graz’zt and", "bows to Orc’zul and"))
    assert "Orc'zul" in out
    assert "RESULT: CLEAN" not in out
