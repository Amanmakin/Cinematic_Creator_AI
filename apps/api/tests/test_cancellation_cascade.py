"""Test cancellation cascade: DAG event recording, PID kill, inflight decrement."""

import os
import signal
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DB_PATH", tempfile.mktemp(suffix=".sqlite"))
os.environ.setdefault("OPENAI_API_KEY", "sk-test")


@pytest.fixture
def db_path(tmp_path):
    p = str(tmp_path / "test_cancel.sqlite")
    os.environ["DB_PATH"] = p
    return p


@pytest.mark.asyncio
async def test_cancel_node_records_dag_event(db_path):
    from api.dag.reducers import get_events, init_dag_tables, record_event
    from api.queue.cancellation import cancel_node

    await init_dag_tables()

    project_id = "proj-cancel"
    dag_node_id = "node-cancel"

    await record_event(
        project_id, "TaskEnqueued", {"task_name": "render_preview"},
        dag_node_id=dag_node_id, arq_job_id="job-abc",
    )

    with (
        patch("api.queue.cancellation.cancel_job", new=AsyncMock(return_value=True)),
        patch("api.queue.cancellation.inflight_decrement", new=AsyncMock(return_value=0)),
    ):
        result = await cancel_node(project_id, dag_node_id)

    assert result["dag_node_id"] == dag_node_id
    assert "job-abc" in result["cancelled_jobs"]

    events = await get_events(project_id, kind="TaskCancelled", dag_node_id=dag_node_id)
    assert len(events) == 1


@pytest.mark.asyncio
async def test_cancel_node_kills_registered_blender_pid(db_path):
    from api.dag.reducers import init_dag_tables
    from api.queue.cancellation import cancel_node, register_blender_pid

    await init_dag_tables()

    project_id = "proj-pid"
    dag_node_id = "node-pid"
    fake_pid = 99999

    register_blender_pid(project_id, dag_node_id, fake_pid)

    killed_signals = []

    def fake_kill(pid, sig):
        killed_signals.append((pid, sig))

    with (
        patch("api.queue.cancellation.cancel_job", new=AsyncMock(return_value=False)),
        patch("api.queue.cancellation.inflight_decrement", new=AsyncMock(return_value=0)),
        patch("os.kill", side_effect=fake_kill),
    ):
        result = await cancel_node(project_id, dag_node_id)

    assert result["killed_pid"] == fake_pid
    assert any(sig == signal.SIGTERM for _, sig in killed_signals)


@pytest.mark.asyncio
async def test_final_render_blocked_without_approval(db_path):
    """render_final task must refuse if no FinalRenderApproved event exists."""
    from api.dag.reducers import get_events, init_dag_tables

    await init_dag_tables()

    os.environ["DB_PATH"] = db_path

    from api.queue.tasks.render_final import render_final

    mock_dsl = {
        "scene": {
            "fps": 24,
            "duration_s": 1.0,
            "resolution": [1920, 1080],
            "camera": {"focal_mm": 35, "position": {"x": 0, "y": 0, "z": 5}},
            "lights": [],
            "world": {},
            "objects": [],
        }
    }
    mock_canon = {
        "aspect_ratio": "16:9",
        "duration_seconds_max": 30.0,
        "aesthetic_tags": [],
        "style_guide": "",
        "banned_terms": [],
    }

    from api.orchestrator.budget import BudgetLedger
    ledger = BudgetLedger(db_path=db_path)
    await ledger.init()
    await ledger.ensure_project("proj-gate", cap=10_000)
    rid = await ledger.reserve("proj-gate", 50)

    result = await render_final(
        {},
        project_id="proj-gate",
        dag_node_id="final-1",
        payload={"dsl": mock_dsl, "canon": mock_canon},
        budget_id=rid,
        budget_amount=50,
    )

    assert result["status"] == "blocked"
    events = await get_events("proj-gate", kind="FinalRenderBlocked")
    assert len(events) == 1
