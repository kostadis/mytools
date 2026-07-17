"""Tests for the prior-failure dispatch filters in batch_convert.py.

`Dispatcher.enqueue` decides which docs get (re)attempted on a run. A doc with
no `<stem>.json` on disk is either never-tried or one the last run marked
`failed`; the `--skip-failed` / `--only-failed` flags split those two so a
restart can make forward progress or run a remediation pass of just the
failures. These tests lock that routing in.
"""
import types
from pathlib import Path

import batch.batch_convert as bc


def _doc(status="pending", text=1000, reason=""):
    return {"status": status, "text_chars": text, "reason": reason}


def _enqueue(tmp_path: Path, docs: dict, *, skip_failed=False, only_failed=False,
             chunk_token_cap=20000, prompt_cap=40000, retry_too_big=False):
    """Build a Dispatcher over a copy of *docs*, run enqueue (no small box, so
    everything routes to .big), and return (queued_rels, counts)."""
    docs = {k: dict(v) for k, v in docs.items()}
    args = types.SimpleNamespace(
        force=False, skip_failed=skip_failed, only_failed=only_failed,
        chunk_token_cap=chunk_token_cap, prompt_cap=prompt_cap,
        retry_too_big=retry_too_big, logdir=str(tmp_path / "logs"),
    )
    disp = bc.Dispatcher(args, docs, tmp_path)
    disp.enqueue(small_endpoint=None)
    queued = sorted(list(disp.big) + list(disp.small))
    return queued, disp.counts, docs


def _scenario(tmp_path: Path):
    """A prior run's manifest: one done (JSON on disk), one failed, one
    never-finished, one deduped-skip."""
    (tmp_path / "done.json").write_text("{}")  # makes done.pdf look converted
    return {
        "done.pdf":   _doc("done"),
        "failed.pdf": _doc("failed"),
        "fresh.pdf":  _doc("pending"),
        "skip.pdf":   _doc("skipped"),
    }


def test_default_reattempts_failures_with_fresh(tmp_path):
    queued, counts, _ = _enqueue(tmp_path, _scenario(tmp_path))
    # Today's behavior: a prior failure is re-queued alongside never-tried docs.
    assert queued == ["failed.pdf", "fresh.pdf"]
    assert counts["already"] == 1          # done.pdf (json on disk)
    assert counts["skipped"] == 1          # skip.pdf (dedup)
    assert counts["total"] == 2
    assert counts["carried_failed"] == 0
    assert counts["deferred"] == 0


def test_skip_failed_carries_failure_forward(tmp_path):
    queued, counts, docs = _enqueue(tmp_path, _scenario(tmp_path), skip_failed=True)
    # Only the never-tried doc is attempted; the prior failure is carried, not retried.
    assert queued == ["fresh.pdf"]
    assert counts["carried_failed"] == 1
    assert counts["total"] == 1
    assert docs["failed.pdf"]["status"] == "failed"   # status preserved, not reset


def test_only_failed_targets_just_the_failures(tmp_path):
    queued, counts, _ = _enqueue(tmp_path, _scenario(tmp_path), only_failed=True)
    # Remediation pass: only the prior failure runs; the fresh doc is deferred.
    assert queued == ["failed.pdf"]
    assert counts["deferred"] == 1         # fresh.pdf (not a prior failure)
    assert counts["total"] == 1
    assert counts["carried_failed"] == 0


def test_done_and_skipped_win_over_both_filters(tmp_path):
    # A doc with JSON on disk is 'already done' and a dedup-skip stays skipped,
    # regardless of the failure filters.
    for sf, of in [(True, False), (False, True)]:
        _, counts, docs = _enqueue(tmp_path, _scenario(tmp_path),
                                   skip_failed=sf, only_failed=of)
        assert docs["done.pdf"]["status"] == "done"
        assert docs["skip.pdf"]["status"] == "skipped"
        assert counts["already"] == 1
        assert counts["skipped"] == 1


def _too_big_scenario(tmp_path: Path, *, cap_tripped=20000):
    """A prior run that failed one doc with chunk_too_big (deterministic) and
    one with a transient partial (retry-worthy), plus a never-tried doc."""
    return {
        "toobig.pdf":  _doc("failed", reason=f"chunk_too_big:cap={cap_tripped}"),
        "partial.pdf": _doc("failed", reason="partial"),
        "fresh.pdf":   _doc("pending"),
    }


def test_too_big_auto_skipped_at_same_cap(tmp_path):
    # Same cap as the one it tripped: a verbatim re-run re-skips the chunk, so
    # the chunk_too_big doc is parked as 'unfixable' while the transient partial
    # and the fresh doc still run.
    queued, counts, docs = _enqueue(tmp_path, _too_big_scenario(tmp_path),
                                    chunk_token_cap=20000)
    assert queued == ["fresh.pdf", "partial.pdf"]
    assert counts["unfixable"] == 1
    assert counts["total"] == 2
    assert docs["toobig.pdf"]["status"] == "failed"   # carried, not reset


def test_too_big_requeued_when_cap_raised(tmp_path):
    # Raising the cap above the tripped value means the chunk may fit now, so the
    # doc re-enters the queue automatically.
    queued, counts, _ = _enqueue(tmp_path, _too_big_scenario(tmp_path, cap_tripped=20000),
                                 chunk_token_cap=30000)
    assert "toobig.pdf" in queued
    assert counts["unfixable"] == 0
    assert counts["total"] == 3


def test_retry_too_big_forces_reattempt_at_same_cap(tmp_path):
    queued, counts, _ = _enqueue(tmp_path, _too_big_scenario(tmp_path),
                                 chunk_token_cap=20000, retry_too_big=True)
    assert "toobig.pdf" in queued
    assert counts["unfixable"] == 0


def test_cap_disabled_never_auto_skips(tmp_path):
    # cap=0 disables the converter's guard, so the chunk would be sent this run.
    queued, counts, _ = _enqueue(tmp_path, _too_big_scenario(tmp_path),
                                 chunk_token_cap=0)
    assert "toobig.pdf" in queued
    assert counts["unfixable"] == 0


def test_prompt_too_big_skipped_and_requeued_by_prompt_cap(tmp_path):
    # The hard prompt-cap failure is keyed on --prompt-cap, not --chunk-token-cap:
    # raising the chunk cap must NOT spring it; raising --prompt-cap must.
    docs = {"big.pdf": _doc("failed", reason="prompt_too_big:cap=40000")}
    _, counts, _ = _enqueue(tmp_path, docs, prompt_cap=40000)
    assert counts["unfixable"] == 1
    _, counts, _ = _enqueue(tmp_path, docs, prompt_cap=40000, chunk_token_cap=99999)
    assert counts["unfixable"] == 1                       # wrong cap raised
    queued, counts, _ = _enqueue(tmp_path, docs, prompt_cap=64000)
    assert queued == ["big.pdf"] and counts["unfixable"] == 0


def test_interrupted_failure_is_retried(tmp_path):
    # A Ctrl-C'd doc (reason 'interrupted') never got a fair attempt -> re-queue.
    docs = {"killed.pdf": _doc("failed", reason="interrupted")}
    queued, counts, _ = _enqueue(tmp_path, docs)
    assert queued == ["killed.pdf"]
    assert counts["unfixable"] == 0


def test_force_reconverts_done_doc(tmp_path):
    # --force ignores existing JSON: done.pdf re-enters the queue.
    docs = {k: dict(v) for k, v in _scenario(tmp_path).items()}
    args = types.SimpleNamespace(force=True, skip_failed=False, only_failed=False,
                                 logdir=str(tmp_path / "logs"))
    disp = bc.Dispatcher(args, docs, tmp_path)
    disp.enqueue(small_endpoint=None)
    assert "done.pdf" in disp.big
    assert disp.counts["already"] == 0
