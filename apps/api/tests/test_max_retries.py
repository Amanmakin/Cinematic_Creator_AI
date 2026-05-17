"""Test that enqueue enforces a max retry cap per (project, dag_node)."""

import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("DB_PATH", tempfile.mktemp(suffix=".sqlite"))
os.environ.setdefault("OPENAI_API_KEY", "sk-test")


@pytest.fixture
def db_path(tmp_path):
    p = str(tmp_path / "test_retries.sqlite")
    os.environ["DB_PATH"] = p
    return p


@pytest.mark.asyncio
async def test_retry_cap_blocks_fourth_attempt(db_path):
    """After 3 TaskEnqueued events for the same node, a 4th enqueue is refused."""
    from api.dag.reducers import init_dag_tables, record_event
    from api.queue.dispatch import MaxRetriesExceeded, _MAX_RETRIES

    await init_dag_tables()

    project_id = "proj-retry"
    dag_node_id = "node-1"

    # Simulate _MAX_RETRIES + 1 previous enqueues in the DAG log
    for _ in range(_MAX_RETRIES + 1):
        await record_event(
            project_id,
            "TaskEnqueued",
            {"task_name": "render_preview"},
            dag_node_id=dag_node_id,
        )

    from api.orchestrator.budget import BudgetLedger
    ledger = BudgetLedger(db_path=db_path)
    await ledger.init()
    await ledger.ensure_project(project_id, cap=10_000)

    with pytest.raises(MaxRetriesExceeded):
        from api.queue.dispatch import enqueue
        await enqueue(
            "render_preview",
            project_id=project_id,
            dag_node_id=dag_node_id,
            payload={},
            budget_token=10,
            queue="render",
            ledger=ledger,
        )


@pytest.mark.asyncio
async def test_clear_retries_resets_counter(db_path):
    from api.dag.reducers import clear_retries, count_retries, init_dag_tables, record_event

    await init_dag_tables()

    project_id = "proj-clear"
    dag_node_id = "node-clear"

    for _ in range(3):
        await record_event(
            project_id, "TaskEnqueued", {}, dag_node_id=dag_node_id
        )

    assert await count_retries(project_id, dag_node_id) == 3
    await clear_retries(project_id, dag_node_id)
    assert await count_retries(project_id, dag_node_id) == 0
