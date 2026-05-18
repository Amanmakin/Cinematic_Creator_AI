"""HybridAdapter — failure paths when local Docker is unavailable."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from api.adapters.base import ProviderUnavailable
from api.adapters.hybrid_adapter import HybridAdapter
from orchestrator.schemas.creative import AssetRef, CreativeIntent


@dataclass
class _Ctx:
    project_id: str = "proj-fallback"
    uar_root: str = "uar"


_INTENT = CreativeIntent(
    kind="generate_background",
    target_path="layers/bg",
    parameters={"prompt": "stormy sky"},
    seed=7,
)

_LOCAL_ASSET = AssetRef(asset_id="local-fallback", adapter="local_diffusers", adapter_version="1.0.0")


@pytest.mark.asyncio
async def test_local_only_raises_when_docker_unavailable():
    adapter = HybridAdapter(strategy="local_only")

    with (
        patch.object(adapter._local, "health_check", AsyncMock(return_value=False)),
        patch.object(
            adapter._local,
            "execute",
            AsyncMock(side_effect=ProviderUnavailable("Docker down")),
        ),
        patch("api.adapters.hybrid_adapter._record_generation", AsyncMock()),
    ):
        payload = adapter.translate(_INTENT, _Ctx())
        with pytest.raises(ProviderUnavailable):
            await adapter.execute(payload)


@pytest.mark.asyncio
async def test_local_fallback_raises_when_docker_unavailable():
    adapter = HybridAdapter(strategy="local_fallback")

    with (
        patch.object(adapter._local, "health_check", AsyncMock(return_value=False)),
        patch.object(
            adapter._local,
            "execute",
            AsyncMock(side_effect=ProviderUnavailable("Docker down")),
        ),
        patch("api.adapters.hybrid_adapter._record_generation", AsyncMock()),
    ):
        payload = adapter.translate(_INTENT, _Ctx())
        with pytest.raises(ProviderUnavailable):
            await adapter.execute(payload)


@pytest.mark.asyncio
async def test_local_fallback_succeeds_when_docker_available():
    adapter = HybridAdapter(strategy="local_fallback")

    with (
        patch.object(adapter._local, "execute", AsyncMock(return_value=_LOCAL_ASSET)),
        patch("api.adapters.hybrid_adapter._record_generation", AsyncMock()),
    ):
        payload = adapter.translate(_INTENT, _Ctx())
        result = await adapter.execute(payload)

    assert result.asset_id == "local-fallback"
    assert result.adapter == "local_diffusers"
