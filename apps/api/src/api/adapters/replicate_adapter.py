"""Replicate adapter — SDXL for generation, rembg for alpha, MiDaS for depth."""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import TYPE_CHECKING

import httpx

from api.adapters.base import ProviderUnavailable
from orchestrator.schemas.creative import AssetRef, CreativeIntent, ProviderPayload

if TYPE_CHECKING:
    from api.adapters.base import ProjectCtx

_SDXL_MODEL = "stability-ai/sdxl:39ed52f2319f9b27d1fd1b43e0d71e5e5cc1dcd0"
_REMBG_MODEL = "cjwbw/rembg:fb8af171cfa1616ddcf1242c851defdfa9538cd3"
_MIDAS_MODEL = "cjwbw/midas:a6ba5798f04f80d3b314de0f0a62277f21ab3793"
_CONTROLNET_MODEL = "jagilley/controlnet-canny:aff48af9c68d162388d230a2ab003f68d2638d88"

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
            width = params.get("width", 1024)
            height = params.get("height", 1024)
            negative = params.get("negative_prompt", "")
            inputs = {
                "prompt": prompt,
                "negative_prompt": negative,
                "width": width,
                "height": height,
                "seed": intent.seed,
                "num_outputs": 1,
                "apply_watermark": False,
            }
            estimated = (width * height // 1024) * _COST_PER_STEP
            return ProviderPayload(
                model=_SDXL_MODEL,
                inputs=inputs,
                adapter_hint=intent.adapter_hint or "replicate.sdxl",
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
            # post-processing intents (lighting, blur, palette) are cheap no-ops at payload level
            return ProviderPayload(
                model="noop",
                inputs={"kind": intent.kind, "parameters": params},
                adapter_hint=intent.adapter_hint or "replicate.noop",
                estimated_tokens=0,
            )

    async def execute(self, payload: ProviderPayload) -> AssetRef:
        if payload.model == "noop":
            return AssetRef(
                asset_id=_short_hash(json.dumps(payload.inputs, sort_keys=True)),
                adapter=self.name,
                adapter_version=self.version,
            )
        headers = {
            "Authorization": f"Token {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {"version": payload.model.split(":")[-1], "input": payload.inputs}
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self._base_url}/predictions", headers=headers, json=body
                )
                resp.raise_for_status()
                prediction = resp.json()
                prediction_id = prediction["id"]
                output_url = await self._poll(client, headers, prediction_id)
        except httpx.ConnectError as exc:
            raise ProviderUnavailable(f"Replicate unreachable: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailable(f"Replicate HTTP {exc.response.status_code}") from exc

        asset_id = _short_hash(output_url + str(time.time()))
        return AssetRef(
            asset_id=asset_id,
            adapter=self.name,
            adapter_version=self.version,
        )

    async def _poll(
        self, client: httpx.AsyncClient, headers: dict, prediction_id: str, *, max_wait: float = 120.0
    ) -> str:
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            resp = await client.get(
                f"{self._base_url}/predictions/{prediction_id}", headers=headers
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
            import asyncio
            await asyncio.sleep(2.0)
        raise ProviderUnavailable(f"Replicate prediction {prediction_id} timed out")

    def cost_estimate(self, payload: ProviderPayload) -> int:
        return payload.estimated_tokens


def _short_hash(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]
