"""D6 — Cold-start determinism.

Verifies that calling build_llm_context twice on the same project (simulating a
restart) produces byte-for-byte identical output, as validated by the SHA-256 of
the assembled context.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import struct

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")


def _install_stub_embed(monkeypatch):
    import api.memory.embeddings as emb_mod

    def _stub(text: str) -> list[float]:
        return [0.01] * 1536

    def _stub_blob(text: str) -> bytes:
        return struct.pack("<1536f", *([0.01] * 1536))

    monkeypatch.setattr(emb_mod, "embed", _stub)
    monkeypatch.setattr(emb_mod, "embed_to_blob", _stub_blob)
    emb_mod._cached_embed.cache_clear()


def _sha(msgs: list[dict]) -> str:
    return hashlib.sha256(json.dumps(msgs, sort_keys=True).encode()).hexdigest()


@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "test.sqlite")


@pytest.mark.asyncio
async def test_cold_start_determinism(db, monkeypatch):
    """Two calls with the same project state must produce identical context bytes."""
    _install_stub_embed(monkeypatch)

    from orchestrator.schemas.canon import ProjectCanon
    from api.memory.build_context import build_llm_context
    from api.memory import retrieval, compressed

    await retrieval.init_tables(db)
    await compressed.init_table(db)

    # Seed the project with a rejection and a style override
    await retrieval.record_rejection("proj-cold", "prompt A", "too dark", db_path=db)
    await retrieval.record_style_override("proj-cold", "warm tones", db_path=db)

    canon = ProjectCanon(
        aspect_ratio="16:9",
        duration_seconds_max=60.0,
        aesthetic_tags=["cinematic"],
        style_guide="noir",
    )

    first = await build_llm_context(
        "proj-cold", "a rainy street at night", canon, db_path=db
    )
    second = await build_llm_context(
        "proj-cold", "a rainy street at night", canon, db_path=db
    )

    assert _sha(first) == _sha(second), (
        "Context SHA mismatch — cold-start determinism broken.\n"
        f"First:  {_sha(first)}\nSecond: {_sha(second)}"
    )


@pytest.mark.asyncio
async def test_canon_section_is_first(db, monkeypatch):
    """Canon must always be the first message for prompt-cache alignment."""
    _install_stub_embed(monkeypatch)

    from orchestrator.schemas.canon import ProjectCanon
    from api.memory.build_context import build_llm_context
    from api.memory import retrieval, compressed

    await retrieval.init_tables(db)
    await compressed.init_table(db)

    canon = ProjectCanon(aspect_ratio="9:16", duration_seconds_max=15.0)
    msgs = await build_llm_context(
        "proj-order", "sky at dawn", canon, db_path=db
    )

    assert msgs, "context is empty"
    assert "Project Canon" in msgs[0]["content"], (
        f"First message is not the canon; got: {msgs[0]['content'][:80]}"
    )


@pytest.mark.asyncio
async def test_rebuild_under_500ms(db, monkeypatch):
    """Rebuild should complete in under 500 ms (D6 performance requirement)."""
    import time
    _install_stub_embed(monkeypatch)

    from orchestrator.schemas.canon import ProjectCanon
    from api.memory.build_context import build_llm_context
    from api.memory import retrieval, compressed
    from api.dag.reducers import record_event

    await retrieval.init_tables(db)
    await compressed.init_table(db)

    # Ensure dag_events table exists by writing a few events with a custom db_path
    # (record_event uses settings.db_path, so we use the retrieval/compressed tables only)

    canon = ProjectCanon(aspect_ratio="1:1", duration_seconds_max=10.0)

    start = time.monotonic()
    await build_llm_context("proj-perf", "test prompt", canon, db_path=db)
    elapsed = time.monotonic() - start

    assert elapsed < 0.5, f"build_llm_context took {elapsed:.3f}s (limit: 0.5s)"
