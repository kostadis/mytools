from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable, Optional

import imagehash
from PIL import Image

from notetaker.contracts.frames_manifest import FrameEntry
from notetaker.contracts.slide_timeline import SlideOccurrence, SlideTimelineSchema
from notetaker.utils.logging import get_logger

logger = get_logger(__name__)


def _phash(path: Path) -> imagehash.ImageHash:
    return imagehash.phash(Image.open(path))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SlideDetector:
    """
    Detects slide transitions from a sequence of captured frames using pHash.

    Frames whose pHash Hamming distance from the previous slide hash exceeds
    `threshold` are recorded as a new SlideOccurrence. Frames that match a
    previously seen slide hash (within threshold) reuse the existing slide_id.
    """

    def __init__(self, threshold: int = 8):
        self.threshold = threshold

    def detect(
        self,
        frames: list[FrameEntry],
        recording_url: str,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> SlideTimelineSchema:
        """
        Run detection over all frames and return a SlideTimelineSchema.

        De-duplication: when a frame matches a prior unique slide's hash (within
        threshold), a new SlideOccurrence is created that references the same
        slide_id. Slide content is only processed once per unique slide_id.
        """
        if not frames:
            logger.warning("slide_detector.empty_input")
            return SlideTimelineSchema(recording_url=recording_url, slides=[])

        # Map from pHash string → slide_id for de-duplication
        known_hashes: dict[str, str] = {}
        slide_counter = 0
        occurrences: list[SlideOccurrence] = []

        prev_hash: imagehash.ImageHash | None = None
        current_slide_id: str | None = None
        current_start_ms: int = frames[0].timestamp_ms
        current_frame: FrameEntry = frames[0]
        current_hash_str: str = ""
        current_sha256: str = ""

        def _close_current(end_ms: int) -> None:
            if current_slide_id is None:
                return
            occ = SlideOccurrence(
                slide_id=current_slide_id,
                start_seconds=current_start_ms / 1000.0,
                end_seconds=end_ms / 1000.0,
                frame_path=current_frame.file_path,
                frame_hash=current_hash_str,
                frame_sha256=current_sha256,
            )
            occurrences.append(occ)
            logger.debug(
                "slide_detector.slide_closed",
                slide_id=current_slide_id,
                start_s=occ.start_seconds,
                end_s=occ.end_seconds,
            )

        total = len(frames)
        for i, frame in enumerate(frames):
            if on_progress is not None:
                on_progress(i, total)
            frame_path = Path(frame.file_path)
            if not frame_path.exists():
                logger.debug("slide_detector.frame_missing", path=frame.file_path)
                continue

            try:
                h = _phash(frame_path)
            except Exception as exc:
                logger.debug("slide_detector.hash_error", path=frame.file_path, error=str(exc))
                continue

            is_transition = prev_hash is None or (prev_hash - h) > self.threshold

            if is_transition:
                if prev_hash is not None:
                    _close_current(frame.timestamp_ms)

                sha = _sha256(frame_path)
                hash_str = str(h)

                # Check if this is a recurring slide
                matched_id = None
                for known_hash_str, known_id in known_hashes.items():
                    known_h = imagehash.hex_to_hash(known_hash_str)
                    if (h - known_h) <= self.threshold:
                        matched_id = known_id
                        break

                if matched_id:
                    slide_id = matched_id
                    logger.debug("slide_detector.recurring_slide", slide_id=slide_id)
                else:
                    slide_counter += 1
                    slide_id = f"s{slide_counter:03d}"
                    known_hashes[hash_str] = slide_id
                    logger.debug(
                        "slide_detector.new_slide",
                        slide_id=slide_id,
                        distance=prev_hash - h if prev_hash else 0,
                    )

                current_slide_id = slide_id
                current_start_ms = frame.timestamp_ms
                current_frame = frame
                current_hash_str = hash_str
                current_sha256 = sha

            prev_hash = h

        # Close the last open slide using the final frame's timestamp
        if current_slide_id is not None:
            _close_current(frames[-1].timestamp_ms + 1000)

        unique_count = len({o.slide_id for o in occurrences})
        logger.info(
            "slide_detector.complete",
            total_occurrences=len(occurrences),
            unique_slides=unique_count,
        )

        return SlideTimelineSchema(recording_url=recording_url, slides=occurrences)
