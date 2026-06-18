"""
Log record contract for the run log file.

This file documents the JSON-lines schema written to
`<log_dir>/<timestamp>-<url_hash>.log` by every notetaker CLI invocation. It
is the *contract* — the authoritative on-disk shape — kept in this spec
folder so reviewers can sign off on it independently of the implementation.

The implementation copy lives at `src/notetaker/contracts/log_record.py` and
must match this file. Any drift is a constitutional violation (Article I.3).

Schema version: 1.0.0
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


SCHEMA_VERSION = "1.0.0"


class EventCategory(str, Enum):
    """Closed set of categories. Drives test assertions and downstream tooling."""

    STAGE_START = "stage_start"
    STAGE_END = "stage_end"
    HEARTBEAT = "heartbeat"
    WAITING_FOR_INPUT = "waiting_for_input"
    RESUMED_FROM_INPUT = "resumed_from_input"
    WARNING = "warning"
    ERROR = "error"
    UNHANDLED_EXCEPTION = "unhandled_exception"
    INFO = "info"


class Stage(str, Enum):
    """Closed set of pipeline stages plus the CLI shell."""

    CAPTURE = "capture"
    EXTRACT = "extract"
    UNDERSTAND = "understand"
    SYNTHESISE = "synthesise"
    CLI = "cli"


class LogRecord(BaseModel):
    """One JSON-line in a run log file.

    Authoritative shape. Producers (the structlog pipeline) must emit fields
    matching this model; consumers (tests, ad-hoc grep, future tooling) may
    rely on it.
    """

    schema_version: str = Field(
        default=SCHEMA_VERSION,
        description="Bumped on breaking changes per Article I.3.",
    )
    ts: str = Field(
        ...,
        description="ISO-8601 UTC timestamp from structlog TimeStamper.",
    )
    level: str = Field(
        ...,
        description="One of: debug, info, warning, error.",
    )
    event: str = Field(
        ...,
        description=(
            "Dotted event name within the stage namespace, e.g. "
            "'capture.heartbeat', 'understand.stage_start'."
        ),
    )
    event_category: EventCategory = Field(
        ...,
        description=(
            "Closed-set category. Drives 'is this run hung / crashed / "
            "complete' decisions in tests and consumers."
        ),
    )
    stage: Optional[Stage] = Field(
        default=None,
        description=(
            "Active pipeline stage. May be null for pre-stage CLI events "
            "(config load, log-store init) or for unhandled_exception "
            "raised before any stage entered."
        ),
    )
    recording_url_hash: Optional[str] = Field(
        default=None,
        description=(
            "16-character hex hash of the recording URL — same identifier "
            "used by Cache. Set as soon as the URL is known."
        ),
        min_length=16,
        max_length=16,
    )
    elapsed_seconds: Optional[float] = Field(
        default=None,
        description=(
            "Wall-clock duration of the stage. Required on stage_end "
            "records; absent otherwise."
        ),
        ge=0.0,
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Free-form structured fields specific to the event. "
            "Contracts per category:\n"
            "  - heartbeat:        non-empty progress fields (e.g. {'frames': 42})\n"
            "  - stage_end:        headline metrics (e.g. unique_slides, total_cost_usd)\n"
            "  - waiting_for_input: {'prompt': <message shown to user>}\n"
            "  - resumed_from_input: {'prompt': <same message>, 'wait_seconds': <float>}\n"
            "  - unhandled_exception: {'exc_type', 'traceback'} required\n"
        ),
    )

    def model_post_init(self, __context: Any) -> None:
        # Closed-set invariants (Article I.3 — contracts validated at producer).
        if self.event_category in {EventCategory.STAGE_START, EventCategory.STAGE_END}:
            if self.stage is None or self.stage == Stage.CLI:
                raise ValueError(
                    f"event_category={self.event_category} requires a pipeline stage"
                )
        if self.event_category == EventCategory.STAGE_END and self.elapsed_seconds is None:
            raise ValueError("stage_end record must carry elapsed_seconds")
        if self.event_category == EventCategory.HEARTBEAT:
            if self.stage is None:
                raise ValueError("heartbeat record must carry a stage")
            if not self.payload:
                raise ValueError("heartbeat record must carry at least one payload field")
        if self.event_category in {
            EventCategory.WAITING_FOR_INPUT,
            EventCategory.RESUMED_FROM_INPUT,
        }:
            if "prompt" not in self.payload:
                raise ValueError(
                    f"{self.event_category} record must carry payload.prompt"
                )
        if self.event_category == EventCategory.UNHANDLED_EXCEPTION:
            for required in ("exc_type", "traceback"):
                if required not in self.payload:
                    raise ValueError(
                        f"unhandled_exception record must carry payload.{required}"
                    )
