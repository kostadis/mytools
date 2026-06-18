from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from notetaker.cache import Cache, url_hash
from notetaker.config import Config
from notetaker.contracts.slide_content import SlideContent, SlideContentSchema
from notetaker.contracts.slide_timeline import SlideTimelineSchema
from notetaker.stages.understanding.ocr import extract_slide_ocr
from notetaker.stages.understanding.vision import extract_slide_vision
from notetaker.utils.heartbeat import HeartbeatTracker, stage_lifecycle
from notetaker.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class UnderstandingResult:
    vision_count: int
    ocr_count: int
    total_cost_usd: float
    output_path: Path


def _tracker(config: Config) -> HeartbeatTracker:
    return getattr(
        config,
        "_heartbeat_tracker",
        HeartbeatTracker(config.logging.heartbeat_interval_seconds),
    )


async def run(
    url: str, config: Config, force: bool = False, debug: bool = False
) -> UnderstandingResult:
    """Run the Slide Understanding stage for the given recording URL."""
    tracker = _tracker(config)
    async with stage_lifecycle(
        "understand",
        tracker=tracker,
        recording_url_hash=url_hash(url),
    ) as life:
        cache = Cache(config.cache_dir_path, recording_url=url, force=force)
        output_path = cache.artifact_path("understanding", "slide_content.json")
        debug_dir = (cache.stage_dir("understanding") / "raw") if debug else None

        if not force and cache.is_hit("understanding", "slide_content.json"):
            logger.info("understanding.cache_hit")
            raw = json.loads(output_path.read_text())
            schema = SlideContentSchema.model_validate(raw)
            vision_count = sum(1 for s in schema.slides if s.extraction_method.value == "vision")
            ocr_count = sum(1 for s in schema.slides if s.extraction_method.value == "ocr")
            life.end_payload.update(
                vision_count=vision_count,
                ocr_count=ocr_count,
                total_cost_usd=schema.total_cost_usd,
                output_path=str(output_path),
                cache_hit=True,
            )
            return UnderstandingResult(
                vision_count=vision_count,
                ocr_count=ocr_count,
                total_cost_usd=schema.total_cost_usd,
                output_path=output_path,
            )

        timeline_path = cache.artifact_path("extraction", "slide_timeline.json")
        if not timeline_path.exists():
            raise FileNotFoundError(
                f"slide_timeline.json not found at {timeline_path}. "
                "Run 'notetaker extract <url>' first."
            )

        timeline = SlideTimelineSchema.model_validate(json.loads(timeline_path.read_text()))

        # Build a mapping from slide_id → (frame_path, frame_sha256) for unique slides only
        seen_ids: dict[str, tuple[Path, str]] = {}
        for occ in timeline.slides:
            if occ.slide_id not in seen_ids:
                seen_ids[occ.slide_id] = (Path(occ.frame_path), occ.frame_sha256)

        # Per-sha256 vision cache (survives across runs)
        vision_cache_dir = cache.stage_dir("understanding") / "vision_cache"
        vision_cache_dir.mkdir(parents=True, exist_ok=True)

        slides: list[SlideContent] = []
        total_cost_usd = 0.0
        vision_count = 0
        ocr_count = 0
        budget = config.understanding.budget_ceiling_usd
        budget_exhausted = False

        unique_total = len(seen_ids)
        for i, (slide_id, (frame_path, sha256)) in enumerate(seen_ids.items(), start=1):
            life.tick(
                "slides",
                processed=i,
                unique_total=unique_total,
                vision=vision_count,
                ocr=ocr_count,
            )
            cache_file = vision_cache_dir / f"{sha256}.json"

            if cache_file.exists():
                content = SlideContent.model_validate(json.loads(cache_file.read_text()))
                content = content.model_copy(update={"slide_id": slide_id})
                logger.debug("understanding.vision_cache_hit", slide_id=slide_id)
            elif budget_exhausted or total_cost_usd >= budget:
                if not budget_exhausted:
                    budget_exhausted = True
                    logger.warning(
                        "understanding.budget_exhausted",
                        spent_usd=total_cost_usd,
                        ceiling_usd=budget,
                    )
                content = extract_slide_ocr(frame_path, slide_id)
                ocr_count += 1
            else:
                try:
                    content, cost = extract_slide_vision(
                        frame_path, sha256, slide_id, config, debug_dir=debug_dir
                    )
                    total_cost_usd += cost
                    vision_count += 1
                    logger.info(
                        "understanding.vision_extracted",
                        slide_id=slide_id,
                        cost_usd=cost,
                        running_total_usd=total_cost_usd,
                    )
                    # Cache the result by sha256
                    cache_file.write_text(content.model_dump_json(indent=2))
                except Exception as exc:
                    logger.warning("understanding.vision_failed", slide_id=slide_id, error=str(exc))
                    content = extract_slide_ocr(frame_path, slide_id)
                    ocr_count += 1

            slides.append(content)

        schema = SlideContentSchema(
            recording_url=url,
            total_cost_usd=total_cost_usd,
            budget_ceiling_usd=budget,
            slides=slides,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(schema.model_dump_json(indent=2))

        logger.info(
            "understanding.complete",
            vision=vision_count,
            ocr=ocr_count,
            total_cost_usd=total_cost_usd,
        )
        life.end_payload.update(
            vision_count=vision_count,
            ocr_count=ocr_count,
            total_cost_usd=total_cost_usd,
            output_path=str(output_path),
        )
        return UnderstandingResult(
            vision_count=vision_count,
            ocr_count=ocr_count,
            total_cost_usd=total_cost_usd,
            output_path=output_path,
        )
