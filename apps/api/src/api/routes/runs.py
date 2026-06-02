import asyncio
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from api.graph_dep import get_graph
from api.orchestrator.mesh_dispatch import _load_reference_image
from api.persistence.projects_db import get_locks, get_project_canon, project_exists
from api.reference_vision import analyze_reference_image
from api.settings import settings
from api.ws.broadcaster import _dumps, broadcast
from orchestrator.schemas.canon import ProjectCanon
from orchestrator.state import AgentState, SemanticLock

router = APIRouter()

# Caption used when an image is submitted with no prompt and the vision pass
# can't name the object (no key / offline / parse failure).
_FALLBACK_CAPTION = "the main object from the reference image"


class RunRequest(BaseModel):
    user_prompt: str = ""
    sample_image_urls: list[str] = []


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

    # Image-only submission: with no prompt, auto-caption the first reference
    # image into a short subject that seeds the existing pipeline. The vision
    # call is cached per image, so the adapter's later crop reuses this result.
    effective_prompt = body.user_prompt
    if not body.user_prompt.strip():
        if not body.sample_image_urls:
            raise HTTPException(status_code=400, detail="Provide a prompt or a reference image")
        image_bytes = _load_reference_image(body.sample_image_urls)
        if image_bytes is None:
            raise HTTPException(status_code=400, detail="Provide a prompt or a reference image")
        analysis = analyze_reference_image(image_bytes, settings.openai_api_key)
        effective_prompt = analysis.label or _FALLBACK_CAPTION

    initial_state = AgentState(
        project_id=project_id,
        user_prompt=effective_prompt,
        project_canon=canon,
        semantic_locks=semantic_locks,
        sample_image_urls=body.sample_image_urls,
    )

    config = {"configurable": {"thread_id": project_id}}
    graph = get_graph()

    async def event_stream() -> AsyncGenerator[dict, None]:
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _stream():
            try:
                for chunk in graph.stream(initial_state.model_dump(), config, stream_mode="values"):
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

        loop.run_in_executor(None, _stream)

        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            await broadcast(project_id, {"type": "state", "data": chunk})
            yield {"event": "state", "data": _dumps(chunk)}

        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_stream())
