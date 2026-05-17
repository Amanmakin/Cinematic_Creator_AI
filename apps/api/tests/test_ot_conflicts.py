"""Tests for OT engine: apply, rebase, conflict, and locked-path rejection."""

import copy

import pytest

from api.orchestrator import ot as ot_module
from api.orchestrator.ot import (
    LockedPathViolation,
    OtConflict,
    apply_commit,
    seed_scene_graph,
)
from api.orchestrator.scene_graph_path import get_value, set_value

_BASE_SG = {
    "dsl_version": "1.0.0",
    "scene": {
        "duration_s": 5.0,
        "fps": 24,
        "resolution": [1920, 1080],
        "camera": {
            "focal_mm": 35.0,
            "sensor_mm": 36.0,
            "position": {"x": 0.0, "y": 1.0, "z": 5.0},
            "look_at": {"x": 0.0, "y": 0.0, "z": 0.0},
            "f_stop": 2.8,
        },
        "lights": [
            {"kind": "key", "position": {"x": 2.0, "y": 3.0, "z": 2.0}, "intensity": 1.0, "color_kelvin": 5600},
            {"kind": "fill", "position": {"x": -2.0, "y": 2.0, "z": 2.0}, "intensity": 0.5, "color_kelvin": 6500},
        ],
        "subjects": [],
    },
}


class _FakeGraph:
    """Minimal LangGraph stand-in for OT tests."""

    def __init__(self, initial_sg: dict) -> None:
        self._state = {"scene_graph": copy.deepcopy(initial_sg)}
        self._thread = "proj-test"

    def get_state(self, config: dict):
        class _S:
            values = {}

        s = _S()
        s.values = copy.deepcopy(self._state)
        return s

    def update_state(self, config: dict, values: dict, as_node: str = "") -> None:
        self._state.update(values)


@pytest.fixture(autouse=True)
def _clean_ot_store():
    """Wipe in-memory OT store before each test."""
    ot_module._ot_store.clear()
    yield
    ot_module._ot_store.clear()


# ── path resolver sanity ──────────────────────────────────────────────────────

def test_get_set_nested_path():
    sg = copy.deepcopy(_BASE_SG)
    assert get_value(sg, "scene.camera.focal_mm") == 35.0
    set_value(sg, "scene.camera.focal_mm", 50.0)
    assert sg["scene"]["camera"]["focal_mm"] == 50.0


def test_get_set_indexed_path():
    sg = copy.deepcopy(_BASE_SG)
    assert get_value(sg, "scene.lights[0].intensity") == 1.0
    set_value(sg, "scene.lights[0].intensity", 2.0)
    assert sg["scene"]["lights"][0]["intensity"] == 2.0


# ── apply_commit happy path ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_apply_commit_accepted():
    graph = _FakeGraph(_BASE_SG)
    seed_scene_graph("proj-1", _BASE_SG)
    ot_module._ot_store["proj-1"]["version"] = 0

    ops = [{"op": "set", "path": "scene.camera.focal_mm", "value": 50.0}]
    new_sg, version, status = await apply_commit("proj-1", 0, ops, graph)

    assert status == "accepted"
    assert version == 1
    assert new_sg["scene"]["camera"]["focal_mm"] == 50.0


@pytest.mark.asyncio
async def test_apply_commit_insert_op():
    sg = copy.deepcopy(_BASE_SG)
    graph = _FakeGraph(sg)
    seed_scene_graph("proj-2", sg)
    ot_module._ot_store["proj-2"]["version"] = 0

    new_light = {"kind": "rim", "position": {"x": 0.0, "y": 2.0, "z": -2.0}, "intensity": 0.3, "color_kelvin": 4000}
    ops = [{"op": "insert", "path": "scene.lights", "index": 2, "value": new_light}]
    new_sg, version, status = await apply_commit("proj-2", 0, ops, graph)

    assert status == "accepted"
    assert len(new_sg["scene"]["lights"]) == 3
    assert new_sg["scene"]["lights"][2]["kind"] == "rim"


# ── rebase (disjoint paths) ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rebase_disjoint_paths():
    graph = _FakeGraph(_BASE_SG)
    seed_scene_graph("proj-3", _BASE_SG)
    store = ot_module._ot_store["proj-3"]
    # Simulate version 1 applied focal_mm
    store["version"] = 1
    store["op_history"][1] = [{"op": "set", "path": "scene.camera.focal_mm", "value": 50.0}]
    set_value(store["scene_graph"], "scene.camera.focal_mm", 50.0)

    # Commit from base_version=0 touches a disjoint path → rebased
    ops = [{"op": "set", "path": "scene.lights[0].intensity", "value": 2.0}]
    new_sg, version, status = await apply_commit("proj-3", 0, ops, graph)

    assert status == "rebased"
    assert version == 2
    assert new_sg["scene"]["lights"][0]["intensity"] == 2.0


# ── OtConflict (overlapping paths) ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_conflict_overlapping_paths():
    graph = _FakeGraph(_BASE_SG)
    seed_scene_graph("proj-4", _BASE_SG)
    store = ot_module._ot_store["proj-4"]
    store["version"] = 1
    store["op_history"][1] = [{"op": "set", "path": "scene.camera.focal_mm", "value": 85.0}]
    set_value(store["scene_graph"], "scene.camera.focal_mm", 85.0)

    ops = [{"op": "set", "path": "scene.camera.focal_mm", "value": 24.0}]
    with pytest.raises(OtConflict):
        await apply_commit("proj-4", 0, ops, graph)


# ── LockedPathViolation ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_locked_path_rejected(monkeypatch):
    graph = _FakeGraph(_BASE_SG)
    seed_scene_graph("proj-5", _BASE_SG)
    ot_module._ot_store["proj-5"]["version"] = 0

    async def _fake_locks(project_id: str):
        return [{"path": "scene.lights[0].intensity"}]

    monkeypatch.setattr("api.orchestrator.ot.get_locks", _fake_locks)

    ops = [{"op": "set", "path": "scene.lights[0].intensity", "value": 5.0}]
    with pytest.raises(LockedPathViolation) as exc_info:
        await apply_commit("proj-5", 0, ops, graph)

    assert "scene.lights[0].intensity" in exc_info.value.path


@pytest.mark.asyncio
async def test_locked_subpath_rejected(monkeypatch):
    """Locking 'scene.camera' must block 'scene.camera.focal_mm'."""
    graph = _FakeGraph(_BASE_SG)
    seed_scene_graph("proj-6", _BASE_SG)
    ot_module._ot_store["proj-6"]["version"] = 0

    async def _fake_locks(project_id: str):
        return [{"path": "scene.camera"}]

    monkeypatch.setattr("api.orchestrator.ot.get_locks", _fake_locks)

    ops = [{"op": "set", "path": "scene.camera.focal_mm", "value": 24.0}]
    with pytest.raises(LockedPathViolation):
        await apply_commit("proj-6", 0, ops, graph)
