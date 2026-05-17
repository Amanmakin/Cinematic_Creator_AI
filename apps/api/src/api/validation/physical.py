"""Pure-Python physical validation for DSL v1 — never invokes the LLM."""

from __future__ import annotations

from orchestrator.schemas.canon import ProjectCanon
from orchestrator.schemas.dsl import BlenderDsl, PlaneCard, Vec3

from api.validation.findings import ValidationFinding, ValidationReport


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


def validate_dsl_full(
    dsl: BlenderDsl,
    canon: ProjectCanon,
    uar_asset_ids: set[str] | None = None,
) -> ValidationReport:
    """Extended validation covering all Plan4 rules.

    Args:
        dsl: The scene description to validate.
        canon: Project-level constraints.
        uar_asset_ids: Known asset IDs in the UAR; if provided, PlaneCard.asset_id
                       is checked for presence.
    """
    findings: list[ValidationFinding] = []
    scene = dsl.scene
    cam = scene.camera

    # Rule 1 — focal_mm range
    if not (1.0 <= cam.focal_mm <= 1000.0):
        findings.append(ValidationFinding(
            severity="error",
            code="camera.focal_mm_out_of_range",
            message=f"focal_mm={cam.focal_mm} outside [1, 1000]",
            path="scene.camera.focal_mm",
        ))

    # Rule 2 — clip planes
    if not (cam.clip_start > 0 and cam.clip_end > 0 and cam.clip_start < cam.clip_end):
        findings.append(ValidationFinding(
            severity="error",
            code="camera.clip_planes_invalid",
            message=(
                f"clip_start={cam.clip_start} and clip_end={cam.clip_end} must both be "
                "positive with clip_start < clip_end"
            ),
            path="scene.camera",
        ))

    # Rule 3 — camera not inside any object AABB (plane-cards)
    for i, obj in enumerate(scene.objects):
        if isinstance(obj, PlaneCard):
            mn, mx = obj.transform.aabb(half_thickness=0.005)
            if _point_in_aabb(cam.position, mn, mx):
                findings.append(ValidationFinding(
                    severity="error",
                    code="camera.inside_plane_card_aabb",
                    message=f"camera is inside objects[{i}] (PlaneCard '{obj.asset_id}') AABB",
                    path=f"scene.objects[{i}]",
                ))

    # Also check legacy subjects
    for i, subject in enumerate(scene.subjects):
        if subject.contains(cam.position):
            findings.append(ValidationFinding(
                severity="error",
                code="camera.inside_subject_aabb",
                message=f"camera is inside subjects[{i}] AABB",
                path=f"scene.subjects[{i}]",
            ))

    # Rule 4 — light intensity and color
    for i, light in enumerate(scene.lights):
        if not (0.0 <= light.intensity <= 10000.0):
            findings.append(ValidationFinding(
                severity="error",
                code="light.intensity_out_of_range",
                message=f"lights[{i}].intensity={light.intensity} outside [0, 10000]",
                path=f"scene.lights[{i}].intensity",
            ))

    # Rule 5 — PlaneCard asset_id resolution
    if uar_asset_ids is not None:
        for i, obj in enumerate(scene.objects):
            if isinstance(obj, PlaneCard) and obj.asset_id not in uar_asset_ids:
                findings.append(ValidationFinding(
                    severity="error",
                    code="plane_card.asset_id_missing",
                    message=f"objects[{i}].asset_id='{obj.asset_id}' not found in UAR",
                    path=f"scene.objects[{i}].asset_id",
                ))

    # Rule 6 — animation track monotonicity and time/value consistency
    for i, track in enumerate(scene.animations):
        if len(track.times) == 0:
            findings.append(ValidationFinding(
                severity="error",
                code="animation.empty_times",
                message=f"animations[{i}] has empty times list",
                path=f"scene.animations[{i}].times",
            ))
            continue

        for j in range(1, len(track.times)):
            if track.times[j] <= track.times[j - 1]:
                findings.append(ValidationFinding(
                    severity="error",
                    code="animation.times_not_monotonic",
                    message=(
                        f"animations[{i}].times is not strictly monotonic "
                        f"at index {j}: {track.times[j-1]} >= {track.times[j]}"
                    ),
                    path=f"scene.animations[{i}].times",
                ))
                break

        if track.times and track.times[-1] > scene.duration_s:
            findings.append(ValidationFinding(
                severity="error",
                code="animation.time_exceeds_duration",
                message=(
                    f"animations[{i}] last time {track.times[-1]} > "
                    f"scene.duration_s={scene.duration_s}"
                ),
                path=f"scene.animations[{i}].times",
            ))

        if len(track.values) != len(track.times):
            findings.append(ValidationFinding(
                severity="error",
                code="animation.values_times_length_mismatch",
                message=(
                    f"animations[{i}] has {len(track.times)} times but "
                    f"{len(track.values)} values"
                ),
                path=f"scene.animations[{i}]",
            ))

    # Rule 7 — scene duration
    if scene.duration_s > canon.duration_seconds_max:
        findings.append(ValidationFinding(
            severity="error",
            code="scene.duration_exceeds_canon",
            message=f"duration_s={scene.duration_s} > canon max {canon.duration_seconds_max}",
            path="scene.duration_s",
        ))

    # Rule 8 — resolution aspect ratio
    if not _aspect_matches(scene.resolution, canon):
        findings.append(ValidationFinding(
            severity="error",
            code="scene.resolution_aspect_mismatch",
            message=(
                f"resolution {scene.resolution} does not match "
                f"canon aspect {canon.aspect_ratio}"
            ),
            path="scene.resolution",
        ))

    has_error = any(f.severity == "error" for f in findings)
    return ValidationReport(ok=not has_error, findings=findings)
