"""Cancellation endpoint: cancel a DAG node and its downstream tasks."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.queue.cancellation import cancel_cascade, cancel_node

router = APIRouter()


class CancelResponse(BaseModel):
    cancelled: list[dict]


@router.delete("/{project_id}/tasks/{dag_node_id}", response_model=CancelResponse)
async def cancel_task(project_id: str, dag_node_id: str, cascade: bool = False):
    """Cancel a queued or running task for a DAG node.

    Set ?cascade=true to also cancel all downstream nodes.
    """
    if cascade:
        results = await cancel_cascade(project_id, dag_node_id)
    else:
        result = await cancel_node(project_id, dag_node_id)
        results = [result]
    return CancelResponse(cancelled=results)
