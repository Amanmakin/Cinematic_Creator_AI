"""Test that POST /projects/{id}/approve resumes an interrupted graph."""

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import SAMPLE_CANON


def _make_snapshot(next_nodes=("intent_validator",)):
    snap = MagicMock()
    snap.next = list(next_nodes)
    snap.values = {
        "execution_status": "awaiting_human_approval",
    }
    return snap


@pytest.mark.asyncio
async def test_approve_accept_resumes_graph(client):
    resp = await client.post("/projects", json={"canon": SAMPLE_CANON})
    project_id = resp.json()["project_id"]

    fake_graph = MagicMock()
    fake_graph.get_state.return_value = _make_snapshot()
    fake_graph.stream.return_value = [{"execution_status": "completed"}]

    with patch("api.routes.approvals.get_graph", return_value=fake_graph):
        resp = await client.post(
            f"/projects/{project_id}/approve",
            json={"decision": "accept"},
            headers={"Accept": "text/event-stream"},
        )
    assert resp.status_code == 200
    fake_graph.update_state.assert_called_once()


@pytest.mark.asyncio
async def test_approve_no_interrupt_returns_409(client):
    resp = await client.post("/projects", json={"canon": SAMPLE_CANON})
    project_id = resp.json()["project_id"]

    fake_graph = MagicMock()
    no_interrupt = MagicMock()
    no_interrupt.next = []
    fake_graph.get_state.return_value = no_interrupt

    with patch("api.routes.approvals.get_graph", return_value=fake_graph):
        resp = await client.post(
            f"/projects/{project_id}/approve",
            json={"decision": "accept"},
        )
    assert resp.status_code == 409
