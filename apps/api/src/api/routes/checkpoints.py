"""GET /projects/{id}/checkpoints — list LangGraph checkpoint history."""

from fastapi import APIRouter, HTTPException

from api.graph_dep import get_graph
from api.persistence.projects_db import project_exists

router = APIRouter()

_SCENE_STATUSES = {
    "scene_graph_generated",
    "physical_validation_failed",
    "completed",
    "awaiting_human_approval",
    "speculative_batching",
}


@router.get("/{project_id}/checkpoints")
async def list_checkpoints(project_id: str):
    if not await project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    graph = get_graph()
    config = {"configurable": {"thread_id": project_id}}

    results = []
    for ct in graph.get_state_history(config):
        cfg = ct.config.get("configurable", {})
        checkpoint_id = cfg.get("checkpoint_id", "")
        status = ct.values.get("execution_status", "unknown")
        has_sg = ct.values.get("scene_graph") is not None
        created_at = getattr(ct, "created_at", None)
        results.append({
            "checkpoint_id": checkpoint_id,
            "execution_status": status,
            "has_scene_graph": has_sg,
            "created_at": created_at,
            "kind": "SceneGraphMutated" if has_sg and status in _SCENE_STATUSES else "AgentStep",
        })

    return results
