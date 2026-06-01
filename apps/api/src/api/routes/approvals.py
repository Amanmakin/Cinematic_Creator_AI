import asyncio
from typing import AsyncGenerator, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from api.dag.reducers import record_event
from api.graph_dep import get_graph
from api.memory.retrieval import record_rejection
from api.persistence.projects_db import project_exists
from api.ws.broadcaster import _dumps, broadcast

router = APIRouter()


class ApprovalRequest(BaseModel):
    decision: Literal[
        # Human-approval decisions
        "accept",
        "modify",
        "reject",
        # Plan9 wireframe decisions
        "previsualization_approve",
        "previsualization_proceed",
        "previsualization_modify",
        "previsualization_reject",
        # Plan9 model decisions
        "model_approve",
        "model_proceed",
        "model_modify",
        "model_reject",
    ]
    modified_prompt: str | None = None
    rejection_reason: str | None = None
    notes: str | None = None  # revision notes for modify decisions


@router.post("/{project_id}/approve")
async def approve(project_id: str, body: ApprovalRequest):
    if not await project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    graph = get_graph()
    config = {"configurable": {"thread_id": project_id}}

    snapshot = graph.get_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(status_code=409, detail="No project state found")

    # snapshot.next is empty when the interrupt is at a terminal edge (→ __end__),
    # so gate on execution_status instead of snapshot.next.
    current_status = snapshot.values.get("execution_status", "idle")
    _approvable = {
        "awaiting_human_approval",
        "previsualization_generated",
        "previsualization_feedback",
        "model_generated",
        "model_feedback",
    }
    if not snapshot.next and current_status not in _approvable:
        raise HTTPException(status_code=409, detail="No pending interrupt for this project")

    # ------------------------------------------------------------------
    # Human-approval phase
    # ------------------------------------------------------------------
    if body.decision == "accept":
        # Force ambiguity_score to 0 so route_after_intent returns "proceed", not "human_approval" again
        graph.update_state(
            config,
            {"execution_status": "intent_validated", "ambiguity_score": 0.0},
            as_node="intent_validator",
        )

    elif body.decision == "modify":
        if not body.modified_prompt:
            raise HTTPException(status_code=422, detail="modified_prompt required for 'modify' decision")
        graph.update_state(
            config,
            {"user_prompt": body.modified_prompt, "execution_status": "intent_validated", "ambiguity_score": 0.0},
            as_node="intent_validator",
        )

    elif body.decision == "reject":
        reason = body.rejection_reason or ""
        current_values = snapshot.values
        prompt = current_values.get("user_prompt", "")
        try:
            rejection_id = await record_rejection(project_id, prompt, reason)
            await record_event(
                project_id,
                "RejectionCaptured",
                {"rejection_id": rejection_id, "prompt": prompt, "reason": reason},
            )
        except Exception:
            pass
        graph.update_state(config, {"execution_status": "idle"}, as_node="intent_validator")
        return {"status": "rejected", "reason": reason}

    # ------------------------------------------------------------------
    # Plan9 — Wireframe decisions
    # ------------------------------------------------------------------
    elif body.decision == "previsualization_approve":
        # Accept wireframes; route_after_wireframe reads generation_mode to decide next node
        graph.update_state(
            config,
            {"execution_status": "previsualization_approved"},
            as_node="wireframe_previs_generator",
        )

    elif body.decision == "previsualization_proceed":
        # User clicked "Proceed to Model Generation" from a wireframe-only halt — upgrade mode
        graph.update_state(
            config,
            {
                "generation_mode": "model",
                "execution_status": "previsualization_approved",
            },
            as_node="wireframe_previs_generator",
        )

    elif body.decision == "previsualization_modify":
        notes = body.notes or ""
        if not notes:
            raise HTTPException(status_code=422, detail="notes required for 'previsualization_modify' decision")
        graph.update_state(
            config,
            {
                "previsualization_feedback": notes,
                "execution_status": "previsualization_feedback",
            },
            as_node="wireframe_previs_generator",
        )

    elif body.decision == "previsualization_reject":
        graph.update_state(
            config,
            {
                "previsualization": None,
                "scene_graph": None,
                "execution_status": "intent_validated",
            },
            as_node="wireframe_previs_generator",
        )

    # ------------------------------------------------------------------
    # Plan9 — Model decisions
    # ------------------------------------------------------------------
    elif body.decision == "model_approve":
        # Accept model renders; route_after_model reads generation_mode to decide next node
        graph.update_state(
            config,
            {"execution_status": "model_approved"},
            as_node="visual_generator",
        )

    elif body.decision == "model_proceed":
        # User clicked "Proceed to Video Generation" from a model-only halt — upgrade mode
        graph.update_state(
            config,
            {
                "generation_mode": "video",
                "execution_status": "model_approved",
            },
            as_node="visual_generator",
        )

    elif body.decision == "model_modify":
        notes = body.notes or ""
        if not notes:
            raise HTTPException(status_code=422, detail="notes required for 'model_modify' decision")
        graph.update_state(
            config,
            {
                "model_feedback": notes,
                "execution_status": "model_feedback",
            },
            as_node="visual_generator",
        )

    elif body.decision == "model_reject":
        graph.update_state(
            config,
            {
                "model_renders": None,
                "execution_status": "previsualization_approved",
            },
            as_node="visual_generator",
        )

    async def resume_stream() -> AsyncGenerator[dict, None]:
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _stream():
            try:
                for chunk in graph.stream(None, config, stream_mode="values"):
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

    return EventSourceResponse(resume_stream())
