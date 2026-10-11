"""mistral_ocr.py — Mistral OCR transport for pdf-translators.

Sync path: upload PDF → OCR all pages → delete → return joined markdown.
The returned string is identical in shape to Marker's markdown output and
feeds the same parse_markdown_headings → normalise_numbered_rooms →
build_synthetic_toc pipeline.

Usage::

    from converters.mistral_ocr import run_mistral_ocr
    md_text = run_mistral_ocr(pdf_path, api_key, verbose=True)

Model: ``mistral-ocr-latest`` ($4 / 1000 pages).
SDK: ``mistralai`` 2.5.0 namespace package — import as
     ``from mistralai.client.sdk import Mistral``.
"""
from __future__ import annotations

from pathlib import Path


def run_mistral_ocr(pdf_path: Path, api_key: str, verbose: bool = False) -> str:
    """Upload *pdf_path* to Mistral, OCR all pages, delete the upload, return
    the page markdowns joined with blank lines.

    Pages are returned in page-index order regardless of API response ordering.
    The file is always deleted in a ``finally`` block even when OCR raises.
    """
    from mistralai.client.sdk import Mistral

    client = Mistral(api_key=api_key)

    if verbose:
        print(f"[mistral-ocr] uploading {pdf_path.name} ...")
    with open(pdf_path, "rb") as f:
        upload = client.files.upload(
            file={"file_name": pdf_path.name, "content": f},
            purpose="ocr",
        )
    file_id = upload.id
    if verbose:
        print(f"[mistral-ocr] uploaded -> file_id={file_id}")

    try:
        resp = client.ocr.process(
            model="mistral-ocr-latest",
            document={"type": "file", "file_id": file_id},
            table_format="markdown",
            extract_header=False,
            extract_footer=False,
        )
    finally:
        client.files.delete(file_id=file_id)
        if verbose:
            print(f"[mistral-ocr] deleted upload {file_id}")

    pages = sorted(resp.pages, key=lambda p: p.index)
    page_mds = []
    n_tbl = 0
    for p in pages:
        md = p.markdown
        # Mistral returns each table's body in page.tables[] and leaves only a
        # [tbl-N.md](tbl-N.md) link in the page markdown. Splice the content
        # back in (same as batch/batch_mistral_ocr.py); without this the
        # stat-block ability tables come out empty.
        for tbl in p.tables or []:
            if not tbl.id or not tbl.content:
                continue
            ref = f"[{tbl.id}]({tbl.id})"
            md = md.replace(ref, tbl.content) if ref in md else f"{md}\n\n{tbl.content}"
            n_tbl += 1
        page_mds.append(md)
    if verbose:
        print(f"[mistral-ocr] {len(pages)} pages OCR'd, {n_tbl} tables inlined")
    return "\n\n".join(page_mds)
