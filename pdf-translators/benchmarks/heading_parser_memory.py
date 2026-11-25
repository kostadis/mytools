#!/usr/bin/env python3
"""Offline RSS comparison; source text and paths are omitted from JSON output.

Each sample is a fresh process. RSS runs have tracemalloc disabled; separate
traced runs diagnose Python allocations without confusing them with native RSS.
Example: python benchmarks/heading_parser_memory.py --markdown /path/book.md
    --native-dir .fast/lib --runs 5 > /tmp/parser-memory.json
"""
import argparse
from contextlib import redirect_stdout
from functools import partial
import hashlib
import importlib
import json
import os
from pathlib import Path
import resource
import statistics
import subprocess
import sys
import tempfile
import time

MODULE = "fa_converters_pdf_to_5etools_v2_py_parse_markdown_headings"
PROJECT = Path(__file__).resolve().parents[1]


class DigestWriter:
    """Hash conversion diagnostics without retaining a document-sized log."""

    def __init__(self):
        self.digest = hashlib.sha256()

    def write(self, text):
        self.digest.update(text.encode("utf-8", "surrogatepass"))
        return len(text)

    def flush(self):
        pass


def worker(args):
    # The baseline must stay Python even when fast-anything is temporarily
    # enabled in the converter. Native mode is selected explicitly below.
    os.environ["FAST_ANYTHING_DISABLE"] = "1"
    sys.path.insert(0, str(PROJECT))
    from converters import pdf_to_5etools_v2 as converter

    if args.mode == "native":
        sys.path.insert(0, str(args.native_dir.resolve()))
        native = importlib.import_module(MODULE).parse_markdown_headings
        converter.parse_markdown_headings = partial(native, heading_type=converter.MdHeading)
    if args.traced:
        import tracemalloc
        tracemalloc.start()
    started = time.perf_counter()
    sink = DigestWriter()
    if args.phase == "parser":
        text = args.markdown.read_text(encoding="utf-8")
        headings, lines = converter.parse_markdown_headings(text)
    else:
        # --from-markdown checks existence but does not read the positional PDF.
        # This existing Markdown path provides naming only. No inference occurs.
        with redirect_stdout(sink):
            status = converter.main([
                str(args.markdown), "--from-markdown", str(args.markdown),
                "--provider", "claude-code", "--dry-run",
            ])
        if status:
            raise RuntimeError(f"offline conversion returned {status}")
    elapsed = time.perf_counter() - started
    python_peak = tracemalloc.get_traced_memory()[1] if args.traced else None
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports KiB.
    if sys.platform == "darwin":
        peak_rss /= 1024
    # Hash after measuring so verification allocations don't affect the sample.
    if args.phase == "parser":
        for line in lines:
            sink.write(json.dumps(line, ensure_ascii=True) + "\n")
        for heading in headings:
            sink.write(json.dumps([heading.level, heading.title, heading.line_no], ensure_ascii=True) + "\n")
    print(json.dumps(dict(pid=os.getpid(), mode=args.mode, phase=args.phase,
                          parser_module=getattr(converter.parse_markdown_headings, "func",
                                                converter.parse_markdown_headings).__module__,
                          traced=args.traced, seconds=elapsed, peak_rss_kib=peak_rss,
                          python_peak_bytes=python_peak, digest=sink.digest.hexdigest())))


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--native-dir", type=Path, required=True)
    parser.add_argument("--runs", type=positive, default=5)
    parser.add_argument("--synthetic-mib", type=positive, default=32)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--mode", choices=["python", "native"], help=argparse.SUPPRESS)
    parser.add_argument("--phase", choices=["parser", "pipeline"], help=argparse.SUPPRESS)
    parser.add_argument("--traced", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    samples = []
    with tempfile.TemporaryDirectory(prefix="heading-parser-bench-") as scratch:
        synthetic = Path(scratch) / "synthetic.md"
        block = "## **Room 🐉**\n" + ("Searchable café text in a large sourcebook. " * 8 + "\n") * 32
        with synthetic.open("w", encoding="utf-8") as stream:
            stream.write("# Synthetic sourcebook\n")
            for _ in range((args.synthetic_mib * 1024 * 1024) // len(block.encode("utf-8")) + 1):
                stream.write(block)
        for label, source in [("real", args.markdown.resolve()), ("synthetic", synthetic)]:
            for phase in ["parser", "pipeline"]:
                for traced in [False, True]:
                    for run in range(args.runs):
                        # Alternate order to limit systematic warm-cache bias.
                        modes = ["python", "native"] if run % 2 == 0 else ["native", "python"]
                        for mode in modes:
                            command = [sys.executable, str(Path(__file__).resolve()),
                                       "--worker", "--markdown", str(source),
                                       "--native-dir", str(args.native_dir.resolve()),
                                       "--mode", mode, "--phase", phase]
                            if traced:
                                command.append("--traced")
                            result = subprocess.run(command, capture_output=True, text=True, check=True)
                            sample = json.loads(result.stdout)
                            sample.update(workload=label, run=run)
                            samples.append(sample)
                            print(f"{label}/{phase} {'traced' if traced else 'RSS'} {run + 1}/{args.runs}: {mode}", file=sys.stderr)
    summaries = []
    equal = True
    for workload in ["real", "synthetic"]:
        for phase in ["parser", "pipeline"]:
            group = [s for s in samples if s["workload"] == workload and s["phase"] == phase]
            equal &= len({s["digest"] for s in group}) == 1
            for mode in ["python", "native"]:
                plain = [s for s in group if s["mode"] == mode and not s["traced"]]
                traced = [s for s in group if s["mode"] == mode and s["traced"]]
                summaries.append(dict(workload=workload, phase=phase, mode=mode,
                    rss_median_kib=statistics.median(s["peak_rss_kib"] for s in plain),
                    rss_min_kib=min(s["peak_rss_kib"] for s in plain),
                    rss_max_kib=max(s["peak_rss_kib"] for s in plain),
                    seconds_median=statistics.median(s["seconds"] for s in plain),
                    python_peak_median_bytes=statistics.median(s["python_peak_bytes"] for s in traced)))
    print(json.dumps(dict(all_outputs_equal=equal, runs=args.runs,
                         synthetic_mib=args.synthetic_mib, python=sys.version,
                         platform=sys.platform, summaries=summaries, samples=samples), indent=2))
    if not equal:
        raise SystemExit("Python/native outputs differ")


if __name__ == "__main__":
    main()
