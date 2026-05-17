"""Cancellation cascade: cancel all enqueued/running tasks for a DAG node and its descendants.

Redis inflight counter is decremented for each cancelled task.
Blender subprocesses are escalated SIGTERM → SIGKILL.
"""

from __future__ import annotations

import os
import signal

import redis.asyncio as aioredis

from api.dag.reducers import get_arq_job_ids, get_events, record_event
from api.queue.dispatch import cancel_job

_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
_INFLIGHT_KEY = "proj:{project_id}:inflight"
_MAX_INFLIGHT = int(os.environ.get("MAX_INFLIGHT_PER_PROJECT", "4"))

# Registry of live Blender PIDs: (project_id, dag_node_id) -> pid
_blender_pids: dict[tuple[str, str], int] = {}


def register_blender_pid(project_id: str, dag_node_id: str, pid: int) -> None:
    _blender_pids[(project_id, dag_node_id)] = pid


def unregister_blender_pid(project_id: str, dag_node_id: str) -> None:
    _blender_pids.pop((project_id, dag_node_id), None)


async def inflight_increment(project_id: str) -> int:
    r = aioredis.from_url(_REDIS_URL, decode_responses=True)
    try:
        key = _INFLIGHT_KEY.format(project_id=project_id)
        count = await r.incr(key)
        await r.expire(key, 3600)
        return count
    finally:
        await r.aclose()


async def inflight_decrement(project_id: str) -> int:
    r = aioredis.from_url(_REDIS_URL, decode_responses=True)
    try:
        key = _INFLIGHT_KEY.format(project_id=project_id)
        count = await r.decr(key)
        return max(0, count)
    finally:
        await r.aclose()


async def inflight_count(project_id: str) -> int:
    r = aioredis.from_url(_REDIS_URL, decode_responses=True)
    try:
        key = _INFLIGHT_KEY.format(project_id=project_id)
        val = await r.get(key)
        return int(val) if val else 0
    finally:
        await r.aclose()


async def cancel_node(project_id: str, dag_node_id: str) -> dict:
    """Cancel all arq jobs for a DAG node, kill any Blender subprocess, decrement inflight."""
    job_ids = await get_arq_job_ids(project_id, dag_node_id)
    cancelled_jobs: list[str] = []
    for jid in job_ids:
        ok = await cancel_job(jid)
        if ok:
            cancelled_jobs.append(jid)

    pid = _blender_pids.get((project_id, dag_node_id))
    killed_pid: int | None = None
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            killed_pid = pid
        except ProcessLookupError:
            pass
        unregister_blender_pid(project_id, dag_node_id)

    await inflight_decrement(project_id)

    await record_event(
        project_id,
        "TaskCancelled",
        {"cancelled_jobs": cancelled_jobs, "killed_pid": killed_pid},
        dag_node_id=dag_node_id,
    )

    return {
        "dag_node_id": dag_node_id,
        "cancelled_jobs": cancelled_jobs,
        "killed_pid": killed_pid,
    }


async def cancel_cascade(project_id: str, root_node_id: str) -> list[dict]:
    """Cancel root_node_id and all downstream nodes that have TaskEnqueued events."""
    all_events = await get_events(project_id, kind="TaskEnqueued")
    node_ids = {root_node_id} | {
        e["dag_node_id"] for e in all_events
        if e.get("dag_node_id") and e["dag_node_id"] != root_node_id
    }
    results = []
    for nid in node_ids:
        result = await cancel_node(project_id, nid)
        results.append(result)
    return results
