#!/usr/bin/env python3
"""Fresh-process controller+worker memory measurement; never prints source text.

Example: python benchmarks/pdf_reader_memory.py --pdf /path/book.pdf --pages 1,2,3
Aggregate RSS is sampled every 2 ms, so report it as approximate. Worker
ru_maxrss includes a possible inherited pre-exec controller RSS floor; use
standalone /usr/bin/time measurements for the reader's own execution peak.
"""
import argparse
import json
import os
from pathlib import Path
import resource
import statistics
import subprocess
import sys
import threading
import time

PROJECT = Path(__file__).resolve().parents[1]


def resident(pid):
    try:
        for line in Path(f'/proc/{pid}/status').read_text().splitlines():
            if line.startswith('VmRSS:'):
                return int(line.split()[1]) / 1024
    except (OSError, ValueError):
        pass
    return 0


def worker(args):
    sys.path.insert(0, str(PROJECT))
    # Count the actual converter imports, not merely a bare adapter harness.
    from converters import pdf_to_5etools_v2  # noqa: F401
    from lib.pdf_backend import RustDocument
    before = resident(os.getpid())
    maximum = [before]
    stop = threading.Event()
    pid = os.getpid()

    def sample():
        while not stop.is_set():
            try:
                children = Path(f'/proc/{pid}/task/{pid}/children').read_text().split()
            except OSError:
                children = []
            maximum[0] = max(maximum[0], resident(pid) + sum(resident(int(p)) for p in children))
            stop.wait(0.002)

    monitor = threading.Thread(target=sample, daemon=True)
    monitor.start()
    started = time.monotonic()
    error = None
    try:
        with RustDocument(args.pdf) as document:
            document.read_pages(args.pages)
    except Exception as failure:
        error = str(failure)
    finally:
        stop.set()
        monitor.join()
    print(json.dumps({'controller_before_mib': before,
                      'aggregate_sampled_peak_mib': maximum[0],
                      'child_process_kernel_peak_mib': resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024,
                      'seconds': time.monotonic() - started, 'error': error}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--pages', required=True, help='at most five comma-separated page numbers')
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        args.pages = sorted(set(int(p) for p in args.pages.split(',')))
    except ValueError:
        parser.error('--pages must contain positive integers')
    if not 1 <= len(args.pages) <= 5 or min(args.pages) < 1 or args.runs < 1:
        parser.error('supply 1–5 positive pages and at least one run')
    if not sys.platform.startswith('linux'):
        parser.error('aggregate RSS sampler currently requires Linux /proc')
    if args.worker:
        worker(args)
        return
    samples = []
    for _ in range(args.runs):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker',
                                 '--pdf', str(args.pdf.resolve()), '--pages', ','.join(map(str,args.pages))],
                                capture_output=True, text=True, check=True)
        samples.append(json.loads(result.stdout))
    summary = {key: statistics.median(sample[key] for sample in samples)
               for key in ['controller_before_mib', 'aggregate_sampled_peak_mib',
                           'child_process_kernel_peak_mib', 'seconds']}
    print(json.dumps({'runs': args.runs, 'aggregate_sampling_interval_ms': 2,
                      'medians': summary, 'samples': samples}, indent=2))
    if any(s['error'] for s in samples):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
