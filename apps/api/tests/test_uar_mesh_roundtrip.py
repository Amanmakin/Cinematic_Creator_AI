"""Wave A1 verification — MeshAsset roundtrip through UAR storage."""

from __future__ import annotations

import os
import tempfile

import pytest

from api.uar import UARStore
from orchestrator.schemas.mesh_asset import BBox3, MeshAsset
from orchestrator.state import AgentState
from orchestrator.schemas.canon import ProjectCanon


_FAKE_GLB = b"glTF\x02\x00\x00\x00FAKE_BINARY_BYTES_FOR_TEST_ONLY"


@pytest.mark.asyncio
async def test_mesh_roundtrip_returns_same_asset():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "uar.sqlite")
        uar_root = os.path.join(tmp, "uar")
        store = UARStore(db_path=db_path, uar_root=uar_root)
        await store.init()

        bounds = BBox3(min_x=-0.5, min_y=-0.5, min_z=-0.5, max_x=0.5, max_y=0.5, max_z=0.5)
        stored = await store.store_mesh(
            project_id="proj-1",
            glb_bytes=_FAKE_GLB,
            bounds_m=bounds,
            source="triposr",
            target_path="subject",
            material_summary="stylised",
            adapter="text_to_3d",
            adapter_version="1.0.0",
        )

        assert stored.asset_id  # sha256 hex digest
        assert os.path.exists(stored.glb_path)
        with open(stored.glb_path, "rb") as f:
            assert f.read() == _FAKE_GLB

        loaded = await store.load_mesh(stored.asset_id)
        assert loaded is not None
        assert loaded.asset_id == stored.asset_id
        assert loaded.glb_path == stored.glb_path
        assert loaded.bounds_m.size == bounds.size
        assert loaded.source == "triposr"
        assert loaded.target_path == "subject"
        assert loaded.material_summary == "stylised"

        by_target = await store.get_mesh_by_target("proj-1", "subject")
        assert by_target is not None and by_target.asset_id == stored.asset_id


@pytest.mark.asyncio
async def test_mesh_storage_is_idempotent_on_content():
    with tempfile.TemporaryDirectory() as tmp:
        store = UARStore(
            db_path=os.path.join(tmp, "uar.sqlite"),
            uar_root=os.path.join(tmp, "uar"),
        )
        await store.init()
        bounds = BBox3(min_x=0, min_y=0, min_z=0, max_x=1, max_y=1, max_z=1)
        a = await store.store_mesh(project_id="p", glb_bytes=_FAKE_GLB, bounds_m=bounds, source="shap_e")
        b = await store.store_mesh(project_id="p", glb_bytes=_FAKE_GLB, bounds_m=bounds, source="shap_e")
        assert a.asset_id == b.asset_id


def test_agent_state_serialises_with_mesh_assets():
    canon = ProjectCanon(aspect_ratio="16:9", duration_seconds_max=10.0)
    state = AgentState(
        user_prompt="a wristwatch",
        project_canon=canon,
        subject_class="object",
        subject_class_confidence=0.94,
        mesh_assets=[
            MeshAsset(
                asset_id="deadbeef",
                glb_path="/tmp/x.glb",
                bounds_m=BBox3(min_x=0, min_y=0, min_z=0, max_x=1, max_y=1, max_z=1),
                source="triposr",
            )
        ],
    )
    blob = state.model_dump_json()
    revived = AgentState.model_validate_json(blob)
    assert revived.subject_class == "object"
    assert revived.mesh_assets[0].source == "triposr"
    assert revived.mesh_assets[0].bounds_m.size == (1.0, 1.0, 1.0)
