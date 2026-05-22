"""Hybrid adapter — routes generation to local Docker or OpenAI DALL-E."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from api.adapters.base import ProviderUnavailable
from api.adapters.local_docker_adapter import LocalDockerAdapter
from orchestrator.schemas.creative import AssetRef, CreativeIntent, ProviderPayload

if TYPE_CHECKING:
    from api.adapters.base import ProjectCtx

logger = logging.getLogger(__name__)

_STRATEGIES = {"local_only", "local_fallback", "openai_dalle"}

_INTENT_KEY = "__hybrid_intent"
_PROJECT_KEY = "__hybrid_project_id"
_UAR_KEY = "__hybrid_uar_root"


@dataclass
class _SimpleCtx:
    project_id: str
    uar_root: str


class HybridAdapter:
    """Routes generation to the configured backend.

    Strategies:
    - local_only     Local Docker inference; fails hard if Docker is down.
    - local_fallback Local Docker inference; raises ProviderUnavailable on error.
    - openai_dalle   OpenAI DALL-E 3 cloud generation. Requires OPENAI_API_KEY.
    """

    name = "hybrid"
    version = "1.1.0"

    def __init__(
        self,
        strategy: str = "local_fallback",
        docker_base_url: str = "http://localhost:8000",
        timeout_local: float = 600.0,
        use_smaller_model: bool = True,
        openai_api_key: str = "",
        **_: object,
    ) -> None:
        if strategy not in _STRATEGIES:
            raise ValueError(f"Unknown strategy {strategy!r}. Choose from {_STRATEGIES}")
        self._strategy = strategy
        self._local = LocalDockerAdapter(
            base_url=docker_base_url,
            timeout_sec=timeout_local,
            use_smaller_model=use_smaller_model,
        )
        self._openai_api_key = openai_api_key

    # ------------------------------------------------------------------
    # CreativeAdapter protocol
    # ------------------------------------------------------------------

    def supports(self, intent: CreativeIntent) -> bool:
        return True

    def translate(self, intent: CreativeIntent, ctx: "ProjectCtx") -> ProviderPayload:
        return ProviderPayload(
            model="hybrid",
            inputs={
                _INTENT_KEY: intent.model_dump(),
                _PROJECT_KEY: ctx.project_id,
                _UAR_KEY: ctx.uar_root,
            },
            adapter_hint="hybrid",
            estimated_tokens=0,
        )

    async def execute(self, payload: ProviderPayload) -> AssetRef:
        intent = CreativeIntent.model_validate(payload.inputs[_INTENT_KEY])
        project_id: str = payload.inputs[_PROJECT_KEY]
        uar_root: str = payload.inputs[_UAR_KEY]
        ctx = _SimpleCtx(project_id=project_id, uar_root=uar_root)

        t0 = time.monotonic()

        if self._strategy == "openai_dalle":
            from api.adapters.openai_dalle_adapter import OpenAIDALLEAdapter
            dalle = OpenAIDALLEAdapter(api_key=self._openai_api_key)
            dalle_payload = dalle.translate(intent, ctx)
            result = await dalle.execute(dalle_payload)
            provider = "openai_dalle"
            model_used = dalle_payload.model
            cost_usd = 0.04  # DALL-E 3 standard 1024x1024
        else:
            local_payload = self._local.translate(intent, ctx)
            result = await self._local.execute(local_payload)
            provider = "local_diffusers"
            model_used = local_payload.model
            cost_usd = 0.0

        elapsed = round(time.monotonic() - t0, 2)

        await _record_generation(
            project_id=project_id,
            asset_id=result.asset_id,
            provider=provider,
            model_used=model_used,
            inference_time_sec=elapsed,
            cost_usd=cost_usd,
            fallback_triggered=False,
        )

        return result

    def cost_estimate(self, payload: ProviderPayload) -> int:
        return 0


async def _record_generation(
    *,
    project_id: str,
    asset_id: str,
    provider: str,
    model_used: str,
    inference_time_sec: float,
    cost_usd: float,
    fallback_triggered: bool,
) -> None:
    from api.dag.reducers import record_event
    try:
        await record_event(
            project_id=project_id,
            kind="AssetGenerated",
            payload={
                "asset_id": asset_id,
                "provider": provider,
                "model_used": model_used,
                "inference_time_sec": inference_time_sec,
                "cost_usd": cost_usd,
                "fallback_triggered": fallback_triggered,
            },
        )
    except Exception:
        logger.exception("Failed to record AssetGenerated event for project %s", project_id)
