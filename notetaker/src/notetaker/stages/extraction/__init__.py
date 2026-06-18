from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from notetaker.cache import Cache, url_hash
from notetaker.config import Config
from notetaker.stages.extraction.frame_sampler import load_and_sample
from notetaker.stages.extraction.slide_detector import SlideDetector
from notetaker.utils.heartbeat import HeartbeatTracker, stage_lifecycle
from notetaker.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ExtractionResult:
    total_slides: int
    unique_slides: int
    output_path: Path


def _tracker(config: Config) -> HeartbeatTracker:
    """Reuse the cli-built tracker if present; otherwise build a default one."""
    return getattr(
        config,
        "_heartbeat_tracker",
        HeartbeatTracker(config.logging.heartbeat_interval_seconds),
    )


async def run(url: str, config: Config, force: bool = False) -> ExtractionResult:
    """Run the Slide Extraction stage for the given recording URL."""
    tracker = _tracker(config)
    async with stage_lifecycle(
        "extract",
        tracker=tracker,
        recording_url_hash=url_hash(url),
    ) as life:
        cache = Cache(config.cache_dir_path, recording_url=url, force=force)
        output_path = cache.artifact_path("extraction", "slide_timeline.json")

        if not force and cache.is_hit("extraction", "slide_timeline.json"):
            logger.info("extraction.cache_hit")
            raw = json.loads(output_path.read_text())
            from notetaker.contracts.slide_timeline import SlideTimelineSchema
            timeline = SlideTimelineSchema.model_validate(raw)
            unique = len({s.slide_id for s in timeline.slides})
            life.end_payload.update(
                total_slides=len(timeline.slides),
                unique_slides=unique,
                output_path=str(output_path),
                cache_hit=True,
            )
            return ExtractionResult(
                total_slides=len(timeline.slides),
                unique_slides=unique,
                output_path=output_path,
            )

        manifest_path = cache.artifact_path("capture", "frames_manifest.json")
        if not manifest_path.exists():
            raise FileNotFoundError(
                f"frames_manifest.json not found at {manifest_path}. "
                "Run 'notetaker capture <url>' first."
            )

        frames = list(load_and_sample(manifest_path, config.extraction.sample_every_n_frames))
        logger.info("extraction.frames_loaded", count=len(frames))

        detector = SlideDetector(threshold=config.extraction.slide_change_threshold)
        timeline = detector.detect(
            frames,
            recording_url=url,
            on_progress=lambda i, n: life.tick("frames", processed=i, total=n),
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(timeline.model_dump_json(indent=2))

        unique = len({s.slide_id for s in timeline.slides})
        logger.info(
            "extraction.complete",
            total_occurrences=len(timeline.slides),
            unique_slides=unique,
            output=str(output_path),
        )
        life.end_payload.update(
            total_slides=len(timeline.slides),
            unique_slides=unique,
            output_path=str(output_path),
        )
        return ExtractionResult(
            total_slides=len(timeline.slides),
            unique_slides=unique,
            output_path=output_path,
        )
