"""Exercise the fresh-process benchmark with a small non-private fixture."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def test_benchmark_compares_equivalent_outputs_in_fresh_processes(tmp_path):
    native_dir = os.environ.get("PDF_HEADING_NATIVE_DIR")
    if not native_dir:
        pytest.skip("optional native experiment")
    source = tmp_path / "book.md"
    source.write_text("# **Book**\nIntro\n## Room 🐉\nSearchable prose\n")
    script = Path(__file__).resolve().parents[1] / "benchmarks/heading_parser_memory.py"
    result = subprocess.run(
        [sys.executable, str(script), "--markdown", str(source),
         "--native-dir", str(Path(native_dir).resolve()), "--runs", "1",
         "--synthetic-mib", "1"], capture_output=True, text=True, check=True,
    )
    report = json.loads(result.stdout)
    assert report["all_outputs_equal"]
    assert len(report["samples"]) == 16  # 2 inputs × 2 modes × 2 phases × RSS/traced
    assert len({s["pid"] for s in report["samples"]}) == 16
    assert all(s["peak_rss_kib"] > 0 for s in report["samples"])
    assert all(s["parser_module"] == "converters.pdf_to_5etools_v2"
               for s in report["samples"] if s["mode"] == "python")
    assert all(s["parser_module"].startswith("fa_converters_")
               for s in report["samples"] if s["mode"] == "native")
    assert all(s["python_peak_bytes"] is not None for s in report["samples"] if s["traced"])
