"""Plan 11 T3 — image-only submission auto-captions; empty+empty → 400."""

from unittest.mock import MagicMock, patch

import pytest

from api.reference_vision import ReferenceAnalysis
from tests.conftest import SAMPLE_CANON


async def _make_project(client) -> str:
    resp = await client.post("/projects", json={"canon": SAMPLE_CANON})
    assert resp.status_code == 201
    return resp.json()["project_id"]


def _fake_graph():
    g = MagicMock()
    g.stream.return_value = [{"execution_status": "completed"}]
    g.get_state.return_value = MagicMock(values={}, next=[])
    return g


@pytest.mark.asyncio
async def test_image_only_submission_seeds_caption(client):
    project_id = await _make_project(client)
    graph = _fake_graph()

    with patch("api.routes.runs.get_graph", return_value=graph), patch(
        "api.routes.runs._load_reference_image", return_value=b"\x89PNG-fake"
    ), patch(
        "api.routes.runs.analyze_reference_image",
        return_value=ReferenceAnalysis(label="ceramic teapot", bbox_norm=(0.1, 0.1, 0.9, 0.9)),
    ):
        resp = await client.post(
            f"/projects/{project_id}/runs",
            json={"user_prompt": "", "sample_image_urls": ["/sample-images/teapot.png"]},
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200
    seeded_state = graph.stream.call_args.args[0]
    assert seeded_state["user_prompt"] == "ceramic teapot"


@pytest.mark.asyncio
async def test_image_only_falls_back_when_no_label(client):
    project_id = await _make_project(client)
    graph = _fake_graph()

    with patch("api.routes.runs.get_graph", return_value=graph), patch(
        "api.routes.runs._load_reference_image", return_value=b"\x89PNG-fake"
    ), patch(
        "api.routes.runs.analyze_reference_image",
        return_value=ReferenceAnalysis(None, None),
    ):
        resp = await client.post(
            f"/projects/{project_id}/runs",
            json={"user_prompt": "  ", "sample_image_urls": ["/sample-images/x.png"]},
            headers={"Accept": "text/event-stream"},
        )

    assert resp.status_code == 200
    seeded_state = graph.stream.call_args.args[0]
    assert seeded_state["user_prompt"] == "the main object from the reference image"


@pytest.mark.asyncio
async def test_empty_prompt_and_no_image_returns_400(client):
    project_id = await _make_project(client)
    resp = await client.post(
        f"/projects/{project_id}/runs",
        json={"user_prompt": "", "sample_image_urls": []},
    )
    assert resp.status_code == 400
