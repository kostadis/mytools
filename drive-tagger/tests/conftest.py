import hashlib

import pytest

from drive_tagger.config import CONFIG


def _fake_embed(texts):
    """Deterministic, network-free, dependency-free fake embedder. Tests here
    only assert on category/document bookkeeping (merge correctness, member
    counts, decision application) — they never assert on vector similarity —
    so the fake vectors' actual values don't matter, only that they exist
    and match CONFIG.embed_dim."""
    out = []
    for t in texts:
        h = hashlib.sha256(t.encode("utf-8")).digest()
        out.append([b / 255.0 for b in h[: CONFIG.embed_dim]])
    return out


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Point CONFIG at a scratch dir and swap in a fast fake embedder, so
    tests never touch the real data/db, reports/, or fastembed's ONNX model
    (which could require a network download on first use)."""
    monkeypatch.setattr(CONFIG, "data_dir", tmp_path / "data")
    monkeypatch.setattr(CONFIG, "reports_dir", tmp_path / "reports")
    monkeypatch.setattr(CONFIG, "embed_dim", 8)
    monkeypatch.setattr("drive_tagger.store.embed", _fake_embed)
    return CONFIG
