import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.graph_dep import get_graph
from api.persistence.projects_db import create_project, get_project_canon, project_exists

router = APIRouter()


class ForkRequest(BaseModel):
    checkpoint_id: str


@router.post("/{project_id}/fork", status_code=201)
async def fork_project(project_id: str, body: ForkRequest):
    if not await project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    graph = get_graph()
    source_config = {"configurable": {"thread_id": project_id}}

    # Collect all checkpoints to find the requested one
    target_checkpoint = None
    for checkpoint_tuple in graph.get_state_history(source_config):
        if checkpoint_tuple.config["configurable"].get("checkpoint_id") == body.checkpoint_id:
            target_checkpoint = checkpoint_tuple
            break

    if target_checkpoint is None:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    # Create a new project with the same canon
    canon_dict = await get_project_canon(project_id)
    fork_id = await create_project(canon_dict)

    # Copy the checkpoint state into the new thread
    fork_config = {"configurable": {"thread_id": fork_id}}
    graph.update_state(fork_config, target_checkpoint.values)

    return {"fork_project_id": fork_id, "source_checkpoint_id": body.checkpoint_id}
