"""OpenAI DALL-E adapter — generates images via OpenAI's images API."""

from __future__ import annotations

import hashlib
import time
from typing import TYPE_CHECKING

from api.adapters.base import ProviderUnavailable
from orchestrator.schemas.creative import AssetRef, CreativeIntent, ProviderPayload

if TYPE_CHECKING:
    from api.adapters.base import ProjectCtx


class OpenAIDALLEAdapter:
    """Calls OpenAI images.generate (DALL-E 3) and returns a hosted URL as AssetRef."""

    name = "openai_dalle"
    version = "1.0.0"

    def __init__(self, api_key: str, model: str = "dall-e-3", size: str = "1024x1024") -> None:
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

        image_url = response.data[0].url
        if not image_url:
            raise ProviderUnavailable("OpenAI returned no image URL")

        asset_id = hashlib.sha256(f"{image_url}{time.time()}".encode()).hexdigest()[:16]
        return AssetRef(
            asset_id=asset_id,
            adapter=self.name,
            adapter_version=self.version,
            source_url=image_url,
        )

    def cost_estimate(self, payload: ProviderPayload) -> int:
        return 40  # rough token-budget equivalent for a DALL-E 3 call
