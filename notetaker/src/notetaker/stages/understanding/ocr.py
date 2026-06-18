from __future__ import annotations

from pathlib import Path

import pytesseract
from PIL import Image

from notetaker.contracts.slide_content import ExtractionMethod, SlideContent
from notetaker.utils.logging import get_logger

logger = get_logger(__name__)


def extract_slide_ocr(frame_path: Path, slide_id: str) -> SlideContent:
    """
    Extract slide content using Tesseract OCR.

    Title heuristic: first non-empty line.
    Bullets heuristic: subsequent non-empty lines.
    """
    raw_text = pytesseract.image_to_string(Image.open(frame_path)).strip()

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    title = lines[0] if lines else ""
    bullets = lines[1:] if len(lines) > 1 else []

    logger.debug("ocr.extracted", slide_id=slide_id, lines=len(lines))

    return SlideContent(
        slide_id=slide_id,
        title=title,
        bullets=bullets,
        visual_description="",
        raw_ocr=raw_text,
        extraction_method=ExtractionMethod.ocr,
        estimated_cost_usd=0.0,
    )
