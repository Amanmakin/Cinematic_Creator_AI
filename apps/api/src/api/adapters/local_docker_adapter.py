"""Local Docker adapter — calls a containerised diffusers inference service."""

from __future__ import annotations

import base64
import hashlib
import os
import time
from typing import TYPE_CHECKING

import httpx

from api.adapters.base import ProviderUnavailable
from orchestrator.schemas.creative import AssetRef, CreativeIntent, ProviderPayload

if TYPE_CHECKING:
    from api.adapters.base import ProjectCtx

_GENERATION_KINDS = {"generate_subject", "generate_background", "generate_foreground_fx", "regenerate_layer"}


class LocalDockerAdapter:
    """HTTP client that delegates image generation to a local Docker diffusers service."""

    name = "local_diffusers"
    version = "1.1.0"  # bumped: Blender 5.x wireframe fix → better SD conditioning

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout_sec: float = 600.0,
        use_smaller_model: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_sec
        self._use_smaller_model = use_smaller_model

    async def health_check(self) -> bool:
        """Return True if the Docker diffusers service is reachable and healthy."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/health")
                return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError):
            return False

    def supports(self, intent: CreativeIntent) -> bool:
        return intent.kind in _GENERATION_KINDS

    def translate(self, intent: CreativeIntent, ctx: "ProjectCtx") -> ProviderPayload:
        params = intent.parameters
        inputs: dict = {
            "prompt": params.get("prompt", ""),
            "negative_prompt": params.get("negative_prompt", ""),
            "width": params.get("width", 512 if self._use_smaller_model else 1024),
            "height": params.get("height", 512 if self._use_smaller_model else 1024),
            "seed": intent.seed,
            "num_inference_steps": 12 if self._use_smaller_model else 20,
        }
        # Pass wireframe path through so execute() can encode it as img2img init_image
        if "wireframe_image_path" in params:
            inputs["_wireframe_image_path"] = params["wireframe_image_path"]
        return ProviderPayload(
            model="sd1.5" if self._use_smaller_model else "sdxl",
            inputs=inputs,
            adapter_hint="local_diffusers",
            estimated_tokens=0,
        )

    async def execute(self, payload: ProviderPayload) -> AssetRef:
        if not await self.health_check():
            raise ProviderUnavailable(
                f"Local Docker service unavailable at {self._base_url}. "
                "Run: docker compose up -d diffusers"
            )

        # Build the request body — strip internal keys not meant for the API
        body = {k: v for k, v in payload.inputs.items() if not k.startswith("_")}

        # If a wireframe sheet is available, encode it for img2img conditioning
        wireframe_path = payload.inputs.get("_wireframe_image_path")
        if wireframe_path and os.path.exists(wireframe_path):
            with open(wireframe_path, "rb") as f:
                body["init_image"] = base64.b64encode(f.read()).decode()
            body["strength"] = 0.50  # 50% denoising keeps wireframe composition intact
            if not body.get("negative_prompt"):
                body["negative_prompt"] = "photograph, photo, real, grainy, blurry, low quality"

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/generate",
                    headers={"Content-Type": "application/json"},
                    json=body,
                )
                resp.raise_for_status()
                result = resp.json()
                output_url = result["image_url"]  # "file:///tmp/gen_XXX.png"
        except httpx.ConnectError as exc:
            raise ProviderUnavailable(f"Docker service unreachable: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable(f"Docker service timed out after {self._timeout}s") from exc
        except httpx.RemoteProtocolError as exc:
            raise ProviderUnavailable(f"Docker service disconnected without response: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailable(
                f"Docker service HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc

        elapsed = time.monotonic() - t0
        asset_id = _short_hash(output_url + str(time.time()))
        self.last_inference_time_sec = round(elapsed, 2)

        # Build an HTTP URL so the UAR store can download the image regardless of
        # whether the diffusers service is in a separate container.
        filename = os.path.basename(output_url.replace("file://", ""))
        http_source_url = f"{self._base_url}/images/{filename}"

        return AssetRef(
            asset_id=asset_id,
            adapter=self.name,
            adapter_version=self.version,
            source_url=http_source_url,
        )

    def cost_estimate(self, payload: ProviderPayload) -> int:
        return 0


def _short_hash(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]
