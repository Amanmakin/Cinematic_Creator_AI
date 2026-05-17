from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.graph_dep import get_graph
from api.persistence.projects_db import create_project, get_project_canon
from orchestrator.schemas.canon import ProjectCanon
from orchestrator.state import AgentState

router = APIRouter()


class CreateProjectRequest(BaseModel):
    canon: ProjectCanon


class ProjectResponse(BaseModel):
    project_id: str
    canon: ProjectCanon


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project_endpoint(body: CreateProjectRequest):
    project_id = await create_project(body.canon.model_dump())
    return ProjectResponse(project_id=project_id, canon=body.canon)


@router.get("/{project_id}")
async def get_project_endpoint(project_id: str):
    canon_dict = await get_project_canon(project_id)
    if canon_dict is None:
        raise HTTPException(status_code=404, detail="Project not found")

    graph = get_graph()
    config = {"configurable": {"thread_id": project_id}}
    state_snapshot = graph.get_state(config)

    canon = ProjectCanon.model_validate(canon_dict)
    agent_state = state_snapshot.values if state_snapshot else None

    return {
        "project_id": project_id,
        "canon": canon.model_dump(),
        "agent_state": agent_state,
        "next": list(state_snapshot.next) if state_snapshot else [],
    }
