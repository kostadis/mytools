import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import imagehash
import pytest

from notetaker.contracts.frames_manifest import FrameEntry
from notetaker.stages.extraction.slide_detector import SlideDetector


def _make_frame(ts_ms: int, path: str = "fake.jpg") -> FrameEntry:
    return FrameEntry(timestamp_ms=ts_ms, file_path=path)


def _stub_phash(value: int):
    """Return a mock imagehash with a given integer value (used for distance arithmetic)."""
    h = MagicMock(spec=imagehash.ImageHash)
    h.__sub__ = lambda self, other: abs(value - other._value)
    h._value = value
    h.__str__ = lambda self: f"{value:016x}"
    return h


URL = "https://zoom.us/rec/play/test"


@patch("notetaker.stages.extraction.slide_detector._phash")
@patch("notetaker.stages.extraction.slide_detector._sha256")
def test_identical_frames_no_transition(mock_sha, mock_phash, tmp_path):
    """Frames with identical pHash → single SlideOccurrence."""
    f1 = tmp_path / "0.jpg"
    f2 = tmp_path / "1000.jpg"
    f1.write_bytes(b"img")
    f2.write_bytes(b"img")

    h = imagehash.hex_to_hash("0" * 16)
    mock_phash.return_value = h
    mock_sha.return_value = "a" * 64

    frames = [
        FrameEntry(timestamp_ms=0, file_path=str(f1)),
        FrameEntry(timestamp_ms=1000, file_path=str(f2)),
    ]
    detector = SlideDetector(threshold=8)
    timeline = detector.detect(frames, URL)

    assert len(timeline.slides) == 1
    assert timeline.slides[0].slide_id == "s001"


@patch("notetaker.stages.extraction.slide_detector._phash")
@patch("notetaker.stages.extraction.slide_detector._sha256")
def test_different_frames_transition(mock_sha, mock_phash, tmp_path):
    """Frames with Hamming distance > threshold → two SlideOccurrences."""
    f1 = tmp_path / "0.jpg"
    f2 = tmp_path / "1000.jpg"
    f1.write_bytes(b"img1")
    f2.write_bytes(b"img2")

    h1 = imagehash.hex_to_hash("0" * 16)
    h2 = imagehash.hex_to_hash("f" * 16)
    mock_phash.side_effect = [h1, h2]
    mock_sha.return_value = "a" * 64

    frames = [
        FrameEntry(timestamp_ms=0, file_path=str(f1)),
        FrameEntry(timestamp_ms=1000, file_path=str(f2)),
    ]
    detector = SlideDetector(threshold=8)
    timeline = detector.detect(frames, URL)

    assert len(timeline.slides) == 2
    assert timeline.slides[0].slide_id == "s001"
    assert timeline.slides[1].slide_id == "s002"


@patch("notetaker.stages.extraction.slide_detector._phash")
@patch("notetaker.stages.extraction.slide_detector._sha256")
def test_recurring_slide_reuses_id(mock_sha, mock_phash, tmp_path):
    """A slide that reappears gets the same slide_id as its first occurrence."""
    files = [tmp_path / f"{i}.jpg" for i in range(3)]
    for f in files:
        f.write_bytes(b"img")

    h_a = imagehash.hex_to_hash("0" * 16)
    h_b = imagehash.hex_to_hash("f" * 16)
    h_a2 = imagehash.hex_to_hash("0" * 16)  # same as h_a
    mock_phash.side_effect = [h_a, h_b, h_a2]
    mock_sha.return_value = "a" * 64

    frames = [FrameEntry(timestamp_ms=i * 1000, file_path=str(files[i])) for i in range(3)]
    detector = SlideDetector(threshold=8)
    timeline = detector.detect(frames, URL)

    ids = [s.slide_id for s in timeline.slides]
    assert ids[0] == ids[2], "Recurring slide should reuse the original slide_id"
    assert ids[0] != ids[1]


def test_empty_input_returns_empty_timeline():
    detector = SlideDetector(threshold=8)
    timeline = detector.detect([], URL)
    assert timeline.slides == []
