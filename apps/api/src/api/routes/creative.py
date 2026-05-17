"""POST /projects/{id}/creative-intents — dispatch a list of creative intents."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.graph_dep import get_adapter, get_ledger, get_uar
from api.orchestrator.creative_dispatch import SimpleProjectCtx
from api.persistence.projects_db import get_locks, project_exists
from orchestrator.schemas.creative import CreativeIntent, LayerAsset
from orchestrator.state import CreativeEvent

router = APIRouter()


class DispatchRequest(BaseModel):
    intents: list[CreativeIntent]
    budget_cap: int | None = None


class DispatchResponse(BaseModel):
    assets: list[LayerAsset]
    events: list[CreativeEvent]
    budget_remaining: int


@router.post("/{project_id}/creative-intents", response_model=DispatchResponse)
async def dispatch_creative_intents(project_id: str, body: DispatchRequest):
    if not await project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    adapter = get_adapter()
    uar = get_uar()
    ledger = get_ledger()

    from api.settings import settings
    ctx = SimpleProjectCtx(project_id=project_id, uar_root=settings.uar_root)

    await uar.init()
    await ledger.ensure_project(project_id, cap=body.budget_cap or 10_000)

    locks_rows = await get_locks(project_id)
    locked_paths = {r["path"] for r in locks_rows}

    assets: list[LayerAsset] = []
    events: list[CreativeEvent] = []

    async def _generate_one(intent: CreativeIntent) -> None:
        from api.adapters.base import ProviderUnavailable
        from api.orchestrator.budget import BudgetExceeded

        payload = adapter.translate(intent, ctx)
        estimate = adapter.cost_estimate(payload)
        try:
            asset, was_cached = await ledger.spend(
                project_id,
                estimate,
                lambda: uar.get_or_create(intent, adapter, ctx, locked_paths),
            )
            assets.append(asset)
            event_kind = "LockedAssetReused" if was_cached else "LayerGenerated"
            events.append(
                CreativeEvent(kind=event_kind, target_path=intent.target_path, asset_id=asset.id)
            )
        except BudgetExceeded as exc:
            events.append(
                CreativeEvent(kind="BudgetExceeded", target_path=intent.target_path, detail=str(exc))
            )
        except ProviderUnavailable as exc:
            events.append(
                CreativeEvent(kind="LayerGenerationFailed", target_path=intent.target_path, detail=str(exc))
            )

    await asyncio.gather(*[_generate_one(intent) for intent in body.intents])

    remaining = await ledger.remaining(project_id)
    return DispatchResponse(assets=assets, events=events, budget_remaining=remaining)
