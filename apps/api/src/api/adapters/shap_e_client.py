"""Async HTTP client for the Shap-E Docker service."""

from __future__ import annotations

import logging

import httpx

from api.adapters.base import ProviderUnavailable
from api.adapters.triposr_client import _parse_mesh_multipart
from orchestrator.schemas.mesh_asset import BBox3

logger = logging.getLogger(__name__)


class ShapEClient:
    name = "shap_e"
    version = "1.0.0"

    def __init__(self, base_url: str = "http://localhost:8003", timeout_sec: float = 600.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_sec

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/health")
                return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError):
            return False

    async def generate(
        self,
        prompt: str,
        *,
        guidance_scale: float = 15.0,
        karras_steps: int = 32,
        seed: int | None = None,
    ) -> tuple[bytes, BBox3]:
        if not await self.health_check():
            raise ProviderUnavailable(
                f"Shap-E service unavailable at {self._base_url}. "
                "Run: docker compose up -d shap_e"
            )
        body = {
            "prompt": prompt,
            "guidance_scale": guidance_scale,
            "karras_steps": karras_steps,
            "seed": seed,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/generate", json=body)
                resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise ProviderUnavailable(f"Shap-E unreachable: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable(f"Shap-E timed out after {self._timeout}s") from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailable(
                f"Shap-E HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc

        return _parse_mesh_multipart(resp.content, resp.headers.get("content-type", ""))
