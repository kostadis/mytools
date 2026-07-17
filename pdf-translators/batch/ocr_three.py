#!/usr/bin/env python3
"""ocr_three.py — Mistral-OCR a short, explicit list of PDFs.

The three docs below are the ones that FAILED the encode pass (partial /
oversized-chunk 400s) and that you tagged with `--force-marker` in their
`.extract_skip` files. They're fast-path-eligible (they have bookmarks), so the
normal `batch_mistral_ocr.py` won't select them — it skips any doc that already
has an `<stem>-extract.json`, and `--force` would re-OCR the whole tree. This
script bypasses selection entirely and runs the *same* tested OCR machinery
(upload → manifest → batch job → poll → render) on exactly the files you name.

Each doc's fast-path `<stem>-extract.json` is OVERWRITTEN with a fresh
Mistral-OCR one (kind="lines"), plus `<stem>-mistral.md`, `-mistral-raw.json`,
and `-mistral-images/`, exactly as the batch tool writes them.

Usage::

    export MISTRAL_API_KEY=...
    python3 batch/ocr_three.py                 # the three hardcoded failures
    python3 batch/ocr_three.py a.pdf b.pdf     # or any explicit PDFs you pass

Then encode them into 5etools JSON:

    python3 batch/batch_convert.py --plan reuse --phase encode
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Reuse the tested Batch-API helpers — no logic is duplicated here.
from batch.batch_mistral_ocr import (
    _upload_pdfs,
    _build_manifest,
    _poll_job,
    _process_results,
    _delete_uploads,
    HERE,
)

ROOT = Path("/mnt/g/My Drive/DriveThru/Dungeon Masters Guild")

# The three encode-phase failures, relative to ROOT.
DEFAULT_TARGETS = [
    "The Book of Dragons for 5th Edition/1347866-The_Book_of_Dragons_5e.pdf",
    "The Infernal Codex_ Expanding Chains of Asmodeus/3628189-The_Infernal_Codex_-_The_Homebrewery.pdf",
    "The Infernal Codex_ Expanding Chains of Asmodeus/3628189-The_Infernal_Codex_-_The_Supreme_Copy_-_The_Homebrewery.pdf",
]

POLL_INTERVAL = 30  # seconds
OUTPUT_TYPE = "adventure"  # recorded in the extract meta


def resolve_targets(argv: list[str]) -> list[Path]:
    """Explicit PDF args if given, else the three hardcoded failures."""
    if argv:
        pdfs = [Path(a).expanduser() for a in argv]
    else:
        pdfs = [ROOT / rel for rel in DEFAULT_TARGETS]
    resolved = []
    for pdf in pdfs:
        if not pdf.exists():
            sys.exit(f"error: PDF not found: {pdf}")
        resolved.append(pdf)
    return resolved


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    pdfs = resolve_targets(argv)

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        sys.exit("error: MISTRAL_API_KEY not set")

    print(f"[ocr-three] OCRing {len(pdfs)} doc(s):")
    for pdf in pdfs:
        print(f"  - {pdf.name}")
        print(f"      -> {pdf.with_name(pdf.stem + '-extract.json')}")

    from mistralai.client.sdk import Mistral
    client = Mistral(api_key=api_key)

    t0 = time.monotonic()

    # 1. Upload the PDFs.
    print(f"[ocr-three] uploading {len(pdfs)} PDFs ...")
    stem_to_fid = _upload_pdfs(client, pdfs, verbose=True)
    stem_to_pdf = {pdf.stem: pdf for pdf in pdfs}

    # Save a resume map so an interrupted poll can be picked back up with
    # `batch_mistral_ocr.py --resume-job JOB_ID --resume-map ocr-three-map.json`.
    map_path = HERE / "ocr-three-map.json"
    map_path.write_text(
        json.dumps({s: str(p) for s, p in stem_to_pdf.items()}, indent=2))
    print(f"[ocr-three] stem map saved to {map_path.name}")

    # 2. Upload the JSONL manifest (raw bytes — see batch_mistral_ocr notes).
    manifest_bytes = _build_manifest(stem_to_fid, include_images=True)
    manifest_upload = client.files.upload(
        file={"file_name": "ocr-three-requests.jsonl", "content": manifest_bytes},
        purpose="batch",
    )
    manifest_fid = manifest_upload.id
    print(f"[ocr-three] manifest uploaded -> {manifest_fid}")

    # 3. Submit the OCR batch job.
    job = client.batch.jobs.create(
        endpoint="/v1/ocr",
        input_files=[manifest_fid],
        model="mistral-ocr-latest",
    )
    print(f"[ocr-three] job submitted: {job.id}")
    print(f"           resume: python3 batch/batch_mistral_ocr.py "
          f"--resume-job {job.id} --resume-map {map_path.name}")

    # 4. Poll to completion.
    job = _poll_job(client, job.id, POLL_INTERVAL, verbose=True)
    dur = round(time.monotonic() - t0, 1)
    print(f"[job] final status={job.status} "
          f"succeeded={job.succeeded_requests} failed={job.failed_requests} "
          f"in {dur}s")

    if job.status != "SUCCESS":
        print("[job] job did not succeed; no extracts written.")
        _delete_uploads(client, list(stem_to_fid.values()) + [manifest_fid],
                        verbose=True)
        return 1

    # 5. Download results and render extracts / markdown / images.
    done, failed = _process_results(client, job, stem_to_pdf, OUTPUT_TYPE,
                                    verbose=True)

    # 6. Best-effort cleanup of uploaded files.
    all_fids = list(stem_to_fid.values()) + [manifest_fid]
    if job.output_file:
        all_fids.append(job.output_file)
    _delete_uploads(client, all_fids, verbose=True)

    print(f"\n=== ocr-three done === extracted {done}, failed {failed} in {dur}s.")
    print("Next: python3 batch/batch_convert.py --plan reuse --phase encode")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
