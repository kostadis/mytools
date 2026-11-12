#!/usr/bin/env python3
"""The one place a review id is made valid.

A page's `reviewId` must match REVIEW_ID_RE (1-128 chars of [A-Za-z0-9_.:@-]).
Anything a caller wants to put in one that does not (a file path, a chapter name
with a space) goes through `derive_review_id`: a text that is already valid is
returned unchanged, otherwise it becomes a slug plus a short hash of the exact
original text, so two different paths never share an id and the same text always
derives the same id. `slug_review_id` is the title -> id rule build_review's
default and read_decisions' expectation both use.

    review_ids.py 'stage0:Chapter 63'        -> prints the id
"""

from __future__ import annotations

import hashlib
import re
import sys

REVIEW_ID_RE = re.compile(r"[A-Za-z0-9_.:@-]{1,128}")
MAX_LEN = 128
_UNSAFE = re.compile(r"[^A-Za-z0-9_.:-]+")


def slug_review_id(text: str, limit: int = MAX_LEN) -> str:
    """Collapse every run of unsafe characters to '-', trim, and cap at `limit`."""
    s = _UNSAFE.sub("-", text).strip("-")[:limit].strip("-")
    return s or "review"


def derive_review_id(text: str) -> str:
    """A valid reviewId for `text`: itself if already valid, else slug + hash of the text."""
    if REVIEW_ID_RE.fullmatch(text):
        return text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"{slug_review_id(text, MAX_LEN - 9)}-{digest}"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: review_ids.py TEXT")
    print(derive_review_id(sys.argv[1]))
