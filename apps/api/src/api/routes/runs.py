import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from api.graph_dep import get_graph
from api.persistence.projects_db import get_locks, get_project_canon, project_exists
from api.ws.broadcaster import broadcast
from orchestrator.schemas.canon import ProjectCanon
from orchestrator.state import AgentState, SemanticLock

router = APIRouter()


class RunRequest(BaseModel):
    user_prompt: str


@router.post("/{project_id}/runs")
async def start_run(project_id: str, body: RunRequest):
    if not await project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    canon_dict = await get_project_canon(project_id)
    canon = ProjectCanon.model_validate(canon_dict)
    locks_rows = await get_locks(project_id)
    semantic_locks = [
        SemanticLock(path=r["path"], asset_id=r.get("asset_id"), reason=r["reason"])
        for r in locks_rows
    ]

    initial_state = AgentState(
        project_id=project_id,
        user_prompt=body.user_prompt,
        project_canon=canon,
        semantic_locks=semantic_locks,
    )

    config = {"configurable": {"thread_id": project_id}}
    graph = get_graph()

    async def event_stream() -> AsyncGenerator[dict, None]:
        loop = asyncio.get_event_loop()
        # Run graph.stream in a thread because it may be sync
        def _stream():
            return list(graph.stream(initial_state.model_dump(), config, stream_mode="values"))

        chunks = await loop.run_in_executor(None, _stream)
        for chunk in chunks:
            payload = json.dumps(chunk, default=str)
            await broadcast(project_id, {"type": "state", "data": chunk})
            yield {"event": "state", "data": payload}

        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_stream())
