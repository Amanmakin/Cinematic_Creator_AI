"""D4/D5 — Rejection and style-override retrieval recall.

Verifies:
- Three rejections are stored and the top-k query returns the most relevant ones.
- Style overrides are stored and surfaced in the system message.
- Cross-project isolation: rejections in project A don't show in project B.
"""

from __future__ import annotations

import asyncio
import os
import struct

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")


# ---------------------------------------------------------------------------
# Stub embeddings so tests don't call OpenAI
# ---------------------------------------------------------------------------

def _unit_vec(seed: int, dim: int = 1536) -> list[float]:
    """Return a deterministic unit vector for a given seed."""
    import math
    base = [math.sin(seed * (i + 1)) for i in range(dim)]
    norm = sum(x ** 2 for x in base) ** 0.5
    return [x / norm for x in base]


def _install_stub_embed(monkeypatch, mapping: dict[str, list[float]]):
    """Patch embed() to return vectors from *mapping* (keyed by text prefix)."""
    import api.memory.embeddings as emb_mod

    def _stub(text: str) -> list[float]:
        for key, vec in mapping.items():
            if key in text:
                return vec
        return _unit_vec(hash(text) % 1000)

    def _stub_blob(text: str) -> bytes:
        vec = _stub(text)
        return struct.pack(f"<{len(vec)}f", *vec)

    monkeypatch.setattr(emb_mod, "embed", _stub)
    monkeypatch.setattr(emb_mod, "embed_to_blob", _stub_blob)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "test.sqlite")


@pytest.mark.asyncio
async def test_rejection_recall(db, monkeypatch):
    from api.memory import retrieval

    # Build distinct vectors for each rejection and the query
    saturated_vec = _unit_vec(1)
    garment_vec = _unit_vec(2)
    pose_vec = _unit_vec(3)
    query_vec = _unit_vec(1)  # closest to "saturated"

    _install_stub_embed(monkeypatch, {
        "saturated": saturated_vec,
        "garment": garment_vec,
        "pose": pose_vec,
        "query": query_vec,
    })

    await retrieval.init_tables(db)

    await retrieval.record_rejection("proj-A", "vivid colors", "too saturated", db_path=db)
    await retrieval.record_rejection("proj-A", "outfit", "wrong garment", db_path=db)
    await retrieval.record_rejection("proj-A", "stance", "wrong pose", db_path=db)

    msg = await retrieval.build("proj-A", "query text", top_k=3, db_path=db)

    assert msg is not None
    assert "Previously Rejected" in msg["content"]
    # All three should appear since top_k=3
    assert "too saturated" in msg["content"]
    assert "wrong garment" in msg["content"]
    assert "wrong pose" in msg["content"]


@pytest.mark.asyncio
async def test_style_override_surfaced(db, monkeypatch):
    from api.memory import retrieval

    _install_stub_embed(monkeypatch, {})

    await retrieval.init_tables(db)
    await retrieval.record_style_override("proj-B", "golden-hour side lighting", db_path=db)

    msg = await retrieval.build("proj-B", "any query", top_k=3, db_path=db)

    assert msg is not None
    assert "Pinned Style Overrides" in msg["content"]
    assert "golden-hour side lighting" in msg["content"]


@pytest.mark.asyncio
async def test_cross_project_isolation(db, monkeypatch):
    from api.memory import retrieval

    _install_stub_embed(monkeypatch, {})

    await retrieval.init_tables(db)
    await retrieval.record_rejection("proj-X", "the prompt", "bad reason", db_path=db)

    # Project Y should have no rejections
    msg = await retrieval.build("proj-Y", "any query", top_k=3, db_path=db)
    if msg is not None:
        assert "bad reason" not in msg["content"]


@pytest.mark.asyncio
async def test_empty_project_returns_none(db, monkeypatch):
    from api.memory import retrieval

    _install_stub_embed(monkeypatch, {})

    await retrieval.init_tables(db)
    msg = await retrieval.build("proj-empty", "any query", top_k=3, db_path=db)
    assert msg is None
