"""POST /projects/{id}/ot — receive and apply OT commits."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.graph_dep import get_graph
from api.orchestrator.ot import LockedPathViolation, OtConflict, apply_commit
from api.persistence.projects_db import project_exists
from api.ws.broadcaster import broadcast

router = APIRouter()


class OtOp(BaseModel):
    op: str  # "set" | "insert" | "delete"
    path: str
    value: object | None = None
    index: int | None = None


class OtCommitRequest(BaseModel):
    base_version: int
    ops: list[OtOp]


@router.post("/{project_id}/ot")
async def ot_commit(project_id: str, body: OtCommitRequest):
    if not await project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    ops = [op.model_dump(exclude_none=True) for op in body.ops]

    try:
        new_sg, new_version, status = await apply_commit(
            project_id, body.base_version, ops, get_graph()
        )
    except LockedPathViolation as exc:
        await broadcast(project_id, {
            "type": "ot_commit_rejected",
            "data": {"reason": "LockedPathViolation", "path": exc.path},
        })
        raise HTTPException(status_code=409, detail=f"Locked path: {exc.path}")
    except OtConflict:
        await broadcast(project_id, {"type": "ot_conflict", "data": {}})
        raise HTTPException(status_code=409, detail="OT conflict — re-fetch and retry")
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Bad path or value: {exc}")

    event_type = "scene_graph_mutated" if status == "accepted" else "ot_commit_rebased"
    await broadcast(project_id, {
        "type": event_type,
        "data": {"version": new_version, "scene_graph": new_sg, "ops": ops},
    })
    return {"version": new_version, "status": status}
