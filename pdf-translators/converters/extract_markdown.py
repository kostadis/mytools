"""extract_markdown.py — PDF → Markdown via OCR.

Runs OCR on a PDF and writes the result as a single ``.md`` file. No LLM
calls, no Anthropic key needed. The output is human-readable and editable —
fix heading levels, remove cover-page fragments, adjust structure — before
feeding it to the converter:

    python3 converters/extract_markdown.py input.pdf                 # Marker (local GPU)
    python3 converters/extract_markdown.py input.pdf --provider mistral
    # edit input.md as needed
    python3 converters/pdf_to_5etools_v2.py input.pdf --from-markdown input.md

Providers:
  marker   — local ML pipeline (requires marker-env/ venv, ~5 GB weights).
             GPU strongly recommended; CPU is 10-30s/page.
  mistral  — Mistral OCR API (mistral-ocr-latest, $4/1000 pages).
             Requires MISTRAL_API_KEY or --mistral-api-key.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("pdf", type=Path, help="Input PDF file.")
    p.add_argument(
        "--provider", choices=["marker", "mistral"], default="marker",
        help="OCR backend (default: marker).",
    )
    p.add_argument(
        "--mistral-api-key", default=None, dest="mistral_api_key",
        help="Mistral API key (also read from MISTRAL_API_KEY). "
             "Required with --provider mistral.",
    )
    p.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Output markdown file (default: <stem>.md next to the PDF).",
    )
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    pdf_path: Path = args.pdf

    if not pdf_path.exists():
        print(f"error: {pdf_path} does not exist")
        return 1

    out_path: Path = args.output or pdf_path.with_suffix(".md")

    if args.provider == "mistral":
        api_key = args.mistral_api_key or os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            print("error: --provider mistral requires MISTRAL_API_KEY or --mistral-api-key")
            return 1
        from converters.mistral_ocr import run_mistral_ocr
        print(f"[extract] Mistral OCR: {pdf_path.name} ...")
        md_text = run_mistral_ocr(pdf_path, api_key, verbose=args.verbose)

    else:  # marker
        from converters.pdf_to_5etools_v2 import run_marker
        print(f"[extract] Marker OCR: {pdf_path.name} ...")
        with tempfile.TemporaryDirectory(prefix="marker-") as tmp:
            md_path = run_marker(pdf_path, Path(tmp), verbose=args.verbose)
            md_text = md_path.read_text()

    out_path.write_text(md_text, encoding="utf-8")
    print(f"[extract] wrote {out_path}  ({len(md_text):,} chars, "
          f"{md_text.count(chr(10)):,} lines)")
    print(f"[extract] edit {out_path.name} if needed, then:")
    print(f"  python3 converters/pdf_to_5etools_v2.py {pdf_path.name} "
          f"--from-markdown {out_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
