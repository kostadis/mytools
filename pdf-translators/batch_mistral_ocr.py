"""batch_mistral_ocr.py — Mistral OCR extraction pass using the Batch API.

Run this AFTER ``batch_convert.py --phase extract`` (the fast PyMuPDF pass).
The fast pass handles bookmarked digital PDFs and *defers* everything else
(scans, un-bookmarked digital) as ``needs_ocr`` — those docs have no
``<stem>-extract.json``. This tool submits all such PDFs to the Mistral Batch
API in a single job (~50% cheaper than individual sync calls, async), producing
the same ``<stem>-extract.json`` artifact (``kind="lines"``) the encode pass
consumes. For the local Marker pipeline instead, use ``batch_marker.py``.

Workflow::

    python3 batch_convert.py --phase extract          # fast structural extraction
    python3 batch_mistral_ocr.py                       # this tool — Mistral OCR the rest
    python3 batch_convert.py --phase encode            # in-process LLM conversion

Batch API flow (this tool):
  1. Select PDFs that lack ``<stem>-extract.json`` and route to the OCR path.
  2. Upload each PDF to Mistral (``purpose="ocr"``).
  3. Build a JSONL manifest with one OCR request per PDF (``custom_id = stem``).
  4. Upload the manifest (``purpose="batch"``).
  5. Submit ``POST /v1/batch/jobs`` with ``endpoint="/v1/ocr"``.
  6. Poll every ``--poll-interval`` seconds until SUCCESS/FAILED.
  7. Download result JSONL; for each doc: run heading extraction pipeline →
     ``chunk_cache.serialize_extract`` → write ``<stem>-extract.json``.
  8. Delete all uploaded files (PDFs + manifest).

Resumable: docs whose ``<stem>-extract.json`` already exists are skipped
(``--force`` rebuilds). If the script is interrupted after job submission, re-run
with ``--resume-job JOB_ID`` to skip upload/submit and go straight to polling.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
from pathlib import Path

from batch_state import StateDB

HERE = Path(__file__).resolve().parent

POLL_INTERVAL_DEFAULT = 30  # seconds


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path,
                   default=Path("/mnt/g/My Drive/DriveThru/Dungeon Masters Guild"),
                   help="Directory tree of PDFs (same as batch_convert --root).")
    p.add_argument("--state-db", default=str(HERE / "dmsguild-state.db"),
                   help="batch_convert state DB.")
    p.add_argument("--type", choices=["adventure", "book"], default="adventure",
                   help="Document type recorded in the extract meta.")
    p.add_argument("--force", action="store_true",
                   help="Re-run OCR even if <stem>-extract.json already exists.")
    p.add_argument("--list", action="store_true",
                   help="List the docs that need Mistral OCR, then exit.")
    p.add_argument("--mistral-api-key", default=None, dest="mistral_api_key",
                   help="Mistral API key (also read from MISTRAL_API_KEY env var).")
    p.add_argument("--poll-interval", type=int, default=POLL_INTERVAL_DEFAULT,
                   dest="poll_interval",
                   help=f"Seconds between job status polls (default {POLL_INTERVAL_DEFAULT}).")
    p.add_argument("--resume-job", default=None, dest="resume_job",
                   metavar="JOB_ID",
                   help="Skip upload/submit; poll an already-running Mistral batch job. "
                        "Provide a stem→pdf mapping via --resume-map.")
    p.add_argument("--resume-map", default=None, dest="resume_map",
                   metavar="FILE",
                   help="JSON file mapping stem → absolute PDF path, required with "
                        "--resume-job (saved automatically as mistral-ocr-map.json).")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def _candidate_rels(root: Path, state_db: str) -> list[str]:
    """Content PDFs to consider, from the state DB if present, else walk root."""
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
    return sorted(
        os.path.relpath(str(p), str(root))
        for p in root.rglob("*.pdf")
        if not re.search(r"\.old-\d+\.pdf$", p.name, re.I)
    )


def _needs_ocr(pdf: Path, profile_pdf) -> bool:
    """True iff this PDF routes to the OCR path (not fast-path / printed-ToC)."""
    prof = profile_pdf(pdf)
    return not (prof.use_fast_path or prof.use_printed_toc_path)


def _select(root: Path, rels: list[str], force: bool, profile_pdf) -> list[Path]:
    """Filter to docs that lack an extract and route to the OCR path."""
    selected = []
    for rel in rels:
        pdf = root / rel
        if not pdf.exists():
            continue
        if pdf.with_suffix(".json").exists():
            continue  # already converted
        extract_path = pdf.with_name(pdf.stem + "-extract.json")
        if extract_path.exists() and not force:
            continue
        try:
            if _needs_ocr(pdf, profile_pdf):
                selected.append(pdf)
        except Exception as e:  # noqa: BLE001
            print(f"[skip] {rel}: profile error {type(e).__name__}: {e}")
    return selected


def _upload_pdfs(client, pdfs: list[Path], verbose: bool) -> dict[str, str]:
    """Upload each PDF and return {stem: file_id}."""
    stem_to_fid: dict[str, str] = {}
    for i, pdf in enumerate(pdfs, 1):
        if verbose:
            print(f"[upload] {i}/{len(pdfs)} {pdf.name} ...", flush=True)
        with open(pdf, "rb") as f:
            resp = client.files.upload(
                file={"file_name": pdf.name, "content": f},
                purpose="ocr",
            )
        stem_to_fid[pdf.stem] = resp.id
        if verbose:
            print(f"[upload] {pdf.name} -> {resp.id}", flush=True)
    return stem_to_fid


def _build_manifest(stem_to_fid: dict[str, str]) -> bytes:
    """Build the JSONL batch manifest bytes."""
    lines = []
    for stem, file_id in stem_to_fid.items():
        req = {
            "custom_id": stem,
            "body": {
                "model": "mistral-ocr-latest",
                "document": {"type": "file", "file_id": file_id},
                "table_format": "markdown",
                "extract_header": False,
                "extract_footer": False,
            },
        }
        lines.append(json.dumps(req))
    return "\n".join(lines).encode()


def _poll_job(client, job_id: str, poll_interval: int, verbose: bool):
    """Poll until terminal status; return the final BatchJob object."""
    terminal = {"SUCCESS", "FAILED", "TIMEOUT_EXCEEDED", "CANCELLED"}
    while True:
        job = client.batch_jobs.get(job_id=job_id)
        status = job.status
        done = job.completed_requests
        total = job.total_requests
        if verbose or True:  # always print progress for long-running jobs
            print(f"[poll] job={job_id} status={status} "
                  f"completed={done}/{total}", flush=True)
        if status in terminal:
            return job
        time.sleep(poll_interval)


def _process_results(client, job, stem_to_pdf: dict[str, Path],
                     output_type: str, verbose: bool) -> tuple[int, int]:
    """Download result JSONL, run heading pipeline, write extract files.
    Returns (done, failed) counts."""
    import pdf_to_5etools_v2 as v2
    import chunk_cache as cc

    output_fid = job.output_file
    if not output_fid:
        print("[results] job has no output_file — nothing to download.")
        return 0, len(stem_to_pdf)

    if verbose:
        print(f"[results] downloading output file {output_fid} ...")
    resp = client.files.download(file_id=output_fid)
    result_lines = resp.text.strip().splitlines()

    done = failed = 0
    for line in result_lines:
        rec = json.loads(line)
        stem = rec["custom_id"]
        pdf = stem_to_pdf.get(stem)
        if pdf is None:
            print(f"[results] unknown custom_id {stem!r} — skipping")
            continue

        status_code = rec.get("response", {}).get("status_code")
        if status_code != 200:
            err = rec.get("error") or rec.get("response", {})
            print(f"[results] FAIL {stem}: status {status_code} {err}")
            failed += 1
            continue

        body = rec["response"]["body"]
        pages = sorted(body.get("pages", []), key=lambda p: p["index"])
        md_text = "\n\n".join(p["markdown"] for p in pages)

        try:
            headings, lines = v2.parse_markdown_headings(md_text)
            headings = v2.normalise_numbered_rooms(headings)
            toc_roots = v2.build_synthetic_toc(headings, total_lines=len(lines))
            toc_roots = v2._unwrap_singleton_root(toc_roots, verbose)

            short_id, name = v2._derive_ids(pdf, None)
            meta = {
                "short_id": short_id,
                "name": name,
                "output_type": output_type,
                "page_count": len(pages),
                "source_kind": "mistral-ocr",
            }
            extract_path = pdf.with_name(pdf.stem + "-extract.json")
            cc.serialize_extract(extract_path, toc_roots, lines, "lines", meta)
            done += 1
            if verbose:
                print(f"[results] OK  {stem} -> {extract_path.name}")
        except Exception as e:  # noqa: BLE001
            print(f"[results] FAIL {stem}: pipeline error {type(e).__name__}: {e}")
            failed += 1

    return done, failed


def _delete_uploads(client, file_ids: list[str], verbose: bool) -> None:
    """Best-effort cleanup of uploaded files."""
    for fid in file_ids:
        try:
            client.files.delete(file_id=fid)
            if verbose:
                print(f"[cleanup] deleted {fid}")
        except Exception as e:  # noqa: BLE001
            print(f"[cleanup] warning: could not delete {fid}: {e}")


def main(argv=None) -> int:
    args = parse_args(argv)
    root = args.root
    if not root.is_dir():
        sys.exit(f"error: --root not a directory: {root}")

    api_key = args.mistral_api_key or os.environ.get("MISTRAL_API_KEY")
    if not api_key and not args.list:
        sys.exit("error: MISTRAL_API_KEY not set and --mistral-api-key not provided")

    from pdf_to_5etools_v2 import profile_pdf

    rels = _candidate_rels(root, args.state_db)

    if args.resume_job:
        # Resume mode: skip selection/upload, go straight to polling.
        if not args.resume_map:
            sys.exit("error: --resume-job requires --resume-map FILE")
        with open(args.resume_map) as f:
            stem_to_path = json.load(f)
        stem_to_pdf = {stem: Path(p) for stem, p in stem_to_path.items()}
        from mistralai.client.sdk import Mistral
        client = Mistral(api_key=api_key)
        print(f"[resume] polling job {args.resume_job} "
              f"({len(stem_to_pdf)} docs) ...")
        job = _poll_job(client, args.resume_job, args.poll_interval, args.verbose)
        print(f"[job] final status={job.status} "
              f"succeeded={job.succeeded_requests} failed={job.failed_requests}")
        if job.status != "SUCCESS":
            print(f"[job] job did not succeed; check Mistral dashboard.")
            return 1
        done, failed = _process_results(
            client, job, stem_to_pdf, args.type, args.verbose)
        print(f"\n=== mistral-ocr done === extracted {done}, failed {failed}.")
        return 1 if failed else 0

    selected = _select(root, rels, args.force, profile_pdf)
    print(f"[mistral-ocr] {len(selected)} doc(s) need Mistral OCR "
          f"(of {len(rels)} content docs under {root})")

    if args.list or not selected:
        for pdf in selected:
            print(f"  - {os.path.relpath(str(pdf), str(root))}")
        if args.list:
            return 0
        print("[mistral-ocr] nothing to do.")
        return 0

    from mistralai.client.sdk import Mistral
    client = Mistral(api_key=api_key)

    # Upload PDFs
    print(f"[mistral-ocr] uploading {len(selected)} PDFs ...")
    t0 = time.monotonic()
    stem_to_fid = _upload_pdfs(client, selected, args.verbose)
    stem_to_pdf = {pdf.stem: pdf for pdf in selected}

    # Save stem→pdf map for --resume-job recovery
    map_path = HERE / "mistral-ocr-map.json"
    with open(map_path, "w") as f:
        json.dump({stem: str(pdf) for stem, pdf in stem_to_pdf.items()}, f, indent=2)
    print(f"[mistral-ocr] stem map saved to {map_path.name} "
          f"(use with --resume-job if interrupted)")

    # Upload manifest JSONL
    manifest_bytes = _build_manifest(stem_to_fid)
    manifest_file = io.BytesIO(manifest_bytes)
    manifest_upload = client.files.upload(
        file={"file_name": "batch-ocr-requests.jsonl",
              "content": manifest_file},
        purpose="batch",
    )
    manifest_fid = manifest_upload.id
    print(f"[mistral-ocr] manifest uploaded -> {manifest_fid}")

    # Submit batch job
    job = client.batch_jobs.create(
        endpoint="/v1/ocr",
        input_files=[manifest_fid],
        model="mistral-ocr-latest",
    )
    print(f"[mistral-ocr] job submitted: {job.id}  "
          f"(resume: --resume-job {job.id} --resume-map {map_path.name})")

    # Poll
    job = _poll_job(client, job.id, args.poll_interval, args.verbose)
    dur = round(time.monotonic() - t0, 1)
    print(f"[job] final status={job.status} "
          f"succeeded={job.succeeded_requests} failed={job.failed_requests} "
          f"in {dur}s")

    # Process results
    if job.status != "SUCCESS":
        print("[job] job did not succeed; no extracts written.")
        _delete_uploads(client, list(stem_to_fid.values()) + [manifest_fid],
                        args.verbose)
        return 1

    done, failed = _process_results(
        client, job, stem_to_pdf, args.type, args.verbose)

    # Cleanup uploads
    all_fids = list(stem_to_fid.values()) + [manifest_fid]
    if job.output_file:
        all_fids.append(job.output_file)
    _delete_uploads(client, all_fids, args.verbose)

    print(f"\n=== mistral-ocr done === extracted {done}, failed {failed} in {dur}s.")
    print("Next: python3 batch_convert.py --phase encode")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
