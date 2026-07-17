#!/usr/bin/env python3
"""batch_marker.py — standalone Marker OCR extraction pass.

Run this AFTER ``batch_convert.py --phase extract`` (the fast PyMuPDF pass).
The fast pass handles bookmarked digital PDFs and *defers* everything else
(scans, un-bookmarked digital) as ``needs_ocr`` — those docs have no
``<stem>-extract.json``. This tool runs Marker on exactly that set, producing the
same ``<stem>-extract.json`` artifact (``kind="lines"``) the encode pass consumes.
For Mistral OCR instead of Marker, use ``batch_mistral_ocr.py``.

Why it's a separate tool, not a phase inside batch_convert:
  * Marker is GPU/ML-heavy (~5 GB of model weights) with a completely different
    resource profile from the fast path and the network-bound encode pass. You
    want to choose when it runs.
  * Isolation: a Marker crash here never touches the encode driver.

Workflow:
    python3 batch/batch_convert.py --phase extract      # fast structural extraction
    python3 batch/batch_marker.py                        # this tool — Marker the rest
    python3 batch/batch_convert.py --phase encode        # in-process LLM conversion

Resumable: a doc whose ``<stem>-extract.json`` already exists is skipped
(``--force`` rebuilds). Marker runs one doc at a time by default (``--workers 1``)
since each ``marker_single`` invocation loads the model weights and contends for
the GPU.

NOTE: ``run_marker`` shells ``marker_single`` per doc, so the model weights are
reloaded for every document. A future optimization is to switch to Marker's batch
CLI (loads once over a whole input set); that's a separate change to
``pdf_to_5etools_v2.run_marker`` and is not done here.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from lib.batch_state import StateDB


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path,
                   default=Path("/mnt/g/My Drive/DriveThru/Dungeon Masters Guild"),
                   help="Directory tree of PDFs (same as batch_convert --root).")
    p.add_argument("--state-db", default=str(HERE / "dmsguild-state.db"),
                   help="batch_convert state DB. If it exists, its content-doc "
                        "list (post scan + dedup) is the source of truth for which "
                        "PDFs to consider; otherwise every PDF under --root is "
                        "considered.")
    p.add_argument("--type", choices=["adventure", "book"], default="adventure",
                   help="Document type recorded in the extract meta.")
    p.add_argument("--workers", type=int, default=1,
                   help="Concurrent Marker subprocesses. Default 1 — Marker loads "
                        "model weights per invocation and contends for the GPU.")
    p.add_argument("--force", action="store_true",
                   help="Re-run Marker even if <stem>-extract.json already exists.")
    p.add_argument("--list", action="store_true",
                   help="List the docs that need Marker, then exit (no extraction).")
    p.add_argument("--verbose", action="store_true",
                   help="Stream Marker subprocess output.")
    return p.parse_args(argv)


def _candidate_rels(root: Path, state_db: str) -> list[str]:
    """Content PDFs to consider, from the state DB if present (post scan+dedup),
    else every PDF under root."""
    db_path = Path(state_db)
    if db_path.exists():
        state = StateDB(state_db)
        try:
            if state.exists_with_docs():
                docs = state.load_docs()
                return [rel for rel, ent in sorted(docs.items())
                        if ent.get("status") != "skipped"]
        finally:
            state.close()
    # Fallback: no usable state DB — walk the tree.
    return sorted(
        os.path.relpath(str(p), str(root))
        for p in root.rglob("*.pdf")
        if not re.search(r"\.old-\d+\.pdf$", p.name, re.I)
    )


def _needs_marker(pdf: Path, profile_pdf) -> bool:
    """True iff this PDF routes to Marker (not fast-path / printed-ToC)."""
    prof = profile_pdf(pdf)
    return not (prof.use_fast_path or prof.use_printed_toc_path)


def _select(root: Path, rels: list[str], force: bool, profile_pdf) -> list[Path]:
    """Filter to docs that (a) still need converting, (b) lack an extract, and
    (c) route to Marker."""
    selected = []
    for rel in rels:
        pdf = root / rel
        if not pdf.exists():
            continue
        if pdf.with_suffix(".json").exists():
            continue  # already converted
        extract_path = pdf.with_name(pdf.stem + "-extract.json")
        if extract_path.exists() and not force:
            continue  # already extracted (fast or a prior Marker run)
        try:
            if _needs_marker(pdf, profile_pdf):
                selected.append(pdf)
        except Exception as e:  # noqa: BLE001 — a bad PDF shouldn't stop selection
            print(f"[skip] {rel}: profile error {type(e).__name__}: {e}")
    return selected


def _marker_one(pdf: Path, output_type: str, verbose: bool):
    """Run Marker structural extraction for one PDF -> <stem>-extract.json.
    Imported lazily so --list / selection works without the Marker venv."""
    import converters.pdf_to_5etools_v2 as v2
    import lib.chunk_cache as cc

    short_id, name = v2._derive_ids(pdf, None)
    roots, units = v2._marker_structure(pdf, verbose=verbose)
    meta = {
        "short_id": short_id,
        "name": name,
        "output_type": output_type,
        "page_count": len(units),
        "source_kind": "marker",
    }
    extract_path = pdf.with_name(pdf.stem + "-extract.json")
    cc.serialize_extract(extract_path, roots, units, "lines", meta)
    return extract_path


def main(argv=None) -> int:
    args = parse_args(argv)
    root = args.root
    if not root.is_dir():
        sys.exit(f"error: --root not a directory: {root}")

    # Imported here (not at top) so the module loads without the Marker venv for
    # callers that only want selection/help.
    from converters.pdf_to_5etools_v2 import profile_pdf

    rels = _candidate_rels(root, args.state_db)
    selected = _select(root, rels, args.force, profile_pdf)

    print(f"[marker] {len(selected)} doc(s) need Marker "
          f"(of {len(rels)} content docs under {root})")
    if args.list or not selected:
        for pdf in selected:
            print(f"  - {os.path.relpath(str(pdf), str(root))}")
        if args.list:
            return 0
        if not selected:
            print("[marker] nothing to do.")
            return 0

    done = failed = 0
    t0 = time.monotonic()
    # Sequential by default; --workers>1 uses a thread pool (each run_marker is a
    # subprocess, so threads suffice — but the GPU is the real limiter).
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {ex.submit(_marker_one, pdf, args.type, args.verbose): pdf
                for pdf in selected}
        for fut in as_completed(futs):
            pdf = futs[fut]
            rel = os.path.relpath(str(pdf), str(root))
            try:
                fut.result()
                done += 1
                flag = "OK  "
                why = ""
            except Exception as e:  # noqa: BLE001
                failed += 1
                flag = "FAIL"
                why = f" [{type(e).__name__}: {e}]"
            print(f"[{time.strftime('%H:%M:%S')}] {flag} "
                  f"{done + failed}/{len(selected)} {rel}{why}", flush=True)

    dur = round(time.monotonic() - t0, 1)
    print(f"\n=== marker done === extracted {done}, failed {failed} in {dur}s.")
    print("Next: python3 batch_convert.py --phase encode")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
