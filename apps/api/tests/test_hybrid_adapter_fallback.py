"""HybridAdapter — fallback paths when local or Replicate fails."""

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

_REP_ASSET = AssetRef(asset_id="rep-fallback", adapter="replicate", adapter_version="1.0.0")
_LOCAL_ASSET = AssetRef(asset_id="local-fallback", adapter="local_diffusers", adapter_version="1.0.0")


@pytest.mark.asyncio
async def test_local_fallback_falls_back_to_replicate_on_provider_unavailable():
    adapter = HybridAdapter(api_key="dummy", strategy="local_fallback")

    with (
        patch.object(
            adapter._local, "health_check", AsyncMock(return_value=False)
        ),
        patch.object(
            adapter._local,
            "execute",
            AsyncMock(side_effect=ProviderUnavailable("Docker down")),
        ),
        patch.object(adapter._replicate, "execute", AsyncMock(return_value=_REP_ASSET)),
        patch("api.adapters.hybrid_adapter._record_generation", AsyncMock()),
    ):
        payload = adapter.translate(_INTENT, _Ctx())
        result = await adapter.execute(payload)

    assert result.asset_id == "rep-fallback"


@pytest.mark.asyncio
async def test_replicate_fallback_falls_back_to_local():
    adapter = HybridAdapter(api_key="dummy", strategy="replicate_fallback")

    with (
        patch.object(
            adapter._replicate,
            "execute",
            AsyncMock(side_effect=ProviderUnavailable("Replicate down")),
        ),
        patch.object(adapter._local, "health_check", AsyncMock(return_value=True)),
        patch.object(adapter._local, "execute", AsyncMock(return_value=_LOCAL_ASSET)),
        patch("api.adapters.hybrid_adapter._record_generation", AsyncMock()),
    ):
        payload = adapter.translate(_INTENT, _Ctx())
        result = await adapter.execute(payload)

    assert result.asset_id == "local-fallback"


@pytest.mark.asyncio
async def test_local_only_raises_when_docker_unavailable():
    adapter = HybridAdapter(api_key="dummy", strategy="local_only")

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
async def test_fallback_triggered_flag_recorded():
    adapter = HybridAdapter(api_key="dummy", strategy="local_fallback")
    recorded: list[dict] = []

    async def capture(**kwargs):
        recorded.append(kwargs)

    with (
        patch.object(adapter._local, "health_check", AsyncMock(return_value=False)),
        patch.object(
            adapter._local,
            "execute",
            AsyncMock(side_effect=ProviderUnavailable("Docker down")),
        ),
        patch.object(adapter._replicate, "execute", AsyncMock(return_value=_REP_ASSET)),
        patch("api.adapters.hybrid_adapter._record_generation", capture),
    ):
        payload = adapter.translate(_INTENT, _Ctx())
        await adapter.execute(payload)

    assert len(recorded) == 1
    assert recorded[0]["fallback_triggered"] is True
    assert recorded[0]["provider"] == "replicate"
