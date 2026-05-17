"""Replicate adapter — Flux Schnell for generation, model-endpoint API."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import TYPE_CHECKING

import httpx

from api.adapters.base import ProviderUnavailable
from orchestrator.schemas.creative import AssetRef, CreativeIntent, ProviderPayload

if TYPE_CHECKING:
    from api.adapters.base import ProjectCtx

logger = logging.getLogger(__name__)

# Deployment models — use POST /models/{owner}/{name}/predictions (no version hash needed).
_FLUX_MODEL = "black-forest-labs/flux-schnell"
_CONTROLNET_MODEL = "jagilley/controlnet-canny"

_GENERATION_KINDS = {"generate_subject", "generate_background", "generate_foreground_fx"}
_REGEN_KINDS = {"regenerate_layer"}

_COST_PER_STEP = 4


class ReplicateAdapter:
    name = "replicate"
    version = "1.0.0"

    def __init__(self, api_key: str, base_url: str = "https://api.replicate.com/v1") -> None:
        self._api_key = api_key
        self._base_url = base_url

    def supports(self, intent: CreativeIntent) -> bool:
        return True

    def translate(self, intent: CreativeIntent, ctx: "ProjectCtx") -> ProviderPayload:
        params = intent.parameters
        if intent.kind in _GENERATION_KINDS:
            prompt = params.get("prompt", "")
            # Flux Schnell accepts width/height up to 1440; use aspect_ratio-friendly sizes.
            width = min(params.get("width", 1024), 1024)
            height = min(params.get("height", 1024), 1024)
            inputs = {
                "prompt": prompt,
                "seed": intent.seed,
                "num_outputs": 1,
                "num_inference_steps": 4,
                "output_format": "png",
                "width": width,
                "height": height,
            }
            estimated = (width * height // 1024) * _COST_PER_STEP
            return ProviderPayload(
                model=_FLUX_MODEL,
                inputs=inputs,
                adapter_hint=intent.adapter_hint or "replicate.flux",
                estimated_tokens=estimated,
            )
        elif intent.kind in _REGEN_KINDS:
            inputs = {
                "prompt": params.get("modification_prompt", ""),
                "seed": intent.seed,
                "num_outputs": 1,
            }
            return ProviderPayload(
                model=_CONTROLNET_MODEL,
                inputs=inputs,
                adapter_hint="replicate.controlnet",
                estimated_tokens=512,
            )
        else:
            return ProviderPayload(
                model="noop",
                inputs={"kind": intent.kind, "parameters": params},
                adapter_hint=intent.adapter_hint or "replicate.noop",
                estimated_tokens=0,
            )

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def execute(self, payload: ProviderPayload) -> AssetRef:
        if payload.model == "noop":
            return AssetRef(
                asset_id=_short_hash(json.dumps(payload.inputs, sort_keys=True)),
                adapter=self.name,
                adapter_version=self.version,
            )
        url = f"{self._base_url}/models/{payload.model}/predictions"
        body = {"input": payload.inputs}
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                for attempt in range(4):
                    resp = await client.post(url, headers=self._headers(), json=body)
                    if resp.status_code == 429 and attempt < 3:
                        wait = 2 ** attempt * 3
                        logger.warning("Replicate 429, retrying in %ss (attempt %d)", wait, attempt + 1)
                        await asyncio.sleep(wait)
                        continue
                    if not resp.is_success:
                        logger.error("Replicate %s — %s", resp.status_code, resp.text[:400])
                    resp.raise_for_status()
                    break
                prediction = resp.json()
                prediction_id = prediction["id"]
                output_url = await self._poll(client, prediction_id)
        except httpx.ConnectError as exc:
            raise ProviderUnavailable(f"Replicate unreachable: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailable(f"Replicate HTTP {exc.response.status_code}") from exc

        return AssetRef(
            asset_id=_short_hash(output_url + str(time.time())),
            adapter=self.name,
            adapter_version=self.version,
        )

    async def _poll(
        self, client: httpx.AsyncClient, prediction_id: str, *, max_wait: float = 120.0
    ) -> str:
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            resp = await client.get(
                f"{self._base_url}/predictions/{prediction_id}", headers=self._headers()
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status")
            if status == "succeeded":
                output = data.get("output")
                if isinstance(output, list):
                    return output[0]
                return str(output)
            if status in ("failed", "canceled"):
                raise ProviderUnavailable(f"Replicate prediction {prediction_id} {status}")
            await asyncio.sleep(2.0)
        raise ProviderUnavailable(f"Replicate prediction {prediction_id} timed out")

    def cost_estimate(self, payload: ProviderPayload) -> int:
        return payload.estimated_tokens


def _short_hash(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]
