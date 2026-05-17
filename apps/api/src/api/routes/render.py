"""Render pipeline endpoints: validate, queued preview, queued final, approval gate, frame serving."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).parents[5])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.dag.reducers import get_events, record_event
from api.graph_dep import get_ledger, get_uar
from api.queue.dispatch import MaxRetriesExceeded, enqueue
from api.render.gltf_builder import scene_hash
from api.render.scene_compiler import collect_plane_card_asset_ids
from api.settings import settings
from api.validation.physical import validate_dsl_full
from orchestrator.schemas.canon import ProjectCanon
from orchestrator.schemas.dsl import BlenderDsl

router = APIRouter()

_RENDERS_ROOT = os.environ.get("RENDERS_ROOT", settings.renders_root)


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
    dag_node_id: str = "preview"
    blender_bin: str = "blender"
    timeout_s: float = 600.0
    budget_estimate: int = 50


class RenderPreviewResponse(BaseModel):
    job_id: str
    scene_hash: str
    status: str = "queued"


class RenderFinalRequest(BaseModel):
    dsl: BlenderDsl
    canon: ProjectCanon
    dag_node_id: str = "final"
    blender_bin: str = "blender"
    timeout_s: float = 3600.0
    budget_estimate: int = 200


class RenderFinalResponse(BaseModel):
    job_id: str
    scene_hash: str
    status: str


class ApproveRenderRequest(BaseModel):
    scene_hash: str


class RetryRequest(BaseModel):
    dag_node_id: str


@router.post("/{project_id}/validate-dsl", response_model=ValidateDslResponse)
async def validate_dsl_endpoint(project_id: str, body: ValidateDslRequest):
    """Validate a BlenderDsl against canon and (optionally) the UAR."""
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
async def enqueue_render_preview(project_id: str, body: RenderPreviewRequest):
    """Validate the DSL then enqueue a low-res preview render to the arq render queue."""
    report = validate_dsl_full(body.dsl, body.canon)
    if not report.ok:
        errors = [f.model_dump() for f in report.findings if f.severity == "error"]
        raise HTTPException(
            status_code=422,
            detail={"message": "DSL validation failed", "findings": errors},
        )

    sha = scene_hash(body.dsl)

    try:
        job_id = await enqueue(
            "render_preview",
            project_id=project_id,
            dag_node_id=body.dag_node_id,
            payload={
                "dsl": body.dsl.model_dump(),
                "canon": body.canon.model_dump(),
                "blender_bin": body.blender_bin,
                "timeout_s": body.timeout_s,
            },
            budget_token=body.budget_estimate,
            queue="render",
            ledger=get_ledger(),
        )
    except MaxRetriesExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return RenderPreviewResponse(job_id=job_id, scene_hash=sha)


@router.post("/{project_id}/render-preview/approve", status_code=204)
async def approve_final_render(project_id: str, body: ApproveRenderRequest):
    """Record a FinalRenderApproved event — the approval gate for render_final."""
    existing = await get_events(
        project_id, kind="FinalRenderApproved", scene_hash=body.scene_hash
    )
    if not existing:
        await record_event(
            project_id,
            "FinalRenderApproved",
            {"approved_by": "user"},
            scene_hash=body.scene_hash,
        )


@router.post("/{project_id}/render-final", response_model=RenderFinalResponse)
async def enqueue_render_final(project_id: str, body: RenderFinalRequest):
    """Request a final render. Emits FinalRenderRequested; the task enforces the approval gate."""
    sha = scene_hash(body.dsl)

    await record_event(
        project_id,
        "FinalRenderRequested",
        {"dag_node_id": body.dag_node_id},
        dag_node_id=body.dag_node_id,
        scene_hash=sha,
    )

    try:
        job_id = await enqueue(
            "render_final",
            project_id=project_id,
            dag_node_id=body.dag_node_id,
            payload={
                "dsl": body.dsl.model_dump(),
                "canon": body.canon.model_dump(),
                "blender_bin": body.blender_bin,
                "timeout_s": body.timeout_s,
            },
            budget_token=body.budget_estimate,
            queue="render",
            ledger=get_ledger(),
        )
    except MaxRetriesExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return RenderFinalResponse(job_id=job_id, scene_hash=sha, status="queued")


@router.post("/{project_id}/tasks/{dag_node_id}/retry", status_code=204)
async def retry_task(project_id: str, dag_node_id: str):
    """Reset the retry counter for a failed task node so it can be re-enqueued."""
    from api.dag.reducers import clear_retries
    await clear_retries(project_id, dag_node_id)


@router.get("/{project_id}/renders/{scene_hash_val}/preview/{frame_index}")
async def serve_preview_frame(project_id: str, scene_hash_val: str, frame_index: int):
    """Serve a preview frame PNG by index."""
    frame_path = (
        Path(_RENDERS_ROOT) / project_id / scene_hash_val / "preview"
        / f"frame_{frame_index:04d}.png"
    )
    if not frame_path.exists():
        raise HTTPException(status_code=404, detail=f"Frame {frame_index} not found")
    return FileResponse(str(frame_path), media_type="image/png")


@router.get("/{project_id}/renders/{scene_hash_val}/events")
async def get_render_events(project_id: str, scene_hash_val: str):
    """Return all DAG events for a scene hash."""
    events = await get_events(project_id, scene_hash=scene_hash_val)
    return {"events": events}
