#!/usr/bin/env python3
"""Compare nested splitting against a Git baseline; synthetic text only.

RSS and tracemalloc run in separate fresh processes. The baseline uses just
the two original splitting functions, with the same current imports and data.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import resource
import statistics
import subprocess
import sys
import tempfile
import time

PROJECT = Path(__file__).resolve().parents[1]


def worker(args):
    sys.path.insert(0, str(PROJECT))
    from converters import pdf_to_5etools_v2 as c
    from lib.pdf_utils import TocNode
    split = c.split_oversized
    if args.mode == "baseline":
        namespace = dict(vars(c))
        exec(compile(args.baseline_file.read_text(), "<baseline splitting>", "exec"), namespace)
        split = namespace["split_oversized"]
    units = [f"{i:08d} " + "Searchable sourcebook prose. " * 18 for i in range(args.lines)]
    end = len(units)
    leaves = [TocNode(4, "West", 4, end // 2), TocNode(4, "East", end // 2 + 1, end)]
    branch = TocNode(3, "Rooms", 3, end, leaves)
    chapter = TocNode(2, "Chapter", 2, end, [branch])
    root = TocNode(1, "Book", 1, end, [chapter])
    if args.traced:
        import tracemalloc
        tracemalloc.start()
    started = time.perf_counter()
    chunks = split([root], lambda node: c._body_from_units(node, units, "lines"), 150000)
    elapsed = time.perf_counter() - started
    peak = tracemalloc.get_traced_memory()[1] if args.traced else None
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        rss /= 1024
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(json.dumps([chunk.root.title, chunk.target_node.title,
                                 chunk.is_prose_stub, chunk.body]).encode())
    print(json.dumps(dict(mode=args.mode, traced=args.traced, seconds=elapsed,
                          peak_rss_kib=rss, python_peak_bytes=peak,
                          digest=digest.hexdigest(), chunks=len(chunks))))


def positive(value):
    result = int(value)
    if result < 8:
        raise argparse.ArgumentTypeError("must be at least 8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", default="76c6229")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--lines", type=positive, default=65536)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--mode", choices=["baseline", "current"], help=argparse.SUPPRESS)
    parser.add_argument("--baseline-file", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--traced", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    if args.worker:
        worker(args)
        return
    source = subprocess.run(["git", "show", f"{args.baseline_ref}:pdf-translators/converters/pdf_to_5etools_v2.py"],
                            cwd=PROJECT, capture_output=True, text=True, check=True).stdout
    functions = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)
                 and node.name in {"split_oversized", "_split_into_chunks"}]
    if len(functions) != 2:
        raise RuntimeError("baseline must contain both splitting functions")
    samples = []
    with tempfile.TemporaryDirectory(prefix="chunk-split-bench-") as scratch:
        baseline = Path(scratch) / "baseline.py"
        baseline.write_text("\n\n".join(ast.get_source_segment(source, f) for f in functions))
        for traced in [False, True]:
            for run in range(args.runs):
                for mode in (["baseline", "current"] if run % 2 == 0 else ["current", "baseline"]):
                    command = [sys.executable, str(Path(__file__).resolve()), "--worker",
                               "--mode", mode, "--baseline-file", str(baseline), "--lines", str(args.lines)]
                    if traced:
                        command.append("--traced")
                    result = subprocess.run(command, capture_output=True, text=True, check=True)
                    sample = json.loads(result.stdout)
                    sample["run"] = run
                    samples.append(sample)
    summaries = []
    for mode in ["baseline", "current"]:
        plain = [s for s in samples if s["mode"] == mode and not s["traced"]]
        traced = [s for s in samples if s["mode"] == mode and s["traced"]]
        summaries.append(dict(mode=mode, rss_median_kib=statistics.median(s["peak_rss_kib"] for s in plain),
            rss_min_kib=min(s["peak_rss_kib"] for s in plain), rss_max_kib=max(s["peak_rss_kib"] for s in plain),
            seconds_median=statistics.median(s["seconds"] for s in plain),
            python_peak_median_bytes=statistics.median(s["python_peak_bytes"] for s in traced)))
    equal = len({s["digest"] for s in samples}) == 1
    print(json.dumps(dict(all_outputs_equal=equal, baseline_ref=args.baseline_ref,
                         runs=args.runs, lines=args.lines, summaries=summaries, samples=samples), indent=2))
    if not equal:
        raise SystemExit("baseline/current chunks differ")


if __name__ == "__main__":
    main()
