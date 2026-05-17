"""POST /projects/{project_id}/style-overrides — pin a style description (D5)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.dag.reducers import record_event
from api.memory.retrieval import record_style_override
from api.persistence.projects_db import project_exists

router = APIRouter()


class StyleOverrideRequest(BaseModel):
    description: str  # e.g. "always use golden-hour side lighting"


@router.post("/{project_id}/style-overrides", status_code=201)
async def pin_style_override(project_id: str, body: StyleOverrideRequest):
    if not await project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    if not body.description.strip():
        raise HTTPException(status_code=422, detail="description must not be empty")

    override_id = await record_style_override(project_id, body.description)
    await record_event(
        project_id,
        "StyleOverridePinned",
        {"override_id": override_id, "description": body.description},
    )
    return {"override_id": override_id}
