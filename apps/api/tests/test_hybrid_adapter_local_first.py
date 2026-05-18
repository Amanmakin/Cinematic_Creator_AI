"""HybridAdapter — local_fallback strategy, happy path (local wins)."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from api.adapters.hybrid_adapter import HybridAdapter
from orchestrator.schemas.creative import AssetRef, CreativeIntent


@dataclass
class _Ctx:
    project_id: str = "proj-1"
    uar_root: str = "uar"


_INTENT = CreativeIntent(
    kind="generate_subject",
    target_path="layers/subject",
    parameters={"prompt": "a cinematic hero"},
    seed=42,
)

_FAKE_ASSET = AssetRef(asset_id="abc123", adapter="local_diffusers", adapter_version="1.0.0")


@pytest.mark.asyncio
async def test_local_fallback_uses_local_when_available():
    adapter = HybridAdapter(strategy="local_fallback")

    with (
        patch.object(adapter._local, "health_check", AsyncMock(return_value=True)),
        patch.object(adapter._local, "execute", AsyncMock(return_value=_FAKE_ASSET)),
        patch("api.adapters.hybrid_adapter._record_generation", AsyncMock()),
    ):
        payload = adapter.translate(_INTENT, _Ctx())
        result = await adapter.execute(payload)

    assert result.asset_id == "abc123"
    assert result.adapter == "local_diffusers"


@pytest.mark.asyncio
async def test_local_only_succeeds():
    adapter = HybridAdapter(strategy="local_only")

    with (
        patch.object(adapter._local, "health_check", AsyncMock(return_value=True)),
        patch.object(adapter._local, "execute", AsyncMock(return_value=_FAKE_ASSET)),
        patch("api.adapters.hybrid_adapter._record_generation", AsyncMock()),
    ):
        payload = adapter.translate(_INTENT, _Ctx())
        result = await adapter.execute(payload)

    assert result.adapter == "local_diffusers"
