"""Plan 11 T2 — TextTo3DAdapter crops the reference before TripoSR."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from api import reference_vision
from api.adapters.text_to_3d_adapter import TextTo3DAdapter
from api.reference_vision import ReferenceAnalysis
from orchestrator.schemas.mesh_asset import BBox3

_BOUNDS = BBox3(min_x=0, min_y=0, min_z=0, max_x=1, max_y=1, max_z=1)
_FAKE_GLB = b"glTF-fake"


def _png_bytes(w: int = 200, h: int = 200) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 200, 90)).save(buf, format="PNG")
    return buf.getvalue()


def setup_function(_fn):
    reference_vision._ANALYSIS_CACHE.clear()


@pytest.mark.asyncio
async def test_triposr_receives_cropped_bytes_when_bbox_returned():
    adapter = TextTo3DAdapter(strategy="openai_assisted", openai_api_key="sk-test")
    captured: dict[str, bytes] = {}

    async def _fake_generate(image_bytes, filename="ref.png"):
        captured["bytes"] = image_bytes
        return _FAKE_GLB, _BOUNDS

    src = _png_bytes()
    with patch.object(adapter._triposr, "generate", side_effect=_fake_generate), patch(
        "api.adapters.text_to_3d_adapter.analyze_reference_image",
        return_value=ReferenceAnalysis(label="bottle", bbox_norm=(0.25, 0.25, 0.75, 0.75)),
    ):
        result = await adapter.generate("bottle", reference_image=src)

    assert result.source == "triposr"
    assert captured["bytes"] != src  # cropped


@pytest.mark.asyncio
async def test_triposr_receives_original_bytes_when_no_bbox():
    adapter = TextTo3DAdapter(strategy="openai_assisted", openai_api_key="")
    captured: dict[str, bytes] = {}

    async def _fake_generate(image_bytes, filename="ref.png"):
        captured["bytes"] = image_bytes
        return _FAKE_GLB, _BOUNDS

    src = _png_bytes()
    # Empty key → analysis returns nulls → no crop.
    adapter._triposr.generate = AsyncMock(side_effect=_fake_generate)  # type: ignore[method-assign]
    result = await adapter.generate("bottle", reference_image=src)

    assert result.source == "triposr"
    assert captured["bytes"] == src
