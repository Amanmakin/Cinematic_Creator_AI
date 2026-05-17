"""Table-driven tests for the PhysicalValidationEngine."""

from __future__ import annotations

import pytest

from orchestrator.nodes.physical_validation import (
    physical_validation_node,
    validate_dsl,
)
from orchestrator.schemas.dsl import Light, Vec3
from orchestrator.state import AgentState

from conftest import make_valid_dsl


def test_valid_dsl_passes(canon, valid_dsl) -> None:
    findings = validate_dsl(valid_dsl, canon)
    assert findings == []


def test_focal_zero_fails(canon) -> None:
    # Bypass Pydantic validation by constructing then mutating.
    dsl = make_valid_dsl()
    dsl.scene.camera.focal_mm = 0.5  # below 1.0
    findings = validate_dsl(dsl, canon)
    assert any(f.code == "camera.focal_mm_out_of_range" for f in findings)


def test_camera_position_equals_look_at(canon) -> None:
    dsl = make_valid_dsl()
    dsl.scene.camera.look_at = dsl.scene.camera.position.model_copy()
    findings = validate_dsl(dsl, canon)
    assert any(f.code == "camera.position_equals_look_at" for f in findings)


def test_camera_inside_subject_aabb(canon) -> None:
    dsl = make_valid_dsl()
    dsl.scene.camera.position = Vec3(x=0.0, y=0.0, z=0.5)  # inside the subject AABB
    findings = validate_dsl(dsl, canon)
    assert any(f.code == "camera.inside_subject_aabb" for f in findings)


def test_light_intensity_out_of_range(canon) -> None:
    dsl = make_valid_dsl()
    dsl.scene.lights[0].intensity = 50000  # bypass via direct assignment
    findings = validate_dsl(dsl, canon)
    assert any(f.code == "light.intensity_out_of_range" for f in findings)


def test_missing_key_light(canon) -> None:
    dsl = make_valid_dsl()
    dsl.scene.lights = [
        Light(kind="fill", position=Vec3(x=0, y=0, z=1), intensity=500, color_kelvin=5000)
    ]
    findings = validate_dsl(dsl, canon)
    assert any(f.code == "scene.missing_key_light" for f in findings)


def test_resolution_aspect_mismatch(canon) -> None:
    dsl = make_valid_dsl()
    dsl.scene.resolution = [1920, 1080]  # 16:9 against a 9:16 canon
    findings = validate_dsl(dsl, canon)
    assert any(f.code == "scene.resolution_aspect_mismatch" for f in findings)


def test_duration_exceeds_canon(canon) -> None:
    dsl = make_valid_dsl(duration_s=10.0)
    dsl.scene.duration_s = canon.duration_seconds_max + 1
    findings = validate_dsl(dsl, canon)
    assert any(f.code == "scene.duration_exceeds_canon" for f in findings)


def test_node_increments_retry_on_error(canon) -> None:
    dsl = make_valid_dsl()
    dsl.scene.camera.focal_mm = 0.5
    state = AgentState(
        user_prompt="p", project_canon=canon, scene_graph=dsl, retry_count=0
    )
    out = physical_validation_node(state)
    assert out["execution_status"] == "physical_validation_failed"
    assert out["retry_count"] == 1


def test_node_marks_completed_when_clean(canon, valid_dsl) -> None:
    state = AgentState(user_prompt="p", project_canon=canon, scene_graph=valid_dsl)
    out = physical_validation_node(state)
    assert out["execution_status"] == "completed"
    assert out["validation_findings"] == []
