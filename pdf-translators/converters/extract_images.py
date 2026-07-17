"""
extract_images.py — Extract embedded PNG/JPG images from a PDF.

Walks every page, asks PyMuPDF for the embedded image objects on that page
(`page.get_images()`), and writes each one out in its original format via
`doc.extract_image()`.  Images referenced on multiple pages are written once
(deduped by xref).

Usage:
    python3 converters/extract_images.py input.pdf [--out DIR] [--pages RANGE] [--min-bytes N]

Examples:
    python3 converters/extract_images.py module.pdf
    python3 converters/extract_images.py module.pdf --out maps/ --pages 10-25
    python3 converters/extract_images.py module.pdf --min-bytes 8192   # skip icons/decorations
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("PyMuPDF is required.  Install with:  pip install pymupdf")


def _parse_pages(spec: str | None, total: int) -> set[int]:
    """Parse '1,3,5-8' into a 0-indexed set of page numbers."""
    if not spec:
        return set(range(total))
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            pages.update(range(int(lo) - 1, int(hi)))
        else:
            pages.add(int(part) - 1)
    return {p for p in pages if 0 <= p < total}


def extract_images(
    pdf_path: Path,
    out_dir: Path,
    pages: set[int] | None = None,
    min_bytes: int = 0,
    verbose: bool = True,
) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    target_pages = pages if pages is not None else set(range(doc.page_count))

    seen_xrefs: set[int] = set()
    written = 0
    skipped_small = 0

    for page_num in sorted(target_pages):
        page = doc[page_num]
        for img_index, info in enumerate(page.get_images(full=True), start=1):
            xref = info[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)

            data = doc.extract_image(xref)
            if not data:
                continue
            image_bytes = data["image"]
            ext = data["ext"]  # 'png', 'jpeg', 'jpg', 'jp2', etc.

            if len(image_bytes) < min_bytes:
                skipped_small += 1
                continue

            name = f"page{page_num + 1:04d}_img{img_index:02d}.{ext}"
            (out_dir / name).write_bytes(image_bytes)
            written += 1
            if verbose:
                w, h = data.get("width"), data.get("height")
                print(f"  {name}  {w}x{h}  {len(image_bytes):,} bytes")

    doc.close()

    if verbose:
        print(
            f"\nExtracted {written} image(s) to {out_dir}"
            + (f"  (skipped {skipped_small} under {min_bytes} bytes)" if skipped_small else "")
        )
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("pdf", type=Path, help="Input PDF file")
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: <pdf-stem>-images/ next to the PDF)",
    )
    ap.add_argument(
        "--pages",
        default=None,
        help="Restrict to a page range, 1-indexed, e.g. '1,3,5-8'",
    )
    ap.add_argument(
        "--min-bytes",
        type=int,
        default=0,
        help="Skip images smaller than this (useful for filtering decorative icons)",
    )
    ap.add_argument("-q", "--quiet", action="store_true", help="Suppress per-image output")
    args = ap.parse_args()

    if not args.pdf.is_file():
        sys.exit(f"Not a file: {args.pdf}")

    out = args.out or args.pdf.with_name(f"{args.pdf.stem}-images")

    doc = fitz.open(args.pdf)
    total = doc.page_count
    doc.close()
    pages = _parse_pages(args.pages, total) if args.pages else None

    extract_images(
        args.pdf,
        out,
        pages=pages,
        min_bytes=args.min_bytes,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()
