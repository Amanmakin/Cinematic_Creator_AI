"""Render pipeline endpoints: compile_dsl, validate_dsl, render_preview."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Ensure workers package (project root) is importable when running from apps/api/
_PROJECT_ROOT = str(Path(__file__).parents[5])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from api.graph_dep import get_uar
from api.render.gltf_builder import build_glb, scene_hash
from api.render.scene_compiler import compile_scene, collect_plane_card_asset_ids
from api.settings import settings
from api.validation.physical import validate_dsl_full
from orchestrator.schemas.canon import ProjectCanon
from orchestrator.schemas.dsl import BlenderDsl

router = APIRouter()

_RENDERS_ROOT = os.environ.get("RENDERS_ROOT", "renders")


class ValidateDslRequest(BaseModel):
    dsl: BlenderDsl
    canon: ProjectCanon
    check_uar: bool = False


class ValidateDslResponse(BaseModel):
    ok: bool
    findings: list[dict]


class RenderPreviewRequest(BaseModel):
    dsl: BlenderDsl
    canon: ProjectCanon
    blender_bin: str = "blender"
    timeout_s: float = 300.0


class RenderPreviewResponse(BaseModel):
    scene_hash: str
    glb_path: str
    status: str
    detail: str = ""


@router.post("/{project_id}/validate-dsl", response_model=ValidateDslResponse)
async def validate_dsl_endpoint(project_id: str, body: ValidateDslRequest):
    """Validate a BlenderDsl against canon and (optionally) the UAR.

    Returns ok=False with findings when the DSL violates any physical rule.
    No subprocess is ever spawned here.
    """
    uar_ids: set[str] | None = None
    if body.check_uar:
        uar = get_uar()
        asset_ids = collect_plane_card_asset_ids(body.dsl)
        resolved = await asyncio.gather(*(uar.get_by_id(aid) for aid in asset_ids))
        uar_ids = {aid for aid, asset in zip(asset_ids, resolved) if asset is not None}

    report = validate_dsl_full(body.dsl, body.canon, uar_asset_ids=uar_ids)
    return ValidateDslResponse(
        ok=report.ok,
        findings=[f.model_dump() for f in report.findings],
    )


@router.post("/{project_id}/render-preview", response_model=RenderPreviewResponse)
async def render_preview(project_id: str, body: RenderPreviewRequest):
    """Validate the DSL, assemble a .glb, then render one frame via Blender.

    Refuses to spawn Blender if validation fails.
    """
    # Validate before touching any subprocess
    report = validate_dsl_full(body.dsl, body.canon)
    if not report.ok:
        errors = [f.model_dump() for f in report.findings if f.severity == "error"]
        raise HTTPException(
            status_code=422,
            detail={"message": "DSL validation failed", "findings": errors},
        )

    sha = scene_hash(body.dsl)
    out_dir = str(Path(_RENDERS_ROOT) / project_id / sha)

    # Build glb
    try:
        glb_path = build_glb(body.dsl, uar_root=settings.uar_root, out_dir=out_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"glTF assembly failed: {exc}") from exc

    # Attempt Blender render (non-blocking — run in thread executor)
    from workers.render.blender_runner import (
        RenderCompleted,
        RenderFailed,
        RenderTimedOut,
        run_render,
    )

    extras_path = str(Path(out_dir) / f"{sha}.extras.json")
    loop = asyncio.get_event_loop()

    def _render():
        return run_render(
            glb_path=glb_path,
            extras_path=extras_path,
            out_dir=out_dir,
            blender_bin=body.blender_bin,
            timeout_s=body.timeout_s,
        )

    result = await loop.run_in_executor(None, _render)

    if isinstance(result, RenderCompleted):
        return RenderPreviewResponse(
            scene_hash=sha,
            glb_path=glb_path,
            status="completed",
            detail=result.frame_path,
        )
    elif isinstance(result, RenderTimedOut):
        return RenderPreviewResponse(
            scene_hash=sha,
            glb_path=glb_path,
            status="timed_out",
            detail=f"Render timed out after {result.timeout_s}s",
        )
    else:
        rc = result.returncode if isinstance(result, RenderFailed) else -1
        tail = result.stderr_tail if isinstance(result, RenderFailed) else ""
        return RenderPreviewResponse(
            scene_hash=sha,
            glb_path=glb_path,
            status="failed",
            detail=f"Blender exited {rc}: {tail[:300]}",
        )
