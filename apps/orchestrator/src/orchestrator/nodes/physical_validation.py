"""Pure-Python geometric / spatial sanity checks on the generated DSL."""

from __future__ import annotations

from orchestrator.schemas.canon import ProjectCanon
from orchestrator.schemas.dsl import BlenderDsl, PlaneCard, Vec3
from orchestrator.state import AgentState, ValidationFinding


def _aspect_matches(resolution: tuple[int, int], canon: ProjectCanon, tol: float = 0.01) -> bool:
    w, h = resolution
    if h == 0:
        return False
    return abs((w / h) - canon.aspect_value()) <= tol


def _point_in_aabb(p: Vec3, mn: Vec3, mx: Vec3) -> bool:
    return (
        mn.x <= p.x <= mx.x
        and mn.y <= p.y <= mx.y
        and mn.z <= p.z <= mx.z
    )


def validate_dsl(dsl: BlenderDsl, canon: ProjectCanon) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    scene = dsl.scene
    cam = scene.camera

    if not (1.0 <= cam.focal_mm <= 1000.0):
        findings.append(
            ValidationFinding(
                severity="error",
                code="camera.focal_mm_out_of_range",
                message=f"focal_mm={cam.focal_mm} outside [1, 1000]",
                path="scene.camera.focal_mm",
            )
        )

    # Clip plane validation (Plan4)
    if not (cam.clip_start > 0 and cam.clip_end > 0 and cam.clip_start < cam.clip_end):
        findings.append(
            ValidationFinding(
                severity="error",
                code="camera.clip_planes_invalid",
                message=(
                    f"clip_start={cam.clip_start} and clip_end={cam.clip_end} must both "
                    "be positive with clip_start < clip_end"
                ),
                path="scene.camera",
            )
        )

    # Plan1 look_at check (backward compat — only when look_at is set)
    if cam.look_at is not None and cam.position.as_tuple() == cam.look_at.as_tuple():
        findings.append(
            ValidationFinding(
                severity="error",
                code="camera.position_equals_look_at",
                message="camera position and look_at are identical",
                path="scene.camera",
            )
        )

    # Legacy subjects AABB (Plan1)
    for i, subject in enumerate(scene.subjects):
        if subject.contains(cam.position):
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="camera.inside_subject_aabb",
                    message=f"camera is inside subject[{i}] AABB",
                    path=f"scene.subjects[{i}]",
                )
            )

    # PlaneCard AABB (Plan4)
    for i, obj in enumerate(scene.objects):
        if isinstance(obj, PlaneCard):
            mn, mx = obj.transform.aabb(half_thickness=0.005)
            if _point_in_aabb(cam.position, mn, mx):
                findings.append(
                    ValidationFinding(
                        severity="error",
                        code="camera.inside_plane_card_aabb",
                        message=f"camera is inside objects[{i}] (PlaneCard '{obj.asset_id}') AABB",
                        path=f"scene.objects[{i}]",
                    )
                )

    for i, light in enumerate(scene.lights):
        if not (0.0 <= light.intensity <= 10000.0):
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="light.intensity_out_of_range",
                    message=f"light[{i}].intensity={light.intensity} outside [0, 10000]",
                    path=f"scene.lights[{i}].intensity",
                )
            )
        if not (1000 <= light.color_kelvin <= 20000):
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="light.color_kelvin_out_of_range",
                    message=f"light[{i}].color_kelvin={light.color_kelvin} outside [1000, 20000]",
                    path=f"scene.lights[{i}].color_kelvin",
                )
            )

    # Animation track validation (Plan4)
    for i, track in enumerate(scene.animations):
        if len(track.times) == 0:
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="animation.empty_times",
                    message=f"animations[{i}] has empty times list",
                    path=f"scene.animations[{i}].times",
                )
            )
            continue

        for j in range(1, len(track.times)):
            if track.times[j] <= track.times[j - 1]:
                findings.append(
                    ValidationFinding(
                        severity="error",
                        code="animation.times_not_monotonic",
                        message=(
                            f"animations[{i}].times not strictly monotonic "
                            f"at index {j}: {track.times[j-1]} >= {track.times[j]}"
                        ),
                        path=f"scene.animations[{i}].times",
                    )
                )
                break

        if track.times and track.times[-1] > scene.duration_s:
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="animation.time_exceeds_duration",
                    message=(
                        f"animations[{i}] last time {track.times[-1]} > "
                        f"scene.duration_s={scene.duration_s}"
                    ),
                    path=f"scene.animations[{i}].times",
                )
            )

        if len(track.values) != len(track.times):
            findings.append(
                ValidationFinding(
                    severity="error",
                    code="animation.values_times_length_mismatch",
                    message=(
                        f"animations[{i}] has {len(track.times)} times but "
                        f"{len(track.values)} values"
                    ),
                    path=f"scene.animations[{i}]",
                )
            )

    if scene.duration_s > canon.duration_seconds_max:
        findings.append(
            ValidationFinding(
                severity="error",
                code="scene.duration_exceeds_canon",
                message=f"duration_s={scene.duration_s} > canon max {canon.duration_seconds_max}",
                path="scene.duration_s",
            )
        )

    if not _aspect_matches(scene.resolution, canon):
        findings.append(
            ValidationFinding(
                severity="error",
                code="scene.resolution_aspect_mismatch",
                message=(
                    f"resolution {scene.resolution} does not match canon aspect "
                    f"{canon.aspect_ratio}"
                ),
                path="scene.resolution",
            )
        )

    if not any(l.kind == "key" for l in scene.lights):
        findings.append(
            ValidationFinding(
                severity="error",
                code="scene.missing_key_light",
                message="scene has no light of kind 'key'",
                path="scene.lights",
            )
        )

    return findings


def physical_validation_node(state: AgentState) -> dict:
    assert state.scene_graph is not None, "physical_validation requires a scene_graph"

    findings = validate_dsl(state.scene_graph, state.project_canon)
    has_error = any(f.severity == "error" for f in findings)

    if has_error:
        return {
            "validation_findings": findings,
            "execution_status": "physical_validation_failed",
            "retry_count": state.retry_count + 1,
        }

    return {
        "validation_findings": findings,
        "execution_status": "completed",
    }
