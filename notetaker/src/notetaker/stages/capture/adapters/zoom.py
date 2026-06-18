from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from notetaker.cache import Cache, url_hash
from notetaker.config import Config
from notetaker.contracts.frames_manifest import FrameEntry, FramesManifestSchema
from notetaker.contracts.transcript import TranscriptSchema, Utterance
from notetaker.stages.capture.base import CaptureAdapter, CaptureAuthError
from notetaker.utils.heartbeat import HeartbeatTracker, stage_lifecycle
from notetaker.utils.logging import get_logger
from notetaker.utils.redact import redact_url

# User-facing prompt strings. Defined as module constants so the print()
# call and the matching waiting_for_input log record (FR-006) stay in sync.
_PROMPT_PLAYBACK_STARTED = "Press Enter when playback has started..."
_PROMPT_PLAYBACK_COMPLETE = "Press Enter when playback is complete..."

logger = get_logger(__name__)

# --- Zoom web-player CSS selectors -------------------------------------------
# These are the ONLY Zoom-specific constants in the codebase (Article I.2).
# Update here if Zoom changes its player DOM; no other file needs changing.
SLIDE_SELECTOR = ".vjs-tech"
TRANSCRIPT_PANEL_SELECTOR = ".transcript-panel__content"
TRANSCRIPT_LINE_SELECTOR = ".transcript-panel__content li"

# Heuristic: Zoom transcript lines have the format "HH:MM:SS Speaker: text"
# or "Speaker\nHH:MM:SS text" depending on player version. We try both patterns.
_TRANSCRIPT_LINE_RE = re.compile(
    r"(?:(\d{1,2}:\d{2}:\d{2})\s+)?([^:]+?):\s+(.*)", re.DOTALL
)

_LOGIN_SELECTORS = [
    "input[type='password']",
    ".zm-signin",
    "#login-btn",
    "[data-testid='signin']",
]

# Zoom recording pages frequently set the document title to the generic
# product name; treat these as cues to fall back to a content-area selector.
_GENERIC_PAGE_TITLES = frozenset({
    "",
    "Zoom",
    "Zoom Meetings",
    "Zoom — Recording",
    "Zoom - Recording",
})


def _parse_timestamp(ts: str) -> float:
    """Convert HH:MM:SS or MM:SS string to seconds."""
    parts = [int(p) for p in ts.strip().split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return float(parts[0])


def _default_chrome_profile() -> str:
    """Return the system default Chrome user-data-dir path."""
    if sys.platform == "darwin":
        return str(Path.home() / "Library" / "Application Support" / "Google" / "Chrome")
    if sys.platform == "win32":
        import os
        return str(Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data")
    # Linux
    return str(Path.home() / ".config" / "google-chrome")


class ZoomAdapter(CaptureAdapter):
    """
    Playwright-based capture adapter for Zoom Cloud Recordings.

    Opens a persistent Chromium browser context using the user's existing Chrome
    profile (so their Zoom session is already active), navigates to the recording
    URL, and waits for the user to confirm playback has started before beginning
    frame capture and transcript scraping.
    """

    def __init__(self, config: Config, debug: bool = False, force: bool = False):
        super().__init__(config, debug, force)
        self._utterances: list[Utterance] = []
        self._frames: list[FrameEntry] = []
        self._transcript_unavailable = False
        self._stop_capture = asyncio.Event()
        self._tracker: HeartbeatTracker | None = None

    def _resolve_tracker(self) -> HeartbeatTracker:
        return getattr(
            self.config,
            "_heartbeat_tracker",
            HeartbeatTracker(self.config.logging.heartbeat_interval_seconds),
        )

    async def _await_user_input(self, prompt: str) -> None:
        """Print a prompt, log waiting_for_input, block on input(), then log resumed_from_input."""
        print(f"\n[notetaker] {prompt}", end="", flush=True)
        logger.info(
            "capture.waiting_for_input",
            event_category="waiting_for_input",
            stage="capture",
            prompt=prompt,
        )
        t0 = time.monotonic()
        await asyncio.get_event_loop().run_in_executor(None, input)
        logger.info(
            "capture.resumed_from_input",
            event_category="resumed_from_input",
            stage="capture",
            prompt=prompt,
            wait_seconds=time.monotonic() - t0,
        )

    async def capture(self, url: str) -> tuple[Path, Path]:
        """Orchestrate browser open → frame capture + transcript scrape → write outputs."""
        self._tracker = self._resolve_tracker()
        async with stage_lifecycle(
            "capture",
            tracker=self._tracker,
            recording_url_hash=url_hash(url),
        ) as life:
            cache = Cache(
                self.config.cache_dir_path,
                recording_url=url,
                force=self.force,
            )

            if not self.force and cache.is_hit("capture", "frames_manifest.json"):
                logger.info("capture.cache_hit", url=redact_url(url))
                frames_path = cache.artifact_path("capture", "frames_manifest.json")
                transcript_path = cache.artifact_path("capture", "transcript.json")
                life.end_payload.update(
                    frames=0,
                    utterances=0,
                    transcript_unavailable=False,
                    cache_hit=True,
                )
                return (frames_path, transcript_path)

            self._utterances = []
            self._frames = []
            self._transcript_unavailable = False
            self._stop_capture = asyncio.Event()

            page = await self._open_browser(url)

            # Scrape the meeting title before capture starts. Best-effort —
            # falls back to None and is logged as unavailable if every probe
            # misses. The title is persisted into meta.json (spec 005, FR-004).
            meeting_title = await self._scrape_meeting_title(page, cache.root)
            cache.initialise(meeting_title=meeting_title)
            frames_dir = cache.stage_dir("capture") / "frames"
            frames_dir.mkdir(parents=True, exist_ok=True)

            try:
                print("\n[notetaker] Browser is open. Start playback in the Zoom player.")
                await self._await_user_input(_PROMPT_PLAYBACK_STARTED)

                logger.info("capture.playback_started")

                await asyncio.gather(
                    self._capture_frames(page, frames_dir, life),
                    self._scrape_transcript(page, life),
                )
            finally:
                await page.context.close()

            frames_path = await self._write_frames_manifest(cache, url)
            transcript_path = await self._write_transcript(cache, url)

            logger.info(
                "capture.complete",
                frames=len(self._frames),
                utterances=len(self._utterances),
                transcript_unavailable=self._transcript_unavailable,
            )
            life.end_payload.update(
                frames=len(self._frames),
                utterances=len(self._utterances),
                transcript_unavailable=self._transcript_unavailable,
            )
            return frames_path, transcript_path

    async def _open_browser(self, url: str):
        """Launch Playwright persistent context and navigate to the recording URL."""
        from playwright.async_api import async_playwright

        profile_path = self.config.capture.browser_profile_path or _default_chrome_profile()
        logger.debug("capture.browser_open", profile=profile_path, url=redact_url(url))

        self._playwright = await async_playwright().start()
        context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        # Check for login wall
        for sel in _LOGIN_SELECTORS:
            if await page.locator(sel).count() > 0:
                await context.close()
                raise CaptureAuthError(
                    f"Zoom login wall detected (selector '{sel}'). "
                    "Please log in to Zoom in your browser and try again."
                )

        logger.debug("capture.browser_ready")
        return page

    async def _scrape_meeting_title(self, page, cache_root: Path) -> str | None:
        """
        Try to retrieve the Zoom recording's meeting title. Returns None on any
        failure. With debug enabled, persist the raw probes to disk under
        capture/raw/title_scrape.json (Article V.2).
        """
        attempted: list[dict] = []
        title: str | None = None
        selector_used: str | None = None

        # Probe 1: page.title()
        try:
            raw_title = await page.title()
            attempted.append({"source": "page.title", "value": raw_title})
            if raw_title and raw_title.strip() not in _GENERIC_PAGE_TITLES:
                title = raw_title.strip()
                selector_used = "page.title"
        except Exception as exc:
            attempted.append({"source": "page.title", "error": str(exc)})

        # Probe 2: configured CSS selector(s) as a fallback.
        if title is None:
            selector = self.config.capture.recording_title_selector
            try:
                locator = page.locator(selector)
                # Take the first matching element's text.
                first = locator.first
                txt = await first.text_content()
                attempted.append({"source": selector, "value": txt})
                if txt and txt.strip():
                    title = txt.strip()
                    selector_used = selector
            except Exception as exc:
                attempted.append({"source": selector, "error": str(exc)})

        if self.debug:
            try:
                raw_dir = cache_root / "capture" / "raw"
                raw_dir.mkdir(parents=True, exist_ok=True)
                (raw_dir / "title_scrape.json").write_text(
                    json.dumps({"attempted": attempted, "result": title}, indent=2)
                )
            except Exception as exc:  # pragma: no cover
                logger.debug("capture.title_scrape_debug_write_failed", error=str(exc))

        if title is not None:
            # Truncate the value-shaped log field per Article VI.1 hygiene.
            logger.info(
                "capture.meeting_title_scraped",
                event_category="info",
                selector_used=selector_used,
                title_len=len(title),
                title_truncated_for_log=title[:80],
            )
            return title

        logger.warning(
            "capture.meeting_title_unavailable",
            event_category="warning",
            recovery_hint=(
                "Re-run with --debug to capture <cache>/<hash>/capture/raw/"
                "title_scrape.json showing the probes attempted."
            ),
        )
        return None

    async def _capture_frames(self, page, frames_dir: Path, life) -> None:
        """
        Periodically screenshot the Zoom slide area until the user signals playback end.

        Runs until _stop_capture is set on this instance.
        """
        interval = self.config.capture.frame_sample_rate_seconds

        # Also start the "press Enter to stop" listener
        stop_task = asyncio.ensure_future(self._wait_for_stop_signal())

        frame_count = 0
        while not self._stop_capture.is_set():
            try:
                locator = page.locator(SLIDE_SELECTOR)
                if await locator.count() > 0:
                    timestamp_ms = int(asyncio.get_event_loop().time() * 1000)
                    filename = f"{timestamp_ms}.jpg"
                    dest = frames_dir / filename
                    await locator.screenshot(path=str(dest), type="jpeg", quality=85)
                    self._frames.append(FrameEntry(timestamp_ms=timestamp_ms, file_path=str(dest)))
                    frame_count += 1
                    life.tick("frames", frames=frame_count)
            except Exception as exc:
                logger.debug("capture.frame_error", error=str(exc))

            await asyncio.sleep(interval)

        stop_task.cancel()

    async def _wait_for_stop_signal(self) -> None:
        """Block until user presses Enter to signal playback has ended."""
        await self._await_user_input(_PROMPT_PLAYBACK_COMPLETE)
        self._stop_capture.set()
        logger.info("capture.stop_signal_received")

    async def _scrape_transcript(self, page, life) -> None:
        """
        Poll the Zoom transcript panel for new utterance lines throughout playback.

        Accumulates Utterance objects. Sets _transcript_unavailable if the panel
        is absent.
        """
        seen_texts: set[str] = set()

        # Wait briefly for the transcript panel to appear
        try:
            await page.locator(TRANSCRIPT_PANEL_SELECTOR).wait_for(
                state="visible", timeout=10_000
            )
        except Exception:
            logger.warning(
                "capture.transcript_unavailable",
                event_category="warning",
                selector_used=TRANSCRIPT_PANEL_SELECTOR,
                recovery_hint=(
                    "See HOWTO.md \"Obtaining a transcript\" to recover via "
                    "post-capture procedure."
                ),
            )
            self._transcript_unavailable = True
            return

        interval = self.config.capture.frame_sample_rate_seconds
        current_seconds = 0.0

        while not self._stop_capture.is_set():
            life.tick("transcript", utterances=len(self._utterances))
            try:
                lines = await page.locator(TRANSCRIPT_LINE_SELECTOR).all_text_contents()
                for raw in lines:
                    raw = raw.strip()
                    if not raw or raw in seen_texts:
                        continue
                    seen_texts.add(raw)

                    m = _TRANSCRIPT_LINE_RE.match(raw)
                    if m:
                        ts_str, speaker, text = m.group(1), m.group(2), m.group(3)
                        start = _parse_timestamp(ts_str) if ts_str else current_seconds
                        end = start + 5.0  # Estimate; Zoom doesn't expose end time per line
                    else:
                        speaker, text = "Unknown", raw
                        start, end = current_seconds, current_seconds + 5.0

                    if text.strip():
                        self._utterances.append(
                            Utterance(
                                start_seconds=start,
                                end_seconds=end,
                                speaker=speaker.strip(),
                                text=text.strip(),
                            )
                        )
                        current_seconds = end
            except Exception as exc:
                logger.debug("capture.transcript_poll_error", error=str(exc))

            await asyncio.sleep(interval)

        logger.info("capture.transcript_complete", utterances=len(self._utterances))

    async def _write_frames_manifest(self, cache: Cache, url: str) -> Path:
        manifest = FramesManifestSchema(
            recording_url=url,
            frames=self._frames,
        )
        path = cache.artifact_path("capture", "frames_manifest.json")
        path.write_text(manifest.model_dump_json(indent=2))
        logger.info("capture.frames_manifest_written", path=str(path), frames=len(self._frames))
        return path

    async def _write_transcript(self, cache: Cache, url: str) -> Path:
        transcript = TranscriptSchema(
            recording_url=url,
            captured_at=datetime.now(timezone.utc).isoformat(),
            utterances=self._utterances,
            transcript_unavailable=self._transcript_unavailable,
        )
        path = cache.artifact_path("capture", "transcript.json")
        path.write_text(transcript.model_dump_json(indent=2))
        logger.info("capture.transcript_written", path=str(path), utterances=len(self._utterances))
        return path
