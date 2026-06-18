from __future__ import annotations

import base64
import json
from pathlib import Path

from notetaker.config import Config, UnderstandingConfig
from notetaker.contracts.slide_content import ExtractionMethod, SlideContent
from notetaker.utils.llm_json import strip_code_fence
from notetaker.utils.logging import get_logger
from notetaker.utils.retry import retry

logger = get_logger(__name__)

_EXTRACTION_PROMPT = """\
You are extracting structured content from a presentation slide image.

Return ONLY a JSON object with these exact keys:
{
  "title": "<slide title, or empty string if none>",
  "bullets": ["<bullet text>", ...],
  "visual_description": "<plain-language description of any chart, diagram, or image; empty string if text-only>",
  "raw_ocr": "<all visible text on the slide in reading order>"
}

Do not include any explanation or markdown fencing — just the raw JSON object.
"""


def _estimate_cost(input_tokens: int, output_tokens: int, cfg: UnderstandingConfig) -> float:
    return (
        input_tokens / 1_000_000 * cfg.input_token_price_per_million
        + output_tokens / 1_000_000 * cfg.output_token_price_per_million
    )


def extract_slide_vision(
    frame_path: Path,
    frame_sha256: str,
    slide_id: str,
    config: Config,
    client=None,
    debug_dir: Path | None = None,
) -> tuple[SlideContent, float]:
    """
    Extract slide content using the Claude vision API.

    Returns (SlideContent, estimated_cost_usd).
    client is injected for testing; if None, creates a real anthropic.Anthropic().
    debug_dir, if set, receives a raw response dump keyed by frame_sha256.
    """
    if client is None:
        import anthropic
        client = anthropic.Anthropic()

    image_data = base64.standard_b64encode(frame_path.read_bytes()).decode()

    @retry(
        attempts=config.api.retry_count,
        delay=config.api.retry_delay_seconds,
    )
    def _call() -> tuple[str, int, int]:
        response = client.messages.create(
            model=config.understanding.vision_model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": _EXTRACTION_PROMPT},
                    ],
                }
            ],
        )
        text = response.content[0].text
        in_tok = response.usage.input_tokens
        out_tok = response.usage.output_tokens
        return text, in_tok, out_tok

    raw_text, in_tok, out_tok = _call()
    cost = _estimate_cost(in_tok, out_tok, config.understanding)

    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        debug_path = debug_dir / f"{frame_sha256}.raw.json"
        debug_path.write_text(json.dumps(
            {
                "slide_id": slide_id,
                "frame_sha256": frame_sha256,
                "model": config.understanding.vision_model,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "estimated_cost_usd": cost,
                "raw_response_text": raw_text,
            },
            indent=2,
        ))

    try:
        parsed = json.loads(strip_code_fence(raw_text))
    except json.JSONDecodeError as exc:
        logger.warning("vision.json_parse_error", slide_id=slide_id, error=str(exc))
        parsed = {"title": "", "bullets": [], "visual_description": "", "raw_ocr": raw_text}

    content = SlideContent(
        slide_id=slide_id,
        title=parsed.get("title", ""),
        bullets=parsed.get("bullets", []),
        visual_description=parsed.get("visual_description", ""),
        raw_ocr=parsed.get("raw_ocr", ""),
        extraction_method=ExtractionMethod.vision,
        estimated_cost_usd=cost,
    )

    logger.debug(
        "vision.extracted",
        slide_id=slide_id,
        tokens_in=in_tok,
        tokens_out=out_tok,
        cost_usd=cost,
    )
    return content, cost
