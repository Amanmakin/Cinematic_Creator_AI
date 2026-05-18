"""Generation settings CRUD endpoints and stats aggregation."""

import pytest

from tests.conftest import SAMPLE_CANON


@pytest.mark.asyncio
async def test_get_settings_returns_global_defaults_when_no_override(client):
    res = await client.post("/projects", json={"canon": SAMPLE_CANON})
    project_id = res.json()["project_id"]

    res = await client.get(f"/projects/{project_id}/generation-settings")
    assert res.status_code == 200
    data = res.json()
    assert data["strategy"] in {"local_fallback", "local_only"}
    assert "use_smaller_models" in data


@pytest.mark.asyncio
async def test_patch_settings_persists(client):
    res = await client.post("/projects", json={"canon": SAMPLE_CANON})
    project_id = res.json()["project_id"]

    patch_body = {
        "strategy": "local_only",
        "use_smaller_models": False,
        "timeout_local_sec": 90,
    }
    res = await client.patch(f"/projects/{project_id}/generation-settings", json=patch_body)
    assert res.status_code == 200
    assert res.json()["strategy"] == "local_only"

    # Fetch again to verify persistence
    res = await client.get(f"/projects/{project_id}/generation-settings")
    assert res.json()["strategy"] == "local_only"
    assert res.json()["use_smaller_models"] is False
    assert res.json()["timeout_local_sec"] == 90


@pytest.mark.asyncio
async def test_patch_settings_rejects_invalid_strategy(client):
    res = await client.post("/projects", json={"canon": SAMPLE_CANON})
    project_id = res.json()["project_id"]

    res = await client.patch(
        f"/projects/{project_id}/generation-settings",
        json={"strategy": "galaxy_brain", "use_smaller_models": True,
              "timeout_local_sec": 180},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_settings_404_for_missing_project(client):
    res = await client.get("/projects/nonexistent/generation-settings")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_stats_returns_zeros_before_any_generations(client):
    res = await client.post("/projects", json={"canon": SAMPLE_CANON})
    project_id = res.json()["project_id"]

    res = await client.get(f"/projects/{project_id}/generation-stats")
    assert res.status_code == 200
    data = res.json()
    assert data["total_generations"] == 0
    assert data["total_cost_usd"] == 0.0
    assert data["local_count"] == 0
