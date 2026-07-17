"""batch_mistral_ocr.py — Mistral OCR extraction pass using the Batch API.

Run this AFTER ``batch_convert.py --phase extract`` (the fast PyMuPDF pass).
The fast pass handles bookmarked digital PDFs and *defers* everything else
(scans, un-bookmarked digital) as ``needs_ocr`` — those docs have no
``<stem>-extract.json``. This tool submits all such PDFs to the Mistral Batch
API in a single job (~50% cheaper than individual sync calls, async), producing
the same ``<stem>-extract.json`` artifact (``kind="lines"``) the encode pass
consumes. For the local Marker pipeline instead, use ``batch_marker.py``.

Workflow::

    python3 batch/batch_convert.py --phase extract          # fast structural extraction
    python3 batch/batch_mistral_ocr.py --no-profile          # this tool — Mistral OCR the rest
    python3 batch/batch_convert.py --phase encode            # in-process LLM conversion

Typical run of THIS tool (after --phase extract has run)::

    export MISTRAL_API_KEY=...
    python3 batch/batch_mistral_ocr.py --no-profile --limit 5 --verbose

  --no-profile  skips the slow per-PDF routing check (every doc lacking both
                <stem>.json and <stem>-extract.json is taken as OCR-bound) —
                seconds instead of minutes on a network mount.
  --limit N     submit at most N docs (the Mistral free tier caps a batch job
                at 10); re-run the same command to take the next N — docs that
                already produced an extract are skipped automatically.

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
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from lib.batch_state import StateDB

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
    p.add_argument("--no-images", action="store_true",
                   help="Don't request/save embedded page images. By default the "
                        "OCR request sets include_image_base64=True and each page "
                        "image is written to <stem>-mistral-images/ with the "
                        "markdown link rewritten to point at it. Use this to keep "
                        "the batch result small when you only need the text.")
    p.add_argument("--no-profile", action="store_true",
                   help="Skip the per-PDF fast-path/OCR routing check (which "
                        "opens every candidate PDF — slow on a network mount). "
                        "Treats any doc lacking both <stem>.json and "
                        "<stem>-extract.json as OCR-bound. Sound after "
                        "'batch_convert --phase extract' has run.")
    p.add_argument("--rebuild-from-raw", action="store_true",
                   dest="rebuild_from_raw",
                   help="Re-render <stem>-mistral.md / images / extract from "
                        "saved <stem>-mistral-raw.json files. NO API calls, no "
                        "cost. Use to re-apply a parsing change (e.g. table "
                        "inlining) across every already-OCR'd doc. Respects "
                        "--limit; ignores --force/--no-profile.")
    p.add_argument("--limit", type=int, default=0, metavar="N",
                   help="Submit at most N docs this run (0 = no limit). The "
                        "Mistral free tier caps a batch job at 10 documents, so "
                        "--limit 10 keeps each run inside it; re-run to take the "
                        "next N (docs that got an extract are skipped on resume).")
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


def _select(root: Path, rels: list[str], force: bool, profile_pdf,
            skip_profile: bool = False) -> list[Path]:
    """Filter to docs that lack an extract and route to the OCR path.

    With ``skip_profile`` the per-doc ``profile_pdf`` call is skipped: any doc
    lacking both ``<stem>.json`` and ``<stem>-extract.json`` is taken as
    OCR-bound. This is sound after ``batch_convert --phase extract`` has run
    (the fast path writes an extract for everything it can handle and defers the
    rest), and avoids opening every PDF off a slow mount just to re-derive the
    routing. Don't use it if the extract phase hasn't run — fast-path-eligible
    docs would then be sent to OCR too."""
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
        if skip_profile:
            selected.append(pdf)
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


def _build_manifest(stem_to_fid: dict[str, str],
                    include_images: bool = True) -> bytes:
    """Build the JSONL batch manifest bytes. With include_images, each request
    asks for the page images inline (base64) so _process_results can save them."""
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
                "include_image_base64": include_images,
            },
        }
        lines.append(json.dumps(req))
    return "\n".join(lines).encode()


def _poll_job(client, job_id: str, poll_interval: int, verbose: bool):
    """Poll until terminal status; return the final BatchJob object."""
    terminal = {"SUCCESS", "FAILED", "TIMEOUT_EXCEEDED", "CANCELLED"}
    while True:
        job = client.batch.jobs.get(job_id=job_id)
        status = job.status
        done = job.completed_requests
        total = job.total_requests
        if verbose or True:  # always print progress for long-running jobs
            print(f"[poll] job={job_id} status={status} "
                  f"completed={done}/{total}", flush=True)
        if status in terminal:
            return job
        time.sleep(poll_interval)


def _raw_path(pdf: Path) -> Path:
    """Path of the complete raw OCR response saved next to a PDF."""
    return pdf.with_name(pdf.stem + "-mistral-raw.json")


def _render_doc(body: dict, pdf: Path, output_type: str, verbose: bool,
                save_raw: bool = True) -> bool:
    """Render one doc's OCR response body into all on-disk artifacts:
    <stem>-mistral-raw.json (the COMPLETE response, saved first so nothing is
    ever lost), <stem>-mistral-images/, <stem>-mistral.md (images saved +
    tables inlined), and <stem>-extract.json (for the encode pass).

    Because the full response is persisted, any later parsing change can be
    re-applied for free via --rebuild-from-raw — no re-OCR. Returns True on a
    successfully written extract."""
    import converters.pdf_to_5etools_v2 as v2
    import lib.chunk_cache as cc

    stem = pdf.stem

    # 1. Persist the complete raw response FIRST — the single source of truth.
    if save_raw:
        try:
            _raw_path(pdf).write_text(json.dumps(body), encoding="utf-8")
        except OSError as e:
            print(f"[results] WARN {stem}: could not write raw response: {e}")

    pages = sorted(body.get("pages", []), key=lambda p: p["index"])

    # 2. Save embedded page images into a per-doc subfolder and rewrite each
    # page's markdown link to the saved file. Filenames are page-prefixed so a
    # repeated id like img-0.jpeg across pages doesn't collide. Image bytes are
    # base64, optionally as a data: URI.
    img_dir = pdf.with_name(pdf.stem + "-mistral-images")
    n_img = 0
    n_tbl = 0
    page_mds = []
    for p in pages:
        md = p["markdown"]
        for img in p.get("images") or []:
            iid = img.get("id")
            b64 = img.get("image_base64")
            if not iid or not b64:
                continue
            data = b64.split(",", 1)[1] if b64.startswith("data:") else b64
            fname = f"p{p['index']:03d}-{iid}"
            try:
                img_dir.mkdir(exist_ok=True)
                (img_dir / fname).write_bytes(base64.b64decode(data))
                n_img += 1
            except (OSError, ValueError) as e:
                print(f"[results] WARN {stem}: image {iid}: {e}")
                continue
            md = md.replace(f"]({iid})", f"]({img_dir.name}/{fname})")
        # 3. Inline tables: Mistral returns each table's body in page.tables[]
        # (id + markdown/html content) and leaves only a [tbl-N.md](tbl-N.md)
        # link in the page markdown. Splice the real content in so the table
        # survives into the .md and into units[] for the encode pass; without
        # this the stat-block ability tables come out empty.
        for tbl in p.get("tables") or []:
            tid = tbl.get("id")
            content = tbl.get("content")
            if not tid or not content:
                continue
            ref = f"[{tid}]({tid})"
            if ref in md:
                md = md.replace(ref, content)
            else:
                md = f"{md}\n\n{content}"  # ref not found — append as fallback
            n_tbl += 1
        page_mds.append(md)
    md_text = "\n\n".join(page_mds)

    # 4. Persist the rendered markdown for cleanup in markdown_editor.py
    # (--from-markdown). Suffixed so it never collides with a Marker <stem>.md.
    md_path = pdf.with_name(pdf.stem + "-mistral.md")
    try:
        md_path.write_text(md_text, encoding="utf-8")
        if verbose:
            bits = []
            if n_img:
                bits.append(f"+{n_img} images -> {img_dir.name}/")
            if n_tbl:
                bits.append(f"+{n_tbl} tables inlined")
            extra = f" ({', '.join(bits)})" if bits else ""
            print(f"[results] md   {stem} -> {md_path.name}{extra}")
    except OSError as e:
        print(f"[results] WARN {stem}: could not write {md_path.name}: {e}")

    # 5. Build the extract the encode pass consumes.
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
        if verbose:
            print(f"[results] OK  {stem} -> {extract_path.name}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[results] FAIL {stem}: pipeline error {type(e).__name__}: {e}")
        return False


def _download_jsonl(client, file_id: str) -> list[dict]:
    """Download a Mistral batch output/error file and parse its JSONL lines.

    files.download returns a *streaming* httpx.Response; its body must be
    read() before .text is accessible (else httpx.ResponseNotRead)."""
    resp = client.files.download(file_id=file_id)
    text = resp.read().decode("utf-8").strip()
    return [json.loads(line) for line in text.splitlines() if line]


def _error_message(rec: dict) -> tuple[int | None, object]:
    """Best-effort (status_code, human message) from a batch error record.

    Mistral records the provider error either at ``rec['error']`` or in
    ``rec['response']['body']``; ``body`` is often a JSON *string* whose
    ``message`` field is the readable text (e.g. 'File is too large...')."""
    resp = rec.get("response") or {}
    code = resp.get("status_code")
    raw = rec.get("error")
    if raw is None:
        raw = resp.get("body")
    msg = raw
    if isinstance(raw, str):
        try:
            msg = json.loads(raw).get("message", raw)
        except (ValueError, AttributeError):
            msg = raw
    elif isinstance(raw, dict):
        msg = raw.get("message", raw)
    return code, msg


def _process_results(client, job, stem_to_pdf: dict[str, Path],
                     output_type: str, verbose: bool) -> tuple[int, int]:
    """Render artifacts from the batch OUTPUT file (successes) and surface the
    reason for every failure from the ERROR file. Mistral routes failed
    requests to ``job.error_file`` — not the output file — so without reading it
    a ``failed=N`` count has no explanation. Returns (done, failed) counts."""
    done = failed = 0
    seen: set = set()

    # 1. Successes: the output file.
    output_fid = getattr(job, "output_file", None)
    if output_fid:
        if verbose:
            print(f"[results] downloading output file {output_fid} ...")
        for rec in _download_jsonl(client, output_fid):
            stem = rec.get("custom_id")
            pdf = stem_to_pdf.get(stem)
            if pdf is None:
                print(f"[results] unknown custom_id {stem!r} in output — skipping")
                continue
            seen.add(stem)
            status_code = (rec.get("response") or {}).get("status_code")
            if status_code != 200:  # defensive: shouldn't appear in output file
                code, msg = _error_message(rec)
                print(f"[results] FAIL {pdf.name}: status {code}: {msg}")
                failed += 1
                continue
            if _render_doc(rec["response"]["body"], pdf, output_type, verbose):
                done += 1
                print(f"[results] OK   {pdf.with_name(pdf.stem + '-extract.json')}")
            else:
                failed += 1
    else:
        print("[results] job has no output_file — no requests succeeded.")

    # 2. Failures: the error file — print each doc's actual reason.
    error_fid = getattr(job, "error_file", None)
    if error_fid:
        if verbose:
            print(f"[results] downloading error file {error_fid} ...")
        for rec in _download_jsonl(client, error_fid):
            stem = rec.get("custom_id")
            if stem in seen:
                continue
            seen.add(stem)
            code, msg = _error_message(rec)
            pdf = stem_to_pdf.get(stem)
            label = pdf.name if pdf else (stem or "<unknown>")
            print(f"[results] FAIL {label}: status {code}: {msg}")
            failed += 1

    # 3. Anything that appeared in neither file.
    for stem, pdf in stem_to_pdf.items():
        if stem not in seen:
            print(f"[results] FAIL {pdf.name}: no result returned "
                  f"(custom_id {stem!r} in neither output nor error file)")
            failed += 1

    return done, failed


def _rebuild_from_raw(root: Path, rels: list[str], output_type: str,
                      verbose: bool) -> tuple[int, int]:
    """Re-render artifacts from saved <stem>-mistral-raw.json files — NO API
    calls, no cost. Use after a parsing change (e.g. the table-inlining fix) to
    refresh every already-OCR'd doc for free. Returns (done, skipped)."""
    done = skipped = 0
    for rel in rels:
        pdf = root / rel
        raw = _raw_path(pdf)
        if not raw.exists():
            skipped += 1
            continue
        try:
            body = json.loads(raw.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"[rebuild] FAIL {pdf.stem}: bad raw file: {e}")
            skipped += 1
            continue
        # save_raw=False: the raw file is the input, don't rewrite it.
        if _render_doc(body, pdf, output_type, verbose, save_raw=False):
            done += 1
    return done, skipped


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
    if not api_key and not args.list and not args.rebuild_from_raw:
        sys.exit("error: MISTRAL_API_KEY not set and --mistral-api-key not provided")

    rels = _candidate_rels(root, args.state_db)

    if args.rebuild_from_raw:
        # Offline re-render from saved raw responses — no API, no cost.
        have_raw = [rel for rel in rels if _raw_path(root / rel).exists()]
        if args.limit and len(have_raw) > args.limit:
            print(f"[rebuild] --limit {args.limit}: rebuilding the first "
                  f"{args.limit} of {len(have_raw)} docs with a raw response.")
            have_raw = have_raw[:args.limit]
        else:
            print(f"[rebuild] {len(have_raw)} doc(s) have a saved raw response.")
        done, skipped = _rebuild_from_raw(root, have_raw, args.type, args.verbose)
        print(f"\n=== rebuild done === re-rendered {done}.")
        return 0

    from converters.pdf_to_5etools_v2 import profile_pdf

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

    selected = _select(root, rels, args.force, profile_pdf,
                       skip_profile=args.no_profile)
    print(f"[mistral-ocr] {len(selected)} doc(s) need Mistral OCR "
          f"(of {len(rels)} content docs under {root})")

    if args.limit and len(selected) > args.limit:
        print(f"[mistral-ocr] --limit {args.limit}: submitting the first "
              f"{args.limit}; {len(selected) - args.limit} deferred to a "
              f"later run.")
        selected = selected[:args.limit]

    if args.list or not selected:
        for pdf in selected:
            print(f"  - {os.path.relpath(str(pdf), str(root))}")
        if args.list:
            return 0
        print("[mistral-ocr] nothing to do.")
        return 0

    # Name exactly which docs this run will OCR, and where each output lands
    # (<stem>-extract.json next to the source PDF), so the files are findable.
    print(f"[mistral-ocr] submitting {len(selected)} doc(s) for OCR:")
    for pdf in selected:
        print(f"  - {os.path.relpath(str(pdf), str(root))}")
        print(f"      -> {pdf.with_name(pdf.stem + '-extract.json')}")

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

    # Upload manifest JSONL. Pass raw bytes (not BytesIO): the mistralai 2.5.0
    # File.content union accepts bytes | IO | BufferedReader, and its pydantic
    # is-instance checks reject a BytesIO — while bytes validate directly.
    manifest_bytes = _build_manifest(stem_to_fid,
                                     include_images=not args.no_images)
    manifest_upload = client.files.upload(
        file={"file_name": "batch-ocr-requests.jsonl",
              "content": manifest_bytes},
        purpose="batch",
    )
    manifest_fid = manifest_upload.id
    print(f"[mistral-ocr] manifest uploaded -> {manifest_fid}")

    # Submit batch job
    job = client.batch.jobs.create(
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
    print("Next: python3 batch/batch_convert.py --phase encode")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
