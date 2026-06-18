from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from notetaker.config import Config


class CaptureError(Exception):
    """Base class for capture-stage errors."""


class CaptureAuthError(CaptureError):
    """Raised when the recording URL requires authentication the adapter cannot satisfy."""


class CaptureAdapter(ABC):
    """
    Abstract base for platform-specific capture adapters.

    Implementors must:
    - Open a browser session pointing to `url`.
    - During playback, capture frames at the configured interval.
    - Simultaneously scrape the platform's transcript panel.
    - Write outputs to the URL-keyed cache and return their paths.
    """

    def __init__(self, config: Config, debug: bool = False, force: bool = False):
        self.config = config
        self.debug = debug
        self.force = force

    @abstractmethod
    async def capture(self, url: str) -> tuple[Path, Path]:
        """
        Run a full capture session for the given recording URL.

        Returns:
            (frames_manifest_path, transcript_path) — absolute paths to the
            written FramesManifestSchema and TranscriptSchema JSON files.

        Raises:
            CaptureAuthError: if the recording is gated by login the user hasn't completed.
            CaptureError: for other unrecoverable capture failures.
        """
