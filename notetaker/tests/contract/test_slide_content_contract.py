import json
import pytest
from pydantic import ValidationError

from notetaker.contracts.slide_content import (
    ExtractionMethod,
    SlideContent,
    SlideContentSchema,
    SCHEMA_VERSION,
)

VALID_SLIDE = {
    "slide_id": "s001",
    "title": "Introduction",
    "bullets": ["Point 1", "Point 2"],
    "visual_description": "",
    "raw_ocr": "Introduction\nPoint 1\nPoint 2",
    "extraction_method": "vision",
    "estimated_cost_usd": 0.0012,
}

VALID_SCHEMA = {
    "schema_version": SCHEMA_VERSION,
    "recording_url": "https://zoom.us/rec/play/abc",
    "total_cost_usd": 0.0012,
    "budget_ceiling_usd": 2.0,
    "slides": [VALID_SLIDE],
}


def test_round_trip_valid():
    obj = SlideContentSchema.model_validate(VALID_SCHEMA)
    restored = SlideContentSchema.model_validate(json.loads(obj.model_dump_json()))
    assert restored == obj


def test_extraction_method_enum():
    assert ExtractionMethod.vision == "vision"
    assert ExtractionMethod.ocr == "ocr"
    with pytest.raises(ValidationError):
        SlideContent.model_validate({**VALID_SLIDE, "extraction_method": "magic"})


def test_cost_non_negative():
    with pytest.raises(ValidationError):
        SlideContent.model_validate({**VALID_SLIDE, "estimated_cost_usd": -0.01})


def test_budget_non_negative():
    with pytest.raises(ValidationError):
        SlideContentSchema.model_validate({**VALID_SCHEMA, "budget_ceiling_usd": -1.0})


def test_total_cost_non_negative():
    with pytest.raises(ValidationError):
        SlideContentSchema.model_validate({**VALID_SCHEMA, "total_cost_usd": -0.01})


def test_schema_version_const():
    with pytest.raises(ValidationError):
        SlideContentSchema.model_validate({**VALID_SCHEMA, "schema_version": "9.9"})


def test_ocr_slide_zero_cost():
    ocr_slide = {**VALID_SLIDE, "extraction_method": "ocr", "estimated_cost_usd": 0.0}
    obj = SlideContent.model_validate(ocr_slide)
    assert obj.extraction_method == ExtractionMethod.ocr
    assert obj.estimated_cost_usd == 0.0
