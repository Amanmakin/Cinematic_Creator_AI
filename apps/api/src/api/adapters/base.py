from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.schemas.creative import AssetRef, CreativeIntent, ProviderPayload


class ProjectCtx(Protocol):
    project_id: str
    uar_root: str


@runtime_checkable
class CreativeAdapter(Protocol):
    name: str
    version: str

    def supports(self, intent: CreativeIntent) -> bool: ...

    def translate(self, intent: CreativeIntent, ctx: ProjectCtx) -> ProviderPayload: ...

    async def execute(self, payload: ProviderPayload) -> AssetRef: ...

    def cost_estimate(self, payload: ProviderPayload) -> int:
        """Return estimated token cost for this payload."""
        ...


class ProviderUnavailable(RuntimeError):
    """Raised when the upstream provider is unreachable or returns a terminal error."""
