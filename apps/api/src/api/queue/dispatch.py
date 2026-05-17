"""Central enqueue entry-point with budget gating, retry enforcement, and DAG event recording."""

from __future__ import annotations

import os
from typing import Any, Literal

from arq import create_pool
from arq.connections import RedisSettings

from api.dag.reducers import count_retries, record_event
from api.orchestrator.budget import BudgetExceeded, BudgetLedger
from api.settings import settings

_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
_QUEUE_MAP: dict[str, str] = {
    "visual": "arq:visual",
    "render": "arq:render",
    "validate": "arq:validate",
}
_MAX_RETRIES = 2


class MaxRetriesExceeded(Exception):
    def __init__(self, project_id: str, dag_node_id: str, attempts: int) -> None:
        super().__init__(
            f"Project {project_id} node {dag_node_id}: max retries ({_MAX_RETRIES}) exceeded "
            f"after {attempts} attempts"
        )
        self.project_id = project_id
        self.dag_node_id = dag_node_id
        self.attempts = attempts


async def enqueue(
    task_name: str,
    project_id: str,
    dag_node_id: str,
    payload: dict[str, Any],
    budget_token: int,
    *,
    queue: Literal["visual", "render", "validate"] = "visual",
    ledger: BudgetLedger | None = None,
) -> str:
    """Enqueue a task with budget gating and retry enforcement.

    Returns the arq job_id of the enqueued task.
    Raises MaxRetriesExceeded or BudgetExceeded before enqueueing.
    """
    attempts = await count_retries(project_id, dag_node_id)
    if attempts > _MAX_RETRIES:
        raise MaxRetriesExceeded(project_id, dag_node_id, attempts)

    if ledger is None:
        ledger = BudgetLedger(db_path=settings.db_path)

    budget_id = await ledger.reserve(project_id, budget_token)

    redis_settings = RedisSettings.from_dsn(_REDIS_URL)
    pool = await create_pool(redis_settings)
    try:
        queue_name = _QUEUE_MAP[queue]
        job = await pool.enqueue_job(
            task_name,
            project_id=project_id,
            dag_node_id=dag_node_id,
            payload=payload,
            budget_id=budget_id,
            budget_amount=budget_token,
            _queue_name=queue_name,
        )
    finally:
        await pool.close()

    job_id = job.job_id if job else ""

    await record_event(
        project_id,
        "TaskEnqueued",
        {
            "task_name": task_name,
            "queue": queue,
            "budget_token": budget_token,
            "budget_id": budget_id,
            "payload": payload,
        },
        dag_node_id=dag_node_id,
        arq_job_id=job_id,
    )

    return job_id


async def cancel_job(job_id: str) -> bool:
    """Attempt to abort an arq job. Returns True if the abort signal was sent."""
    redis_settings = RedisSettings.from_dsn(_REDIS_URL)
    pool = await create_pool(redis_settings)
    try:
        from arq import Job
        job = Job(job_id, pool)
        await job.abort(timeout=5)
        return True
    except Exception:
        return False
    finally:
        await pool.close()
