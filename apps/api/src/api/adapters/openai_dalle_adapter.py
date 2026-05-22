"""OpenAI image adapter — generates images via OpenAI's images API (gpt-image-1)."""

from __future__ import annotations

import base64
import hashlib
import time
from pathlib import Path
from typing import TYPE_CHECKING

from api.adapters.base import ProviderUnavailable
from api.settings import settings
from orchestrator.schemas.creative import AssetRef, CreativeIntent, ProviderPayload

if TYPE_CHECKING:
    from api.adapters.base import ProjectCtx


class OpenAIDALLEAdapter:
    """Calls OpenAI images.generate (gpt-image-1) and persists the b64 result as a local asset."""

    name = "openai_dalle"
    version = "2.0.0"

    def __init__(self, api_key: str, model: str = "gpt-image-1", size: str = "1024x1024") -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for the openai_dalle strategy")
        self._api_key = api_key
        self._model = model
        self._size = size

    def supports(self, intent: CreativeIntent) -> bool:
        return True

    def translate(self, intent: CreativeIntent, ctx: "ProjectCtx") -> ProviderPayload:
        params = intent.parameters
        prompt = params.get("prompt", "")
        return ProviderPayload(
            model=self._model,
            inputs={"prompt": prompt, "size": self._size},
            adapter_hint="openai_dalle",
            estimated_tokens=0,
        )

    async def execute(self, payload: ProviderPayload) -> AssetRef:
        try:
            import openai
        except ImportError as exc:
            raise ProviderUnavailable("openai package not installed") from exc

        client = openai.AsyncOpenAI(api_key=self._api_key)
        prompt: str = payload.inputs.get("prompt", "")
        size: str = payload.inputs.get("size", self._size)

        if not prompt:
            raise ProviderUnavailable("DALL-E requires a non-empty prompt")

        try:
            response = await client.images.generate(
                model=self._model,
                prompt=prompt,
                size=size,  # type: ignore[arg-type]
                n=1,
            )
        except openai.AuthenticationError as exc:
            raise ProviderUnavailable(f"OpenAI authentication failed — check OPENAI_API_KEY: {exc}") from exc
        except openai.RateLimitError as exc:
            raise ProviderUnavailable(f"OpenAI rate limit reached: {exc}") from exc
        except openai.OpenAIError as exc:
            raise ProviderUnavailable(f"OpenAI API error: {exc}") from exc

        item = response.data[0]
        # gpt-image-1 returns b64_json; older models may still return url.
        b64 = getattr(item, "b64_json", None)
        if b64:
            img_bytes = base64.b64decode(b64)
            asset_id = hashlib.sha256(img_bytes).hexdigest()[:16]
            out_dir = Path(settings.uar_root) / "openai_images"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{asset_id}.png"
            out_path.write_bytes(img_bytes)
            return AssetRef(
                asset_id=asset_id,
                adapter=self.name,
                adapter_version=self.version,
                source_url=str(out_path),
            )

        image_url = getattr(item, "url", None)
        if not image_url:
            raise ProviderUnavailable("OpenAI returned neither b64_json nor url")
        asset_id = hashlib.sha256(f"{image_url}{time.time()}".encode()).hexdigest()[:16]
        return AssetRef(
            asset_id=asset_id,
            adapter=self.name,
            adapter_version=self.version,
            source_url=image_url,
        )

    def cost_estimate(self, payload: ProviderPayload) -> int:
        return 40  # rough token-budget equivalent for a gpt-image-1 call
