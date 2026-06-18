from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from notetaker.contracts.frames_manifest import FrameEntry, FramesManifestSchema
from notetaker.utils.logging import get_logger

logger = get_logger(__name__)


def load_and_sample(
    manifest_path: Path,
    sample_every_n: int = 1,
) -> Iterator[FrameEntry]:
    """
    Load frames_manifest.json, validate against FramesManifestSchema, and
    yield every Nth FrameEntry in playback order.
    """
    raw = json.loads(manifest_path.read_text())
    manifest = FramesManifestSchema.model_validate(raw)

    total = len(manifest.frames)
    logger.debug("frame_sampler.loaded", total_frames=total, sample_every_n=sample_every_n)

    for i, frame in enumerate(manifest.frames):
        if i % sample_every_n == 0:
            yield frame
