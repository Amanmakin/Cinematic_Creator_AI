"""Compile a finalized BlenderDsl + UAR LayerAssets into a render-ready BlenderDsl.

Responsibilities:
- Resolve PlaneCard.asset_id values to actual UAR paths.
- Verify all referenced assets exist in the UAR store.
- Return the DSL unchanged if all references resolve (it is already render-ready).
"""

from __future__ import annotations

from orchestrator.schemas.dsl import BlenderDsl, PlaneCard

from api.validation.findings import ValidationFinding, ValidationReport
from api.validation.physical import validate_dsl_full
from orchestrator.schemas.canon import ProjectCanon


async def compile_scene(
    dsl: BlenderDsl,
    canon: ProjectCanon,
    uar_asset_ids: set[str],
) -> tuple[BlenderDsl, ValidationReport]:
    """Validate the DSL against canon and UAR, then return it as render-ready.

    Returns (dsl, report). If report.ok is False the caller should not enqueue a render.
    """
    report = validate_dsl_full(dsl, canon, uar_asset_ids=uar_asset_ids)
    return dsl, report


def collect_plane_card_asset_ids(dsl: BlenderDsl) -> list[str]:
    """Return all asset_id values referenced by PlaneCard objects in the scene."""
    return [
        obj.asset_id
        for obj in dsl.scene.objects
        if isinstance(obj, PlaneCard)
    ]
