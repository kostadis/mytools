"""
Per-cache-entry metadata stored at <cache-root>/<url-hash>/meta.json.

Promoted to a versioned Pydantic schema in spec 005. Legacy v1 reads (no
schema_version field, no meeting_title / recording_date / summary) succeed
with the new fields defaulted to None; the next write upgrades the file to
schema_version="2".

This is per-entry metadata, not an inter-stage contract (Article I.3).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, field_validator, model_validator


CURRENT_SCHEMA_VERSION = "2"
_ACCEPTED_VERSIONS_ON_READ = frozenset({"1", "2"})
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class RecordingMetaSchema(BaseModel):
    schema_version: str = CURRENT_SCHEMA_VERSION
    recording_url: str
    created_at: str
    meeting_title: str | None = None
    recording_date: str | None = None
    summary: str | None = None

    @field_validator("schema_version")
    @classmethod
    def _version_known(cls, v: str) -> str:
        if v not in _ACCEPTED_VERSIONS_ON_READ:
            raise ValueError(
                f"schema_version must be one of {sorted(_ACCEPTED_VERSIONS_ON_READ)}, got {v!r}"
            )
        return v

    @field_validator("recording_url")
    @classmethod
    def _url_non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("recording_url must be non-empty")
        return v

    @field_validator("recording_date")
    @classmethod
    def _date_iso(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _DATE_RE.match(v):
            raise ValueError(
                f"recording_date must match YYYY-MM-DD, got {v!r}"
            )
        return v

    @model_validator(mode="after")
    def _normalise_empties(self) -> "RecordingMetaSchema":
        # Empty strings on optional fields become None — keeps consumers from
        # having to distinguish "missing" vs "blank".
        if self.meeting_title is not None and not self.meeting_title.strip():
            self.meeting_title = None
        if self.summary is not None and not self.summary.strip():
            self.summary = None
        return self

    @classmethod
    def from_path(cls, path: Path) -> "RecordingMetaSchema":
        """
        Load a meta.json. Lenient on legacy v1 files: missing schema_version is
        treated as "1" and the v2 fields default to None.
        """
        raw = json.loads(path.read_text())
        if "schema_version" not in raw:
            raw["schema_version"] = "1"
        return cls.model_validate(raw)

    def write(self, path: Path) -> None:
        """Serialise as v2 (the current version)."""
        out = self.model_copy(update={"schema_version": CURRENT_SCHEMA_VERSION})
        path.write_text(json.dumps(out.model_dump(), indent=2))
