"""LocalDockerAdapter.health_check() — unit tests (no real Docker required)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from api.adapters.local_docker_adapter import LocalDockerAdapter


@pytest.mark.asyncio
async def test_health_check_returns_true_when_service_ok():
    adapter = LocalDockerAdapter(base_url="http://localhost:8001")
    mock_resp = MagicMock(status_code=200)

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_cls.return_value = mock_client

        result = await adapter.health_check()

    assert result is True


@pytest.mark.asyncio
async def test_health_check_returns_false_on_connect_error():
    adapter = LocalDockerAdapter(base_url="http://localhost:8001")

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_cls.return_value = mock_client

        result = await adapter.health_check()

    assert result is False


@pytest.mark.asyncio
async def test_health_check_returns_false_on_timeout():
    adapter = LocalDockerAdapter(base_url="http://localhost:8001")

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout", request=None))
        mock_cls.return_value = mock_client

        result = await adapter.health_check()

    assert result is False


@pytest.mark.asyncio
async def test_execute_raises_provider_unavailable_when_docker_down():
    from api.adapters.base import ProviderUnavailable
    from orchestrator.schemas.creative import ProviderPayload

    adapter = LocalDockerAdapter(base_url="http://localhost:8001")

    with patch.object(adapter, "health_check", AsyncMock(return_value=False)):
        payload = ProviderPayload(
            model="sd1.5",
            inputs={"prompt": "test"},
            adapter_hint="local_diffusers",
            estimated_tokens=0,
        )
        with pytest.raises(ProviderUnavailable, match="unavailable"):
            await adapter.execute(payload)
