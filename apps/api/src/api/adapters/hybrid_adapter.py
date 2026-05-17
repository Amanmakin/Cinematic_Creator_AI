"""Hybrid adapter — routes generation to local Docker or Replicate based on strategy."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from api.adapters.base import ProviderUnavailable
from api.adapters.local_docker_adapter import LocalDockerAdapter
from api.adapters.replicate_adapter import ReplicateAdapter
from orchestrator.schemas.creative import AssetRef, CreativeIntent, ProviderPayload

if TYPE_CHECKING:
    from api.adapters.base import ProjectCtx

logger = logging.getLogger(__name__)

_STRATEGIES = {"local_only", "local_fallback", "replicate_only", "replicate_fallback"}

# Sentinel key embedded in payload.inputs so execute() can re-translate per provider.
_INTENT_KEY = "__hybrid_intent"
_PROJECT_KEY = "__hybrid_project_id"
_UAR_KEY = "__hybrid_uar_root"


@dataclass
class _SimpleCtx:
    project_id: str
    uar_root: str


class HybridAdapter:
    """Delegates to LocalDockerAdapter, falls back to ReplicateAdapter on error or config.

    Strategies:
    - local_only         fail if local inference unavailable
    - local_fallback     local first, Replicate on error (default)
    - replicate_only     always use Replicate
    - replicate_fallback Replicate first, local on API failure
    """

    name = "hybrid"
    version = "1.0.0"

    def __init__(
        self,
        api_key: str,
        strategy: str = "local_fallback",
        docker_base_url: str = "http://localhost:8000",
        timeout_local: float = 600.0,
        timeout_replicate: float = 120.0,
        use_smaller_model: bool = True,
    ) -> None:
        if strategy not in _STRATEGIES:
            raise ValueError(f"Unknown strategy {strategy!r}. Choose from {_STRATEGIES}")
        self._strategy = strategy
        self._local = LocalDockerAdapter(
            base_url=docker_base_url,
            timeout_sec=timeout_local,
            use_smaller_model=use_smaller_model,
        )
        self._replicate = ReplicateAdapter(api_key=api_key)

    # ------------------------------------------------------------------
    # CreativeAdapter protocol
    # ------------------------------------------------------------------

    def supports(self, intent: CreativeIntent) -> bool:
        return True

    def translate(self, intent: CreativeIntent, ctx: "ProjectCtx") -> ProviderPayload:
        # Store the intent + ctx so execute() can re-translate for whichever provider wins.
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
        provider: str
        model_used: str
        fallback_triggered = False

        if self._strategy == "local_fallback":
            try:
                local_payload = self._local.translate(intent, ctx)
                result = await self._local.execute(local_payload)
                provider = "local_diffusers"
                model_used = local_payload.model
            except (ProviderUnavailable, RuntimeError, MemoryError) as exc:
                logger.warning("Local inference failed (%s). Falling back to Replicate.", exc)
                fallback_triggered = True
                rep_payload = self._replicate.translate(intent, ctx)
                result = await self._replicate.execute(rep_payload)
                provider = "replicate"
                model_used = "sdxl"

        elif self._strategy == "replicate_fallback":
            try:
                rep_payload = self._replicate.translate(intent, ctx)
                result = await self._replicate.execute(rep_payload)
                provider = "replicate"
                model_used = "sdxl"
            except ProviderUnavailable as exc:
                logger.warning("Replicate unavailable (%s). Trying local.", exc)
                fallback_triggered = True
                local_payload = self._local.translate(intent, ctx)
                result = await self._local.execute(local_payload)
                provider = "local_diffusers"
                model_used = local_payload.model

        elif self._strategy == "local_only":
            local_payload = self._local.translate(intent, ctx)
            result = await self._local.execute(local_payload)
            provider = "local_diffusers"
            model_used = local_payload.model

        else:  # replicate_only
            rep_payload = self._replicate.translate(intent, ctx)
            result = await self._replicate.execute(rep_payload)
            provider = "replicate"
            model_used = "sdxl"

        elapsed = round(time.monotonic() - t0, 2)
        cost_usd = 0.0 if provider == "local_diffusers" else 0.05

        await _record_generation(
            project_id=project_id,
            asset_id=result.asset_id,
            provider=provider,
            model_used=model_used,
            inference_time_sec=elapsed,
            cost_usd=cost_usd,
            fallback_triggered=fallback_triggered,
        )

        return result

    def cost_estimate(self, payload: ProviderPayload) -> int:
        if self._strategy in ("local_only", "local_fallback"):
            return 0
        return 512


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
