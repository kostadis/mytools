"""Embedder dispatcher: local ONNX (fastembed) or DGX Ollama endpoint.

Set DT_EMBED_PROVIDER=dgx to route through Ollama on spark2
(http://192.168.1.121:11434/v1, model qwen3-embedding:0.6b, 1024-dim).
Default is "local" (all-MiniLM-L6-v2 via fastembed, 384-dim, no network).

IMPORTANT: switching providers requires `drive-tagger reset` because vectors
from different models are incompatible. Set DT_EMBED_DIM to match the model
(384 for local, 1024 for qwen3-embedding:0.6b).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Sequence

from .config import CONFIG


@lru_cache(maxsize=1)
def _local_model():
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=CONFIG.embed_model)


def _embed_local(texts: Sequence[str]) -> list[list[float]]:
    model = _local_model()
    return [vec.astype("float32").tolist() for vec in model.embed(list(texts))]


@lru_cache(maxsize=1)
def _dgx_client():
    from openai import OpenAI

    return OpenAI(base_url=CONFIG.dgx_embed_endpoint, api_key="unused")


def _embed_dgx(texts: Sequence[str]) -> list[list[float]]:
    client = _dgx_client()
    response = client.embeddings.create(model=CONFIG.dgx_embed_model, input=list(texts))
    return [e.embedding for e in response.data]


def embed(texts: Sequence[str]) -> list[list[float]]:
    """Embed a batch of texts into float vectors."""
    if not texts:
        return []
    if CONFIG.embed_provider == "dgx":
        return _embed_dgx(texts)
    return _embed_local(texts)


# Stable identity string so turbovecdb detects provider/model mismatches.
if CONFIG.embed_provider == "dgx":
    embed.__name__ = f"dgx::{CONFIG.dgx_embed_model}"
else:
    embed.__name__ = f"fastembed::{CONFIG.embed_model}"
