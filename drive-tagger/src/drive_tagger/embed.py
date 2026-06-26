"""Local ONNX embedder via fastembed (no torch).

Exposes an ``embed(texts) -> list[list[float]]`` callable suitable for handing to
a turbovecdb collection. The model is loaded lazily on first use so importing
this module stays cheap. turbovecdb L2-normalizes vectors internally, so the raw
fastembed output is fine.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Sequence

from .config import CONFIG


@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=CONFIG.embed_model)


def embed(texts: Sequence[str]) -> list[list[float]]:
    """Embed a batch of texts into float vectors."""
    if not texts:
        return []
    model = _model()
    return [vec.astype("float32").tolist() for vec in model.embed(list(texts))]


# A stable __name__ so turbovecdb's embedder-identity check is meaningful.
embed.__name__ = f"fastembed::{CONFIG.embed_model}"
