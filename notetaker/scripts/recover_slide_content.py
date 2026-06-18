"""
One-shot recovery for slide_content.json files produced before the fenced-JSON
parser fix. Each affected slide has its real Haiku output stuffed into raw_ocr
as a stringified ```json ... ``` block, with title/bullets/visual_description
left empty. This script strips the fence and lifts the inner fields back into
place. Idempotent: slides that already have a non-empty title are skipped.

Usage:
    python scripts/recover_slide_content.py <path-to-slide_content.json>

Writes a sibling .bak before modifying the file in place.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from notetaker.contracts.slide_content import SlideContentSchema
from notetaker.utils.llm_json import strip_code_fence


def recover(path: Path) -> tuple[int, int, int]:
    data = json.loads(path.read_text())
    SlideContentSchema.model_validate(data)

    fixed = skipped_ok = unrecoverable = 0

    for slide in data["slides"]:
        if slide["title"] or slide["bullets"] or slide["visual_description"]:
            skipped_ok += 1
            continue

        raw = slide.get("raw_ocr", "")
        if not raw.lstrip().startswith("```"):
            unrecoverable += 1
            continue

        try:
            inner = json.loads(strip_code_fence(raw))
        except json.JSONDecodeError:
            unrecoverable += 1
            continue

        slide["title"] = inner.get("title", "")
        slide["bullets"] = inner.get("bullets", [])
        slide["visual_description"] = inner.get("visual_description", "")
        slide["raw_ocr"] = inner.get("raw_ocr", "")
        fixed += 1

    SlideContentSchema.model_validate(data)

    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(json.dumps(data, indent=2))

    return fixed, skipped_ok, unrecoverable


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2

    path = Path(argv[1]).expanduser()
    if not path.is_file():
        print(f"not a file: {path}", file=sys.stderr)
        return 1

    fixed, skipped_ok, unrecoverable = recover(path)
    total = fixed + skipped_ok + unrecoverable
    print(f"slides: {total}  fixed: {fixed}  already-ok: {skipped_ok}  unrecoverable: {unrecoverable}")
    print(f"backup: {path.with_suffix(path.suffix + '.bak')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
