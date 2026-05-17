"""Tests for the glTF/glb assembler (Plan4 D3)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from orchestrator.schemas.dsl import (
    AnimationTrack,
    BlenderDsl,
    Camera,
    Light,
    PlaneCard,
    Scene,
    Transform,
    Vec3,
    WorldEnv,
)
from api.render.gltf_builder import build_glb, scene_hash


def _make_dsl(with_plane_card: bool = False, use_depth_map: bool = False) -> BlenderDsl:
    objects = []
    if with_plane_card:
        objects.append(
            PlaneCard(
                asset_id="test_card",
                transform=Transform(
                    position=Vec3(x=0.0, y=0.0, z=0.0),
                    rotation_euler=Vec3(x=0.0, y=0.0, z=0.0),
                    scale=Vec3(x=1.0, y=1.0, z=1.0),
                ),
                use_depth_map=use_depth_map,
            )
        )
    return BlenderDsl(
        scene=Scene(
            duration_s=5.0,
            fps=24,
            resolution=(1920, 1080),
            camera=Camera(
                focal_mm=50.0,
                position=Vec3(x=0.0, y=-3.0, z=1.6),
                rotation_euler=Vec3(x=0.0, y=0.0, z=0.0),
                clip_start=0.01,
                clip_end=1000.0,
            ),
            lights=[
                Light(kind="key", position=Vec3(x=2, y=-2, z=3), intensity=800, color_kelvin=4200),
            ],
            objects=objects,
            animations=[],
            world=WorldEnv(background_color=(0.05, 0.05, 0.05)),
        )
    )


# ---------------------------------------------------------------------------
# scene_hash
# ---------------------------------------------------------------------------

def test_scene_hash_is_deterministic():
    dsl = _make_dsl()
    h1 = scene_hash(dsl)
    h2 = scene_hash(dsl)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_scene_hash_changes_when_dsl_changes():
    dsl1 = _make_dsl()
    dsl2 = _make_dsl()
    dsl2.scene.camera.focal_mm = 35.0
    assert scene_hash(dsl1) != scene_hash(dsl2)


# ---------------------------------------------------------------------------
# build_glb — empty scene (no plane cards)
# ---------------------------------------------------------------------------

def test_build_glb_empty_scene_produces_file():
    dsl = _make_dsl(with_plane_card=False)
    with tempfile.TemporaryDirectory() as out_dir:
        with tempfile.TemporaryDirectory() as uar_root:
            path = build_glb(dsl, uar_root=uar_root, out_dir=out_dir)
            assert Path(path).exists()
            assert path.endswith(".glb")


def test_build_glb_writes_extras_json():
    dsl = _make_dsl(with_plane_card=False)
    with tempfile.TemporaryDirectory() as out_dir:
        with tempfile.TemporaryDirectory() as uar_root:
            glb_path = build_glb(dsl, uar_root=uar_root, out_dir=out_dir)
            sha = scene_hash(dsl)
            extras_path = Path(out_dir) / f"{sha}.extras.json"
            assert extras_path.exists()
            extras = json.loads(extras_path.read_text())
            assert "cvc_camera" in extras
            assert "cvc_lights" in extras
            assert "cvc_world" in extras


# ---------------------------------------------------------------------------
# build_glb — with plane card
# ---------------------------------------------------------------------------

def test_build_glb_with_plane_card():
    dsl = _make_dsl(with_plane_card=True)
    with tempfile.TemporaryDirectory() as out_dir:
        with tempfile.TemporaryDirectory() as uar_root:
            path = build_glb(dsl, uar_root=uar_root, out_dir=out_dir)
            assert Path(path).exists()
            assert Path(path).stat().st_size > 0


def test_build_glb_glb_is_parseable():
    """Round-trip: built glb should be loadable by pygltflib."""
    import pygltflib

    dsl = _make_dsl(with_plane_card=True)
    with tempfile.TemporaryDirectory() as out_dir:
        with tempfile.TemporaryDirectory() as uar_root:
            path = build_glb(dsl, uar_root=uar_root, out_dir=out_dir)
            gltf = pygltflib.GLTF2().load(path)
            assert gltf.asset.version == "2.0"


def test_build_glb_scene_has_vendor_extras():
    import pygltflib

    dsl = _make_dsl(with_plane_card=True)
    with tempfile.TemporaryDirectory() as out_dir:
        with tempfile.TemporaryDirectory() as uar_root:
            path = build_glb(dsl, uar_root=uar_root, out_dir=out_dir)
            gltf = pygltflib.GLTF2().load(path)
            extras = gltf.scenes[0].extras or {}
            assert "cvc_camera" in extras
            assert "cvc_lights" in extras
            assert "cvc_dsl_hash" in extras


def test_build_glb_camera_extras_match_dsl():
    import pygltflib

    dsl = _make_dsl(with_plane_card=False)
    with tempfile.TemporaryDirectory() as out_dir:
        with tempfile.TemporaryDirectory() as uar_root:
            path = build_glb(dsl, uar_root=uar_root, out_dir=out_dir)
            gltf = pygltflib.GLTF2().load(path)
            cam_extras = gltf.scenes[0].extras["cvc_camera"]
            assert cam_extras["focal_mm"] == pytest.approx(50.0)
            assert cam_extras["clip_start"] == pytest.approx(0.01)
            assert cam_extras["clip_end"] == pytest.approx(1000.0)


def test_build_glb_with_depth_map():
    """use_depth_map=True should produce a larger mesh (grid geometry)."""
    dsl_flat = _make_dsl(with_plane_card=True, use_depth_map=False)
    dsl_depth = _make_dsl(with_plane_card=True, use_depth_map=True)

    with tempfile.TemporaryDirectory() as out_dir:
        with tempfile.TemporaryDirectory() as uar_root:
            path_flat = build_glb(dsl_flat, uar_root=uar_root, out_dir=out_dir + "/flat")
            path_depth = build_glb(dsl_depth, uar_root=uar_root, out_dir=out_dir + "/depth")
            # depth mesh has more vertices → larger file
            assert Path(path_depth).stat().st_size > Path(path_flat).stat().st_size


def test_build_glb_output_path_uses_scene_hash():
    dsl = _make_dsl()
    sha = scene_hash(dsl)
    with tempfile.TemporaryDirectory() as out_dir:
        with tempfile.TemporaryDirectory() as uar_root:
            path = build_glb(dsl, uar_root=uar_root, out_dir=out_dir)
            assert sha in path
