"""ComfyUI adapter stub — interface placeholder for Plan6+."""

from __future__ import annotations

from typing import TYPE_CHECKING

from orchestrator.schemas.creative import AssetRef, CreativeIntent, ProviderPayload

if TYPE_CHECKING:
    from api.adapters.base import ProjectCtx


class ComfyUIAdapter:
    name = "comfyui"
    version = "0.0.0"

    def supports(self, intent: CreativeIntent) -> bool:
        return False

    def translate(self, intent: CreativeIntent, ctx: "ProjectCtx") -> ProviderPayload:
        raise NotImplementedError("ComfyUI adapter not yet implemented")

    async def execute(self, payload: ProviderPayload) -> AssetRef:
        raise NotImplementedError("ComfyUI adapter not yet implemented")

    def cost_estimate(self, payload: ProviderPayload) -> int:
        raise NotImplementedError("ComfyUI adapter not yet implemented")
