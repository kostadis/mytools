from __future__ import annotations

import re

# Models occasionally wrap JSON in ```json ... ``` fences despite being told not to.
# Strip a single leading/trailing fence so json.loads succeeds.
_FENCE_RE = re.compile(
    r"\A\s*```(?:[A-Za-z0-9_+-]+)?\s*\n?(.*?)\n?\s*```\s*\Z",
    re.DOTALL,
)


def strip_code_fence(text: str) -> str:
    """Return *text* with a surrounding ```...``` fence removed, if present."""
    match = _FENCE_RE.match(text)
    return match.group(1) if match else text
