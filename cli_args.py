"""
cli_args.py — Shared argparse helpers for all pdf-to-5etools converters.

When adding, removing, or changing a shared CLI argument, edit this file ONLY.
Each converter adds its own unique arguments after calling the helpers here.

Functions
---------
add_common_args(parser, *, default_chunk, default_model)
    Arguments shared by ALL THREE converters (pdf_to_5etools, _ocr, _1e).

add_ocr_args(parser, *, default_dpi)
    Arguments shared by the OCR and 1e converters (--dpi, --force-ocr, --lang).
"""

from __future__ import annotations

import argparse
from pathlib import Path


def add_common_args(
    parser: argparse.ArgumentParser,
    *,
    default_chunk: int,
    default_model: str,
) -> None:
    """Add CLI arguments shared by all three converters."""
    parser.add_argument("pdf", type=Path, help="Input PDF file")
    parser.add_argument(
        "--type",
        choices=["adventure", "book"],
        default="adventure",
        dest="output_type",
        help="Content type (default: adventure)",
    )
    parser.add_argument(
        "--output-mode",
        choices=["homebrew", "server"],
        default="homebrew",
        dest="output_mode",
        help=(
            "homebrew = single file for Load from File (default); "
            "server = two files for permanent server install"
        ),
    )
    parser.add_argument(
        "--id",
        default=None,
        dest="short_id",
        help="Short uppercase ID, e.g. MYMOD (default: derived from filename)",
    )
    parser.add_argument("--author", default="Unknown", help="Author name")
    parser.add_argument(
        "--out", type=Path, default=None,
        help="Full output filename (overrides --output-dir)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None, dest="output_dir",
        help="Directory to write output file(s) into (default: same folder as the PDF)",
    )
    parser.add_argument("--api-key", default=None, help="Anthropic API key")
    parser.add_argument(
        "--pages-per-chunk",
        type=int,
        default=default_chunk,
        dest="chunk_size",
        help=f"Pages per Claude call (default: {default_chunk})",
    )
    parser.add_argument(
        "--model",
        default=default_model,
        help=f"Claude model (default: {default_model})",
    )
    parser.add_argument(
        "--extract-monsters",
        action="store_true",
        dest="extract_monsters",
        help=(
            "Run a second Claude pass on each chunk to extract monster stat blocks "
            "into the bestiary. Monsters appear in bestiary.html after loading."
        ),
    )
    parser.add_argument(
        "--monsters-only",
        action="store_true",
        dest="monsters_only",
        help=(
            "Skip adventure text extraction entirely — only extract monster stat "
            "blocks. Produces a bestiary-only homebrew JSON. Fastest and cheapest "
            "if you only need the bestiary entries."
        ),
    )
    parser.add_argument(
        "--debug-dir",
        type=Path,
        default=None,
        dest="debug_dir",
        help=(
            "Directory to save raw chunk inputs and Claude responses for debugging. "
            "Creates one -input.txt and one -response.txt / -parsed.json per chunk."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run_only",
        help=(
            "Count tokens and estimate API cost without calling Claude. "
            "Requires an API key (token counting is free)."
        ),
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--no-toc-hint",
        action="store_true",
        dest="no_toc_hint",
        help="Do not inject the PDF bookmark outline as a section hint for Claude.",
    )
    parser.add_argument(
        "--pages", default=None, metavar="RANGE",
        help='Only process these pages, e.g. "10-20" or "5,10-15".',
    )
    parser.add_argument(
        "--page", type=int, default=None, metavar="N",
        help="Only process this single page number.",
    )


def add_ocr_args(
    parser: argparse.ArgumentParser,
    *,
    default_dpi: int,
) -> None:
    """Add OCR-specific arguments shared by the OCR and 1e converters."""
    parser.add_argument(
        "--dpi", type=int, default=default_dpi,
        help=f"DPI for OCR rendering (default: {default_dpi})",
    )
    parser.add_argument(
        "--force-ocr",
        action="store_true",
        help="OCR every page, even those with digital text",
    )
    parser.add_argument(
        "--lang", default="eng",
        help="Tesseract language code (default: eng)",
    )
