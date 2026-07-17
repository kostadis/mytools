"""Tests for the concurrent chunk runner (_map_chunks_ordered).

Verifies the ordering guarantee that TOC/data alignment depends on: results
come back in chunk order even when workers finish out of order, each chunk runs
exactly once, and the sequential path (concurrency=1) behaves identically.
"""

import threading
import time

import converters.pdf_to_5etools_v2 as v2


def test_sequential_preserves_order_and_index():
    chunks = ["a", "b", "c", "d"]
    seen = []

    def run(i, c):
        seen.append((i, c))
        return f"{i}:{c}"

    out = v2._map_chunks_ordered(chunks, run, concurrency=1)
    assert out == ["0:a", "1:b", "2:c", "3:d"]
    assert seen == [(0, "a"), (1, "b"), (2, "c"), (3, "d")]


def test_concurrent_results_in_chunk_order_despite_reversed_completion():
    # Make later chunks finish FIRST: chunk i sleeps (N-i) ms, so completion
    # order is the reverse of submission order. Results must still be ordered.
    chunks = list(range(8))

    def run(i, c):
        time.sleep((len(chunks) - i) * 0.005)
        return c * 10

    out = v2._map_chunks_ordered(chunks, run, concurrency=4)
    assert out == [c * 10 for c in chunks]


def test_each_chunk_runs_exactly_once():
    chunks = list(range(20))
    counts = {}
    lock = threading.Lock()

    def run(i, c):
        with lock:
            counts[i] = counts.get(i, 0) + 1
        return i

    out = v2._map_chunks_ordered(chunks, run, concurrency=8)
    assert out == chunks
    assert counts == {i: 1 for i in range(20)}


def test_concurrency_capped_at_chunk_count():
    # concurrency far larger than the work list must not error or reorder.
    chunks = ["x", "y"]
    out = v2._map_chunks_ordered(chunks, lambda i, c: c.upper(), concurrency=100)
    assert out == ["X", "Y"]


def test_empty_chunks():
    assert v2._map_chunks_ordered([], lambda i, c: c, concurrency=4) == []
