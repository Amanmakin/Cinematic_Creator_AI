"""D2 — Context window builder token-cap enforcement.

Verifies that build_llm_context stays under the requested cap and that the
trim order is: oldest compressed chunks first, then working-memory events,
and canon is never dropped.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

# ---------------------------------------------------------------------------
# Helpers that create fake memory entries without calling OpenAI
# ---------------------------------------------------------------------------

def _make_canon_msg() -> dict:
    return {"role": "system", "content": "## Project Canon\n\n" + ("x" * 500)}


def _make_compressed_msg(idx: int) -> dict:
    return {
        "role": "system",
        "content": f"## Compressed History\n\n[Chunk {idx}]: " + ("e" * 400),
    }


def _make_working_msg(n_events: int) -> dict:
    lines = [f"- [TaskEnqueued] node=n{i} payload={{}}" for i in range(n_events)]
    return {"role": "assistant", "content": "## Recent Events\n\n" + "\n".join(lines)}


def _make_user_msg(prompt: str = "test prompt") -> dict:
    return {"role": "user", "content": prompt}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_trim_needed():
    from api.memory.build_context import trim_to_cap

    msgs = [_make_canon_msg(), _make_user_msg()]
    result = trim_to_cap(msgs, token_cap=10_000)
    assert result == msgs


def test_drops_compressed_first():
    from api.memory.build_context import trim_to_cap

    canon = _make_canon_msg()
    c1 = _make_compressed_msg(1)
    c2 = _make_compressed_msg(2)
    working = _make_working_msg(5)
    user = _make_user_msg()

    # Build a context that's over cap — compressed chunks should be trimmed first.
    # Each msg is ~100-150 tokens; set cap tight enough to force dropping c1.
    msgs = [canon, c1, c2, working, user]
    result = trim_to_cap(msgs, token_cap=400)

    contents = [m["content"] for m in result]
    # Canon must survive
    assert any("Project Canon" in c for c in contents), "canon was dropped"
    # At least one compressed chunk should have been removed
    compressed_count = sum(1 for c in contents if "Compressed History" in c)
    total_original = 2
    assert compressed_count < total_original, "no compressed chunk was dropped"


def test_canon_never_dropped():
    from api.memory.build_context import trim_to_cap

    # Even with a tiny cap, canon should remain.
    msgs = [
        _make_canon_msg(),
        _make_compressed_msg(1),
        _make_compressed_msg(2),
        _make_compressed_msg(3),
        _make_working_msg(20),
        _make_user_msg(),
    ]
    result = trim_to_cap(msgs, token_cap=50)
    assert any("Project Canon" in m["content"] for m in result), "canon was dropped"


def test_token_estimate_accuracy():
    from api.memory.build_context import _token_estimate

    msg = {"role": "system", "content": "a" * 400}
    # 400 chars / 4 = 100 tokens
    assert _token_estimate(msg) == 100


def test_context_under_cap_async(tmp_path):
    """Full async build with stub embeddings — checks the output fits cap."""
    import sys
    sys.path.insert(0, str(tmp_path))

    # Patch embed to avoid real API calls
    import api.memory.embeddings as emb_mod
    original_embed = emb_mod._cached_embed

    def _fake_embed(text: str):
        import struct
        fake = [0.01] * 1536
        return tuple(fake)

    emb_mod._cached_embed = _fake_embed  # type: ignore

    try:
        from orchestrator.schemas.canon import ProjectCanon
        from api.memory.build_context import build_llm_context, _token_estimate

        db = str(tmp_path / "test.sqlite")
        canon = ProjectCanon(aspect_ratio="16:9", duration_seconds_max=30.0)

        msgs = asyncio.run(
            build_llm_context(
                "proj-cap-test",
                "generate a knight",
                canon,
                scene_graph=None,
                token_cap=12_000,
                db_path=db,
            )
        )
        total = sum(_token_estimate(m) for m in msgs)
        assert total <= 12_000, f"context exceeds cap: {total} tokens"
    finally:
        emb_mod._cached_embed = original_embed  # type: ignore
