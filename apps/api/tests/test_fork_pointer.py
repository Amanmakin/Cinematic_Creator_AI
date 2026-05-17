"""Tests for POST /projects/{id}/fork — checkpoint forking."""

import pytest

from tests.conftest import SAMPLE_CANON


@pytest.mark.asyncio
async def test_fork_unknown_project(client):
    res = await client.post("/projects/no-such-id/fork", json={"checkpoint_id": "ckpt-abc"})
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_fork_unknown_checkpoint(client):
    create = await client.post("/projects", json={"canon": SAMPLE_CANON})
    assert create.status_code == 201
    project_id = create.json()["project_id"]

    res = await client.post(
        f"/projects/{project_id}/fork",
        json={"checkpoint_id": "nonexistent-checkpoint"},
    )
    # 404 because the checkpoint doesn't exist in LangGraph history
    assert res.status_code == 404
    assert "Checkpoint not found" in res.json()["detail"]


@pytest.mark.asyncio
async def test_fork_returns_new_project_id(client, monkeypatch):
    """When a valid checkpoint is found, fork returns a distinct project_id."""
    create = await client.post("/projects", json={"canon": SAMPLE_CANON})
    assert create.status_code == 201
    project_id = create.json()["project_id"]

    # Inject a fake checkpoint into the graph so fork can find it
    from api.graph_dep import get_graph

    graph = get_graph()
    config = {"configurable": {"thread_id": project_id}}

    # Write minimal state to create at least one checkpoint
    graph.update_state(config, {"execution_status": "idle", "scene_graph": None})

    # Grab the checkpoint_id that was just created
    checkpoints = list(graph.get_state_history(config))
    assert checkpoints, "LangGraph produced no checkpoints"
    ckpt_id = checkpoints[0].config["configurable"]["checkpoint_id"]

    res = await client.post(
        f"/projects/{project_id}/fork",
        json={"checkpoint_id": ckpt_id},
    )
    assert res.status_code == 201
    body = res.json()
    assert "fork_project_id" in body
    assert body["fork_project_id"] != project_id
    assert body["source_checkpoint_id"] == ckpt_id
