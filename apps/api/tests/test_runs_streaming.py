"""Test that POST /projects/{id}/runs streams SSE state events."""

import json
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import SAMPLE_CANON


@pytest.mark.asyncio
async def test_run_streams_state_events(client):
    # Create a project first
    resp = await client.post("/projects", json={"canon": SAMPLE_CANON})
    assert resp.status_code == 201
    project_id = resp.json()["project_id"]

    # Mock the graph so it doesn't call OpenAI
    fake_graph = MagicMock()
    fake_state = {"execution_status": "completed", "user_prompt": "test"}
    fake_graph.stream.return_value = [fake_state]
    fake_graph.get_state.return_value = MagicMock(values=fake_state, next=[])

    with patch("api.routes.runs.get_graph", return_value=fake_graph):
        resp = await client.post(
            f"/projects/{project_id}/runs",
            json={"user_prompt": "A dramatic mountain scene"},
            headers={"Accept": "text/event-stream"},
        )
    assert resp.status_code == 200
    # SSE response contains at least one state event
    assert b"state" in resp.content


@pytest.mark.asyncio
async def test_run_returns_404_for_unknown_project(client):
    resp = await client.post(
        "/projects/nonexistent-id/runs",
        json={"user_prompt": "test"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_and_get_project(client):
    resp = await client.post("/projects", json={"canon": SAMPLE_CANON})
    assert resp.status_code == 201
    data = resp.json()
    assert "project_id" in data

    project_id = data["project_id"]
    fake_graph = MagicMock()
    fake_graph.get_state.return_value = MagicMock(values={}, next=[])

    with patch("api.routes.projects.get_graph", return_value=fake_graph):
        resp = await client.get(f"/projects/{project_id}")
    assert resp.status_code == 200
    assert resp.json()["project_id"] == project_id
