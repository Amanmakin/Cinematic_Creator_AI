"""Tests for the API-level extended physical validation (Plan4 rules)."""

from __future__ import annotations

import pytest

from orchestrator.schemas.canon import ProjectCanon
from orchestrator.schemas.dsl import (
    AnimationTrack,
    BlenderDsl,
    Camera,
    Light,
    PlaneCard,
    Scene,
    SubjectPlaceholder,
    Transform,
    Vec3,
)
from api.validation.findings import ValidationReport
from api.validation.physical import validate_dsl_full


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def canon() -> ProjectCanon:
    return ProjectCanon(
        aspect_ratio="16:9",
        duration_seconds_max=30.0,
        aesthetic_tags=["cinematic"],
    )


def _make_dsl(
    *,
    focal_mm: float = 50.0,
    duration_s: float = 10.0,
    resolution: tuple[int, int] = (1920, 1080),
    clip_start: float = 0.01,
    clip_end: float = 1000.0,
    objects: list | None = None,
    animations: list | None = None,
) -> BlenderDsl:
    return BlenderDsl(
        scene=Scene(
            duration_s=duration_s,
            fps=24,
            resolution=resolution,
            camera=Camera(
                focal_mm=focal_mm,
                position=Vec3(x=0.0, y=-3.0, z=1.6),
                clip_start=clip_start,
                clip_end=clip_end,
            ),
            lights=[
                Light(kind="key", position=Vec3(x=2, y=-2, z=3), intensity=800, color_kelvin=4200),
            ],
            objects=objects or [],
            animations=animations or [],
        )
    )


# ---------------------------------------------------------------------------
# Rule 1 — focal_mm
# ---------------------------------------------------------------------------

def test_valid_dsl_passes(canon):
    report = validate_dsl_full(_make_dsl(), canon)
    assert report.ok


def test_focal_mm_below_1_fails(canon):
    report = validate_dsl_full(_make_dsl(focal_mm=0.5), canon)
    assert not report.ok
    assert any(f.code == "camera.focal_mm_out_of_range" for f in report.findings)


def test_focal_mm_above_1000_fails(canon):
    dsl = _make_dsl()
    dsl.scene.camera.focal_mm = 1001.0  # bypass Pydantic via direct mutation
    report = validate_dsl_full(dsl, canon)
    assert not report.ok
    assert any(f.code == "camera.focal_mm_out_of_range" for f in report.findings)


# ---------------------------------------------------------------------------
# Rule 2 — clip planes
# ---------------------------------------------------------------------------

def test_clip_start_negative_fails(canon):
    report = validate_dsl_full(_make_dsl(clip_start=-0.1), canon)
    assert not report.ok
    assert any(f.code == "camera.clip_planes_invalid" for f in report.findings)


def test_clip_start_greater_than_clip_end_fails(canon):
    report = validate_dsl_full(_make_dsl(clip_start=100.0, clip_end=10.0), canon)
    assert not report.ok
    assert any(f.code == "camera.clip_planes_invalid" for f in report.findings)


def test_clip_start_equal_clip_end_fails(canon):
    report = validate_dsl_full(_make_dsl(clip_start=1.0, clip_end=1.0), canon)
    assert not report.ok
    assert any(f.code == "camera.clip_planes_invalid" for f in report.findings)


# ---------------------------------------------------------------------------
# Rule 3 — camera inside plane-card AABB
# ---------------------------------------------------------------------------

def test_camera_inside_plane_card_aabb(canon):
    # PlaneCard at origin, scale 2×2; camera at (0, -3, 1.6) is NOT inside
    card = PlaneCard(
        asset_id="test_asset",
        transform=Transform(
            position=Vec3(x=0.0, y=-3.0, z=1.6),  # same as camera position
            scale=Vec3(x=2.0, y=2.0, z=1.0),
        ),
    )
    report = validate_dsl_full(_make_dsl(objects=[card]), canon)
    assert not report.ok
    assert any(f.code == "camera.inside_plane_card_aabb" for f in report.findings)


def test_camera_outside_plane_card_aabb_passes(canon):
    card = PlaneCard(
        asset_id="test_asset",
        transform=Transform(
            position=Vec3(x=10.0, y=10.0, z=10.0),
            scale=Vec3(x=1.0, y=1.0, z=1.0),
        ),
    )
    report = validate_dsl_full(_make_dsl(objects=[card]), canon)
    assert report.ok


# ---------------------------------------------------------------------------
# Rule 4 — light intensity
# ---------------------------------------------------------------------------

def test_light_intensity_over_10000_fails(canon):
    dsl = _make_dsl()
    dsl.scene.lights[0].intensity = 99999
    report = validate_dsl_full(dsl, canon)
    assert not report.ok
    assert any(f.code == "light.intensity_out_of_range" for f in report.findings)


# ---------------------------------------------------------------------------
# Rule 5 — UAR asset_id resolution
# ---------------------------------------------------------------------------

def test_plane_card_asset_id_missing_from_uar(canon):
    card = PlaneCard(asset_id="nonexistent_asset")
    report = validate_dsl_full(_make_dsl(objects=[card]), canon, uar_asset_ids={"other_id"})
    assert not report.ok
    assert any(f.code == "plane_card.asset_id_missing" for f in report.findings)


def test_plane_card_asset_id_present_passes(canon):
    card = PlaneCard(asset_id="known_asset")
    report = validate_dsl_full(_make_dsl(objects=[card]), canon, uar_asset_ids={"known_asset"})
    assert report.ok


def test_uar_check_skipped_when_ids_not_provided(canon):
    card = PlaneCard(asset_id="nonexistent_asset")
    report = validate_dsl_full(_make_dsl(objects=[card]), canon, uar_asset_ids=None)
    assert report.ok  # no uar_asset_ids → skip check


# ---------------------------------------------------------------------------
# Rule 6 — animation track validation
# ---------------------------------------------------------------------------

def test_animation_empty_times_fails(canon):
    track = AnimationTrack(target_path="$.scene.camera.focal_mm", times=[], values=[])
    report = validate_dsl_full(_make_dsl(animations=[track]), canon)
    assert not report.ok
    assert any(f.code == "animation.empty_times" for f in report.findings)


def test_animation_not_monotonic_fails(canon):
    track = AnimationTrack(
        target_path="$.scene.camera.focal_mm",
        times=[0.0, 2.0, 1.0],
        values=[50.0, 70.0, 60.0],
    )
    report = validate_dsl_full(_make_dsl(animations=[track]), canon)
    assert not report.ok
    assert any(f.code == "animation.times_not_monotonic" for f in report.findings)


def test_animation_time_exceeds_duration_fails(canon):
    track = AnimationTrack(
        target_path="$.scene.camera.focal_mm",
        times=[0.0, 5.0, 15.0],
        values=[50.0, 60.0, 70.0],
    )
    report = validate_dsl_full(_make_dsl(duration_s=10.0, animations=[track]), canon)
    assert not report.ok
    assert any(f.code == "animation.time_exceeds_duration" for f in report.findings)


def test_animation_values_count_mismatch_fails(canon):
    track = AnimationTrack(
        target_path="$.scene.camera.focal_mm",
        times=[0.0, 5.0],
        values=[50.0],
    )
    report = validate_dsl_full(_make_dsl(animations=[track]), canon)
    assert not report.ok
    assert any(f.code == "animation.values_times_length_mismatch" for f in report.findings)


def test_valid_animation_passes(canon):
    track = AnimationTrack(
        target_path="$.scene.camera.focal_mm",
        times=[0.0, 5.0, 9.0],
        values=[50.0, 60.0, 70.0],
    )
    report = validate_dsl_full(_make_dsl(animations=[track]), canon)
    assert report.ok


# ---------------------------------------------------------------------------
# Rule 7 — duration
# ---------------------------------------------------------------------------

def test_duration_exceeds_canon_fails(canon):
    report = validate_dsl_full(_make_dsl(duration_s=60.0), canon)
    assert not report.ok
    assert any(f.code == "scene.duration_exceeds_canon" for f in report.findings)


# ---------------------------------------------------------------------------
# Rule 8 — resolution aspect ratio
# ---------------------------------------------------------------------------

def test_resolution_aspect_mismatch_fails(canon):
    report = validate_dsl_full(_make_dsl(resolution=(1080, 1920)), canon)
    assert not report.ok
    assert any(f.code == "scene.resolution_aspect_mismatch" for f in report.findings)


# ---------------------------------------------------------------------------
# ValidationReport shape
# ---------------------------------------------------------------------------

def test_validation_report_ok_true_when_no_errors(canon):
    report = validate_dsl_full(_make_dsl(), canon)
    assert isinstance(report.ok, bool)
    assert report.ok is True
    assert isinstance(report.findings, list)


def test_validation_report_ok_false_when_errors(canon):
    dsl = _make_dsl()
    dsl.scene.camera.focal_mm = 0.5  # bypass Pydantic via direct mutation
    report = validate_dsl_full(dsl, canon)
    assert report.ok is False
    assert len(report.findings) > 0
