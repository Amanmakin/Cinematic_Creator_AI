import asyncio
import json
from typing import AsyncGenerator, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from api.dag.reducers import record_event
from api.graph_dep import get_graph
from api.memory.retrieval import record_rejection
from api.persistence.projects_db import project_exists
from api.ws.broadcaster import broadcast

router = APIRouter()


class ApprovalRequest(BaseModel):
    decision: Literal["accept", "modify", "select_variant", "reject"]
    modified_prompt: str | None = None
    variant_index: int | None = None
    rejection_reason: str | None = None  # required when decision == "reject"


@router.post("/{project_id}/approve")
async def approve(project_id: str, body: ApprovalRequest):
    if not await project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    graph = get_graph()
    config = {"configurable": {"thread_id": project_id}}

    snapshot = graph.get_state(config)
    if not snapshot or not snapshot.next:
        raise HTTPException(status_code=409, detail="No pending interrupt for this project")

    if body.decision == "accept":
        # Resume with execution_status cleared to proceed
        graph.update_state(config, {"execution_status": "intent_validated"}, as_node="intent_validator")

    elif body.decision == "modify":
        if not body.modified_prompt:
            raise HTTPException(status_code=422, detail="modified_prompt required for 'modify' decision")
        graph.update_state(
            config,
            {"user_prompt": body.modified_prompt, "execution_status": "intent_validated"},
            as_node="intent_validator",
        )

    elif body.decision == "select_variant":
        if body.variant_index is None:
            raise HTTPException(status_code=422, detail="variant_index required for 'select_variant' decision")
        current_values = snapshot.values
        variants = current_values.get("speculative_variants", [])
        if body.variant_index >= len(variants):
            raise HTTPException(status_code=422, detail="variant_index out of range")
        chosen = variants[body.variant_index]
        graph.update_state(
            config,
            {"scene_graph": chosen, "speculative_variants": []},
            as_node="speculative_batcher",
        )

    elif body.decision == "reject":
        reason = body.rejection_reason or ""
        current_values = snapshot.values
        prompt = current_values.get("user_prompt", "")
        # Record rejection in memory tier asynchronously (fire-and-forget style is fine
        # here; if the embed call fails we still want the graph reset to continue).
        try:
            rejection_id = await record_rejection(project_id, prompt, reason)
            await record_event(
                project_id,
                "RejectionCaptured",
                {"rejection_id": rejection_id, "prompt": prompt, "reason": reason},
            )
        except Exception:
            pass  # don't block the user flow on memory write failures
        # Reset the graph to idle so the user can provide a new prompt.
        graph.update_state(config, {"execution_status": "idle"}, as_node="intent_validator")
        return {"status": "rejected", "reason": reason}

    async def resume_stream() -> AsyncGenerator[dict, None]:
        loop = asyncio.get_event_loop()

        def _stream():
            return list(graph.stream(None, config, stream_mode="values"))

        chunks = await loop.run_in_executor(None, _stream)
        for chunk in chunks:
            payload = json.dumps(chunk, default=str)
            await broadcast(project_id, {"type": "state", "data": chunk})
            yield {"event": "state", "data": payload}

        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(resume_stream())
