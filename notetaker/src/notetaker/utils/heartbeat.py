"""Heartbeat throttling and stage lifecycle markers.

`HeartbeatTracker.tick(stage, key, **payload)` emits a structured heartbeat
record at most once per `interval_seconds` per (stage, key) tuple. Stage
loops call it on every iteration; the throttle decides when to actually
emit. No background tasks, no asyncio, no shared state across runs —
under a SIGKILL the process simply stops calling tick().

`stage_lifecycle(stage, recording_url_hash, *, tracker)` is the
async context manager every pipeline stage wraps its body in. On enter it
emits `<stage>.stage_start`; on clean exit it emits `<stage>.stage_end`
with elapsed time and whatever the stage stashed in `life.end_payload`.
On exception it emits NO `stage_end` and re-raises — leaving the run log
with a stage_start whose absent stage_end is the diagnostic fingerprint
of a stage that died (SC-003).
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

from notetaker.utils.logging import bind_contextvars, clear_contextvars, get_logger

logger = get_logger(__name__)


class HeartbeatTracker:
    """Per-(stage, key) throttle. Constructed once per CLI invocation."""

    def __init__(self, interval_seconds: float) -> None:
        self.interval_seconds = float(interval_seconds)
        self._last_emit_at: dict[tuple[str, str], float] = {}

    def tick(self, stage: str, key: str, **payload) -> None:
        """Emit a heartbeat record if `interval_seconds` has elapsed for (stage, key)."""
        now = time.monotonic()
        last = self._last_emit_at.get((stage, key))
        if last is not None and (now - last) < self.interval_seconds:
            return
        self._last_emit_at[(stage, key)] = now
        logger.info(
            f"{stage}.heartbeat",
            event_category="heartbeat",
            stage=stage,
            heartbeat_key=key,
            **payload,
        )


@dataclass
class _Life:
    """Object yielded by `stage_lifecycle`. Mutable; the stage body
    populates `end_payload` with whatever metrics it wants in the
    stage_end record."""

    stage: str
    tracker: HeartbeatTracker
    end_payload: dict = field(default_factory=dict)

    def tick(self, key: str, **payload) -> None:
        self.tracker.tick(self.stage, key, **payload)


@contextlib.asynccontextmanager
async def stage_lifecycle(
    stage: str,
    *,
    tracker: HeartbeatTracker,
    recording_url_hash: Optional[str] = None,
) -> AsyncIterator[_Life]:
    """Async context manager that brackets a pipeline stage with lifecycle records."""
    bind_kwargs: dict[str, object] = {"stage": stage}
    if recording_url_hash:
        bind_kwargs["recording_url_hash"] = recording_url_hash
    bind_contextvars(**bind_kwargs)

    logger.info(
        f"{stage}.stage_start",
        event_category="stage_start",
        stage=stage,
    )
    t0 = time.monotonic()
    life = _Life(stage=stage, tracker=tracker)

    try:
        yield life
    except BaseException:
        # Per data-model.md state diagram and SC-003: emit no stage_end on
        # exception. The unhandled_exception handler at cli.main() captures
        # the failure with the stage tag still bound to contextvars.
        raise
    else:
        elapsed = time.monotonic() - t0
        logger.info(
            f"{stage}.stage_end",
            event_category="stage_end",
            stage=stage,
            elapsed_seconds=elapsed,
            **life.end_payload,
        )
    finally:
        # Clear contextvars so a sibling stage in the same `notetaker run`
        # invocation starts with a clean slate.
        clear_contextvars()
